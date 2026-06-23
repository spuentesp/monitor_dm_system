# Gameplay Narrative Implementation Plan

> Purpose: close the gap between the new gameplay example docs and MONITOR's current autonomous-GM implementation.
>
> Reference material:
> - `docs/gameplay-examples/README.md`
> - `docs/gameplay-examples/*.md`
> - `packages/agents/src/monitor_agents/loops/`
> - `packages/ui/backend/src/monitor_ui/routers/chat.py`
> - `tests/e2e/`

## Status legend

- `[x]` completed
- `[-]` in progress
- `[ ]` not started

---

## Phase 1 — Clarification, transparency, and state visibility

**Objective:** make the current play loop feel more like a conversational duet by improving risk clarification, mechanical readability, and session-state inspection.

### Exact objectives
- [x] Expand OOC / clarification detection so benchmark-style questions are routed correctly.
- [x] Return structured risk and consequence metadata from the live resolution path.
- [x] Expose a session-state API for UI, debugging, and benchmark tooling.
- [x] Add regression tests for clarification detection and narrative-resolution metadata.

### Success criteria
- Benchmark prompts such as `((what would I roll here?))` and `what looks dangerous before I commit?` route to clarification instead of a blind action roll.
- GM replies include more explicit audit data for risks, stakes, and possible consequences.
- Session state can be fetched without scraping the full message list.

---

## Phase 2 — Rich turn semantics and consequence handling

**Objective:** make turns represent actual narrative intent rather than a generic action → narration pipeline.

### Exact objectives
- [x] Implement real intent parsing in `Resolver` / `SceneLoop` (`action`, `dialogue`, `query`, `ooc`, `meta`). `TurnLoop` has been removed.
- [x] Add structured mixed-success / success-at-cost options.
- [x] Support player follow-up choice when a resolution requires selecting a consequence.
- [x] Persist richer per-turn resolution records tied to `turn_id`.

### Success criteria
- The system can distinguish dialogue, investigation, risk questions, and explicit OOC requests.
- Partial successes can produce explicit player-facing options instead of only prose.
- Resolution records are first-class artifacts, not just metadata blobs.

---

## Phase 3 — Persistent narrative state evolution

**Objective:** model the kinds of evolving pressure shown in the gameplay examples.

### Exact objectives
- [x] Track character resources (`HP`, `Hunger`, `oxygen`, `Void Points`, `Heat`, `SP`) through active scenes.
- [x] Normalize conditions and temporary tags into a canonical scene/state contract.
- [x] Stage state changes via proposals and commit them safely through `CanonKeeper`.
- [x] Add scene summaries/checkpoints that include resource and condition snapshots.

### Success criteria
- Survival pressure and social/emotional drift survive across turns and scenes.
- Scene-end canonization can apply accepted resource and condition changes cleanly.

---

## Phase 4 — NPC memory, relationship canon, and social play

**Objective:** make NPC conversations persist beyond the current exchange.

> Architecture-first note: implementation should follow `docs/architecture/NPC_SOCIAL_PLAY_ARCHITECTURE.md`, which defines the social-state contract, canon boundary, and edge-case handling for this phase.

### Exact objectives
- [x] Normalize `NPCVoice` relationship/emotion outputs into typed proposal payloads.
- [x] Canonize accepted social state changes into Neo4j relationship/state-tag updates.
- [x] Surface NPC stance/emotional state in UI and debugging tools.
- [x] Add e2e tests proving that a social scene changes future behavior.

### Success criteria
- NPCs remember the consequences of a conversation.
- Social play affects later scenes in a measurable, persisted way.

---

## Phase 5 — System breadth and benchmark-driven narrative validation

**Objective:** align shipped systems and tests with the example library.

### Exact objectives
- [ ] Add packaged defaults / seeded system definitions for `Death in Space`, `Lancer`, `Monster of the Week`, and `7th Sea`.
- [x] Make benchmark runs system-safe by resolving missing exact packs to always-seeded baseline test systems (`Narrative Pure`, `Narrative Weighted`, `Powered by the Apocalypse`) instead of silently failing or binding the wrong ruleset.
- [x] Add player-consent dice prompts for `propose_roll`, persist the pending roll request on the session, and convert submitted dice results into resolved `SceneLoop` turns.
- [ ] Convert the example docs into benchmark-backed regression cases.
- [ ] Add long-form duet tests (8–12 turns) for pacing, continuity, and recovery from clarification.
- [ ] Track benchmark metrics across runs using the same scripted flows.

