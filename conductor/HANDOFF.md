# Handoff — next steps (2026-11-11)

> For whoever picks up the MONITOR work next. Canonical status remains
> [`docs/STATUS.md`](../docs/STATUS.md); gap plans live in
> [`docs/architecture/gm-assistant-gap-plans/`](../docs/architecture/gm-assistant-gap-plans/_index.md).
> This file records where the branch stands, the owner's sequencing
> decisions, and the traps learned this session.

## Decisions (owner, 2026-11-11)

1. **Real human table verification (G11) is deferred** until all planned
   feature work is implemented. Do not run the ≥2 h GM session before then.
2. **First priority: tests about "basic workings"** (see Step 1 — confirm the
   intended scope with the owner if unclear).
3. **No push / no PR yet.** Commits stay local on `gap/wave1-integration`
   until the owner says otherwise.

## Where we are

Branch `gap/wave1-integration` (7 unpushed commits on top of `master` =
`29b92a4`). Quality gates at `HEAD`:

- `uv run pytest packages tests -q -n auto` — **10,146 passed, 0 failed**
  (the suite is hermetic; see traps below about `.env`)
- `ruff check packages scripts` + strict mypy — clean
- `python scripts/check_layer_dependencies.py` — clean

Shipped this session:

| Item | Commits |
|------|---------|
| Wave-1 gap plans G01 combat (CF-9), G03 entry correction, G04 clock (CF-11), G07 sharing (CF-14), G10 doc drift — merged via PR #144, re-verified here | (pre-existing) |
| Status drift fix: CF-9/CF-11/CF-14 ymls+specs+gap plans → `done`, USE_CASES.md aligned | `6ddcb83` |
| G05 campaign recap (CF-12) merged from `gap/g05-recap` (branch can be deleted) | `200620f` |
| Integration fixes: AUTHORITY_MATRIX audit grants + cross-tenant sweep combat coverage | `6aa2f4a` |
| CF-14 live verification 8/8 + owner_id UUID/str publish bug fix | `5c1e1a1`, `201b6d1` |

Live verification transcripts: `docs/testing/live_gm_assistant_share_cf14_2026-11-11.md`
(G07 Phase 5, all boxes ticked in the gap plan). G11 remains the only
un-run live gate.

## Step 1 — tests about "basic workings" (owner's stated next priority)

Interpretation to confirm: add behavior-level tests for the **basic workflows
of the shipped surfaces** before building new features — i.e. exercise real
calls (TestClient-level, hermetic fakes), not just unit pieces:

- Play loop basics: create session → send → wrap-up → persisted recap
- GM recorder: entry log → insights → strike/edit/restore (G03) → retract proposals
- Combat (CF-9): start → initiative → round/damage → end → proposals staged (no Neo4j writes)
- Share (CF-14): publish/unpublish/revoke + spoiler matrix + export (mirrors the live checklist, hermetically)
- Clock (CF-11): advance → deadline flip → briefing section
- Arc recap (CF-12): generate → persist → regenerate
- Forge basics: quick-world → canon queue → accept/reject

The alternate reading — "basic workings" = the core autonomous play loop —
applies the same style to `SceneLoop`/narrator/resolver flows. Ask the owner
which surface they mean before starting.

Place new tests in `tests/behavior/`, `tests/api/`, or `packages/ui/backend/tests/`
per [AGENTS.md](../AGENTS.md). Never touch `tests/verification/**` or
`tests/property/**` (sealed).

## Step 2 — implement the remaining work ("all stuff")

Per the gap-plan index's priority order (G02/G06/G08/G09 remain):

1. **G08 contradiction hardening** (P1) — *gated on recall*: first expand the
   synthetic implication-check corpus into a repeatable `scripts/` harness with
   per-class recall reporting; target ≥90% recall (direct+timeline) before
   turning on hard rejection (`CANONKEEPER_REJECT_TRANSITION_VIOLATIONS`).
   Plan: `docs/architecture/gm-assistant-gap-plans/G08-contradiction-hardening.md`;
   baseline: `docs/testing/canonkeeper_depth_measurement_2026-11-07.md`
   (currently 0% FP but only 25% detection).
