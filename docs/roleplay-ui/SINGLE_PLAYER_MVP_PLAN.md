# Single-Player MVP Plan: Ingest → Play → Story Arc

**Date:** 2026-05-31
**Status:** Proposed
**Goal:** Close the 5 critical gaps that block a single player from going from "ingest a game" to "complete a multi-scene story arc with progression."

---

## Current State Summary

A single player **can already**:
1. Upload a PDF → document chunked, entities/rules extracted, KnowledgePack created
2. Apply the pack to a Universe (via API, not UI)
3. Create a Standalone Character → stored in MongoDB
4. Start a scene → NPC data + rulebook facts loaded into context
5. Take IC turns → Resolver rolls dice → Narrator generates prose
6. Toggle OOC/IC modes

**But stops at:** no memory persistence across scenes, no scene-end choreography, no story arc tracking, characters don't bridge to world entities, and the "Apply Pack" button is missing from the Forge UI.

---

## Gap 1: Unify Character Systems

**Problem:** `StandaloneCharacter` (MongoDB) and `Entity` (Neo4j) are two separate systems. Context assembly only queries Neo4j, so standalone characters are invisible to the narrator. NPCs can't form relationships with PCs.

**Files to modify:**

| File | Change |
|------|--------|
| `packages/ui/backend/src/monitor_ui/routers/character_resolution.py` | **NEW** — `resolve_actor_character()` function that checks MongoDB first (standalone), then Neo4j (entity), returns unified `CharacterContext` dict |
| `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` | In `run_scene_turn()` and `run_ooc_turn()`, call `resolve_actor_character()` before creating SceneLoop; pass resolved character data as `actor_context` |
| `packages/agents/src/monitor_agents/loops/scene_loop.py` | Add `actor_context: Optional[Dict[str, Any]]` to `SceneState`; pass to `load_context()` |
| `packages/agents/src/monitor_agents/context_assembly.py` | Add `actor_context: Optional[Dict[str, Any]]` parameter to `assemble()`; if present, inject character personality/tags into context result |
| `packages/agents/src/monitor_agents/narrator.py` | Include `actor_context` (personality, state_tags, role) in narrator prompt so the GM speaks to/about the character correctly |

**New schema:**

```python
# In packages/ui/backend/src/monitor_ui/routers/character_resolution.py
class CharacterContext(BaseModel):
    """Unified character reference (standalone OR entity)."""
    source: Literal["standalone", "entity"]
    id: UUID
    name: str
    personality: str = ""
    description: str = ""
    is_ooc_persona: bool = False
    role: str = "pc"
    state_tags: list[str] = []
    attributes: dict[str, Any] = {}
    skills: dict[str, Any] = {}
    resources: dict[str, Any] = {}
```

**Implementation steps:**

1. Create `character_resolution.py` with `resolve_actor_character(session, db)` that:
   - Reads `session["speaker_character_id"]`
   - If present, queries MongoDB `characters` collection for standalone character
   - If not found, queries Neo4j for entity with matching ID
   - Returns `CharacterContext` or `None`

2. Modify `chat_loops.py`:
   - In `run_scene_turn()`, after getting session, call `resolve_actor_character()`
   - Pass result to `SceneLoop` via `SceneState.actor_context`
   - In `run_ooc_turn()`, same resolution for persona injection

3. Modify `scene_loop.py`:
   - Add `actor_context: Optional[Dict[str, Any]] = None` to `SceneState`
   - In `load_context()`, pass `actor_context` to `ContextAssembly.assemble()`

4. Modify `context_assembly.py`:
   - Add `actor_context` parameter to `assemble()`
   - If present, add character personality/description to context result under `"actor"` key
   - In `_fetch_memories()`, use `actor_context["id"]` as `entity_id` filter when available

5. Modify `narrator.py`:
   - Include actor personality and state in the narrator prompt template

**Estimated effort:** ~8h
**Tests:** Add `test_character_resolution.py` with 6 tests (standalone found, entity fallback, not found, OOC persona, state tags, attributes)

---

