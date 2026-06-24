# Character Versions — per-universe incarnations

**Related use cases:** M-31 (entity templates), DL-20 (NPC memory),
P-17 (conversatory), the Characters tab in the UI.

A **Character Version** is one incarnation of a roster character in a specific
universe. A character card is the source of truth; each version is a separate
`(entity_id, universe_id)` pair with its own NPCProfile, memory set,
emotional state, and relationship deltas. Versions are isolated — no
cross-incarnation leak unless the caller explicitly opts in.

## Why

Without versions, the same character card used in multiple universes (or in
the hidden Conversatory + a real world) would leak:

- **Memories** — `qdrant_search_memories` was filtered by `entity_id` alone,
  so recall in universe B would surface memories from universe A.
- **Emotional state** — `current_emotional_state` is a single string per
  entity; chat in universe B would inherit universe A's mood.
- **Relationship deltas** — `relationship_states[player_id]` is a flat map;
  every chat in any universe accumulated into one global trust score.

## Storage

The fix is in the agent layer; the storage layer already supports partitioning:

- **Qdrant memory payloads** (`qdrant_embed_memory`) already carry
  `universe_id` + `entity_id`; the search request already accepts both.
- **Mongo NPCProfile** gained two new fields:
  - `relationship_states_by_universe: Dict[str, Dict[str, target_id, state]]`
  - `current_emotional_state_by_universe: Dict[str, str]`
  Both are populated when an NPCProfile is created via the version-aware
  path; legacy `relationship_states` / `current_emotional_state` remain as
  a fallback for callers that haven't migrated.

## Agent layer changes

- `NPCVoice._recall_memories` now accepts `universe_id` and
  `include_cross_incarnation` kwargs and forwards both to Qdrant.
- `NPCVoice._write_npc_memory` now stamps `universe_id` on the
  `mongodb_create_memory` call (falls back to the entity's home universe
  for legacy callers).
- `NPCVoice._relationship_snapshot`, `_build_relationship_snapshot`,
  `_format_emotional_context`, `_update_working_social_state`, and
  `_build_proposals` all read/write the per-universe partition maps first
  and fall back to legacy fields when absent.
- `ConversationLoop.generate_npc_responses` threads the loop's
  `state.universe_id` (and an optional `state.include_cross_incarnation`
  flag set by the conversatory endpoint) into `respond_direct`.
- `ConversationLoop.close_session` stamps `universe_id` on every staged
  `ProposedChange` so CanonKeeper can route the change to the right
  incarnation.

## Character doc shape

`characters` collection — new fields on top of the existing card:

```python
{
  "id": "char-1",
  "name": "Maeve",
  # ...card fields unchanged...
  "default_universe_id": "uni-A",   # promoted automatically to last-chat'd
  "versions": [
    {
      "version_id": "uuid",
      "universe_id": "uni-A",
      "entity_id": "uuid",
      "npc_profile_id": "uuid",
      "created_at": "iso",
      "last_chatted_at": "iso|null",
    },
    ...
  ],
}
```

`character_storage.add_version(character_id, universe_id, entity_id, npc_profile_id)`
is idempotent per `(character_id, universe_id)`. `delete_version` removes the
entry and (when called via `character_conversation.delete_incarnation`) also
drops the backing Neo4j entity + Mongo NPCProfile doc.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/entities/characters/{id}/expand` | Promote light card (now accepts optional `{universe_id}`) |
| POST | `/api/entities/characters/{id}/versions` | Create/fetch a per-universe incarnation |
| GET  | `/api/entities/characters/{id}/versions` | List incarnations (newest first) |
| DELETE | `/api/entities/characters/{id}/versions/{universe_id}` | Tear down incarnation (entity + NPCProfile) |
| POST | `/api/entities/characters/{id}/conversations` | Start a session (now accepts `{universe_id}`) |
| POST | `/api/entities/characters/{id}/conversations/{conv_id}/send` | Send a line (now accepts `include_cross_incarnation: bool`) |

## Frontend

The Characters tab (`/characters`) shows:

- **Roster**: each card displays `MONITOR` badge + a `N×` badge when the
  character has more than one incarnation.
- **Editor**: an "Incarnations" panel lists each per-universe incarnation
  with a delete button, and an input to add a new incarnation in a chosen
  universe.
- **Chat**: a "Remember across incarnations" toggle in the input area
  passes `include_cross_incarnation=true` on each send.

## Verification

- `pytest packages/agents/tests/test_npc_voice_universe_scoping.py` —
  asserts `universe_id` + `include_cross_incarnation` reach recall, write,
  and working-state update; legacy callers still work.
- `pytest packages/ui/backend/tests/test_character_conversation.py` —
  asserts per-universe version idempotency, distinct entity_ids across
  universes, and that `delete_incarnation` cleans both stores.
- `npm test` — frontend API payloads (versions + cross-incarnation flag).

## Migration

Existing character docs (no `versions[]`, no `default_universe_id`) keep
working: `ensure_character_backed` falls back to the legacy
`entity_id` + `source_universe_id` and lazily promotes them into a
default version on first call. `_serialise_character` defaults the new
fields so old docs serialize cleanly.
