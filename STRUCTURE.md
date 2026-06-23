# MONITOR - Complete Folder Structure

> **This document defines EVERY folder in the monorepo. No exceptions.**

---

## Root Level

```text
<repo-root>/
├── ARCHITECTURE.md      # Layer architecture and dependency rules
├── AGENTS.md            # AI agent instructions
├── STRUCTURE.md         # THIS FILE - folder definitions
├── README.md            # Project overview for humans
├── .gitignore
├── env.example          # Environment template (never commit `.env`)
│
├── docs/                # Canonical documentation and design references
├── infra/               # Docker infrastructure
├── packages/            # Core layers + user-facing surfaces
└── scripts/             # Development utilities
```

---

## docs/ - Canonical Documentation

```
docs/
├── README.md                     # Documentation index and placement rules
├── AI_DOCS.md                    # Quick reference for contributors and AI agents
├── USE_CASES.md                  # Use case catalog index (→ use-cases/)
├── GM_CRAFT.md                   # GM-tone index (→ gm-craft/)
├── FULL_GM_SYSTEM_PLAN.md        # GM implementation plan index (→ gm-plan/)
│
├── use-cases/                    # Use cases split by epic (from USE_CASES.md)
│   ├── epic-0-data-layer.md      # DL-1 to DL-14 (index)
│   ├── epic-1-play.md            # P-1 to P-20 (→ play/)
│   ├── epic-2-manage.md          # M-1 to M-35 (→ manage/)
│   ├── epic-3-query.md           # Q-1 to Q-11 (→ query/)
│   ├── epic-4-ingest.md          # I-1 to I-13 (→ ingest/)
│   ├── epic-11-system.md          # SYS-1 to SYS-12 (→ system/)
│   ├── epic-7-copilot.md        # CF-1 to CF-8 (→ co-pilot/)
│   ├── epic-8-story.md           # ST-1 to ST-8 (→ story/)
│   ├── epic-5-rules.md           # RS-1 to RS-8 (→ rules/)
│   ├── epic-9-docs.md            # DOC-1
│   ├── epic-10-packs.md          # MP-1 to MP-9 (→ packs/)
│   ├── rollout-plan.md           # MVP and phase planning
│   ├── data-layer-details.md     # DL-focused index (→ data-layer/)
│   ├── play/                     # P-1..P-20: 7 thematic files
│   ├── manage/                   # M-1..M-35: 6 thematic files
│   ├── data-layer/               # DL-1..DL-26: 4 thematic files
│   ├── rules/                    # RS-1..RS-8: 3 thematic files
│   ├── story/                    # ST-1..ST-7: 2 thematic files
│   ├── co-pilot/                 # CF-1..CF-8: 2 thematic files
│   ├── query/                    # Q-1..Q-11: 2 thematic files
│   ├── ingest/                   # I-1..I-13: 2 thematic files
│   ├── system/                   # SYS-1..SYS-12: 2 thematic files
│   ├── packs/                    # MP-1..MP-9: 2 thematic files
│   └── */                        # Per-use-case YAML definitions
│
├── gm-plan/                      # GM system plan split by phase
│   ├── index.md
│   ├── phase-a-core-loop.md
│   ├── phase-b-gm-craft.md
│   ├── phase-c-living-world.md
│   ├── phase-d-co-pilot.md
│   ├── phase-e-polish.md
│   └── dependencies-timeline-risks.md
│
├── gm-craft/                     # GM craft analysis split by topic
│   ├── index.md
│   ├── core-problem.md
│   ├── principles.md
│   ├── defects.md
│   ├── use-cases.md
│   └── design-implications.md
│
├── architecture/                 # Current system design documents
│   ├── AGENT_ORCHESTRATION.md    # Agent orchestration index (→ agent-orchestration/)
│   ├── CONVERSATIONAL_LOOPS.md   # Loop/state-machine behavior
│   ├── DATABASE_INTEGRATION.md   # Storage roles and canonization flow
│   ├── DATA_LAYER_API.md         # API index (→ data-layer-api/)
│   ├── MCP_TRANSPORT.md          # MCP transport index (→ mcp-transport/)
│   ├── VALIDATION_SCHEMAS.md     # Validation schemas index (→ validation-schemas/)
│   ├── agent-orchestration/      # Agent specs and coordination
│   ├── data-layer-api/           # API operations by database
│   ├── mcp-transport/            # MCP tool specs by database
│   ├── validation-schemas/       # Pydantic models by database
│   └── ...                       # Additional design plans and audits
│
├── ontology/                     # Data model documents
│   ├── ENTITY_TAXONOMY.md        # EntityArchetype vs EntityInstance
│   ├── ERD_DIAGRAM.md            # Entity-relationship diagrams
│   └── ONTOLOGY.md               # Complete data model
│
├── gameplay-examples/            # Example sessions and reference play patterns
├── use-cases/                    # Structured YAML use-case sources for automation
└── archive/                      # Historical plans, audits, and superseded notes
```