## Gap 2: Auto-Create Character Memories on IC Turns

**Problem:** Memories are stored but never auto-created at turn end. Each scene is isolated — "Remember when we fought the dragon?" has no answer.

**Files to modify:**

| File | Change |
|------|--------|
| `packages/agents/src/monitor_agents/prompts/memory_extraction.py` | **NEW** — DSPy module `MemoryExtractor` that takes (narrative_text, resolution, actor_name) and returns list of salient facts |
| `packages/agents/src/monitor_agents/loops/scene_loop.py` | Add `extract_memories` node after `narrate` in the graph; add `memories_to_persist: List[Dict]` to `SceneState` |
| `packages/agents/src/monitor_agents/loops/scene_support.py` | Add `persist_memories()` helper that calls `mongodb_create_memory` for each extracted memory |
| `packages/data-layer/src/monitor_data/tools/mongodb_tools/memories.py` | Relax Neo4j entity check — allow standalone character IDs (MongoDB UUID) as `entity_id` |

**Implementation steps:**

1. Create `memory_extraction.py`:
   ```python
   class MemoryExtractor(dspy.Module):
       """Extract salient memories from a narrative turn."""
       def __init__(self):
           super().__init__()
           self.extract = dspy.ChainOfThought(MemoryExtractionSignature)
       
       def forward(self, narrative_text, resolution, actor_name):
           # Returns list of {text, importance, emotional_valence}
           ...
   ```

2. Add `extract_memories` node to `scene_loop.py`:
   - After `narrate` node, before `check_events`
   - Calls `MemoryExtractor` with `state.narrative_text`, `state.resolution`, actor name from `state.actor_context`
   - Stores results in `state.memories_to_persist`

3. Add `persist_memories` step to `persist_turn_artifacts`:
   - After persisting resolution, iterate `state.memories_to_persist`
   - Call `mongodb_create_memory()` for each, with `entity_id=actor_id`, `scene_id=scene_id`
   - Fire Qdrant embedding for each (reuse existing `qdrant_embed_memory`)

4. Relax `mongodb_create_memory` entity check:
   - Currently requires `entity_id` to exist in Neo4j as `EntityArchetype` or `EntityInstance`
   - Add fallback: if not found in Neo4j, check MongoDB `characters` collection
   - This allows standalone characters to own memories

**Estimated effort:** ~3h
**Tests:** Add `test_memory_extraction.py` with 4 tests (extract from narrative, persist to MongoDB, Qdrant embedding, standalone character ID accepted)

---

## Gap 3: Scene End Choreography

**Problem:** `/end-scene` calls `finalize()` and `complete_current_scene()` but doesn't update scene status in MongoDB, generate a scene summary, or formally close the scene.

**Files to modify:**

| File | Change |
|------|--------|
| `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` | In `run_end_scene()`, add scene status transitions and summary generation |
| `packages/data-layer/src/monitor_data/tools/mongodb_tools/scenes.py` | Ensure `mongodb_update_scene()` supports `status="finalizing"` and `status="completed"` transitions |
| `packages/data-layer/src/monitor_data/schemas/scenes.py` | Add `summary: Optional[str]` to `SceneUpdate` if not present |

**Implementation steps:**

1. Verify `SceneUpdate` schema supports `status` and `summary` fields (likely already does — check).

2. In `run_end_scene()`, add after `loop_instance.finalize()`:
   ```python
   from monitor_data.schemas.scenes import SceneUpdate
   from monitor_data.tools.mongodb_tools.scenes import mongodb_update_scene
   
   # Mark scene as finalizing
   await run_sync_read(
       mongodb_update_scene,
       uuid.UUID(scene_id),
       SceneUpdate(status="finalizing"),
   )
   ```

3. After `story_loop.complete_current_scene()` succeeds:
   ```python
   # Generate summary from last few turns
   summary = await _generate_scene_summary(session_id, messages)
   
   await run_sync_read(
       mongodb_update_scene,
       uuid.UUID(scene_id),
       SceneUpdate(status="completed", summary=summary),
   )
   ```

