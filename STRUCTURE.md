# MONITOR - Complete Folder Structure

> **This document defines EVERY folder in the monorepo. No exceptions.**

---

## Root Level

```
monitor2/
├── ARCHITECTURE.md      # Layer architecture and dependency rules
├── CLAUDE.md            # AI agent instructions
├── STRUCTURE.md         # THIS FILE - folder definitions
├── README.md            # Project overview for humans
├── .gitignore
├── .env.example         # Environment template (never commit .env)
│
├── docs/                # Documentation (read-only reference)
├── infra/               # Docker infrastructure
├── packages/            # THE THREE CODE LAYERS
└── scripts/             # Development utilities
```

---

## docs/ - Documentation (Reference Only)

```
docs/
├── AI_DOCS.md                    # Quick reference for AI agents
├── USE_CASES.md                  # Complete use case catalog (READ THIS!)
├── IMPLEMENTATION_GUIDE.md       # Step-by-step implementation
│
├── architecture/                 # System design documents
│   ├── AGENT_ORCHESTRATION.md    # 7 agents, roles, coordination
│   ├── CONVERSATIONAL_LOOPS.md   # 4 nested loops (Main/Story/Scene/Turn)
│   ├── DATABASE_INTEGRATION.md   # 5 databases, canonization
│   ├── DATA_LAYER_API.md         # 64+ API operations
│   ├── MCP_TRANSPORT.md          # MCP tool specifications
│   └── VALIDATION_SCHEMAS.md     # Pydantic model definitions
│
└── ontology/                     # Data model documents
    ├── ENTITY_TAXONOMY.md        # EntityArchetype vs EntityInstance
    ├── ERD_DIAGRAM.md            # Entity-relationship diagrams
    └── ONTOLOGY.md               # Complete data model
```

**Rules:**
- Documentation is READ-ONLY reference
- Code changes may require doc updates
- AI agents should read relevant docs before coding

---

## infra/ - Infrastructure

```
infra/
├── README.md                     # Infrastructure setup guide
├── docker-compose.yml            # All 5 database services
├── .env.example                  # Environment template
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
└── opensearch/                   # OpenSearch configuration
    └── data/                     # Persistent data (gitignored)
```

**Rules:**
- Only infrastructure configuration goes here
- No application code
- Data directories are gitignored

---

## packages/ - The Three Layers

```
packages/
├── data-layer/      # LAYER 1 - Bottom (no MONITOR dependencies)
├── agents/          # LAYER 2 - Middle (depends on data-layer)
└── cli/             # LAYER 3 - Top (depends on agents)
```

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
│       │
│       ├── db/                   # Database clients
│       │   ├── __init__.py
│       │   ├── neo4j.py          # Neo4jClient class
│       │   ├── mongodb.py        # MongoDBClient class
│       │   ├── qdrant.py         # QdrantClient class
│       │   ├── minio.py          # MinIOClient class
│       │   └── opensearch.py     # OpenSearchClient class
│       │
│       ├── tools/                # MCP tool implementations
│       │   ├── __init__.py
│       │   ├── neo4j_tools.py    # 41 Neo4j operations
│       │   ├── mongodb_tools.py  # 18 MongoDB operations
│       │   ├── qdrant_tools.py   # 3 Qdrant operations
│       │   └── composite_tools.py # 2 composite operations
│       │
│       ├── schemas/              # Pydantic models
│       │   ├── __init__.py
│       │   ├── base.py           # Base models, enums
│       │   ├── entities.py       # Entity schemas
│       │   ├── facts.py          # Fact, Event schemas
│       │   ├── scenes.py         # Scene, Turn schemas
│       │   ├── proposals.py      # ProposedChange schemas
│       │   ├── memories.py       # CharacterMemory schemas
│       │   ├── sources.py        # Source, Document schemas
│       │   └── queries.py        # Query/filter schemas
│       │
│       └── middleware/           # Request processing
│           ├── __init__.py
│           ├── auth.py           # Authority enforcement
│           └── validation.py     # Request validation
│
└── tests/
    ├── __init__.py
    ├── conftest.py               # Pytest fixtures
    ├── test_db/                  # Database client tests
    ├── test_tools/               # MCP tool tests
    └── test_schemas/             # Schema validation tests
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