**Rules:**
- Prefer the canonical docs (`SYSTEM.md`, `STRUCTURE.md`, `ARCHITECTURE.md`, `docs/README.md`, `docs/USE_CASES.md`) over duplicated summaries
- Keep documentation aligned with the current repo state when code or structure changes
- Move historical planning snapshots into `docs/archive/` instead of leaving them beside canonical docs
- AI agents should read the relevant canonical docs before coding

---

## infra/ - Infrastructure

```
infra/
├── README.md                     # Infrastructure setup guide
├── docker-compose.yml            # All 6 local data services
│
├── neo4j/                        # Neo4j configuration
│   ├── plugins/                  # APOC, GDS plugins
│   ├── data/                     # Persistent data (gitignored)
│   └── logs/                     # Logs (gitignored)
│
├── mongodb/                      # MongoDB configuration
│   ├── init/                     # Initialization scripts
│   │   └── 01-init.js            # Create collections, indexes
│   └── data/                     # Persistent data (gitignored)
│
├── qdrant/                       # Qdrant configuration
│   └── storage/                  # Persistent data (gitignored)
│
├── minio/                        # MinIO configuration
│   └── data/                     # Persistent data (gitignored)
│
├── postgres/                     # PostgreSQL configuration
│   └── data/                     # Persistent data (gitignored)
│
└── opensearch/                   # OpenSearch configuration
    └── data/                     # Persistent data (gitignored)
```

**Rules:**
- Only infrastructure configuration goes here
- No application code
- Data directories are gitignored

---

## packages/ - Core Layers + User-Facing Surfaces

```text
packages/
├── data-layer/      # LAYER 1 - Bottom (no MONITOR dependencies)
├── agents/          # LAYER 2 - Middle (depends on data-layer)
├── cli/             # LAYER 3 - Top (depends on agents)
└── ui/              # Browser-facing backend/frontend surfaces
```

The architecture rules still revolve around the three core layers: `data-layer → agents → cli`. The `ui/` package provides additional user-facing surfaces and should respect the same boundary model.

---

## packages/data-layer/ - LAYER 1

**Package name:** `monitor-data-layer`
**Import as:** `from monitor_data import ...`
**Dependencies:** External libraries only (neo4j, pymongo, etc.)

