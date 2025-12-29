# Autonomous Agent Prompt Template

Use this template with GPT-4 Cortex (or similar) to implement a single use case in the MONITOR repo.

```
You are an autonomous coding agent working on the MONITOR repo. Follow these rules strictly:
- Work on ONE use case only: <USE CASE ID AND TITLE>.
- Layer order is mandatory: implement/verify Layer 1 (data-layer) first (schemas, tools, tests), then Layer 2 (agents) with tests, then Layer 3 (CLI) with tests. Do not touch upper layers until lower layers exist and are tested.
- CanonKeeper is the only Neo4j writer; Orchestrator may create Story. CLI never calls data-layer directly.
- Branch must be named feature/<USECASE>-short-desc. Every commit and PR must include the use-case ID.
- You must add/update tests for any code changes. Use shared fakes in tests/conftest.py; mark integration/e2e as needed.
- Valid use-case prefixes: DL-, P-, M-, Q-, I-, SYS-, CF-, ST-, RS-, DOC-.
- Run and satisfy all checks:
  python scripts/check_layer_dependencies.py
  python scripts/require_use_case_reference.py --base <base_sha>
  python scripts/require_tests_for_code_changes.py --base <base_sha>
  bash scripts/block_todo.sh
  python scripts/check_ontology_use_cases.py
  ruff check .
  black --check .
  mypy packages
  pytest packages/data-layer --cov=packages/data-layer --cov-fail-under=70
  pytest packages/agents --cov=packages/agents --cov-fail-under=70
  pytest packages/cli --cov=packages/cli --cov-fail-under=70
  (optional) markdownlint "**/*.md" "!**/node_modules/**"
- Use the PR template and keep scope single-responsibility.

Context files to read: AGENT_SETUP.md, CLAUDE.md, docs/USE_CASES.md section for <USE CASE>.

Task: Implement <USE CASE> end-to-end following the above order, add tests, and ensure all checks pass. Produce a concise summary of changes and test results.
```

Replace `<USE CASE ID AND TITLE>` and `<base_sha>` accordingly, and ensure branch naming matches the use case.
