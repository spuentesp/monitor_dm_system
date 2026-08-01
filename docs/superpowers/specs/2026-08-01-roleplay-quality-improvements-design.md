# Roleplay Quality Improvements (Design)

Date: 2026-08-01
Status: Approved (design, post gap analysis), pending spec review
Approach: 3 phases, 7 work items (one item — NPC voice — was folded into NPC state surfacing after gap analysis)

## Problem

Eight roleplay-quality gaps were identified, traced in code, and (after gap analysis) collapsed into seven. The narrative loop has rich infrastructure (NPCProfile schema, NPCVoice, Qdrant memories, Lorebook, NPCConversationLoop) but the *Narrator in SceneLoop* never reads NPCProfile and never writes back emotion deltas. NPCs forget across scenes; scene-mode play doesn't update emotional state. Other gaps (pacing, foreshadowing, recap, soft-retry, memory hygiene) lack obvious existing infrastructure and need new code.

## Goal

Make NPCs remember and feel consistent across scenes by surfacing existing NPCProfile data to the Narrator and writing back scene-mode emotion updates. Add the six remaining items with minimal blast radius.

Non-goals: changing the resolver, redesigning NPCVoice, changing Neo4j write authority, frontend UI changes.

## Architecture

- All changes touch only the agents + data-layer packages. UI backend unchanged (no new HTTP endpoints; existing flows carry the new context).
- Persistence changes: one new data-layer tool (`mongodb_get_npc_profiles_by_entities`); one new MongoDB collection (`scene_foreshadowing`); `recall_count` field added to memory docs (extension). No new Neo4j writes — emotion updates use the existing `mongodb_update_npc_profile` path that NPCVoice already uses.
- Narrator's `profile_context` grows by at most three new blocks (`NPC STATE`, `PACE`, `FALLBACK RECAP` plus foreshadowing); each is omitted when empty.
- SceneState gets at most three new fields (`npc_profiles`, `pacing`, `scene_foreshadowing_open`); each defaults to `[]` / `{}` / `None`.

## Existing infrastructure to reuse (do not duplicate)

| Capability | File / line | Notes |
|---|---|---|
| `NPCProfile` schema (current_emotional_state + per-universe, relationship_states + per-universe, values, fears, desires, speech_style, catchphrases, mannerisms, emotional_tendencies, preferences, triggers, secrets, gm_notes) | `packages/data-layer/src/monitor_data/schemas/npc_profiles.py:111-249` | Already partitioned per-universe + per-player. Nothing to add. |
| `mongodb_update_npc_profile(entity_id, params)` | `packages/data-layer/src/monitor_data/tools/mongodb_tools/npc_profiles.py:104` | Used by NPCVoice for emotion + relationship writes. Reuse as-is for scene-mode emotion writes. |
| NPCVoice DSPy signature (`emotional_state_after: str`, `social_read: dict`) | `packages/agents/src/monitor_agents/npc_voice/agent.py:52-145` | Reference for what "emotion" looks like. We do NOT call NPCVoice from SceneLoop — we add a structured output to the Narrator instead (Option 1). |
| `mongodb_create_memory` + Qdrant hook | `packages/data-layer/src/monitor_data/tools/mongodb_tools/memories.py:22` | Used by `PersistenceService.persist_memories`. We reuse for recall-count increment. |
| SceneState / SceneLoop / `load_context` | `packages/agents/src/monitor_agents/loops/scene_loop.py:185-303` | Standard place for new context fields. |

## Phase 1 — pure narrator code (low risk)

### #4 Soft-retry on degraded narration

`Narrator._generate_narrative_and_proposals` (`packages/agents/src/monitor_agents/narrator/agent.py:396`) returns a degraded fallback on provider failure. Today we ship the fallback. Add one in-process retry with trimmed context: drop `lorebook_context` + `recent_chat` + `context_summary`, keep entities, memories, source_profile, established_facts, agreements, actor. If the retry also degrades, ship the original fallback and surface a new field `degraded["retried"] = True` so the UI can show "recovered after retry" if it cares.