4. Add `_generate_scene_summary()` helper:
   - Takes last 5-10 turns from `messages[session_id]`
   - Calls Narrator (or a lightweight DSPy module) to produce 2-3 sentence summary
   - Returns summary string

5. Add scene status to metadata returned to frontend:
   ```python
   metadata["scene_status"] = "completed"
   metadata["scene_summary"] = summary
   ```

**Estimated effort:** ~4h
**Tests:** Add 3 tests to `test_session_api.py` (end scene sets finalizing → completed, summary generated, error recovery)

---

## Gap 4: Story Arc Persistence & Exposure

**Problem:** `StoryLoop` works internally but isn't exposed to the frontend. No REST endpoints for story state, no arc/tension/thread visibility, no way to see "my campaign progress."

**Files to modify:**

| File | Change |
|------|--------|
| `packages/ui/backend/src/monitor_ui/routers/stories.py` | **NEW** — REST endpoints for story state |
| `packages/ui/backend/src/monitor_ui/app.py` | Register `stories` router |
| `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` | Cache `StoryState` alongside `SceneLoop`; expose arc/tension/threads in session metadata |
| `packages/ui/backend/src/monitor_ui/routers/chat_schemas.py` | Add `StoryInfo` schema with arc_label, tension_score, active_threads, scenes_completed |
| `packages/ui/frontend/src/lib/api.ts` | Add `storiesApi` with `getStory()`, `listScenes()` |
| `packages/ui/frontend/src/components/play/StoryPanel.tsx` | **NEW** — React component showing arc phase, tension, threads, scene list |

**New endpoints:**

```
GET  /api/stories/{story_id}           → StoryResponse (arc, tension, threads, scenes)
GET  /api/stories/{story_id}/scenes    → List[SceneSummary] (ordered scene list)
PATCH /api/stories/{story_id}          → Update arc_label, tension override
```

**Implementation steps:**

1. Create `stories.py` router:
   - `GET /{story_id}` — fetch story from MongoDB `stories` collection, return `StoryResponse`
   - `GET /{story_id}/scenes` — list scenes for story, ordered by creation
   - `PATCH /{story_id}` — update arc_label or tension_score

2. Add `StoryResponse` schema:
   ```python
   class StoryResponse(BaseModel):
       story_id: UUID
       universe_id: UUID
       arc_label: str
       tension_score: float
       scenes_completed: int
       active_threads: list[str]
       completed_threads: list[str]
       next_scene_type: Optional[str]
       created_at: datetime
       updated_at: datetime
   ```

3. In `chat_loops.py`:
   - After `story_loop.complete_current_scene()`, cache `story_result` in session dict
   - Include `story_arc`, `tension_score`, `active_threads` in turn metadata

4. Register router in `app.py`:
   ```python
   from .routers.stories import router as stories_router
   app.include_router(stories_router, prefix="/api/stories", tags=["stories"])
   ```

5. Frontend: Add `StoryPanel.tsx` component:
   - Shows current arc phase (rising_action → climax → falling_action → resolution)
   - Tension meter (0.0–1.0)
   - Active plot threads as tags
   - Scene history as timeline
   - Add to `PlayConsole.tsx` sidebar

**Estimated effort:** ~4h
**Tests:** Add `test_stories_api.py` with 4 tests (get story, list scenes, update arc, 404 handling)

---

## Gap 5: "Apply Pack" Button in Forge UI

**Problem:** The backend canonize endpoint exists (`POST /api/ingest/packs/{id}/canonize`), and the frontend `PackLibrary.tsx` already has a `canonize` mutation. But the UX flow is incomplete — there's no clear "Apply to World" button with universe selection.

**Current state:** `PackLibrary.tsx` already has:
- `canonize` mutation that calls `ingestApi.canonizePack()`
- `applyingId` state for tracking which pack is being applied
- An expandable section per pack with "Apply to World" UI

**What's missing:**
- The expandable apply section needs a clearer flow: select multiverse → choose existing universe OR create new → confirm
- Success/error feedback after canonization
- Auto-refresh of pack status after canonization