### Success criteria
- Benchmarks never depend on a licensed or genre-specific system already being seeded in MongoDB.
- If an exact pack is missing, MONITOR uses a visible benchmark-safe fallback instead of silently defaulting to an unrelated system.
- The example docs function as living regression targets.
- Narrative quality is measured across real benchmark flows, not only smoke tests.

---

## Immediate implementation log

- [x] Create the implementation plan doc.
- [x] Implement clarification/risk routing improvements.
- [x] Implement live narrative audit metadata improvements.
- [x] Implement `GET /api/chat/{session_id}/state`.
- [x] Add and run regression tests for the above.
- [x] Implement structured turn intent parsing in `Resolver` / `SceneLoop` (`TurnLoop` removed).
- [x] Add follow-up consequence choice handling in the live chat loop.
- [x] Persist turn-linked resolution records from `SceneLoop`.
- [x] Upsert per-scene `CharacterWorkingState` during active play.
- [x] Surface working-state snapshots and scene checkpoints through the chat session state API.
- [x] Stage `state_change` proposals from scene persistence and route them through `CanonKeeper`'s commit path.
- [x] Write the Phase 4 NPC social-play architecture before further implementation.
- [x] Normalize `NPCVoice` direct/actor outputs to canonical `state_change` / `relationship` / `entity` / `fact` proposal shapes.
- [x] Pass player / scene / story context through `ConversationLoop` and stage canonical social proposals for `CanonKeeper`.
- [x] Commit accepted social relationship changes through `CanonKeeper` and keep NPC working social state in MongoDB.
- [x] Surface latest NPC social stance and relationship snapshot through the session-state API and Play Console audit UI.
- [x] Add a GM-mode e2e regression showing that social state persists across scene turns and changes later behavior.

### Verification

Verified with:

```bash
/home/sebastian/monitor/monitor_dm_system/.venv/bin/python -m pytest \
  packages/agents/tests/test_resolver.py \
  packages/agents/tests/test_scene_loop.py \
  tests/test_chat_router_ooc.py \
  tests/e2e/test_05_gm_modes.py -q
```

Result: `102 passed, 6 skipped in 4.19s`.

Additional persistence verification:

```bash
/home/sebastian/monitor/monitor_dm_system/.venv/bin/python -m pytest \
  packages/agents/tests/test_resolver.py \
  packages/agents/tests/test_scene_loop.py \
  tests/test_chat_router_ooc.py \
  tests/e2e/test_05_gm_modes.py -q
```

Result: `103 passed, 6 skipped in 3.82s`.

Canonization + persistence follow-up verification:

```bash
/home/sebastian/monitor/monitor_dm_system/.venv/bin/python -m pytest \
  packages/agents/tests/test_resolver.py \
  packages/agents/tests/test_scene_loop.py \
  packages/agents/tests/test_canonkeeper.py \
  tests/test_chat_router_ooc.py \
  tests/e2e/test_05_gm_modes.py -q
```

Result: `130 passed, 6 skipped in 3.87s`.

Phase 4 social-state verification:

```bash
/home/sebastian/monitor/monitor_dm_system/.venv/bin/python -m pytest \
  packages/agents/tests/test_npc_voice.py \
  packages/agents/tests/test_conversation_loop.py \
  packages/agents/tests/test_canonkeeper.py \
  packages/data-layer/tests/test_tools/test_npc_profile_tools.py -q
```

Result: `75 passed, 2 warnings in 1.50s`.

Phase 4 UI + social continuity verification:

```bash
/home/sebastian/monitor/monitor_dm_system/.venv/bin/python -m pytest \
  tests/test_chat_router_ooc.py \
  tests/e2e/test_05_gm_modes.py -q
```

Result: `5 passed, 7 skipped, 2 warnings in 3.66s`.

Scoped regression verification (repo root):

```bash
/home/sebastian/monitor/monitor_dm_system/.venv/bin/python -m pytest -q
```

Result: `1144 passed, 82 skipped, 2 warnings in 15.72s`.

Current roleplay-startup regression verification:

```bash
uv run pytest \
  packages/agents/tests/test_resolver.py \
  packages/agents/tests/test_scene_loop.py \
  packages/agents/tests/test_story_loop.py \
  tests/test_chat_router_ooc.py -q
```

Result: `137 passed` as of 2026-05-03.