Implementation: factor the call into `_generate_once(trimmed_context: bool) -> tuple[str, list, int, dict]` returning `(narrative, proposals, minutes, degraded)`. The public `_generate_narrative_and_proposals` calls it once with full context; if degraded, calls again with trimmed context; picks the non-degraded result (or first if both degraded).

Tests: monkeypatch the inner DSPy call to fail once then succeed; assert narrative is the retry's output and `degraded["retried"] = True`. Failure-twice case: assert both degraded and original fallback is returned.

### #6 Pacing instrumentation

Pure derivation. Add a `pacing: dict[str, Any]` field to `SceneState` with default `{"tempo": 0.5, "phase": "setup"}`. `load_context` computes it deterministically:
- `tempo = clamp(0.4 + 0.04 * turns_count - 0.3 * recent_proposal_count, 0.0, 1.0)` where `recent_proposal_count` is the count of `pending_proposals` accepted in the last 3 turns (already in `state`).
- `phase`: `setup` if `turns_count < 3`, else `rising` if tempo < 0.4, `peak` if tempo ≥ 0.7 and at least one proposal landed in the last 3 turns, `falling` if tempo ≤ 0.3 and `turns_count > 5`, else `coda` if `turns_count > 30`.

The Narrator injects a one-line `PACE: tempo=X phase=Y` block right after the source-profile block. Cap 1 line. Omit when both fields are at defaults.

Tests: `compute_pacing(turns_count, recent_proposal_count)` is a pure module-level function (test it with a matrix). Narrator block is rendered when state.pacing is non-default; omitted otherwise.