```
packages/data-layer/
├── README.md                     # Layer 1 documentation
├── pyproject.toml                # Package definition
│
├── src/
│   └── monitor_data/
│       ├── __init__.py           # Package root, exports
│       ├── server.py             # MCP server entry point
│       ├── config.py             # Environment/connection config
│       ├── health.py             # Database health checks
│       │
│       ├── db/                   # Database clients (6)
│       │   ├── __init__.py
│       │   ├── _utils.py         # Shared client utilities
│       │   ├── neo4j.py          # Neo4jClient class
│       │   ├── mongodb.py        # MongoDBClient class
│       │   ├── qdrant.py         # QdrantClient class
│       │   ├── postgres.py       # PostgreSQL client (LLM config, sessions)
│       │   ├── minio.py          # MinIO / S3 object storage client
│       │   └── embeddings.py     # Embedding client (LiteLLM backend)
│       │
│       ├── tools/                # MCP/tool implementations
│       │   ├── __init__.py
│       │   ├── neo4j_tools/      # Neo4j operations (multiverse, entities, stories, facts)
│       │   │   ├── __init__.py
│       │   │   ├── core.py       # Multiverse/Universe/Source ops
│       │   │   ├── entities.py   # Entity CRUD
│       │   │   ├── relationships.py # Relationship management
│       │   │   ├── stories.py    # Story/PlotThread ops
│       │   │   ├── facts.py      # Fact/Event/Axiom ops
│       │   │   └── parties.py    # Party management
│       │   ├── mongodb_tools.py  # MongoDB narrative/state operations
│       │   ├── qdrant_tools.py   # Qdrant vector search operations
│       │   ├── ingest_tools.py   # Ingestion/runtime helpers (currently auto-registered)
│       │   └── rpg_tools.py      # RPG helper functions (present in repo; not in current auto-discovery)
│       │
│       ├── schemas/              # Pydantic models (35 modules)
│       │   ├── __init__.py
│       │   ├── base.py           # Base models, enums (CanonLevel, Authority, etc.)
│       │   ├── entities.py       # Entity schemas (Archetype, Instance, CRUD)
│       │   ├── facts.py          # Fact, Event, Axiom schemas
│       │   ├── scenes.py         # Scene, Turn schemas
│       │   ├── proposed_changes.py # ProposedChange schemas
│       │   ├── memories.py       # CharacterMemory schemas
│       │   ├── documents.py      # Source, Document schemas
│       │   ├── agent_responses.py # NarratorResponse, CanonKeeperVerdict, etc.
│       │   ├── character_sheets.py
│       │   ├── combat.py
│       │   ├── conversations.py
│       │   ├── game_systems.py
│       │   ├── ingestion_jobs.py
│       │   ├── knowledge_packs.py
│       │   ├── llm_config.py
│       │   ├── parties.py
│       │   ├── relationships.py
│       │   ├── resolutions.py
│       │   ├── stories.py
│       │   ├── story_outlines.py
│       │   ├── working_state.py
│       │   ├── vectors.py
│       │   ├── universe.py
│       │   ├── rpg_ontology/     # RPG ontology sub-schemas
│       │   └── ...               # Additional domain schemas
│       │
│       ├── middleware/           # Request processing
│       │   ├── __init__.py
│       │   ├── auth.py           # Authority enforcement (CanonKeeper matrix)
│       │   ├── validation.py     # Request validation
│       │   └── logging.py        # Audit trails
│       │
│       ├── defaults/             # Built-in game system templates
│       │   └── systems/          # dnd5e.json, vampire.json, etc.
│       │
│       └── utils/                # Shared utilities
│           └── dice.py           # Dice rolling (NdS+/-M syntax)
│
└── tests/
    ├── __init__.py
    ├── conftest.py               # Pytest fixtures
    ├── test_db/                  # Database client tests
    ├── test_tools/               # MCP tool tests
    ├── test_middleware/           # Auth/validation tests
    ├── test_server/              # MCP server tests
    └── test_utils/               # Utility tests (dice, etc.)
```

**What goes here:**
- Database connection and query logic
- MCP tool implementations
- Pydantic schemas for all data types
- Authority/validation middleware

