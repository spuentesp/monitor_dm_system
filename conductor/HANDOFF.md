# Handoff — next steps (2026-11-11, evening)

> For whoever picks up the MONITOR work next. Canonical status remains
> [`docs/STATUS.md`](../docs/STATUS.md); gap plans live in
> [`docs/architecture/gm-assistant-gap-plans/`](../docs/architecture/gm-assistant-gap-plans/_index.md).
> This file records where the branch stands, the owner's sequencing
> decisions, and the traps learned.

## Decisions (owner, 2026-11-11)

1. **Real human table verification (G11) is deferred** until all planned
   feature work is implemented. Do not run the ≥2 h GM session before then.
2. **First priority: tests about "basic workings"** — confirmed to mean
   *both* the shipped GM-assistant surfaces and the core autonomous play
   loop.
3. **No push / no PR yet.** Commits stay local on `gap/wave1-integration`
   until the owner says otherwise.
4. **Audio capture (G02)**: both a local and a hosted transcription
   backend, plug-and-play — the backend is configuration, not code.

## Where we are

Branch `gap/wave1-integration`, commits `42e9dac..HEAD` unpushed (4 new
commits on top of the previous 8; nothing pushed, no PR).

Quality gates at `HEAD`:

- `uv run pytest packages tests -q -n auto` — **10,341 passed, 235
  skipped** (one CLI test flaked under load and passes in isolation and
  under `-n auto` for the whole CLI package).
- `uv run ruff check packages scripts` — clean.
- `uv run mypy packages/data-layer/src packages/agents/src packages/cli/src
  packages/ui/backend/src --cache-dir /tmp/mypy-cache` — **clean**. (Note:
  the branch was *not* mypy-clean before this session — 11 pre-existing
  errors in `player_share.py`, `combat/agent.py` and `recap/agent.py`; they
  are fixed now.)
- `python scripts/check_layer_dependencies.py` — clean.
- `uv run pytest tests/verification -q` — 9 passed (the sealed DST suite).
- Frontend: `npx vitest run` in `packages/ui/frontend` — **87 files, 576
  tests passed**; `npx tsc --noEmit` clean. (`npm run lint` is broken in
  this checkout — an ESLint 9 / @rushstack/eslint-patch incompatibility
  that predates this work.)

Shipped in this session:

| Item | What landed |
|------|-------------|
| Behaviour tests | A hermetic stack (`tests/behavior/_hermetic_stack.py`) running the real MCP tool path over mongomock; tests for share (CF-14), combat (CF-9), clock (CF-11), arc recap (CF-12), recorder corrections (G03), canon queue (CF-8), and the play loop's resolve/persist/scene-end nodes |
| G08 | Per-class recall corpus + `scripts/eval_canonkeeper_recall.py`; per-candidate check shape; focused-context builder; CF-8 soft block with an audited override; opt-in per-owner hard rejection |
| G06 (CF-13) | Deterministic encounter-difficulty estimation + `POST /gm/encounter/check` + the CF-7 prep estimate |
| G09 (CF-15) | Knowledge audit tool + `KnowledgeAuditAgent` + audit/challenge routes |
| G02 (CF-10) | Pluggable transcription registry (hosted OpenAI-compatible **or** local whisper) + upload/transcribe/queue routes |

Measurement record: `docs/testing/canonkeeper_recall_measurement_2026-11-11.md`
(per-candidate: 100% direct, 100% status, 100% timeline, 83% implication,
5.0% FP — every class at or above its floor).

## What is still open

- **G11 — the human table test** (protocol:
  `docs/testing/GM_TABLE_TEST_PROTOCOL.md`). This is the last thing; until
  it runs, every "done" in this repo means code-level done. **A pre-flight
  now exists** — `scripts/gm_table_test_preflight.py` exercises every
  endpoint the protocol touches against a live backend and gates the
  session (first run: `docs/testing/gm_table_test_preflight_2026-11-11.md`,
  which found and fixed a 500 in the Complication lookup and a latency
  problem in the Name lookup).
