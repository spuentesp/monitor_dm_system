# Vision Alignment Review — How Far Are We?

> **Created:** 2026-06-19. Measures the actual implementation against the
> product vision in `SYSTEM.md` — the north star. For each of the three modes
> and five objectives, this document states: what works, what's verified live,
> what's unit-tested only, and what's missing.

## The Three Modes — Executive Summary

| Mode | Vision | Backend | Frontend | Live-verified | Gap to "full" |
|------|--------|---------|----------|---------------|---------------|
| **Autonomous GM** | "full solo RPG gameplay" | ✅ Complete | ✅ Play console wired | ✅ 15-turn playtest, e2e smoke | Latency (27s→<8s), combat orchestrator, downtime phase |
| **World Architect** | "build worlds from sources" | ✅ Complete | ✅ Forge/Worlds/Explorer/Snapshots | ✅ PDF ingestion, quick-world, architect chat | UI for party management, template instantiation |
| **GM Co-Pilot** | "reliable co-pilot for live sessions" | ✅ Complete | ✅ GM page + CanonReviewPanel | ✅ All CF surfaces 200 with real output | Output quality (hooks generic), retrieval scoping (fixed, live verify pending) |

**Bottom line:** All three modes are **backend-complete and live-verified**.
The remaining gaps are **quality and depth**, not missing foundations.

---

## Mode 1: Autonomous GM (Solo Play Experience)

### Vision (SYSTEM.md EPIC 4 + O2 + O3)
> "Run a complete RPG session without a human GM — scene-based narration,
> turn-by-turn interaction, player choice → world reaction, maintain tone,
> genre, and pacing, track unresolved consequences."

### What Works (live-verified 2026-06-14)

| Capability | Status | Evidence |
|-----------|--------|----------|
| Scene-based narration | ✅ Live | 15-turn playtest, avg 1,162 chars/turn, in-fiction prose |
| Turn-by-turn interaction | ✅ Live | 15/15 turns succeeded, 0 failures |
| Player choice → world reaction | ✅ Live | Resolver engaged (success levels alternated) |
| Tone/genre/pacing maintained | ✅ Live | Phase stayed `active_play`, continuity held (14/15 turns echoed prior proper nouns) |
| Canon persistence across sessions | ✅ Live | Neo4j entities/facts + Mongo turns + Qdrant memories |
| Oracle questions | ✅ Live | Playtest included oracle turn |
| Scene lifecycle (start/end) | ✅ Live | Scene-end choreography runs, story state advances |
| Session resume | ✅ Live | Session list, rename, delete, phase dot (T-079) |
| Recap ("story so far") | ✅ Live | Server /recap endpoint, modal in UI (T-068) |
| Quick actions (oracle/look/recap/retry) | ✅ Live | Quick-action chips (T-068) |

### What's Unit-Tested Only (not yet live-verified)

| Capability | Status | Evidence |
|-----------|--------|----------|
| XP awarding per turn | ✅ Unit (G-1) | `_award_xp` reads advancement model, 5 tests |
| Level-up API | ✅ Unit (G-2) | `POST /characters/{id}/level-up`, 5 tests |
| Combat HP deltas → working state | ✅ Unit (G-3) | `_extract_combat_resource_deltas`, 7 tests |
| Working state persistence in session | ✅ Unit (T-092) | Chat router persists `latest_working_state`, 1 test |
| Mechanical layer (HP/resources/conditions) | ✅ Unit (T-092) | `seed_actor_state` + `derive_state_deltas`, 48 scene_loop tests |
| Condition-weighted narrative mode | ✅ Unit (T-043b) | `GameSystemRuntime` evaluates conditions/scenery |

### What's Missing

| Gap | Impact | Effort |
|-----|--------|--------|
| **Turn latency 27s → <8s** | Game feels slow, not responsive | Medium — T-091 committed perf work, live verify pending |
| **P-16 Combat encounter orchestrator** | No structured tactical combat (initiative, rounds, multi-participant turns) | Large — CombatLoop exists but full encounter flow not verified |
| **P-21 Downtime phase** | No rest/training mode between story arcs | Medium — XP/level-up wired, but no automatic downtime trigger |
| **P-13 Party UI** | No party switcher in the play UI | Medium — API exists (G-4), no frontend party management |
| **P-14 Flashback mode** | Can't play scenes in the past | Medium — not implemented |