2. **G06 encounter balancing** (P2, CF-13) and **G09 memory inspector** (P2,
   CF-15) — analysis tooling; both plans are written and self-contained.
3. **G02 audio capture** (P2, XL, CF-10) — needs a transcription vendor
   decision first; epic-sized.

Also open from [docs/STATUS.md](../docs/STATUS.md) (keep current when done):

- Co-Pilot workflow polish (`docs/architecture/GM_ASSISTANT_MODE_PLAN.md`; gap 4)
- CanonKeeper Phase 3 switch (part of G08)
- Auth hardening leftovers: provider API keys plaintext in Postgres, per-user
  LLM spend/model quota, shared hidden "Conversatory" universe, idempotent
  pre-auth owner backfill
- Deferred by decision: whole-repo mutation score, autonomous PC (G07 in
  `GAP_REMEDIATION_PLAN.md`), latency work (accepted < 40 s/turn)

## Step 3 — G11 real human table test (after "all stuff" is implemented)

Protocol: [`docs/testing/GM_TABLE_TEST_PROTOCOL.md`](../docs/testing/GM_TABLE_TEST_PROTOCOL.md)
(≥2 h human GM session; lookup log S1–S9 + combat C1–C4 filled during play;
report template at the bottom → `docs/testing/gm_table_test_report_<date>.md`).
Then: fix the ranked top five, re-run a short confirmation, and only then
flip `epics.md`/STATUS to "field-validated". Until that happens, CF "done"
means code-level done (this convention is now consistent across CF-1…CF-14).

## Traps learned this session (read before touching tests or live runs)

1. **`.env` breaks the hermetic suite if `MONITOR_AUTH_DISABLED=true`** —
   pydantic-settings reads it and the hermetic guard does not override that
   key → 141 auth tests fail. Keep `.env` at `MONITOR_AUTH_DISABLED=false`
   and `export MONITOR_AUTH_DISABLED=true` only when launching a live backend.
   (A worktree `.env` exists, gitignored, with working local values.)
2. **`NEO4J_PASSWORD` in `env.example` does not match the running container** —
   compose defaults to `monitor_dev_pass`; the worktree `.env` has it.
3. **The sealed DST wiring audit runs on the weekly workflow, not per-PR CI**
   — PRs can merge with it red. Run `uv run pytest tests/verification -q`
   before merging anything that adds agent→tool calls.
4. **AUTHORITY_MATRIX naming convention for new tools** (`middleware/auth.py`):
   grant the runtime `agent_type` *and* the name the wiring audit's
   `infer_agent_type` attributes (unmapped files → `CanonKeeper`;
   `ingestion/*.py` → `IngestionPipeline`). See the GmTableAgent world-clock
   comment for precedent.
5. **Cross-tenant route sweep** (`test_cross_tenant.py`): routes with
   body-carried resource ids need a `BODIES` entry using the `$kind`/`$uuid`
   sentinels (see the CF-9 combat entries); query params go in `QUERIES`.
6. **`FakeMCPClient` skips tool-argument Pydantic validation** — type
   mismatches at agent↔tool boundaries (like the CF-14 owner_id bug) only
   surface in live runs. When a live pass 500s, check the tool schema types.
7. **Public share API is `/api/share/{token}`** — `/share/{token}` is the
   Next.js page route (starlette's plain `Not Found` vs the share layer's
   `Not found` tells them apart). The `share_path` in API responses is the
   frontend link.
8. **Live-run recipe** (mirrors `docs/testing/live_gm_assistant_phase_a_2026-11-06.md`):
   backend from this worktree on `:8123` (`uvicorn monitor_ui.main:app --app-dir src`
   from `packages/ui/backend`, env sourced, auth disabled via export); leave the
   owner's main-checkout backend on `:8000` alone. LLM providers resolve from
   the Postgres registry; ollama `qwen2.5:7b` is available as fallback.

## Repo state

- Branch: `gap/wave1-integration` — commits `68f1404..201b6d1` unpushed.
- `gap/g05-recap` fully merged (safe to delete). `master` is behind this
  branch only by the commits above.
- Driver/probe scratch scripts used for the live pass were kept outside the
  repo (`/tmp/g07_live_check.py`, `/tmp/g07_probe.py`) and are not needed.