(No separate #7 — voice handling is part of Phase 2 NPC state surfacing.)

## Phase 2 — NPC memory + foreshadowing (medium risk)

### Gap A: bulk NPC fetch (one new data-layer tool)

New `mongodb_get_npc_profiles_by_entities(entity_ids: list[UUID]) -> list[NPCProfileResponse]` in `packages/data-layer/src/monitor_data/tools/mongodb_tools/npc_profiles.py`. Single Mongo `find` with `{entity_id: {"$in": [str(eid) for eid in entity_ids]}}`, mapped through `_npc_profile_doc_to_response`. Re-export from `packages/data-layer/src/monitor_data/tools/mongodb_tools/__init__.py`. Limit 16 per call (cap matches max entities in a scene).

Tests: write 3 NPCProfile docs, call tool with the 3 entity_ids, assert all returned; assert ordering matches input; assert empty list when no matches.

### Gap B: surface NPC state to the Narrator

1. New field on `SceneState`: `npc_profiles: dict[str, NPCProfileResponse]` (default `{}`), keyed by `entity_id`.
2. `load_context` (scene_loop.py:185) — after the existing `entity_context = assemble.assemble(...)` call, gather entity_ids from `entity_context`, call `mongodb_get_npc_profiles_by_entities`, store in `state.npc_profiles`.
3. Narrator `narrate` node (scene_loop.py:436) — pass `"npc_profiles": {eid: profile.model_dump(mode="json") for eid, profile in state.npc_profiles.items()}` in the context dict.
4. New module-level helper `_npc_state_block(npc_profiles: Any, *, universe_id: str | None, player_id: str | None, cap: int = 4, max_chars: int = 200) -> str` in `narrator/agent.py`. Projects `current_emotional_state_by_universe[universe_id]` and `relationship_states_by_universe.get(universe_id, {}).get(player_id, {})` for the first `cap` NPCs that have non-empty projections. Also includes `speech_style` when present. Renders as `NPC STATE (use these in dialogue; do not contradict):\n- <name>: emotion="X", disposition="Y", speech_style="Z"\n...`.
5. Inject after source-profile block. Omit when empty.

Tests: `_npc_state_block` unit tests (empty, single NPC, per-universe scoping, cap, char truncation). SceneLoop integration: SceneState carries npc_profiles; narrator context receives it.

### Gap C: scene-mode emotion write (Option 1 — Narrator signature)

1. Add one structured output field to the Narrator's DSPy signature: `npc_emotional_states: dict[str, str]` mapping NPC entity name (or display name) → short emotion phrase (≤5 words). Docstring: "For each named NPC present in the scene, the emotion they should be carrying after this turn's events. Use their existing NPCProfile.current_emotional_state as the baseline; only include NPCs whose emotion has clearly shifted, or all NPCs present if multiple are relevant."
2. After Narrator runs, parse `npc_emotional_states` from the prediction. Resolve names → entity_ids via `state.entity_context` (fuzzy match against `entity.get('name')`). For each (entity_id, emotion_after), look up the current `npc_profiles[entity_id].current_emotional_state_by_universe.get(universe_id)`; skip writes when equal. Otherwise call `mongodb_update_npc_profile(entity_id, NPCProfileUpdate(current_emotional_state=emotion_after, current_emotional_state_by_universe={uid: emotion_after}))` via the existing tool.
3. Implementation lives in a new module-level helper `apply_npc_emotion_updates(state, prediction_npc_emotional_states) -> None` in `narrator/agent.py` (or a new tiny `npc_emotion_writer.py`). Called from the narrate post-node in scene_loop.py. Failures are logged and swallowed (one bad write must not break the turn).
4. DSPy signature change: existing tests that mock predictors (`_FakePredict` in `test_begin_story_command.py`) need to start returning the new field. Default to `{}` in fakes so existing assertions stay green.

Tests:
- `apply_npc_emotion_updates` unit: empty input → no calls; one change → one update; same value as current → no update; unknown name → silently ignored.
- Narrator signature change: existing tests still pass (fake predictors return default `{}`); one new test asserts the field is wired through.

### #3 Foreshadowing registry (new collection, minimal new code)

1. New MongoDB collection `scene_foreshadowing` with schema:
   ```
   {
     _id: UUID,
     scene_id: UUID,
     story_id: UUID,
     kind: "plant" | "payoff",
     summary: str,           # ≤200 chars
     planted_by_turn: int,   # turns_count when plant recorded
     target_turn: int,       # when payoff is expected (≥ planted_by_turn)
     status: "open" | "paid",
     created_at: datetime,
     paid_at: datetime | None,
   }
   ```
2. Data-layer tools: `mongodb_create_foreshadowing(params)`, `mongodb_list_open_foreshadowing(scene_id, story_id, *, limit=5)`, `mongodb_mark_foreshadowing_paid(foreshadowing_id, *, paid_at_turn)`.
3. **Plant** step: after `check_events` node (or in the same phase) — a small `check_foreshadowing` node calls a LIGHT DSPy signature that proposes 0–2 plants and 0–2 payoffs per turn. The signature input is the last narrative_text + entities + the player's action; output is `{"plants": [{"summary": str, "target_turn": int}], "payoffs": [{"foreshadowing_id": UUID, "summary": str}]}`. Each proposed plant is written via `mongodb_create_foreshadowing`. Each proposed payoff is matched against an open plant (by id when the LLM returns one, otherwise by fuzzy summary match); if matched, call `mongodb_mark_foreshadowing_paid`. If the LLM returns a payoff for an unmatched summary, ignore (don't create a phantom payoff).
4. **Read** step: `load_context` calls `mongodb_list_open_foreshadowing(scene_id, story_id, limit=5)` and stores the result in `SceneState.scene_foreshadowing_open: list[dict]`. Narrator injects `OPEN FORESHADOWING (pay off or reference these where natural):\n- <summary> (target turn N)\n...`. Cap 5 items. Omit when empty. Items with `target_turn ≤ turns_count` are flagged "(overdue — pay off soon)" in the block.

Tests: data-layer CRUD round-trip; check_foreshadowing DSPy module returns plants/payoffs deterministically (test with fake predictor); scene_state carries the open list; narrator renders block + overdue flag.