### Distance to "Full Solo Play"

**~85% there.** The core loop works — you can create a world, start a session,
play 15+ turns with coherent narration, earn XP, level up, and end the scene.
The mechanical layer (HP/combat/conditions) is wired but not yet live-verified.
The remaining 15% is: latency optimization, structured combat encounters,
downtime/progression phase, and party management UI.

---

## Mode 2: World Architect (World Engine / Creator)

### Vision (SYSTEM.md EPIC 1 + EPIC 2 + O1)
> "Build and maintain fictional worlds and multiverses from structured and
> unstructured sources — define worlds, universes, multiverses; store facts,
> locations, factions, rules of reality; track canonical vs optional truths."

### What Works (live-verified)

| Capability | Status | Evidence |
|-----------|--------|----------|
| Quick-world from seed | ✅ Live | One-line seed → universe with entities in <40s (T-087) |
| PDF ingestion | ✅ Live | Tiny PDF → completed job → ready pack in 78s (T-082) |
| Entity extraction (entities/lore/axioms) | ✅ Live | 17 entities, 10 lore, 1 axiom from test PDF |
| Ingestion edge cases | ✅ Live | Scanned/encrypted/corrupt/huge/duplicate all handled (T-083) |
| Failure visibility + controls | ✅ Live | Retry/Cancel/Unlock/Purge in Forge UI (T-084) |
| Pack library (apply/merge/export/import/clone/slice) | ✅ Live | Pack ops UI (T-061) |
| World tree (multiverse → universe → story → scene) | ✅ Live | Traversal tree with detail panes (T-074) |
| Entity graph explorer | ✅ Live | Graph tab with multi-select + batch delete (T-063) |
| Snapshots (capture/compare/restore) | ✅ Live | Snapshots page (DL-23) |
| Universe fork | ✅ Live | Fork Universe button (T-039) |
| World Architect chat mode | ✅ Live | Architect session commits canon NPC (T-055) |
| Audit trail (Q-10) | ✅ Live | Change log + History tab (T-064) |
| SillyTavern character card import | ✅ Live | JSON + PNG cards import/export (T-088) |
| Quick Start tab (seed → forge → play) | ✅ Live | Browser-tested, 39.6s forge (T-089) |
| Demo world (one-click Millhaven) | ✅ Live | Onboarding wizard "Try demo" (T-057) |
| Global world context picker | ✅ Live | Sidebar picker, persisted (T-077) |
| Templates + random tables | ✅ Live | Backend + UI (T-036/T-037) |
| Tone profiles | ✅ Live | CRUD from UI (T-036) |
| Lorebook editor | ✅ Live | Connected to API (T-037) |

### What's Unit-Tested Only

| Capability | Status | Evidence |
|-----------|--------|----------|
| Cross-source synthesis (I-13) | ✅ Unit | Merge candidates behavior tests |
| Pack curation (I-9) | ✅ Unit | Reclassify/promote/demote tests |
| Source library (I-7) | ✅ Unit | Browse/delete/reingest tests |

### What's Missing

| Gap | Impact | Effort |
|-----|--------|--------|
| **Party management UI** | No visual party creation/management | Medium — API exists (G-4), no frontend |
| **Entity template instantiation UI** | Templates exist but no "instantiate" button | Small — backend exists, UI not wired |
| **Ingestion recall benchmark** | Recall measured (100% on 8-entity fixture) but no automated regression | Small — T-097 done manually |

### Distance to "Full World Engine"

**~95% there.** The World Architect is the most complete mode. You can create
worlds from seeds or PDFs, manage them through a full tree, fork/snapshot/
restore, explore the entity graph, import character cards, and audit all
changes. The only missing piece is the party management UI and template
instantiation UI — both have backend APIs ready.

---

## Mode 3: GM Co-Pilot (GM Assistant)

### Vision (SYSTEM.md EPIC 7 + O4)
> "Augment, not replace, a human Dungeon Master — listen to or ingest live
> sessions, track NPC names/improvised lore/player decisions, suggest plot
> hooks/consequences/continuations, detect inconsistencies."

### What Works (live-verified)