- **G02 phase 5 — the live pass** against a real recording.
- ~~G02 phase 4 — the segment review UI~~ **done 2026-11-12**:
  `AudioTranscriptPanel` (moved into `SessionRecorder`) plays a segment,
  edits its text, maps speakers, and queues it; upload keys are
  collision-proof and failed transcriptions clean up after themselves.
- ~~G06 phase 4 — the UI badge~~ **done** (`DifficultyBadge`).
- ~~G09 phase 4 — the UI panel~~ **done 2026-11-12**: `KnowledgePanel`
  with paginated provenance and a challenge flow (retract / correct) into
  CF-8 review; accepting a knowledge correction applies it through
  CanonKeeper across MongoDB + Qdrant + fact properties with a retryable
  checkpoint (`prepare_knowledge_memory_change` /
  `apply_knowledge_correction`). The multi-store write is not one
  transaction, but the **auto-reconciler**
  (`monitor_ui/correction_reconcile.py`, interval
  `MONITOR_CORRECTION_RECONCILER_INTERVAL`, default 60 s, 0 disables)
  finishes interrupted accepts automatically; a correction whose target
  moved under it is marked `knowledge_reconciliation_error` and left for a
  human (edit/defer/reject stay blocked while a checkpoint is live).
- **The STATUS.md open items** that are not gap work — now closed or
  reduced to ops: P3.2(b) is implemented 2026-11-13 (`story_id` threaded
  from scratchpad ingest through the job into proposal attribution),
  closing co-pilot gap 4's last code item; provider-key encryption is
  **enabled on this worktree** — `MONITOR_PROVIDER_KEY_ENCRYPTION_KEY`
  was generated into `.env` and documented in `env.example`. Remaining
  ops step: with the stack up, re-save the provider keys (e.g. via the
  `/config` page) so rows written before the key existed get encrypted.
  The other three items STATUS listed as open were **stale** and are now
  verified as done: per-user LLM spend quota (`monitor_data/usage.py`),
  the per-owner Conversatory universe, and — new this session — the
  idempotent pre-auth owner
  backfill (`POST /admin/ownership/backfill`).

## Traps learned (read before touching tests or live runs)

1. **`.env` breaks the hermetic suite if `MONITOR_AUTH_DISABLED=true`** —
   pydantic-settings reads it and the hermetic guard does not override that
   key → 141 auth tests fail. Keep `.env` at `MONITOR_AUTH_DISABLED=false`
   and `export MONITOR_AUTH_DISABLED=true` only when launching a live
   backend. (A worktree `.env` exists, gitignored, with working local
   values.)
2. **`NEO4J_PASSWORD` in `env.example` does not match the running
   container** — compose defaults to `monitor_dev_pass`; the worktree
   `.env` has it.
3. **The sealed DST wiring audit runs on the weekly workflow, not per-PR
   CI** — PRs can merge with it red. Run `uv run pytest tests/verification
   -q` before merging anything that adds agent→tool calls.
4. **AUTHORITY_MATRIX naming convention for new tools**
   (`middleware/auth.py`): grant the runtime `agent_type` *and* the name
   the wiring audit's `infer_agent_type` attributes (unmapped files →
   `CanonKeeper`; `ingestion/*.py` → `IngestionPipeline`).
5. **Cross-tenant route sweep** (`test_cross_tenant.py`): routes with
   body-carried resource ids need a `BODIES` entry using the `$kind`/`$uuid`
   sentinels; query params go in `QUERIES`.
6. **`FakeMCPClient` skips tool-argument Pydantic validation** — type
   mismatches at agent↔tool boundaries only surface in live runs.
7. **Public share API is `/api/share/{token}`** — `/share/{token}` is the
   Next.js page route.
8. **Live-run recipe**: backend from this worktree on `:8123`; leave the
   owner's main-checkout backend on `:8000` alone. LLM providers resolve
   from the Postgres registry.
9. **New (2026-11-11): the `tests/conftest.py` autouse fixture patches
   `get_mongodb_client` in every tool module** to a `FakeMongoClient` that
   has no `replace_one`. Any test that needs real Mongo behaviour must
   re-point it — the hermetic stack does this for every `monitor_*` module
   it can see, so prefer it over hand-rolled doubles.
