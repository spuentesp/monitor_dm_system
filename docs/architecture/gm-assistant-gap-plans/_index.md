# GM Assistant Gap Plans — Index

> **Status:** proposed 2026-11-11. One plan per gap from the 2026-11-11 GM
> Assistant gap review (Epic 7 / CF-1…CF-8 vs. real GM needs).
> Parent context: `docs/architecture/GM_ASSISTANT_MODE_PLAN.md` (status board
> 2026-11-10), `docs/STATUS.md` gap 4, `docs/1_product/epics.md` (EPIC 7).
>
> Conventions (from `AGENTS.md`): pydantic v2; line-length 100; mypy strict;
> layer rules (UI/CLI → agents → data-layer via MCP tools only; **only
> CanonKeeper writes Neo4j** — everything else stages `ProposedChange`);
> `structlog`, no `print`; DSPy modules co-located with their agents. Never
> touch `tests/verification/**` or `tests/property/**` (sealed). New tests go
> in `packages/*/tests/`, `packages/ui/backend/tests/`, or
> `packages/ui/frontend/src/**/*.test.tsx`. Every commit/PR references at
> least one use-case ID (CI-enforced).

## Plans

| # | Gap | Plan | Proposed UC | Effort | Priority |
|---|-----|------|-------------|--------|----------|
| G01 | No combat/initiative/HP tracking at the table | [G01-combat-tracker-CF-9.md](G01-combat-tracker-CF-9.md) | CF-9 | L | **P0** |
| G02 | Audio/hybrid capture descoped — GM must type while running | [G02-audio-capture-CF-10.md](G02-audio-capture-CF-10.md) | CF-10 | XL | P2 |
| G03 | No mid-session strike/edit of captured entries | [G03-entry-correction.md](G03-entry-correction.md) | CF-1 amendment | S | **P0** |
| G04 | No in-fiction clock / time advancement between sessions | [G04-world-clock-CF-11.md](G04-world-clock-CF-11.md) | CF-11 | M | P1 |
| G05 | No campaign-level (story-arc) recap, only per-session | [G05-campaign-recap-CF-12.md](G05-campaign-recap-CF-12.md) | CF-12 | M | P1 |
| G06 | Prep encounters not balanced against the party | [G06-encounter-balancing-CF-13.md](G06-encounter-balancing-CF-13.md) | CF-13 | M | P2 |
| G07 | Recap/handouts are GM-only; nothing shareable to players | [G07-player-facing-sharing-CF-14.md](G07-player-facing-sharing-CF-14.md) | CF-14 | M | **P1** |
| G08 | Contradiction enforcement advisory-only (G-9 off, recall 25%) | [G08-contradiction-hardening.md](G08-contradiction-hardening.md) | CF-5 amendment (G-9) | L | P1 |
| G09 | No per-character knowledge inspector (memory audit) | [G09-memory-inspector-CF-15.md](G09-memory-inspector-CF-15.md) | CF-15 | M | P2 |
| G10 | CF specs still document a `monitor copilot` CLI that never shipped; YAML/epics status disagree | [G10-spec-doc-drift.md](G10-spec-doc-drift.md) | DOC-1 | S | **P0** (cheap) |
| G11 | "Done" is code-level only; real table test never run | [G11-table-test.md](G11-table-test.md) | — (protocol exists) | M (human time) | **P0** (gates "Epic 7 complete") |

## Suggested execution order

1. **G10** (docs, hours) + **G03** (small backend+frontend) + **G11** (schedule the table test) — all cheap, remove confusion and start field validation.
2. **G01** combat tracker — the highest-frequency at-table need; builds on existing resolver/initiative logic from the autonomous loop.
3. **G07** player-facing sharing — closes the recap/handout loop with players.
4. **G04**, **G05** — prep quality-of-life, both read-mostly.
5. **G08** — gated on implication-check recall (see `GAP_REMEDIATION_PLAN.md` §G-9 and `docs/testing/canonkeeper_depth_measurement_2026-11-07.md`).
6. **G06**, **G09** — analysis tooling.
7. **G02** audio capture — largest effort, needs a transcription vendor decision; its own epic-sized plan.