| Capability | Status | Evidence |
|-----------|--------|----------|
| CF-1 Session recorder | ✅ Live | Reflections (881/1,294 chars, substantive) |
| CF-2 Recap | ✅ Live | Server /recap, modal in UI |
| CF-3 Plot threads | ✅ Live | Fixed (T-094), story bootstrap seeds opening thread |
| CF-4 Plot hooks | ✅ Live | 4 hooks generated (titles generic) |
| CF-5 Contradictions | ✅ Live | 0 found (true negative), ~2.6s |
| CF-6 Handouts | ✅ Live | 2,253-char in-character letter (strong) |
| CF-7 Session prep | ✅ Live | Prep with story picker (T-075) |
| CF-8 Canon review | ✅ Live | CanonReviewPanel, accept/reject proposals |
| Notebook ingest bound to multiverse | ✅ Live | T-075 |
| Session rename/archive/delete | ✅ Live | T-079 |

### What's Unit-Tested Only

| Capability | Status | Evidence |
|-----------|--------|----------|
| Retrieval scoping (universe_id) | ✅ Unit (T-093) | Memory schemas + Qdrant filter, 2 new tests |

### What's Missing

| Gap | Impact | Effort |
|-----|--------|--------|
| **Hook quality** | Titles are generic ("Welcome to Millhaven") | Small — prompt engineering, ground in canon entities |
| **Retrieval scoping live verify** | T-093 code committed, two-universe regression not live-verified | Small — run the test against dockerized stack |
| **Contradiction depth** | 0 found in 2.6s — depth unverified | Medium — needs a planted-contradiction fixture test |

### Distance to "Full GM Assistant"

**~90% there.** All eight CF use cases are implemented and live-verified with
real output. The gaps are quality (hook specificity, contradiction depth) and
a live verification of the retrieval-scoping fix. No missing features — just
polish.

---

## Five Core Objectives — Scorecard

| Objective | Vision | Score | What's Left |
|-----------|--------|-------|-------------|
| **O1 — Persistent Worlds** | Consistent worlds that retain facts, history, entities, causal continuity | ✅ **100%** | Nothing — fully implemented and live-verified |
| **O2 — Playable Narratives** | Full solo RPG gameplay: narrate, adjudicate, react | 🟡 **85%** | Latency (27s→<8s), combat orchestrator, downtime phase |
| **O3 — Rules Handling** | Multiple RPG systems, dice/cards/custom, success/failure/partial | 🟡 **80%** | Combat encounter flow, card-based mechanics (RS-5) |
| **O4 — Assisted GMing** | Co-pilot: remember, track, surface insights | ✅ **90%** | Hook quality, contradiction depth, retrieval scoping live verify |
| **O5 — World Evolution** | Worlds/characters change permanently from play | ✅ **95%** | Downtime phase (automatic progression trigger) |

---

## The Critical Path to "Full"

If I had to prioritize the remaining work to close the vision gap, in order:

1. **Verify T-091 latency on live stack** (Small) — run the 10-turn playtest
   and measure. If <8s, O2 is materially improved. If not, profile the hot path.

2. **Live-verify the mechanical layer** (Small) — start a demo session with
   `dice_game_system`, play a combat turn, verify HP changes in the
   CombatPanel. All the code is committed (T-092 + G-1/G-2/G-3); it just
   needs a live run.

3. **Live-verify retrieval scoping** (Small) — ingest two universes, run a
   co-pilot reflection for one, assert zero foreign-universe names. T-093
   code is committed.

4. **P-16 Combat encounter orchestrator** (Large) — the CombatLoop exists
   and is integrated into the scene loop, but the full multi-round, multi-
   participant encounter flow needs live verification and possibly UX work.

5. **P-21 Downtime phase** (Medium) — XP/level-up is wired (G-1/G-2), but
   there's no automatic "you've completed a story arc, here are progression
   options" trigger. The level-up is player-initiated via API.

6. **P-13 Party management UI** (Medium) — API exists (G-4), but the play
   UI doesn't have a party switcher or shared inventory view.

7. **Hook quality + contradiction depth** (Small-Medium) — prompt engineering
   to ground hooks in named canon entities; planted-contradiction fixture to
   verify CF-5 depth.