**What does NOT go here:**
- AI/LLM logic (that's agents/)
- User interface code (that's cli/)
- Business logic beyond data access

---

## packages/agents/ - LAYER 2

**Package name:** `monitor-agents`
**Import as:** `from monitor_agents import ...`
**Dependencies:** `monitor-data-layer` + external (anthropic, etc.)

```text
packages/agents/
├── README.md                     # Layer 2 documentation
├── pyproject.toml                # Package definition
│
├── src/
│   └── monitor_agents/
│       ├── __init__.py           # Package root, exports
│       ├── base.py               # BaseAgent abstract class
│       │
│       │  # --- 9 Agents (BaseAgent subclasses) ---
│       ├── context_assembly.py   # Context retrieval (read-only)
│       ├── narrator.py           # Narrative generation + proposal extraction
│       ├── canonkeeper.py        # Neo4j writes (EXCLUSIVE)
│       ├── resolver.py           # Rules/dice resolution
│       ├── indexer.py            # Document chunking + embedding → Qdrant
│       ├── analyzer.py           # Structured knowledge extraction from chunks
│       ├── ingestion_pipeline.py # Document ingestion orchestration
│       ├── world_architect.py    # Conversational world-building partner
│       ├── npc_voice.py          # In-character NPC dialogue (DIRECT/ACTOR)
│       │
│       │  # --- Utilities (not BaseAgent subclasses) ---
│       ├── game_system.py        # GameSystemRuntime — schema-driven rule engine
│       ├── llm_registry.py       # LLM provider/model routing
│       ├── dspy_runtime.py       # DSPy context management
│       │
│       ├── loops/                # 5 LangGraph StateGraph loop state machines
│       │   ├── __init__.py
│       │   ├── scene_loop.py     # Core play loop (checkpointed)
│       │   ├── story_loop.py     # Campaign lifecycle (checkpointed)
│       │   ├── turn_loop.py      # Single user→GM exchange
│       │   ├── conversation_loop.py # NPC dialogue (DIRECT/ACTOR)
│       │   └── world_building_loop.py # Collaborative setting creation
│       │
│       ├── prompts/              # DSPy Signatures & Modules
│       │   ├── __init__.py
│       │   ├── narrator.py       # NarratorModule, ContextAssemblyModule
│       │   ├── canonkeeper.py    # CanonKeeperReasoningModule, PolicyCheckModule
│       │   ├── context_assembly.py # QueryFormulationModule, TurnIntentModule
│       │   ├── analyzer.py       # 7 extraction modules
│       │   ├── npc_voice.py      # NPCDirectVoiceModule, NPCActorModule
│       │   └── world_architect.py # WorldArchitectModule, WorldGapAnalysisModule
│       │
│       └── utils/                # Agent utilities
│           └── __init__.py
│
└── tests/
    ├── __init__.py
    ├── conftest.py               # Pytest fixtures
    ├── test_*.py                 # Agent and loop coverage
    └── ...
```

**What goes here:**
- Agent implementations (9 agents + GameSystemRuntime utility)
- Loop logic (5 LangGraph loops: Story, Scene, Turn, Conversation, WorldBuilding)
- DSPy prompt signatures and modules
- LLM provider routing and runtime wiring

**What does NOT go here:**
- Database access code (use data-layer tools)
- User interface code (that's cli/)
- Raw database queries

---

## packages/cli/ - LAYER 3

**Package name:** `monitor-cli`
**Import as:** `from monitor_cli import ...`
**Dependencies:** `monitor-agents` + external (typer, rich, etc.)

```text
packages/cli/
├── README.md                     # Layer 3 documentation
├── pyproject.toml                # Package definition
│
├── src/
│   └── monitor_cli/
│       ├── __init__.py           # Package root, exports
│       ├── main.py               # Typer app entry point
│       │
│       ├── commands/             # Current command groups
│       │   ├── __init__.py
│       │   ├── ingest.py         # `monitor ingest` - document and URI ingestion
│       │   ├── mechanics.py      # `monitor mechanics` - checks and resolution
│       │   ├── playtest.py       # `monitor playtest` - live autonomous-GM smoke/benchmark runs
│       │   ├── rules.py          # `monitor rules` - game system management
│       │   └── state.py          # `monitor state` - working state management
│       │
│       ├── repl/                 # Interactive REPL (stub)
│       │   └── __init__.py
│       │
│       └── ui/                   # Terminal UI components (stub)
│           └── __init__.py
│
└── tests/
    ├── __init__.py
    ├── conftest.py               # Pytest fixtures
    └── ...
```

**What goes here:**
- CLI command implementations
- Interactive REPL logic
- Terminal UI formatting
- User input handling

**What does NOT go here:**
- Agent logic (use agents package)
- Database access (agents handle that)
- LLM calls (agents handle that)

---

## packages/ui/ - Web UI Surfaces

The UI package provides browser-facing surfaces and sits alongside CLI as a peer user-facing layer. The backend imports from both `monitor_agents` and `monitor_data`.

```text
packages/ui/
├── backend/                      # FastAPI service
│   ├── pyproject.toml
│   └── src/monitor_ui/
│       ├── main.py               # FastAPI app entry (uvicorn)
│       ├── config.py             # Environment settings
│       └── routers/              # 10 mounted API route groups + shared pack helpers
│           ├── chat.py           # WebSocket + session management
│           ├── databases.py      # Database health/status
│           ├── entities.py       # Entity browsing
│           ├── game_systems.py   # Game-system browsing endpoints
│           ├── graph.py          # Neo4j graph queries
│           ├── ingest.py         # Document upload + ingestion (mounts pack review/apply flows)
│           ├── llm_mgmt.py       # LLM provider management
│           ├── modes.py          # System mode selection
│           ├── prompts.py        # Prompt management / prompt testing
│           ├── universes.py      # Universe CRUD
│           └── pack_library.py   # Shared pack-library router/helpers used by ingest flow
│
└── frontend/                     # Next.js app
    ├── package.json
    ├── next.config.ts
    └── src/                      # React components + pages
```

**What goes here:**
- Browser-facing UX and APIs
- Supporting services that sit at the user-facing edge of the stack
- Development surfaces launched by `./dev.sh`

---

## scripts/ - Development Utilities

```text
scripts/
├── monitor                       # Main helper entry point
├── setup_env.sh                  # Local environment bootstrap
├── seed_world.py                 # Seed demo/test data
├── check_layer_dependencies.py   # Architecture guardrail
├── sync_docs_to_wiki.sh          # Documentation publishing helper
└── ...                           # Additional automation and project sync utilities
```

---

## File Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Python modules | snake_case | `neo4j_tools.py` |
| Python classes | PascalCase | `class Neo4jClient:` |
| Python functions | snake_case | `def create_entity():` |
| Constants | UPPER_SNAKE | `AUTHORITY_MATRIX = {}` |
| Test files | `test_*.py` | `test_neo4j_tools.py` |

---

## Import Rules (Enforced)

```python
# LAYER 1: data-layer can only import external packages
from neo4j import GraphDatabase       # ✅ OK
from pydantic import BaseModel        # ✅ OK
from monitor_agents import X          # ❌ FORBIDDEN
from monitor_cli import X             # ❌ FORBIDDEN

# LAYER 2: agents can only import data-layer + external
from monitor_data.tools import X      # ✅ OK
from anthropic import Anthropic       # ✅ OK
from monitor_cli import X             # ❌ FORBIDDEN

# LAYER 3: cli can only import agents + external
from monitor_agents import X          # ✅ OK
from typer import Typer               # ✅ OK
from monitor_data import X            # ❌ FORBIDDEN (skip-layer!)
```

---

## Summary Table

| Folder | Layer | Contains | Imports From |
|--------|-------|----------|--------------|
| `packages/data-layer/` | 1 | DB clients, MCP tools, schemas | External only |
| `packages/agents/` | 2 | 9 agents, 5 loops, prompts | data-layer |
| `packages/cli/` | 3 | Commands, REPL, UI | agents |
| `packages/ui/` | — | FastAPI backend, Next.js frontend | agents + data-layer |
| `docs/` | - | Documentation | N/A |
| `infra/` | - | Docker, DB configs | N/A |
| `scripts/` | - | Dev utilities | N/A |
