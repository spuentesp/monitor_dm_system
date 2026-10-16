# Anti-Reward-Hacking Base — Sealed Suite, Diff Mutation Gate, Topology (Design)

Date: 2026-10-16
Status: Awaiting user approval of written spec
Approach: Hard CI gate + shared guard script + label-based exception; mutation gate scoped to the PR diff; lightweight topology checks on the existing DST suite.

## Problem

Code agents are rewarded for making the test command exit 0, not for making the system
work. Two failure modes follow:

- **Feature Isolation** — modules pass their own unit tests but fail when composed,
  because tests feed synthetic fixtures instead of real module output.
- **Reward Hacking** — an agent "fixes" a failure by hardcoding answers, weakening
  assertions, or bypassing layers (`except Exception: pass`, early `return state`),
  leaving every test green and the logic dead.

This spec covers the **first of four sub-programs** (anti-reward-hacking base). The
remaining three — full DST (seeded env, stateful Hypothesis, adversarial network,
shadow model), real-composition rules (write-then-read, process-edge-only mocking), and
the TS↔Python OpenAPI contract — are separate cycles and are explicitly out of scope
here.

Current repo state that this design builds on:

- `tests/verification/test_monitor_wiring_dst.py` — DST-style suite: strict wire bridge
  (bans `FakeMCPClient`), seeded raw-LLM transport, cross-store oracle over
  Neo4j/MongoDB/Qdrant/MinIO. This is the seed of `T_test`.
- `tests/property/` — 11 Hypothesis files, 132 `@given` decorators, plus a dedicated CI
  workflow (`property-tests.yml`).
- Cosmic Ray is already configured: 13 per-module `cosmic-ray-*.toml` files with curated
  `test-command`s and a weekly `mutation.yml` workflow that only publishes a badge.
- `scripts/check_layer_dependencies.py` — line-prefix layer check (kept; not replaced).
- No `CODEOWNERS`, no pre-commit config, no diff-scoped mutation gate, no rule against
  silent exception swallowing.

## Goal

Make it impossible for a code agent to weaken the verification layer or fake a passing
test run, without a maintainer explicitly signing off:

1. The suites that verify composition (`tests/verification/`, `tests/property/`) become
   **sealed**: the implementer agent cannot modify them; only a maintainer-authorized
   change can.
2. A PR that adds logic covered by weak or missing assertions fails CI, because mutants
   on the changed lines survive.
3. A PR that "fixes" a pipeline by swallowing exceptions or skipping graph nodes fails
   lint or the DST topology check.

## Non-goals

- No full DST harness (SimulationEnv injection, `RuleBasedStateMachine`, adversarial
  scheduler, full shadow model) — that is the DST sub-program.
- No write-then-read policy and no ban on internal-layer mocks — the real-composition
  sub-program. (The ~225 test files that patch internal modules are untouched here.)
- No OpenAPI→TS codegen, Schemathesis, fast-check, or MSW — the contract sub-program.
- No relocation/renaming of existing test directories. Sealing is in place.
- No hash manifest of sealed files (rejected alternative; see Decisions).
- No branch-protection configuration itself — we ship `CODEOWNERS` plus instructions;
  the GitHub settings toggle is a maintainer action.

## Decisions

| Decision | Chosen | Rejected alternatives |
|---|---|---|
| `T_test` contents | Seal `tests/verification/` + `tests/property/` in place | Rehome under `tests/verification_dst/` (import/CI churn); new empty sealed dir (existing suites stay exposed); also sealing `tests/contracts/` (too much friction for implementer iteration) |
| Enforcement | Hard CI gate; changes require `sealed-override` label applied by a maintainer | Advisory-first window (leaves the hole open); hash-manifest guard (extra mechanism, same guarantee) |
| Mutation gate | Zero survivors on changed lines; explicit allowlist for equivalent mutants | Kill-rate threshold (measurable gap agents can sit under); report-only (no guarantee) |
| Cycle shape | Shared guard script + incremental topology now; full topology with the DST cycle | Full anti-reward-hacking all at once (rework when DST rewrites the harness); sealing only (leaves empty-assert vector open) |
| Mutation tool | Cosmic Ray (already invested: 13 configs + CI) | Mutmut/StrykerJS (new toolchain; StrykerJS only matters for the TS sub-program) |