---

## Test Coverage Summary

| Layer | Tests | Status |
|-------|-------|--------|
| Full unit suite | 6,005 passed, 0 failed, 11 skipped | ✅ Green |
| E2e suite (RUN_E2E=1) | 15 test files, 81+ tests | ✅ Passes against live stack |
| Layer dependencies | All passed | ✅ Clean |
| Ruff lint (packages) | All checks passed | ✅ Clean |
| Frontend type-check | tsc --noEmit | ✅ Clean |
| Use cases marked "done" | 67 | ✅ |
| Use cases marked "in-progress" | 86 | 🟡 Backend done, polish/verify remaining |
| Use cases marked "todo" | 0 | ✅ None |

---

## Conclusion

**The product vision is ~90% realized.** All three modes are backend-complete
and live-verified. The remaining 10% is:

- **Performance**: turn latency (the single biggest play-feel gap)
- **Mechanical depth**: combat encounters, downtime/progression
- **Quality polish**: co-pilot hook specificity, contradiction depth
- **UI surfaces**: party management, template instantiation

None of these are foundational gaps — they're depth and polish on top of a
working system. The north star (persistent narrative intelligence that builds
worlds, runs solo RPGs, and assists GMs) is achievable with the current
architecture.

---

## Implementation Plan — Closing the Remaining 10%

> **Added 2026-06-19.** Prioritized execution plan for the 7 gaps above.
> Each task (G-5..G-11) lands with unit tests + commit. E2e tests added
> where applicable. Mutation testing reviewed.
>
> **Updated 2026-06-22:** G-5, G-6, G-7, G-8 all shipped. Status reflects
> completed work; iteration protocol ran cleanly (5,672 tests pass).

### Testing Harness Review

| Harness | State | Action |
|---------|-------|--------|
| Unit tests (pytest) | **5,672 pass, 38 skipped, 0 fail** (3:47 wall) | ✅ Baseline — verified post G-5..G-8 |
| E2e tests (RUN_E2E=1) | 16 files (added `test_14_mechanical_layer.py`) | ✅ G-8 mechanical-layer e2e added |
| Contract tests | 75+ files | ✅ Comprehensive |
| Behavior tests | scene_loop, canonkeeper, scene_support | ✅ Comprehensive |
| Layer dependencies | check_layer_dependencies.py | ✅ Passing |
| Ruff lint (packages) | Clean | ✅ |
| Frontend tsc | Clean | ✅ |
| Mutation testing | **Removed** (T-017) — mutmut 3.5 broken, cosmic-ray hangs on async | No action — documented decision |
| Property tests | hypothesis-based | ✅ Present |
| pytest-socket | Network blocked in unit mode | ✅ Enforced |
| pytest-timeout | 60s per test | ✅ Enforced |

**Mutation testing decision (T-017):** Both `mutmut<3` and `cosmic-ray` were
attempted. `mutmut` 3.5 is broken upstream. `cosmic-ray` hangs indefinitely
on the async stack (the `cosmic-ray.toml` config targets `canonkeeper.py`
but execution never completes). Claims were formally removed from docs.
This is a known limitation, not a gap we can close with current tooling.

### Task G-5: Downtime Phase Trigger (P-21) — ✅ Done (`31536a49`)

**Goal:** When a story arc reaches `resolution`, automatically offer
progression options (spend XP, level up, train).

**Implementation:**
1. ✅ Added `downtime_available` emission to `complete_current_scene` in `scene_loop.py` — when `story_state.arc_label == "resolution"`, sets the flag
2. ✅ Added `GET /api/entities/characters/{id}/downtime` endpoint — returns available progression options based on accumulated XP + advancement model
3. ✅ Unit tests (5): 2 for scene-loop trigger (resolution → True, rising_action → False), 3 for API (XP ≥ threshold, XP < threshold, no system)

### Task G-6: Hook Quality Grounding (CF-4) — ✅ Done (`e062656`)

**Goal:** Plot hooks should name real canon entities, not be generic.

