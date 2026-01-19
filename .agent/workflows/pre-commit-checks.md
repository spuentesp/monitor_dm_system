---
description: Run all pre-commit validation checks
---

# Pre-Commit Checks

Runs all validation checks required before committing code.

## When to Run

- Before committing code
- Before pushing to remote
- Before creating a PR
- After making significant changes

## Automated via Pre-Commit Hook

To run these automatically on every commit:

```bash
pre-commit install
```

This will run checks automatically when you `git commit`.

## Manual Execution

### Full Check Suite

// turbo-all

1. **Layer Dependency Check**
   ```bash
   python scripts/check_layer_dependencies.py
   ```
   Expected: No violations

2. **Ruff Linter**
   ```bash
   ruff check .
   ```
   Expected: No errors

3. **Black Formatter Check**
   ```bash
   black --check .
   ```
   Expected: All files formatted correctly

4. **MyPy Type Checker**
   ```bash
   mypy packages
   ```
   Expected: No type errors

5. **Run Unit Tests**
   ```bash
   pytest packages/data-layer packages/agents packages/cli -v
   ```
   Expected: All tests pass

6. **Coverage Check**
   ```bash
   pytest packages/data-layer --cov=src/monitor_data --cov-fail-under=80
   pytest packages/agents --cov=src/monitor_agents --cov-fail-under=80
   pytest packages/cli --cov=src/monitor_cli --cov-fail-under=80
   ```
   Expected: >80% coverage for all layers

### Quick Checks (Fast Development Loop)

For faster iteration during development:

```bash
# Linting only
ruff check .

# Type checking only
mypy packages

# Unit tests only (fast)
pytest -x
```

## Checks Required for PR

Before creating a PR, these must all pass:

1. ✅ Layer dependency check
2. ✅ Use case reference in branch name and commits
3. ✅ Code changes have corresponding test changes
4. ✅ Ruff linting passes
5. ✅ Black formatting passes
6. ✅ MyPy type checking passes
7. ✅ All unit tests pass
8. ✅ Coverage >80% for all layers

## Common Failures and Fixes

### Layer Dependency Violation

**Error**: `Found forbidden import: monitor_data in packages/cli`

**Fix**: Remove the import and use agents layer instead:
```python
# ❌ WRONG
from monitor_data.db import Neo4jClient

# ✅ CORRECT
from monitor_agents import Orchestrator
```

### Ruff Linting Errors

**Error**: `F401 'X' imported but unused`

**Fix**: Remove unused import or use it

**Error**: `E501 Line too long (>120 characters)`

**Fix**: Break line or use Black auto-formatter

### Black Formatting

**Error**: `would reformat file.py`

**Fix**: Run Black formatter:
```bash
black .
```

### MyPy Type Errors

**Error**: `error: Argument 1 has incompatible type "str"; expected "int"`

**Fix**: Add type hints and fix type mismatches

### Test Failures

**Error**: Test fails in CI but passes locally

**Fix**: 
- Check for environment-specific dependencies
- Ensure tests don't depend on local state
- Use fixtures and mocks properly

### Coverage Below Threshold

**Error**: `FAIL Required test coverage of 80% not reached`

**Fix**: Add tests for uncovered code paths

## Auto-Fix Commands

Some issues can be auto-fixed:

```bash
# Auto-fix Ruff issues
ruff check --fix .

# Auto-format with Black
black .

# Auto-sort imports
ruff check --select I --fix .
```

## CI Integration

These same checks run in CI. The workflow is:

1. Push to branch
2. CI runs all checks
3. If any fail, PR cannot be merged
4. Fix issues locally and push again

## Git Pre-Commit Hook

To run checks automatically on commit:

```bash
# Install hook
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

The hook will:
- Run ruff
- Run black
- Run mypy
- Run unit tests

If any fail, the commit is blocked.

## Quick Reference

| Check | Command | Auto-Fix |
|-------|---------|----------|
| Layer deps | `python scripts/check_layer_dependencies.py` | Manual |
| Linting | `ruff check .` | `ruff check --fix .` |
| Formatting | `black --check .` | `black .` |
| Types | `mypy packages` | Manual |
| Tests | `pytest` | Manual |
| Coverage | `pytest --cov --cov-fail-under=80` | Add tests |

## Next Steps

- All checks pass → Commit and push
- Some checks fail → Fix and re-run
- Ready to submit → Create PR with template
