# Development Workflow

## Use Case ID Mandatory
Reference use case (e.g., `DL-20`, `P-4`) in branches and commits.

## Pre-Commit Checklist
Run before submitting:
1. `python scripts/check_layer_dependencies.py`
2. `ruff check .`
3. `black --check .`
4. `mypy packages`
5. `pytest packages/agents` (etc)

## Documentation Maintenance
Update `docs/` when changing code:
- New Tool → `docs/architecture/DATA_LAYER_API.md`
- New Agent → `docs/architecture/AGENT_ORCHESTRATION.md`