## Architecture — three enforcement layers

1. **Local (best-effort):** a pre-commit hook runs `scripts/sealed_suite_guard.py --staged`
   and rejects staged changes under sealed paths. Bypassable with `--no-verify`; it is a
   safety net, not the guarantee.
2. **CI (the real guarantee):**
   - `sealed-suite-guard` job on every PR: fails if the diff touches sealed paths and the
     PR lacks the `sealed-override` label. Label application requires write access to the
     repository, so an agent cannot label its own PR.
   - `mutation-diff` job on every PR: fails if mutants survive on production lines changed
     by the PR, except allowlisted ones.
3. **Governance:** `CODEOWNERS` covering sealed paths (enforced when the maintainer enables
   *Require review from Code Owners* in branch protection), plus explicit agent rules in
   `AGENTS.md` and `CLAUDE.md`.

`scripts/sealed_suite_guard.py` is the single body of seal rules; pre-commit and CI invoke
the same script. This is the two-agent protocol made structural: the builder writes under
`packages/*/src/`, the verifier writes under `tests/`, and neither can cross over without
maintainer action.

## Component A — Sealed-suite guard

**New files**

- `scripts/sealed_suite_guard.py`
  - Constants in one place: `SEALED_PATHS = ("tests/verification/", "tests/property/")`,
    `OVERRIDE_LABEL = "sealed-override"`.
  - Modes: `--base <ref>` (CI: inspect `git diff <ref>...HEAD`) and `--staged`
    (pre-commit: inspect the index).
  - Exit codes: `0` clean, `1` seal violation, `2` usage/environment error (e.g. missing
    base ref).
  - Failure message names the rule violated, the offending paths, and the legitimate route
    (maintainer applies `sealed-override`; CODEOWNERS review still required).
- `.github/CODEOWNERS` — entries for `tests/verification/**` and `tests/property/**` owned
  by the repository maintainer. Maintainer GitHub handle confirmed at implementation time.
- `.pre-commit-config.yaml` — local hook invoking the guard on staged changes.
- `tests/unit/test_sealed_suite_guard.py` (in `T_val`, visible) — meta-tests with synthetic
  diffs: flags sealed paths, passes when untouched, honors the override flag, correct exit
  codes.

**Modified files**

- `.github/workflows/ci.yml` — add the `sealed-suite-guard` job. The label check reads
  `github.event.pull_request.labels` from the event payload (no extra API call); the base
  ref is `github.event.pull_request.base.sha` fetched explicitly by the job.
- `CONTRIBUTING.md` — the T_val/T_test split, what may and may not change under sealed
  paths, how a legitimate sealed-suite change lands, and the branch-protection setup the
  maintainer must toggle (*Require review from Code Owners*).
- `AGENTS.md`, `CLAUDE.md` — agent rules: no modifications or deletions under
  `tests/verification/**` or `tests/property/**`; builder/verifier write permissions.

Sealing is in place: no moves, no import changes. `property-tests.yml` and the DST suite
keep running exactly as today.

## Component B — Diff-scoped mutation gate

**New files**

- `scripts/mutation_diff.py`
  1. Compute changed production files: `git diff --name-only <base>...HEAD -- 'packages/**/*.py'`,
     excluding anything under a `tests/` directory. Empty → exit 0 (docs/CI-only PRs cost
     no CI minutes).
  2. Map each changed file to a Cosmic Ray target: if it belongs to one of the 13 modules
     with a `cosmic-ray-*.toml`, reuse that file's curated `test-command`; otherwise generate
     a temporary config with `module-path` = the changed module and a `test-command` of
     `pytest` over the owning package's tests plus `tests/unit` (bounded with `--timeout`).
  3. Run `cosmic-ray init` + `cosmic-ray exec` + `cr-report` on those targets only.
  4. **Line filter:** Cosmic Ray mutates whole modules, so the gate only *fails* on
     survivors whose mutant line falls inside the PR's diff hunks. Survivors outside the
     diff are pre-existing debt: reported as warnings, never blocking.
  5. Compare in-diff survivors against `scripts/mutation_allowlist.toml` (mutant id +
     justification comment). Non-allowlisted survivor → exit 1 with the mutant, line, and
     the tests that failed to kill it.
