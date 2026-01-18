---
description: Implement a game mechanic (Phase 1)
---

# Implement Game Mechanic (Resolution)

Guide for adding mechanical resolution (Attack, Skill Check, Save) in Phase 1.

## 1. Data Layer (DL-24)
- **Schema**: Add to `monitor_data/schemas/resolutions.py`.
- **Enum**: Update `ActionType` and `ResolutionType`.
- **Tools**: Ensure `mongodb_create_resolution` handles the new type.
- **Authority**: Update `monitor_data/middleware/auth.py` if needed.

## 2. Agent Layer (Resolver)
- **File**: `packages/agents/src/monitor_agents/resolver.py`.
- **Logic**: Implement `resolve_<action>` method.
  - Retrieve stats (DL-26).
  - Calculate modifiers (from DL-20 system).
  - Roll dice (using `monitor_data.utils.dice`).
  - Determine outcome (Success/Fail).
  - Apply effects (Damage, Condition).
  - Log resolution (DL-24).

## 3. Integration (PC-Agent)
- **File**: `packages/agents/src/monitor_agents/pc_agent.py` (P-15).
- **Prompt**: Ensure PC-Agent knows it can take this action.
- **Decision**: Update action scoring to include this mechanic.

## Verification
```bash
# Test Resolver
pytest packages/agents/tests/test_resolver.py

# Test Data Layer
pytest packages/data-layer/tests/test_tools/test_resolution_tools.py
```
