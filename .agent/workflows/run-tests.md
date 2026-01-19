---
description: Run complete test suite for all layers
---

# Run Tests

Runs the complete test suite for all three layers of MONITOR.

## Prerequisites

- All packages installed in development mode
- Infrastructure running (if testing with real databases)

## Steps

### 1. Run Data Layer Tests

// turbo
```bash
cd packages/data-layer
pytest --cov=src/monitor_data --cov-report=term-missing
```

Expected: All unit tests pass with >80% coverage

### 2. Run Agent Layer Tests

// turbo
```bash
cd ../agents
pytest --cov=src/monitor_agents --cov-report=term-missing
```

Expected: All unit tests pass with >80% coverage

### 3. Run CLI Layer Tests

// turbo
```bash
cd ../cli
pytest --cov=src/monitor_cli --cov-report=term-missing
```

Expected: All unit tests pass with >80% coverage

### 4. Run Integration Tests (Optional)

Integration tests require running infrastructure:

```bash
cd ../../
RUN_INTEGRATION=1 pytest -m integration -v
```

Skip if infrastructure is not running.

### 5. Run E2E Tests (Optional)

E2E tests require running infrastructure and take longer:

```bash
RUN_E2E=1 pytest -m e2e -v
```

Skip unless verifying full workflows.

## Fast Test Run (Unit Only)

For quick feedback during development:

// turbo-all
```bash
cd packages/data-layer && pytest -x
cd ../agents && pytest -x
cd ../cli && pytest -x
```

The `-x` flag stops at first failure for faster feedback.

## Coverage Report

To generate HTML coverage report:

```bash
pytest --cov=packages --cov-report=html
open htmlcov/index.html
```

## Test Markers

- `@pytest.mark.unit` - Fast unit tests (default, always run)
- `@pytest.mark.integration` - Cross-layer tests (skipped unless `RUN_INTEGRATION=1`)
- `@pytest.mark.e2e` - Full workflow tests (skipped unless `RUN_E2E=1`)

## Troubleshooting

**Import errors**: Ensure packages are installed in editable mode:
```bash
cd packages/data-layer && pip install -e ".[dev]"
cd ../agents && pip install -e ".[dev]"
cd ../cli && pip install -e ".[dev]"
```

**Database connection errors**: Start infrastructure with `/start-infra`

**Slow tests**: Run only unit tests (default) or use `-x` flag

## Next Steps

- If all tests pass: Proceed with commit/PR
- If tests fail: Fix issues before committing
- Run `/pre-commit-checks` before submitting PR