- `scripts/mutation_allowlist.toml` — starts empty; entries require a justification comment.
- `.github/workflows/mutation-diff.yml` — `pull_request` workflow running the script.
  Checkout must fetch the base ref (`fetch-depth: 0` or explicit fetch) so the diff can be
  computed.

**Operational bounds:** per-test timeout (already present in the curated `test-command`s),
limited worker count, and skip-on-empty-diff. The weekly full-module `mutation.yml` badge
job is untouched.

## Component C — Lightweight topology (anti no-op bypass)

- **Lint rules** in `pyproject.toml` ruff config, applied to `packages/**`:
  `BLE001` (blind except), `S110` (`try-except-pass`), `S112` (`try-except-continue`),
  `E722` (bare except). Existing violations are fixed in this change. If the violation
  count turns out to be unreasonably large, the user is consulted before scope is cut.
- **Node/tool invocation counters** on the existing DST suite
  (`tests/verification/test_monitor_wiring_dst.py`), owned by the verifier role:
  - Add `inline-snapshot` as a dev dependency.
  - After each simulation scenario: inline-snapshot of the invocation trace (LangGraph
    nodes + critical MCP tools) and assertions that every graph node and every critical
    tool was invoked at least N times (N=1 for nodes; tool-specific minimums live in a
    `MIN_TOOL_INVOCATIONS` dict in the DST test module) and that no error was swallowed
    silently during the run.
  - The full trace harness (richer telemetry, per-node timing, exception-attribution)
    belongs to the DST sub-program and is deliberately not built here.

## Two-agent protocol (applies to this sub-program's own implementation)

- **Builder:** write access limited to `packages/*/src/`, `scripts/` guard/mutation code,
  workflow and config files. May not touch `tests/verification/**` or `tests/property/**`.
- **Verifier:** write access limited to `tests/`. Writes the meta-tests, the DST counter
  checks, and may only propose sealed-suite changes that land via maintainer override.
- Both roles must run `scripts/check_layer_dependencies.py`, `uv run ruff check packages`,
  and `uv run pytest packages tests -q` before reporting done.

## Verification (meta-tests for the machinery itself)

- Guard meta-tests (synthetic diffs): sealed path touched → violation; untouched → clean;
  override flag present → clean; bad usage → exit 2.
- Mutation-gate meta-test: a seed module with a deliberately empty-assert test must produce
  a surviving mutant and a non-zero exit; the same module with a real assertion must
  produce zero in-diff survivors.
- CI smoke: one throwaway PR that edits a sealed path without the label (expect red), then
  with the label (expect green), documented as a manual step in the rollout.

## Rollout (single PR, in order)

1. `scripts/sealed_suite_guard.py` + meta-tests + pre-commit + `CODEOWNERS` + docs
   (`CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`).
2. `scripts/mutation_diff.py` + `scripts/mutation_allowlist.toml` + `mutation-diff.yml`.
3. Ruff rules + fix existing violations in `packages/**`.
4. Invocation counters + inline snapshots in the DST suite.
5. Manual CI smoke PR (sealed path, with and without label).

## Definition of Done

1. A PR editing `tests/property/**` (or `tests/verification/**`) without `sealed-override`
   leaves `sealed-suite-guard` red with an actionable message.
2. The same PR with the label is green, and CODEOWNERS demands maintainer review.
3. A PR whose changed lines contain a surviving mutant leaves `mutation-diff` red; the
   allowlist is the only exception route.
4. A new `except Exception: pass` in `packages/**` fails `ruff check packages`.
5. A DST run where a graph node is never invoked fails the suite.
6. `uv run pytest packages tests -q`, `uv run ruff check packages`, and
   `python scripts/check_layer_dependencies.py` are green after the change.
7. `CONTRIBUTING.md`, `AGENTS.md`, and `CLAUDE.md` document the new rules.

## Open items

- **CODEOWNERS handle:** the maintainer's GitHub handle is needed for the owner entries.
  Placeholder `<maintainer-handle>` ships in the file and is replaced at implementation
  time once the user provides it.
- **Ruff violation volume:** counted at implementation time; if fixing all blind-except
  violations is disproportionately large, the user decides whether to scope down (e.g.
  `packages/agents` + `packages/ui/backend` first).
