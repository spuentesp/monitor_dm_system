# MONITOR Agents Layer (Layer 2 of 3)

> **This is the MIDDLE layer. It depends ONLY on data-layer (Layer 1).**

---

## What This Package Does

- Implements the 7 stateless AI agents
- Manages the 4 conversational loops (Main, Story, Scene, Turn)
- Handles LLM interactions via Anthropic Claude
- Coordinates agent communication

---

## The 7 Agents

| Agent | File | Responsibility | Neo4j Write? |
|-------|------|----------------|--------------|
| Orchestrator | `orchestrator.py` | Loop controller | No* |
| ContextAssembly | `context_assembly.py` | Context retrieval | No |
| Narrator | `narrator.py` | Narrative generation | No |
| Resolver | `resolver.py` | Rules/dice resolution | No |
| **CanonKeeper** | `canonkeeper.py` | Canonization | **YES** |
| MemoryManager | `memory_manager.py` | Character memories | No |
| Indexer | `indexer.py` | Background indexing | No |

*Orchestrator can only create Story nodes

---

## Folder Structure

```
src/monitor_agents/
├── __init__.py           # Package root
├── base.py               # BaseAgent class
│
├── orchestrator.py       # Loop controller
├── context_assembly.py   # Context retrieval (read-only)
├── narrator.py           # Narrative generation
├── resolver.py           # Rules/dice resolution
├── canonkeeper.py        # Neo4j writes (EXCLUSIVE)
├── memory_manager.py     # Character memories
├── indexer.py            # Background indexing
│
├── loops/                # Loop implementations
│   ├── main_loop.py      # Main menu loop
│   ├── story_loop.py     # Story/campaign loop
│   ├── scene_loop.py     # Scene loop
│   └── turn_loop.py      # Turn loop
│
├── prompts/              # LLM prompt templates
│   ├── narrator.py       # Narrator prompts
│   ├── resolver.py       # Resolver prompts
│   └── canonkeeper.py    # CanonKeeper prompts
│
└── utils/                # Agent utilities
    ├── context.py        # Context building
    └── parsing.py        # Response parsing
```

---

## Dependency Rules

```python
# ✅ ALLOWED imports in this package:
from monitor_data.tools import neo4j_create_fact
from monitor_data.schemas import EntityCreate
from anthropic import Anthropic
import structlog

# ❌ FORBIDDEN imports in this package:
from monitor_cli import ...      # NEVER import Layer 3
```

---

## Who Calls This Package

Only `packages/cli/` (Layer 3) imports from this package.

```python
# In packages/cli/src/monitor_cli/commands/play.py
from monitor_agents import Orchestrator  # ✅ Correct
```

---

## Critical Rule: CanonKeeper

**Only CanonKeeper can write to Neo4j.**

All other agents that need to change canonical state must:
1. Create a `ProposedChange` document in MongoDB
2. Wait for CanonKeeper to evaluate at scene end
3. CanonKeeper commits accepted proposals to Neo4j

```python
# In narrator.py - CORRECT approach
async def handle_action(self, action: str):
    # Create proposal, don't write to Neo4j directly
    await self.call_tool("mongodb_create_proposal", {
        "type": "state_change",
        "content": {"entity_id": "...", "tag": "wounded"}
    })

# WRONG - Narrator should never do this
async def handle_action(self, action: str):
    await self.call_tool("neo4j_update_entity", {...})  # ❌ FORBIDDEN
```

---

## Key Files to Implement

1. `base.py` - BaseAgent with tool calling
2. `orchestrator.py` - Loop management (see docs/architecture/CONVERSATIONAL_LOOPS.md)
3. `canonkeeper.py` - Canonization logic (see docs/architecture/AGENT_ORCHESTRATION.md)
4. `loops/scene_loop.py` - Scene loop implementation

---

## Running

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
pytest
```