```
packages/agents/
├── README.md                     # Layer 2 documentation
├── pyproject.toml                # Package definition
│
├── src/
│   └── monitor_agents/
│       ├── __init__.py           # Package root, exports
│       ├── base.py               # BaseAgent class
│       │
│       ├── orchestrator.py       # Loop controller
│       ├── context_assembly.py   # Context retrieval (read-only)
│       ├── narrator.py           # Narrative generation
│       ├── resolver.py           # Rules/dice resolution
│       ├── canonkeeper.py        # Neo4j writes (EXCLUSIVE)
│       ├── memory_manager.py     # Character memories
│       ├── indexer.py            # Background indexing
│       │
│       ├── loops/                # Loop implementations
│       │   ├── __init__.py
│       │   ├── main_loop.py      # Main menu loop
│       │   ├── story_loop.py     # Story/campaign loop
│       │   ├── scene_loop.py     # Scene loop
│       │   └── turn_loop.py      # Turn loop
│       │
│       ├── prompts/              # LLM prompt templates
│       │   ├── __init__.py
│       │   ├── narrator.py       # Narrator prompts
│       │   ├── resolver.py       # Resolver prompts
│       │   └── canonkeeper.py    # CanonKeeper prompts
│       │
│       └── utils/                # Agent utilities
│           ├── __init__.py
│           ├── context.py        # Context building
│           └── parsing.py        # Response parsing
│
└── tests/
    ├── __init__.py
    ├── conftest.py               # Pytest fixtures
    ├── test_orchestrator.py
    ├── test_narrator.py
    ├── test_canonkeeper.py
    └── test_loops/
```

**What goes here:**
- Agent implementations (the 7 agents)
- Loop logic (Main, Story, Scene, Turn)
- LLM prompt templates
- Agent coordination logic

**What does NOT go here:**
- Database access code (use data-layer tools)
- User interface code (that's cli/)
- Raw database queries

---

## packages/cli/ - LAYER 3

**Package name:** `monitor-cli`
**Import as:** `from monitor_cli import ...`
**Dependencies:** `monitor-agents` + external (typer, rich, etc.)

```
packages/cli/
├── README.md                     # Layer 3 documentation
├── pyproject.toml                # Package definition
│
├── src/
│   └── monitor_cli/
│       ├── __init__.py           # Package root, exports
│       ├── main.py               # Typer app entry point
│       │
│       ├── commands/             # CLI commands (7 command groups)
│       │   ├── __init__.py
│       │   ├── play.py           # `monitor play` - P- use cases (Solo Play mode)
│       │   ├── manage.py         # `monitor manage` - M- use cases (World Design mode)
│       │   ├── query.py          # `monitor query` - Q- use cases
│       │   ├── ingest.py         # `monitor ingest` - I- use cases
│       │   ├── copilot.py        # `monitor copilot` - CF- use cases (GM Assistant mode)
│       │   ├── story.py          # `monitor story` - ST- use cases (Planning)
│       │   └── rules.py          # `monitor rules` - RS- use cases (Game Systems)
│       │
│       ├── repl/                 # Interactive REPL
│       │   ├── __init__.py
│       │   ├── session.py        # REPL session management
│       │   └── handlers.py       # Input handlers
│       │
│       └── ui/                   # Terminal UI components
│           ├── __init__.py
│           ├── output.py         # Rich output formatting
│           ├── prompts.py        # User prompts
│           └── tables.py         # Table displays
│
└── tests/
    ├── __init__.py
    ├── conftest.py               # Pytest fixtures
    ├── test_commands/
    └── test_repl/
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

## scripts/ - Development Utilities

```
scripts/
├── dev-setup.sh                  # Install all packages for dev
├── run-tests.sh                  # Run all tests
├── lint.sh                       # Run linters
└── start-infra.sh                # Start Docker services
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
| `packages/agents/` | 2 | 7 agents, loops, prompts | data-layer |
| `packages/cli/` | 3 | Commands, REPL, UI | agents |
| `docs/` | - | Documentation | N/A |
| `infra/` | - | Docker, DB configs | N/A |
| `scripts/` | - | Dev utilities | N/A |
