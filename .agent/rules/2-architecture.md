# Architecture Rules

## 1. Layer Dependencies (Downward ONLY)
`CLI (L3) → Agents (L2) → Data Layer (L1)`

## 2. CanonKeeper Exclusivity
**ONLY CanonKeeper writes to Neo4j.**
- Other agents create `ProposedChange` (MongoDB).
- CanonKeeper evaluates and writes to Neo4j.
- Exception: Orchestrator can create `Story` nodes.

## 3. Implementation Order
1. **Layer 1 (Data)**: Schemas, Tools, Tests.
2. **Layer 2 (Agents)**: Logic, Prompts, Mocked Tests.
3. **Layer 3 (CLI)**: Commands, UI.

## File Locations
- **Data Layer**: `packages/data-layer/src/monitor_data/`
- **Agents**: `packages/agents/src/monitor_agents/`
- **CLI**: `packages/cli/src/monitor_cli/`
