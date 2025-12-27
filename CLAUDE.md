# MONITOR - AI Agent Instructions

> **You are working on MONITOR, a narrative AI system with a strict layered architecture.**

---

## Before You Do Anything

1. **Read `STRUCTURE.md`** - Complete folder definitions (REQUIRED)
2. **Read `ARCHITECTURE.md`** - Layer architecture and rules
3. **Identify which layer** your changes belong to
4. **Respect layer boundaries** - Dependencies flow downward ONLY

---

## Key Documents (Read Order)

| Order | Document | What It Contains |
|-------|----------|------------------|
| 1 | `STRUCTURE.md` | Every folder defined, what goes where |
| 2 | `ARCHITECTURE.md` | Layer rules, dependency diagram |
| 3 | `docs/USE_CASES.md` | All use cases (S-, U-, ST-, C-, G-, I-, Q-, CF-) |
| 4 | `packages/*/README.md` | Layer-specific instructions |
| 5 | `docs/AI_DOCS.md` | Quick reference for implementation |

---

## The Three Layers (Memorize This)

```
Layer 3: CLI          packages/cli/           → imports agents ONLY
Layer 2: AGENTS       packages/agents/        → imports data-layer ONLY
Layer 1: DATA-LAYER   packages/data-layer/    → imports external libs ONLY
```

### What Goes Where

| If you're working on... | It belongs in... |
|-------------------------|------------------|
| User commands, REPL, terminal UI | `packages/cli/` |
| AI agents, loops, LLM calls | `packages/agents/` |
| DB clients, MCP tools, schemas | `packages/data-layer/` |

---

## Forbidden Patterns (DO NOT DO)

```python
# ❌ FORBIDDEN: CLI importing data-layer directly
# File: packages/cli/src/monitor_cli/commands/play.py
from monitor_data.db import Neo4jClient  # WRONG!

# ✅ CORRECT: CLI imports agents, agents import data-layer
from monitor_agents import Orchestrator  # RIGHT!
```

```python
# ❌ FORBIDDEN: Data-layer importing agents
# File: packages/data-layer/src/monitor_data/tools/neo4j_tools.py
from monitor_agents import CanonKeeper  # WRONG!

# ✅ CORRECT: Data-layer has no MONITOR dependencies
from neo4j import GraphDatabase  # RIGHT!
```

```python
# ❌ FORBIDDEN: Agents importing CLI
# File: packages/agents/src/monitor_agents/orchestrator.py
from monitor_cli import app  # WRONG!
```

---

## CanonKeeper Rule (CRITICAL)

**Only CanonKeeper can write to Neo4j.**

```python
# In packages/data-layer/src/monitor_data/middleware/auth.py
AUTHORITY_MATRIX = {
    "neo4j_create_entity": ["CanonKeeper"],
    "neo4j_create_fact": ["CanonKeeper"],
    "neo4j_update_state": ["CanonKeeper"],
    # ... all Neo4j writes require CanonKeeper
}
```

If you're implementing a feature that needs to write to Neo4j:
1. The write MUST go through CanonKeeper
2. Other agents create `ProposedChange` documents in MongoDB
3. CanonKeeper evaluates and commits at scene end

---

## When Adding New Code

### Step 1: Determine the Layer

Ask yourself:
- Is this user-facing? → Layer 3 (CLI)
- Is this AI/LLM logic? → Layer 2 (Agents)
- Is this data access? → Layer 1 (Data-layer)

### Step 2: Check Dependencies

Before adding an import, verify:
- CLI can only import from `monitor_agents`
- Agents can only import from `monitor_data`
- Data-layer can only import external libraries

### Step 3: Follow Existing Patterns

Look at existing code in the same layer:
- Same file structure
- Same naming conventions
- Same patterns (e.g., Pydantic models, async/await)

---

## Quick Reference

### Package Names

