---
description: Validate layer boundary compliance
---

# Check Layer Dependencies

Validates that the 3-layer architecture rules are being followed.

## What It Checks

- Layer 1 (data-layer) imports only external packages
- Layer 2 (agents) imports only data-layer + external
- Layer 3 (cli) imports only agents + external
- No skip-layer imports (cli → data-layer)
- No upward imports (data-layer → agents)

## Steps

// turbo
1. Run the layer dependency checker:
   ```bash
   python scripts/check_layer_dependencies.py
   ```

2. Review output:
   - **✅ All checks passed**: Layer boundaries are correct
   - **❌ Violations found**: See error messages for details

## Common Violations

### Skip-Layer Import

```python
# ❌ WRONG: CLI importing data-layer directly
# File: packages/cli/src/monitor_cli/commands/play.py
from monitor_data.db import Neo4jClient
```

**Fix**: CLI should import from agents instead:
```python
# ✅ CORRECT
from monitor_agents import Orchestrator
```

### Upward Import

```python
# ❌ WRONG: Data-layer importing agents
# File: packages/data-layer/src/monitor_data/tools/neo4j_tools.py
from monitor_agents import CanonKeeper
```

**Fix**: Data-layer should only import external libraries:
```python
# ✅ CORRECT
from neo4j import GraphDatabase
```

### Circular Dependency

```python
# ❌ WRONG: Two layers importing each other
from monitor_agents import X  # in data-layer
from monitor_data import Y     # in agents (but this is OK!)
```

**Fix**: Remove the upward import.

## When to Run

- Before committing code
- After adding new files
- After modifying imports
- As part of CI checks

## CI Integration

This check runs automatically in CI. PRs will fail if violations are detected.

## Next Steps

- If checks pass: Continue with commit
- If violations found: Fix imports and re-run
- Run `/pre-commit-checks` for complete validation
