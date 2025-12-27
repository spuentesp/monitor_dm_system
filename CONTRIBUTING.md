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
   - `black --check .`
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
- PRs to `main` run: layer check, use-case reference check, test-requirement check, ruff, black, mypy, pytest with coverage. Failing any gate blocks merge.

## Optional Tools
- `pre-commit install` to run ruff/black/mypy/pytest hook before commits.
