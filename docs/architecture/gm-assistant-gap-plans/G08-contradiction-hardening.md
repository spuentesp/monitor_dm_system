# G08 — Contradiction enforcement hardening (CF-5 amendment, G-9)

> **Status:** implemented 2026-11-11 (phases 1–4): the per-class recall
> corpus and harness, the per-candidate check shape, the CF-8 soft block
> with an audited override, and the opt-in per-owner hard rejection.
> Measured: `docs/testing/canonkeeper_recall_measurement_2026-11-11.md`.
> Originally proposed 2026-11-11. Gap: CF-5 detection is advisory-only.
> G-9 Phase 3 (hard rejection on canon transition violations) is opt-in off,
> and implication-check recall measured 25% on the synthetic set
> (`docs/testing/canonkeeper_depth_measurement_2026-11-07.md`), so a wrong
> fact can sail through CF-8 into canon.

## Goal

Make CF-5/CF-8 trustworthy enough to gate canon: raise implication-check
recall to a measured threshold, then turn on hard rejection for the
violation classes that pass it, keeping an explicit GM override with an
audit trail.

## Use case

Amend **CF-5** (detection → enforcement) — no new UC ID; the work item is
G-9 in `docs/architecture/GAP_REMEDIATION_PLAN.md` §G-9. This plan sequences
it; it does not duplicate G-9's design.

## Phases

1. **Measurement harness first** (prerequisite): expand the synthetic
   implication-check set from the 2026-11-07 measurement into a repeatable
   script under `scripts/` (not in sealed suites), with per-class recall
   reporting. Target: ≥90% recall on direct + timeline violations, ≥80% on
   implication chains, before any hard rejection ships.
2. **Retrieval improvements:** implication checks currently miss because
   related facts aren't retrieved — improve the fact-graph expansion in
   `canonkeeper/verification.py` (multi-hop relationship traversal, temporal
   ordering features), re-measure.
3. **Soft-block in CF-8:** when CanonKeeper flags a likely violation on a
   pending proposal, the CF-8 queue shows a blocking warning with
   "override with reason" (reason persisted on the proposal). Default:
   proposals with unresolved *direct* contradictions cannot be accepted
   without override.
4. **Hard rejection (G-9 Phase 3, opt-in flag):** per-owner config
   (SYS-6 style), off by default; when on, transition-violating proposals
   are rejected at the API. Audit log of overrides in Mongo.
5. **Regression net:** property-style tests in `tests/property/` are sealed
   — add new cases in `packages/agents/tests/test_canonkeeper_*.py` and
   `packages/ui/backend/tests/test_canon_review.py` instead.

## Acceptance

- Recall thresholds in phase 1 met and recorded in a new
  `docs/testing/canonkeeper_depth_measurement_<date>.md`.
- CF-8 accept on a direct-contradiction proposal requires an explicit
  override reason; override is visible in the review UI and audit log.
- Hard mode (flag on) returns 409 with a readable client error (pattern:
  `6fb92eb` quota/owner refusals).
- Commits reference CF-5 / G-9.

## Open decisions

- Threshold values (proposed above) — confirm against the expanded
  measurement set before locking.
- Whether hard mode is per-owner (recommended, tenancy) or global.
