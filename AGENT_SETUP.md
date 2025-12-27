# AI Development Setup Guide

This guide is for AI coding agents (ChatGPT/Codex, Claude Code, Copilot, etc.) working on MONITOR. Follow it to stay within boundaries, ship single-use-case changes, and pass CI.

## Before You Start
- Read: `CLAUDE.md`, `ARCHITECTURE.md`, `STRUCTURE.md`, `docs/USE_CASES.md`, `CONTRIBUTING.md`.
- Branch naming: `feature/<USECASE>-short-desc` or `bugfix/<USECASE>-short-desc` (e.g., `feature/P-6-answer-question`). CI enforces.
- Reference a use-case ID (P-, M-, Q-, I-, SYS-, CF-, ST-, RS-) in commits and PR body. CI enforces.

## Local Checks (run all)
```
python scripts/check_layer_dependencies.py
python scripts/require_use_case_reference.py --base <base_sha>
python scripts/require_tests_for_code_changes.py --base <base_sha>
ruff check .
black --check .
mypy packages
pytest packages/data-layer --cov=packages/data-layer
pytest packages/agents --cov=packages/agents
pytest packages/cli --cov=packages/cli
# Integration / e2e when relevant:
RUN_INTEGRATION=1 pytest -m integration
RUN_E2E=1 pytest -m e2e
```

## Testing Expectations
- Every code change must add/update tests (unit + integration/e2e where applicable). No tests → CI fail.
- Markers: `@pytest.mark.unit` (default), `@pytest.mark.integration`, `@pytest.mark.e2e` (skipped unless env flags set).
- Use shared fakes in `tests/conftest.py` (fake MCP client, fake LLM) to avoid touching real services by default.

## Layer Boundaries (critical)
- CLI (Layer 3) → imports only agents.
- Agents (Layer 2) → imports only data-layer.
- Data-layer (Layer 1) → imports no MONITOR packages.
- CanonKeeper is the only Neo4j writer (Orchestrator can create Story).

## Workflow (single use case)
1. Pick one use case (e.g., `P-6 Answer Question`).
2. Create branch with that ID; reference the ID in commit and PR.
3. Implement minimal, scoped changes + tests.
4. Run all checks above; fix failures.
5. Open PR using `.github/pull_request_template.md`. Keep scope to one responsibility.

## CI Gate (what will fail the PR)
- Branch naming check.
- Use-case reference check.
- Code changes without test changes.
- Layer boundary violations.
- Ruff, Black, Mypy failures.
- Pytest (with coverage) failures.

## Optional
- Install hooks: `pre-commit install` (runs ruff/black/mypy/pytest-unit).
- Sync docs to wiki (requires gh auth): `scripts/sync_docs_to_wiki.sh`.

By following this checklist, an AI agent can develop and submit changes that are containable, test-backed, and aligned with MONITOR’s architecture.***