## Phase 3 — wiring + hygiene (varied risk)

### #5 Auto-recap on scene transition

`run_end_scene` (`packages/ui/backend/src/monitor_ui/routers/chat_loops.py`) already calls `_generate_scene_summary` (chat_loops.py:883) which uses Narrator. Pipe the summary into the *next* scene's state.

1. Add `SceneState.opening_recap: str = ""`.
2. `load_context` in scene-loop: if `state.turns_count == 0` and the session has a stored `last_scene_summary` (new key on `session` dict, set by `run_end_scene`), set `state.opening_recap = last_scene_summary`.
3. Narrator injects a one-line `LAST SCENE: <120-char summary>` block at scene start when `opening_recap` is non-empty. Cleared to `""` after first use (set to `""` at the end of the narrate post-node on the first turn).
4. `run_end_scene` writes the generated summary to `session["last_scene_summary"]` alongside the existing `SceneUpdate(summary=summary)` call.

Frontend unchanged — the GM's opening message already contains the recap text.

Tests: state field default; narrator block when set, omitted when empty; clear-after-first-use; end_scene writes session["last_scene_summary"].

### #8 Memory hygiene (conservative eviction)

1. Add `recall_count: int = 0` to the persisted memory document (the doc model returned by `mongodb_get_memory` / `_npc_profile_doc_to_response`-style helpers — identify during implementation; almost certainly a Pydantic model in `packages/data-layer/src/monitor_data/schemas/memories.py` or `CharacterMemory`).
2. `ContextAssembly._fetch_memories` (`context_assembly/agent.py:682`) and `_search_memories` (`:786`): after each retrieval, increment `recall_count` for each returned memory. New batched data-layer tool `mongodb_increment_memory_recall(memory_ids: list[UUID], *, increment_by: int = 1) -> int` does the work in a single Mongo `update_many`; the assembly code collects the returned memory IDs and calls the tool once per turn. **No-op for tests that mock the tool.**
3. New data-layer tool `mongodb_forget_stale_memories(*, story_id: UUID, min_age_scenes: int = 10, max_importance: float = 0.1, max_recall_count: int = 0) -> int` — deletes matching docs (`scene_id` from any scene older than `min_age_scenes`, `importance <= max_importance`, `recall_count <= max_recall_count`), returns count.
4. `run_end_scene` calls the tool and logs the count. Idempotent and safe.

Tests: data-layer CRUD; increment_memory_recall updates counts correctly; forget tool deletes only the right docs; run_end_scene logs the count (test that the tool is called with correct args).

## Global constraints

- Caps enforced at render time, not just write time: 4 NPCs in state block, 200 chars per NPC, 6 message tail, 5 foreshadowing items, etc.
- Every block degrades to silence (empty → omitted) — no exceptions.
- Layer rules: agents → data-layer only via MCP tools; no new direct DB calls.
- CanonKeeper authority: emotion writes go through `mongodb_update_npc_profile` (NPCProfile path), not direct Neo4j.
- No frontend changes.
- Minimal diffs; do not reformat pre-existing drift.
- Test fakes follow the `_FakePredict` + `dspy_context_for` nullcontext pattern.
- Verification commands: `uv run pytest packages/agents -q && uv run pytest packages/ui/backend -q && uv run pytest packages/cli -q`; `uv run ruff check packages`; `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`; `python scripts/check_layer_dependencies.py`; frontend: `npx tsc --noEmit -p packages/ui/frontend/tsconfig.json`.

## Out of scope

- Adding relationship-state writes in scene mode (relationship_states stay maintained by NPCVoice + Resolver; only emotion gets the scene-mode write hook).
- User-tunable memory-hygiene thresholds.
- Multi-universe emotional-state merging logic (per-universe partitioning is enough for now).
- NPCVoice integration with the SceneLoop (we add our own output; we don't call NPCVoice from SceneLoop).