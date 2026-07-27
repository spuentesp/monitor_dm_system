# MONITOR Agents Layer (Layer 2 of 3)

> **This is the MIDDLE layer. It depends ONLY on data-layer (Layer 1).**

---

## What This Package Does

- Implements 9 stateless AI agents + 1 logic engine utility
- Manages 4 LangGraph loop state machines (Story, Scene, Conversation, WorldBuilding)
- Handles LLM interactions via DSPy + instructor (provider-flexible)
- Coordinates agent communication through shared data stores

---

## The 10 Agent Classes

| Agent | File | Responsibility | Neo4j Write? | LLM? |
|-------|------|----------------|--------------|------|
| ContextAssembly | `context_assembly.py` | Context retrieval & ranking | No (read-only) | DSPy |
| Narrator | `narrator.py` | Narrative generation + proposal extraction | No | DSPy + instructor |
| Resolver | `resolver.py` | Rules/dice resolution | No | No (rule engine) |
| **CanonKeeper** | `canonkeeper.py` | Canonization & policy enforcement | **YES (exclusive)** | DSPy + instructor |
| Indexer | `indexer.py` | Document chunking + embedding → Qdrant | No | Vision LLM (images) |
| Analyzer | `analyzer.py` | Structured knowledge extraction from chunks | No | DSPy (6 modules) |
| IngestionPipeline | `ingestion_pipeline.py` | Full file ingest orchestration | Neo4j (Source node only) | No |
| WorldArchitect | `world_architect.py` | Conversational world creation | Via CanonKeeper auto-accept | DSPy |
| NPCVoice | `npc_voice.py` | In-character NPC dialogue (DIRECT/ACTOR) | No | DSPy + instructor |
| GameSystemRuntime | `game_system.py` | Schema-driven rules engine (utility, not BaseAgent) | No | No (pure logic) |

> **Note:** There is no monolithic Orchestrator. Loop orchestration is handled by LangGraph `StateGraph` state machines in `loops/`.

---

## Folder Structure

```text
src/monitor_agents/
├── __init__.py           # Package root
├── base.py               # BaseAgent abstract class
│
│  # --- Agents (BaseAgent subclasses) ---
├── context_assembly/     # Context retrieval (read-only)
├── narrator/             # Narrative generation + proposal extraction
├── canonkeeper/          # Neo4j writes (EXCLUSIVE)
├── resolver.py           # Rules/dice resolution
├── indexer/              # Document chunking + embedding → Qdrant
├── analyzer/             # Structured knowledge extraction from chunks
├── ingestion/            # Ingest orchestration
├── world_architect/      # Conversational world-building partner
├── npc_voice/            # In-character NPC dialogue (DIRECT/ACTOR)
├── extraction/           # Extraction agents for facts, memory, entities
├── story/                # Story Agent
│
│  # --- Utilities ---
├── game_system/          # GameSystemRuntime — schema-driven rule engine
├── llm_registry.py       # LLM provider/model routing
├── dspy_runtime.py       # DSPy context management
│
├── loops/                # 4 LangGraph StateGraph loop state machines
│   ├── scene_loop.py     # Core play loop (checkpointed)
│   ├── story_loop.py     # Campaign lifecycle (checkpointed)
│   ├── conversation_loop.py # NPC dialogue (DIRECT/ACTOR)
│   └── world_building_loop.py # Collaborative setting creation
│
├── services/             # Persistence and retrieval services
│
└── utils/                # Agent utilities
    └── __init__.py
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
# In packages/cli/src/monitor_cli/commands/state.py
from monitor_agents.resolver import Resolver  # ✅ Correct
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

## Key Modules

1. `base.py` - BaseAgent with tool calling
2. `resolver.py` - Rules and mechanics resolution
3. `canonkeeper.py` - Canonization logic (see `docs/architecture/AGENT_ORCHESTRATION.md`)
4. `ingestion_pipeline.py` - Source ingestion orchestration
5. `loops/scene_loop.py` - Scene loop implementation

---

## Running

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
pytest
```