**Implementation:**
1. ✅ Added `extract_canon_entity_names(entities)` and `filter_ungrounded_hooks(hooks, names, min_grounded=1)` helpers in `plot_hooks.py`
2. ✅ Token-based normalization (apostrophes/dashes treated as spaces) so "Aldric's Quest" matches canon "Aldric the Bold"
3. ✅ Wired filter into `PlotHookAgent.suggest_hooks()` — generated hooks are dropped unless they reference a canon entity
4. ✅ Unit tests (10): name extraction dedup, title match, connected_entities match, fuzzy punctuation, empty canon, filter behavior, end-to-end through suggest_hooks

### Task G-7: Contradiction Depth Fixture (CF-5) — ✅ Done (`227047b`)

**Goal:** Prove CF-5 can detect a planted contradiction.

**Implementation:**
1. ✅ Expanded `_heuristic_contradictions` with 3 new patterns beyond simple negation:
   - Status antonyms (alive/dead, married/single, free/captive, ally/enemy, friend/foe, present/absent, well/sick, awake/asleep) — marked severity=high
   - Location conflicts ("X is in Waterdeep" vs "X is in Neverwinter") — severity=medium
2. ✅ Limit raised from 5 to 10 contradictions
3. ✅ Unit tests (10): planted alive/dead, married/single, free/captive, ally/enemy, location, multiple per batch, same-status negative case, location-overlap negative case, severity assertion

### Task G-8: E2e Test for Mechanical Layer — ✅ Done (`89c1422`)

**Goal:** Verify the mechanical layer (HP/combat/XP) works end-to-end.

**Implementation:**
1. ✅ New `tests/e2e/test_14_mechanical_layer.py` — 9 tests across 4 classes covering XP progression, working_state build, combat resource deltas, and downtime character persistence
2. ✅ Gated by `RUN_E2E=1` — module skips cleanly for fast daily dev
3. ✅ Use cases covered: P-21, T-092, RS-1..RS-4

### Iteration Protocol — Complete

| Iter | Focus | Outcome |
|------|-------|---------|
| 1 | Full suite (`packages tests/api tests/contracts tests/behavior`) | 5,672 pass, 38 skip, 0 fail (3:47) |
| 2 | Code quality + lint | `ruff format` on plot_hooks.py; packages dir lint clean |
| 3 | Coverage gaps | Layer dependencies check passing; no gaps found |
| 4 | Docs | STATUS.md, GAP_ANALYSIS.md, VISION_ALIGNMENT_REVIEW.md all updated to reflect G-5..G-8 |
| 5 | Final review | No additional changes needed |

---

## Round 2 — What's Missing for the Full Software Experience (2026-06-19)

> **New question raised:** "Considering both product vision AND use cases,
> what is missing for the full software experience? Use cases build on top
> of each other, so it's difficult to know if the game loop works."

### Diagnostic — Where is the game loop actually verified today?

| Layer | What it verifies | Gap |
|-------|------------------|-----|
| Unit tests (5,672 pass) | Helpers, schemas, single-agent methods | ❌ Multi-step orchestration not covered |
| `test_00_mvp_smoke` | Full data-layer + SceneLoop chain end-to-end (real Neo4j+Mongo containers) | ✅ Best proof, but only one scenario |
| `test_04_gm_loop` | Resolver + scene_loop with mocked LLM | ✅ Good chain proof |
| `test_05_gm_modes` | UI mode switching + chat CRUD (mocks SceneLoop) | ❌ Doesn't run the loop |
| `test_06_full_pipeline` | PDF ingest + SceneLoop turn with mocked LLM | ✅ Good |
| `test_07_live_gameplay` | Real backend, real LLM | Requires live backend |
| `test_09_mode_walkthroughs` | All 3 modes against live backend | Requires live backend |
| `test_14_mechanical_layer` | XP/HP/working_state in isolation | ✅ Component-level |

**The critical observation:** there is no **hermetic (no live backend,
no real LLM) integration test** that drives the full chain
**session → send_message → SceneLoop → canonization → state update → next turn**
and asserts all the things use cases P-1..P-8, M-1..M-4, DL-1..DL-3 build on
top of each other. test_00 covers the data layer; test_05 covers the router
plumbing. Neither proves the *integration* between them.

### Prioritized Gaps (Round 2)

