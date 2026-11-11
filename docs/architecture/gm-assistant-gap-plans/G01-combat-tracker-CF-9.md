# G01 — At-the-table combat & initiative tracker (proposed CF-9)

> **Status:** proposed 2026-11-11. Gap: the `/gm` surface has a dice roller
> (`POST /gm/roll`) and rules *lookup* (`POST /gm/lookup/rules`) but no
> initiative order, no HP/condition tracking for PCs or enemies, no enemy
> stat blocks. Initiative logic exists only in the autonomous loop
> (`packages/agents/src/monitor_agents/loops/scene_loop.py`,
> `resolver.py`) and was never exposed to the GM page.

## Goal

Give the human GM a one-panel combat tracker inside `/gm`: start an
encounter, roll/track initiative, adjust HP and conditions per combatant,
advance rounds, and end the encounter — with permanent world changes (an
NPC dying, a faction's standing shifting) staged as `ProposedChange` for
CF-8, never written to Neo4j directly.

## Use case

Propose **CF-9 "Run an Encounter at the Table"** in
`docs/use-cases/epic-7-copilot-CF/CF-9/` (yml + specification, status
`proposed`), catalogued in `docs/USE_CASES.md`. Amend EPIC 7 coverage row in
`docs/1_product/epics.md` when shipped.

## Scope

**In:** initiative list with tie-breaks, round counter, per-combatant HP /
max HP / temp HP, conditions (poisoned, prone, …) as tags, death/unconscious
flags, enemy stat-block *reference* cards (read from canon, not edited
inline), damage/heal application with dice expressions via existing
`/gm/roll`, concentration/reminder notes, end-encounter summary that stages
proposals.
**Out (v1):** automated enemy AI turns, map/grid positioning, spell
resource pools, loot distribution (loot goes through the existing session-log
proposal path).

## Design (layer rules apply)

- **Layer 1 (data-layer):** new `mongodb_tools/combat.py` — combat state is
  *ephemeral session state*, so it lives in MongoDB keyed by
  `(universe_id, session_id)`, never in Neo4j:
  `combat_start`, `combat_get`, `combat_update_combatant`,
  `combat_set_initiative`, `combat_next_round`, `combat_end`, plus schemas in
  `schemas/combat.py`. Permanent canon effects → existing
  `ProposedChange` tools (CF-8 path).
- **Layer 2 (agents):** new `CombatAgent` (`packages/agents/src/monitor_agents/combat.py`,
  inherits `BaseAgent`) with co-located DSPy module for optional LLM bits:
  initiative roll narration, "what does this condition do" (delegates to
  the bound game system via `game_system` package), end-of-encounter summary.
  Deterministic state transitions (HP math, round advance) are plain code,
  not LLM calls.
- **Layer 3 (UI):** routes in `routers/gm_tools.py`
  (`POST /gm/combat/start`, `GET /gm/combat/{session_id}`,
  `POST /gm/combat/{session_id}/initiative`, `PATCH /gm/combat/{session_id}/combatant/{id}`,
  `POST /gm/combat/{session_id}/next-round`, `POST /gm/combat/{session_id}/end`),
  all behind the tenancy guard (pattern from `f1860c5`). Frontend: new
  "Combat" panel in `GM_PANELS` (`app/gm/page.tsx:1413`) +
  `components/gm/CombatPanel.tsx`.

## Phases

| Phase | Work | Files | Tests |
|-------|------|-------|-------|
| 1 | Schemas + Mongo tools + tool tests | `schemas/combat.py`, `mongodb_tools/combat.py` | `packages/data-layer/tests/test_tools/test_combat_tools.py` |
| 2 | `CombatAgent` + DSPy module + agent tests | `monitor_agents/combat.py`, `monitor_agents/combat/` | `packages/agents/tests/test_combat_agent.py` (FakeMCPClient/FakeLLMClient) |
| 3 | Routes + authz | `routers/gm_tools.py`, `middleware/auth.py` if new scopes | `packages/ui/backend/tests/test_gm_combat_routes.py` incl. CF authz regression style (`test_cf_authz_regressions.py`) |
| 4 | CombatPanel UI + page wiring | `components/gm/CombatPanel.tsx`, `app/gm/page.tsx` | `CombatPanel.test.tsx`, extend `page.test.tsx` |
| 5 | Encounter-end → proposals for CF-8; live table-test scenario | `gm_tools.py` end route | extend `docs/testing/GM_TABLE_TEST_PROTOCOL.md` with a combat scenario |

## Acceptance

- GM can run a full encounter from the `/gm` Combat panel without leaving
  the page: start → initiative → rounds with damage/conditions → end.
- End-of-encounter stages `ProposedChange` items (deaths, faction reactions)
  visible in the CF-8 queue; no direct Neo4j writes anywhere in the flow.
- All new tests green; `check_layer_dependencies.py` clean; commit messages
  reference CF-9.

## Open decisions

- Enemy stat blocks: read-only from canon entities (preferred) vs. ad-hoc
  quick-stats entry that is *not* persisted (v1: read-only + improvise
  lookup reuse).
- Condition effects per game system: reuse `game_system/_advanced_systems.py`
  definitions; fall back to free-text tags for systems without structured
  conditions.
