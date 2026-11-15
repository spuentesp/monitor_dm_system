# G11 — Real table test (field validation of EPIC 7)

> **Status:** proposed 2026-11-11. Gap: all CF-1…CF-8 "done" claims are
> code-level — unit/backend/vitest green plus an 11/11 **API-level** live
> pass (`docs/testing/live_gm_assistant_phase_a_2026-11-06.md`). Phase 7
> Part B tasks 5–6 (table test, fix the top five) have never run because
> they need a human GM and a real ≥2 h session.
> Protocol: `docs/testing/GM_TABLE_TEST_PROTOCOL.md`.

## Goal

Run one real ≥2 h human-GM session using only the `/gm` surface, capture
ranked problems, fix the top five, and only then let `epics.md`/STATUS claim
EPIC 7 field-validated.

## Plan

1. **Recruit & schedule:** one human GM (ideally not the dev team), one
   universe with seeded canon (Fallout/VtM seed per the Phase A
   observations), 2–4 players optional (solo GM + test players fine).
2. **Pre-flight:** infra up (`docker compose`), backend on :8000, a live
   chat provider in the registry, protocol sheet printed/open.
3. **Run per protocol:** follow `GM_TABLE_TEST_PROTOCOL.md` step list —
   recorder, dice, lookups, prep-to-table, session log, wrap-up, CF-8
   review — plus, once G01 ships, a scripted combat. Observer logs every
   friction point with timestamp and panel.
4. **Measure, don't vibe:** latency of each `/gm/*` call (script exists:
   `6d4802f` streaming latency script pattern), number of clicks per task,
   any wrong-answer from lookups/hooks, any canon mistake caught or missed.
5. **Rank & fix:** top five problems → issues with UC IDs (CF-N or new
   gap IDs), fixed in priority order; re-run a short confirmation session.
6. **Record:** write `docs/testing/live_gm_assistant_table_<date>.md` with
   pass/fail per protocol step and the ranked problem list; update the
   status board in `GM_ASSISTANT_MODE_PLAN.md` and EPIC 7 row in
   `epics.md` to "field-validated <date>" only after the fixes land.

## Acceptance

- One completed protocol run with a written report in `docs/testing/`.
- Top five fixes merged with tests, each commit referencing its CF-N.
- Status board + epics.md updated consistently (avoid the G10 drift).

## Open decisions

- Compensation/incentive for the human GM.
- Whether players join as accounts (SYS-6 tenancy) or the GM plays all PCs
  (v1: GM plays all PCs — simpler, still exercises the surface).