```python
# Layer 1
from monitor_data import ...
from monitor_data.db import ...
from monitor_data.tools import ...
from monitor_data.schemas import ...

# Layer 2
from monitor_agents import ...
from monitor_agents.orchestrator import Orchestrator
from monitor_agents.canonkeeper import CanonKeeper

# Layer 3
from monitor_cli import ...
from monitor_cli.commands import ...
```

### File Locations (Exact Paths)

| To modify... | Edit files in... | Layer |
|--------------|------------------|-------|
| Neo4j client | `packages/data-layer/src/monitor_data/db/neo4j.py` | 1 |
| MongoDB client | `packages/data-layer/src/monitor_data/db/mongodb.py` | 1 |
| Qdrant client | `packages/data-layer/src/monitor_data/db/qdrant.py` | 1 |
| Neo4j MCP tools | `packages/data-layer/src/monitor_data/tools/neo4j_tools.py` | 1 |
| MongoDB MCP tools | `packages/data-layer/src/monitor_data/tools/mongodb_tools.py` | 1 |
| Entity schemas | `packages/data-layer/src/monitor_data/schemas/entities.py` | 1 |
| Fact schemas | `packages/data-layer/src/monitor_data/schemas/facts.py` | 1 |
| Scene schemas | `packages/data-layer/src/monitor_data/schemas/scenes.py` | 1 |
| Authority rules | `packages/data-layer/src/monitor_data/middleware/auth.py` | 1 |
| Orchestrator agent | `packages/agents/src/monitor_agents/orchestrator.py` | 2 |
| Narrator agent | `packages/agents/src/monitor_agents/narrator.py` | 2 |
| CanonKeeper agent | `packages/agents/src/monitor_agents/canonkeeper.py` | 2 |
| Scene loop | `packages/agents/src/monitor_agents/loops/scene_loop.py` | 2 |
| LLM prompts | `packages/agents/src/monitor_agents/prompts/` | 2 |
| Play command | `packages/cli/src/monitor_cli/commands/play.py` | 3 |
| Query command | `packages/cli/src/monitor_cli/commands/query.py` | 3 |
| REPL session | `packages/cli/src/monitor_cli/repl/session.py` | 3 |
| Terminal output | `packages/cli/src/monitor_cli/ui/output.py` | 3 |

### Documentation

| Topic | Read... |
|-------|---------|
| Architecture overview | `ARCHITECTURE.md` |
| Data model | `docs/ontology/ONTOLOGY.md` |
| Database integration | `docs/architecture/DATABASE_INTEGRATION.md` |
| Agent orchestration | `docs/architecture/AGENT_ORCHESTRATION.md` |
| API specification | `docs/architecture/DATA_LAYER_API.md` |
| Quick reference | `docs/AI_DOCS.md` |

---

## Common Tasks

### Adding a new MCP tool

1. Add schema to `packages/data-layer/src/monitor_data/schemas/`
2. Implement tool in `packages/data-layer/src/monitor_data/tools/`
3. Add authority check in middleware
4. Update `docs/architecture/MCP_TRANSPORT.md`

### Adding a new agent capability

1. Implement in `packages/agents/src/monitor_agents/<agent>.py`
2. Agent calls data-layer tools via MCP
3. Update `docs/architecture/AGENT_ORCHESTRATION.md`

### Adding a new CLI command

1. Create command in `packages/cli/src/monitor_cli/commands/`
2. Command calls agents, never data-layer directly
3. Register in `packages/cli/src/monitor_cli/main.py`

---

## Testing

```bash
# Run tests for each layer independently
cd packages/data-layer && pytest
cd packages/agents && pytest
cd packages/cli && pytest
```

---

## Summary

1. **Three layers**: data-layer → agents → cli
2. **Dependencies flow down**: Never import from a higher layer
3. **No skip-layer imports**: CLI never imports data-layer
4. **CanonKeeper writes Neo4j**: All other agents use proposals
5. **Follow existing patterns**: Look at similar code first
