# Contributing Guide (AI-Friendly)

This repo enforces single-responsibility PRs with mandatory tests and strict layer boundaries. Follow these steps for every change.

## Workflow
1. Pick one documented use case (e.g., `P-6`, `ST-2`). Reference it in commit message and PR body.
2. Make changes scoped to that use case only.
3. Add/adjust tests: unit + integration/e2e as appropriate.
4. Run checks locally:
   - `python scripts/check_layer_dependencies.py`
   - `python scripts/require_use_case_reference.py --base <base_sha>`
   - `python scripts/require_tests_for_code_changes.py --base <base_sha>`
   - `ruff check .`
   - `ruff format --check .`
   - `mypy packages`
   - `pytest packages/data-layer --cov=packages/data-layer`
   - `pytest packages/agents --cov=packages/agents`
   - `pytest packages/cli --cov=packages/cli`
   - To run integration/e2e: `RUN_INTEGRATION=1 pytest -m integration` / `RUN_E2E=1 pytest -m e2e`
5. Open PR using the template; ensure tests are included.

## Layer Boundaries
- CLI (Layer 3) imports only agents.
- Agents (Layer 2) import only data-layer.
- Data-layer (Layer 1) imports no MONITOR packages.
- CanonKeeper is the only Neo4j writer.

## Testing Expectations
- Unit tests for all code changes.
- Integration/e2e tests for cross-layer flows (use markers `integration`, `e2e`; skipped unless `RUN_INTEGRATION=1` or `RUN_E2E=1`).
- No code changes without test changes (enforced by CI).

## Branch/Commit Hygiene
- Use branch names with the use-case ID, e.g., `feature/P-6-answer-question`.
- Mention the use-case ID in commit messages and PR body.

## CI Gate
- PRs to `main` run: layer check, use-case reference check, test-requirement check, ruff, mypy, pytest with coverage. Failing any gate blocks merge.

## Sealed Verification Suites (T_val / T_test)

This repo splits its tests into two trust tiers:

- **T_val (visible, freely editable):** `tests/unit/`, `tests/api/`, `tests/contracts/`,
  `tests/behavior/`, `tests/e2e/`, `tests/smoke/` and per-package `tests/` dirs. Iterate
  here as fast as you need.
- **T_test (sealed):** `tests/verification/` (DST + cross-store oracle) and
  `tests/property/` (Hypothesis properties). **Implementers may not modify or delete
  files under these paths.**

Enforcement:

1. Pre-commit runs `scripts/sealed_suite_guard.py --staged` (best effort).
2. CI job `sealed-suite-guard` fails any PR whose diff touches sealed paths unless the
   PR carries the `sealed-override` label. Labels require write access — an agent cannot
   label its own PR.
3. `.github/CODEOWNERS` routes sealed-path changes to `@spuentesp`. Enable *Require
   review from Code Owners* in branch protection to enforce reviews.

A legitimate sealed-suite change (new property, stronger invariant, DST extension) lands
via: open the PR, explain why the sealed suite must change, and ask a maintainer to apply
`sealed-override` and review.

Mutation gate: `mutation-diff.yml` runs Cosmic Ray on the modules your PR touches and
fails when a mutant on a changed line survives. Kill it with a real assertion; the only
exception is `scripts/mutation_allowlist.toml`, which requires a written justification
including the mutant's source `line` (use it for proven equivalent mutants only).

Silent swallowing policy: `except Exception: pass/continue` is banned in `packages/**`
(ruff S110/S112/BLE001). `contextlib.suppress(...)` is the idiomatic form for *intentional*
tolerance (teardown, branch-coverage drivers) and must carry an intent comment — it is not
a loophole for hiding failures in production code.

## Optional Tools
- `pre-commit install` to run the sealed-suite guard before commits.