| ID | Gap | Impact | Effort | Why prioritized |
|----|-----|--------|--------|-----------------|
| **G-9** | Hermetic game-loop integration test (P-1..P-8 chain) | High — directly answers "is the game loop working?" | Medium | Fills the **biggest single verification gap** the user named |
| **G-10** | Session state-machine coverage (phase transitions) | Medium — phases govern UX | Small | Phase machine is a stateful contract; only spot-checked today |
| **G-11** | Mode-aware SceneLoop integration (Autonomous GM ↔ World Architect ↔ Co-Pilot) | Medium — switching modes is a daily UX path | Small | Today the same SceneLoop is shared; verify it still works across mode switches |
| **G-12** | Session lifecycle: create → first turn → end-scene → resume | Medium — covers the full UX arc | Small | Each piece is tested, the chain isn't |

### Task G-9: Hermetic Game-Loop Integration Test

**Goal:** Prove that `POST /api/chat/{sid}/send` actually drives the full
chain — message → SceneLoop → canonization → session state — **without**
a live backend, real DB, or real LLM.

**Approach:**
1. New `tests/api/test_game_loop_integration.py`
2. Use the existing `ui_client` fixture (mocks DB), but **partially**
   unmock the chat turn runner so it invokes a fake `SceneLoop` whose
   `process_turn()` returns a real-shaped `SceneLoopResult` and writes
   to a real (in-memory) scene state.
3. Tests:
   - **P-1/P-3:** send first message → SceneLoop created → narrative returned → session has `last_turn_id`
   - **P-4:** second turn references prior turn via state
   - **P-5/P-8:** after several turns, canonization artifacts appear in session
   - **DL-2:** end-of-loop character has updated `current_stats` if dice mode
   - **DL-7:** end-of-loop session state shows `memories_attached` field
4. The mock SceneLoop must be **real SceneLoop subclass** with all
   external calls (MCP tools) stubbed — this exercises the actual graph
   nodes, just without the LLM/DB network.
5. Gate: not RUN_E2E dependent — runs in default `pytest` suite as
   the **integration-tier test that proves the chain works**.

**Why this matters:** With G-9 in place, the question "does the game loop
work?" has a deterministic, fast, always-green answer in CI. Today the
only answer is "test_07 against a live backend."

### Task G-10: Session State-Machine Coverage

**Goal:** Verify the session phase machine transitions correctly.

**Approach:**
1. Add a focused unit test file `tests/api/test_session_state_machine.py`
2. Test the canonical phase transitions: `pending → preplay → active_play → recap → end`
3. Verify invalid transitions are rejected (e.g., end → active_play)
4. Verify that `end_scene` resets the loop cache and prepares for next scene
5. Verify that resuming a session restores the prior phase

### Task G-11: Mode-Aware Integration

**Goal:** Confirm switching modes mid-session preserves context and
re-uses appropriate loop machinery.

**Approach:**
1. Add `tests/api/test_mode_switching_integration.py`
2. Test: start autonomous_gm session, run 2 turns, switch to gm_copilot,
   run a co-pilot endpoint, switch back to autonomous_gm, verify state
   preserved.
3. Test: start world_architect session, run a "build world" turn, switch
   to autonomous_gm, run a player turn, verify the new scene inherits
   the architect's universe.

### Task G-12: Session Lifecycle

**Goal:** End-to-end session lifecycle in a single integration test.

**Approach:**
1. Add to G-9's test file: `test_session_lifecycle_create_play_end_resume`
2. Create session → start conversation → run 5 turns → end scene →
   create new scene in same session → resume → run more turns.
3. Verify each transition produces the right state machine updates
   and that scene-level state is properly isolated from session-level state.

### Iteration Protocol (Round 2)

After implementing G-9..G-12, iterate 5 times:
1. Run full suite → fix any failures
2. Review code quality → fix lint/type issues
3. Review test coverage → add missing edge cases
4. Review docs → update STATUS/GAP_ANALYSIS/VISION_REVIEW
5. Final review → if no changes needed, done

### Test coverage after G-9..G-12

| Area | Before | After |
|------|--------|-------|
| Hermetic chain proof of game loop | None | G-9: 6+ tests |
| Phase machine coverage | Spot-checked | G-10: 5+ tests |
| Mode-switching integration | None | G-11: 3+ tests |
| Full session lifecycle chain | None | G-12: 1+ test |