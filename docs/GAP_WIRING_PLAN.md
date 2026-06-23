# Gap Wiring Plan — From Analysis to Implementation

> **Created:** 2026-06-19. Execution plan for wiring the gaps identified in
> `docs/GAP_ANALYSIS.md`. Each task lands with unit tests + commit.
>
> **Priority order:** P-21 (progression) → P-16 (combat integration) →
> P-13 (party) — because progression is the highest-impact "characters grow
> from play" gap, combat integration already has the loop built, and party
> is the lowest-risk schema-first task.

## Task G-1: P-21 — XP Awarding in Scene Loop

**Goal:** Characters earn XP from play, tracked in working state.

**What exists:**
- `AdvancementSystem` schema with `xp_per_session`, `progression_table`
- `GameSystemRuntime.get_advancement_model()` returns the advancement dict
- `CharacterWorkingState` has `current_stats` dict (can hold XP/level)
- CombatPanel shows XP bar (T-071) but it's always empty

**Implementation:**
1. Add `xp` and `level` fields to `CharacterWorkingState` (optional, default 0/1)
2. In `persist_working_state` (scene_support.py), after applying resource
   deltas, call `_award_xp(resolution, game_context)` which:
   - Reads `xp_per_session` from the advancement model
   - Awards XP based on success level (critical_success > success > partial)
   - Returns an XP delta that gets written into `current_stats["xp"]`
3. Add `_award_xp` helper in scene_support.py (pure function, testable)

**Verify:** Unit test — mock resolution with success_level="success" + game
context with advancement model → assert XP delta > 0 in working state.

## Task G-2: P-21 — Level-Up API Endpoint

**Goal:** Player can spend XP to level up when they have enough.

**Implementation:**
1. `POST /api/entities/{entity_id}/level-up` in a new or existing router
2. Reads the entity's current XP/level from working state
3. Reads the advancement model from the bound game system
4. Checks if XP >= `progression_table[level+1].xp_required`
5. If yes: applies level-up (increments level, applies `resource_increases`,
   adds `features_gained` as conditions)
6. Returns the updated level + what was gained

**Verify:** Unit test — mock working state with XP >= threshold → assert
level-up returns new level + resource increases.

## Task G-3: P-16 — Combat Integration Tests

**Goal:** Verify the combat loop + HP delta wiring (G-1 from GAP_ANALYSIS,
already committed in `e19c10c`) works end-to-end in the scene loop.

**Implementation:**
1. Add a test that mocks the scene loop with a combat-triggering user input
2. Verify `_extract_combat_resource_deltas` is called and HP deltas appear
   in the result's `resource_deltas`
3. Verify the combat result narrative is appended to the scene narrative

**Verify:** Unit test passes with mocked CombatLoop.

## Task G-4: P-13 — Party API + Session Binding

**Goal:** Sessions can have multiple characters (a party), not just one PC.

**What exists:**
- `PartyInventoryCreate/Response` schemas (DL-16)
- `controlled_character_ids` field on `SessionCreate` (already used by
  quick-world T-092)
- Neo4j party nodes (DL-15)

**Implementation:**
1. `POST /api/parties` — create a party for a universe
2. `POST /api/parties/{id}/members` — add character to party
3. `GET /api/parties?universe_id=` — list parties
4. Session creation already accepts `controlled_character_ids` — verify
   this flows through to the scene loop's entity_context

**Verify:** Unit test — create party → add members → start session with
party → assert all members appear in entity_context.

## Execution Rules

- One commit per task (G-1, G-2, G-3, G-4)
- Unit tests for each
- Layer deps + ruff clean before each commit
- Update GAP_ANALYSIS.md after each task
- Update FINAL_FABLE_TASKS.md with new task IDs (G-*)