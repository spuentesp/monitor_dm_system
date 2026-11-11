# G06 — Encounter difficulty estimation in prep (proposed CF-13)

> **Status:** implemented 2026-11-11 as **CF-13** (deterministic difficulty
> estimation + `POST /gm/encounter/check` + the CF-7 prep estimate + the
> difficulty badge in the session prep panel). Originally proposed
> 2026-11-11. Gap: CF-7 suggests "potential
> encounters" and `POST /gm/lookup/improvise` can create NPCs, but nothing
> checks a suggested encounter against the actual party (levels, size,
> resources), so prep suggestions are unvetted.

## Goal

When CF-7 (or the Tonight panel) proposes an encounter, attach a
difficulty estimate and a one-line rationale ("deadly for a level-3 party
of 4"), computed from the bound game system's rules — not vibes.

## Use case

Propose **CF-13 "Estimate Encounter Difficulty"**; amends CF-7's
"Suggested Prep" step.

## Scope

**In:** for a proposed encounter (list of NPC/entity IDs + party roster),
compute a difficulty label using the bound `game_system`
(`packages/agents/src/monitor_agents/game_system/`, incl.
`_advanced_systems.py` — it already knows initiative etc.); support the
common system conventions (CR vs. party level, action-economy heuristic) and
a generic fallback ("unknown system — no estimate"); show the math in the
UI (transparency, per EPIC 5's "consistent and transparent").
**Out (v1):** encounter *generation* (how many of what), terrain effects,
per-PC resource exhaustion modeling.

## Design

- **Layer 1:** read-only — entity stats from Neo4j via MCP tools, party
  roster from Mongo/Neo4j, game-system definition from the registry.
- **Layer 2:** pure function `estimate_difficulty(encounter, party, system)`
  in the game-system package (deterministic — **no LLM** for the math), plus
  a DSPy module only for rendering the human-readable rationale. Agent:
  extend `GmTableAgent` / prep module in `plot_hooks.py` (`generate_session_prep`).
- **Layer 3:** difficulty field on `POST /gm/session-prep` and
  `/gm/prep/extract` responses; `POST /gm/encounter/check` for ad-hoc
  "is this fight fair?"; UI badge in the Tonight/Prep panels.

## Phases

1. `estimate_difficulty` per bundled game system + generic fallback + unit
   tests (table-driven: known party vs. known encounter → expected label).
2. Prep pipeline integration: attach estimates to proposed encounters;
   agent tests with fakes.
3. Routes + response schema; backend tests incl. unknown-system fallback.
4. UI badges + rationale tooltip; vitest.

## Acceptance

- Every proposed encounter in CF-7/Tonight carries `difficulty` +
  `rationale`; unknown systems degrade to "unrated" instead of guessing.
- Math is deterministic and unit-tested; LLM only phrases the rationale.
- Commits reference CF-13; tests green; layer check clean.

## Open decisions

- Which systems get first-class estimators (suggest: D&D 5e CR, PBTA-style
  none) vs. generic party-size heuristic.
- Whether the estimate can *filter* hook suggestions (CF-4) by target
  difficulty — nice follow-up, out of v1.