**Files to modify:**

| File | Change |
|------|--------|
| `packages/ui/frontend/src/components/forge/ingest/PackLibrary.tsx` | Polish the apply flow: add confirmation dialog, success toast, error handling, auto-refresh |
| `packages/ui/frontend/src/components/forge/ingest/StatusBadge.tsx` | Add "canonizing" status animation |
| `packages/ui/frontend/src/lib/api.ts` | Already has `canonizePack()` — verify it works end-to-end |

**Implementation steps:**

1. In `PackLibrary.tsx`, improve the existing expandable apply section:
   - Add a `DialogShell` confirmation modal before canonizing
   - Show universe selector dropdown (populated from `multiverses` query)
   - Add "Create New World" option with name/system fields
   - On success: show toast notification, invalidate pack list, close expandable
   - On error: show error message inline

2. Add `StatusBadge` state for "canonizing" (spinner animation while pack is being committed)

3. Test end-to-end: upload PDF → wait for extraction → expand pack → select universe → click "Apply" → verify entities appear in Neo4j

**Estimated effort:** ~2h
**Tests:** Manual E2E test (frontend change, no backend modification needed)

---

## Implementation Order & Dependencies

```
Gap 5 (Apply Pack UI) ────────────────────────────────────┐
                                                           │
Gap 3 (Scene End Choreography) ────────────────────────────┤
                                                           │  ← Can be done in parallel
Gap 1 (Unify Characters) ─────────────────────────────────┤
                                                           │
Gap 2 (Auto-Memories) ─── depends on Gap 1 ──────────────┤
   (needs actor_context to know entity_id)                 │
                                                           │
Gap 4 (Story Arc Exposure) ─── depends on Gap 3 ──────────┘
   (needs scene completion to advance arc)
```

**Recommended sequence:**

| Phase | Gap | Effort | Cumulative |
|-------|-----|--------|------------|
| **Phase 1** | Gap 5 — Apply Pack UI | 2h | 2h |
| **Phase 2** | Gap 3 — Scene End Choreography | 4h | 6h |
| **Phase 3** | Gap 1 — Unify Characters | 8h | 14h |
| **Phase 4** | Gap 2 — Auto-Memories | 3h | 17h |
| **Phase 5** | Gap 4 — Story Arc Exposure | 4h | 21h |

**Phase 1 and 2 can be done in parallel.** Phase 3 and 4 are sequential (memories need character resolution). Phase 5 depends on Phase 3 (scene completion drives arc advancement).

---

## Acceptance Criteria

After all 5 gaps are closed, a single player should be able to:

1. **Ingest** a game document → see extracted pack in Forge → click "Apply to World" → entities/rules committed to Neo4j ✅
2. **Create** a standalone character → character appears in Play Console sidebar ✅
3. **Start** a scene in that world → context assembly pulls world entities + character personality ✅
4. **Play** IC turns → narrator responds with world-aware prose → memories auto-created per turn ✅
5. **End** a scene → scene status transitions to "completed" → summary generated → proposals canonized ✅
6. **Continue** to next scene → story arc advances → tension/threads visible in StoryPanel ✅
7. **Complete** a 3-5 scene story arc → arc label progresses (rising_action → climax → resolution) ✅

---

## High-Priority Follow-Ups (Post-MVP)

These are not blockers but significantly improve the experience:

| Item | Effort | Impact |
|------|--------|--------|
| Game-system-specific character sheets (D&D AC/HP, Vampire disciplines) | 16h | High — players expect system-specific mechanics |
| Resource spend UX (show HP/Pressure changes in frontend) | 4h | Medium — makes consequences visible |
| NPC roster tab during play | 4h | Medium — browse universe NPCs while in scene |
| Relationship edges for PCs (DERIVES_FROM archetype) | 8h | High — enables "tell me about my rival" |
| Contradiction detection during ingestion | 4h | Low — nice-to-have for quality |
| Combat initiative tracker | 16h | Medium — needed for party-based RPGs |