10. **New: `ruff format packages` reformats files that were never
    formatted** (plot_hooks, recap/agent, mongodb_tools/combat,
    gm_tools). Do not let a formatting run smuggle unrelated diffs into a
    commit — format only the files you touched.
11. **New: the Postgres provider registry has no `provider_type` column** —
    the column is `provider` (`openai`, `custom`, `minimax`, …), and
    `provider_type` reads as NULL in a query. The transcription registry
    (`llm/transcription_providers.py`) keys off `provider` and `role`.
12. **New: `pkill -f "<the command you are running>"` kills your own shell** —
    the pattern matches the wrapper's own command line. Find the PID with
    `ps` and kill that.
13. **New: the LIGHT tier's default model cannot follow the structured
    output contract.** `llama3.2:1b` wrote a JSON string where an array
    belongs and every GM-table lookup that asks for a list 500'd. Fixed with
    `recover_instructor_failure` + a provider fallback
    (`BaseAgent.call_llm_structured`), but the latency remains: those lookups
    are as fast as the LIGHT provider, and a 1B model can take 120 s. Check
    the LIGHT row before a table session.

## Unmerged work sitting on a backup branch

**Update (2026-11-12/13): everything described below is now applied in the
`gap/wave1-integration` worktree and shipped as PR #154** (together
with the knowledge-correction flow, inspector pagination, and the G02/G09
phase-4 panels). The two backup snapshot branches were retired after
verification — fully superseded by `cdf597a` (only pre-pagination versions
of now-evolved functions differed) — deleted locally and on GitHub.

`backup/g09-g08-review-fixes-20261112` (commit `b5df647`, pushed) held
uncommitted review fixes found in the `gap/wave1-integration` worktree *after*
PR #147 merged. The interesting parts (all landed now):

- The G08 soft block was only wired into the single accept route. These
  changes route the batch verdict paths (`apply_verdicts`,
  `apply_verdicts_by_filter`) through `accept_proposal` too, so a batch
  accept cannot sidestep the override requirement. That is a real hole in
  what shipped.
- The by-filter verdict path owner-checks each matched proposal (it did not).
- `_resolve_review_flags` merges existing flags with newly detected ones;
  the merged version returns early on *any* flag and drops existing ones when
  stamping new ones.
- `knowledge_audit` fetches the universe's facts and filters afterwards —
  a witness need not be involved in a fact, so filtering by `entity_id`
  missed exactly the facts the inspector is for.

A second snapshot, `backup/g09-g08-review-fixes-2-20261112` (pushed), was taken
later the same day: more live edits appeared in the worktree after the first
snapshot (new tests for the batch-accept fix, frontend work in
`AudioTranscriptPanel`/`SessionRecorder`/`page.tsx`). That one is a stash
commit — `git checkout backup/g09-g08-review-fixes-2-20261112` restores it, or
`git stash apply dabbb72` on a matching base.

**Another session was actively editing this worktree while this was written.**
Before you assume a branch is up to date, run `git status`.

## Repo state

- Branch: `gap/wave1-integration` — **PR #154 merged** (2026-11-13,
  `b80ed01`): the post-#147 follow-up — review fixes + knowledge
  corrections + G02/G09 phase-4 panels (`cdf597a`), P3.2(b) story
  attribution (`4d50d62`), the correction auto-reconciler (`4c4d207`),
  the general lifecycle behaviour test (`e272874`), and the docs
  close-outs. The branch stays as the working branch for what comes next.
- `gap/g05-recap` fully merged (safe to delete).
- The local Postgres has a **live provider registry** (MiniMax M2.7,
  MiMo v2.6 Flash, Ollama qwen2.5:7b / llama3.2:1b). The measurement runs
  above used `mimo-v2.6-flash` (the HEAVY role's provider).
- The scratch scripts for the live pass were kept outside the repo
  (`/tmp/g07_live_check.py`, `/tmp/g07_probe.py`) and are not needed.
