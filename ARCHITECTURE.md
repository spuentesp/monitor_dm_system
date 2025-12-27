# MONITOR Architecture

> **READ THIS FIRST** - This document defines the monorepo structure and layer rules.

---

## Monorepo Structure

```
monitor2/
├── ARCHITECTURE.md          ← YOU ARE HERE (read first!)
├── README.md                # Project overview
├── CLAUDE.md                # AI agent instructions
│
├── docs/                    # Documentation
│   ├── architecture/        # System design
│   ├── ontology/            # Data model
│   └── AI_DOCS.md           # Quick reference for AI agents
│
├── infra/                   # Infrastructure
│   ├── docker-compose.yml   # All 5 databases
│   └── README.md
│
├── packages/                # THE THREE LAYERS
│   ├── data-layer/          # Layer 1: MCP Server + DB clients
│   ├── agents/              # Layer 2: AI Agents
│   └── cli/                 # Layer 3: User Interface
│
└── scripts/                 # Dev utilities
```

---

## The Three Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     LAYER 3: CLI                             │
│  packages/cli/                                               │
│  - User-facing commands (play, ingest, query, manage)        │
│  - Interactive REPL                                          │
│  - Depends on: Layer 2 ONLY                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ imports
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 2: AGENTS                           │
│  packages/agents/                                            │
│  - 7 stateless AI agents                                     │
│  - Loop management (Main, Story, Scene, Turn)                │
│  - LLM interactions                                          │
│  - Depends on: Layer 1 ONLY                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ imports
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   LAYER 1: DATA-LAYER                        │
│  packages/data-layer/                                        │
│  - MCP server                                                │
│  - Database clients (Neo4j, MongoDB, Qdrant, MinIO)          │
│  - Pydantic schemas                                          │
│  - Authority enforcement                                     │
│  - Depends on: External libraries + databases ONLY           │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ connects to
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      DATABASES                               │
│  Neo4j │ MongoDB │ Qdrant │ MinIO │ OpenSearch              │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer Rules (CRITICAL)

### Rule 1: Dependencies Flow Downward Only

```
✅ ALLOWED:
   cli → agents → data-layer → external

❌ FORBIDDEN:
   data-layer → agents (Layer 1 cannot import Layer 2)
   data-layer → cli    (Layer 1 cannot import Layer 3)
   agents → cli        (Layer 2 cannot import Layer 3)
```

### Rule 2: Skip-Layer Imports Are Forbidden

```
❌ FORBIDDEN:
   cli → data-layer   (Layer 3 cannot bypass Layer 2)

✅ REQUIRED:
   cli → agents → data-layer
```

### Rule 3: Each Layer Has Its Own pyproject.toml

```
packages/
├── data-layer/pyproject.toml   # No MONITOR dependencies
├── agents/pyproject.toml       # Depends on: monitor-data-layer
└── cli/pyproject.toml          # Depends on: monitor-agents
```

---

## Why This Architecture?

| Benefit | Explanation |
|---------|-------------|
| **Clear boundaries** | Each layer has explicit responsibilities |
| **Testable** | Each layer can be tested in isolation |
| **Replaceable** | CLI can be swapped for web UI without changing agents |
| **Authority enforcement** | Data layer enforces who can write what |
| **Scalable** | Agents can be distributed without architecture changes |

---

## Package Details

### Layer 1: data-layer (`packages/data-layer/`)

**Package name:** `monitor-data-layer`

**Responsibilities:**
- Database clients (Neo4j, MongoDB, Qdrant, MinIO, OpenSearch)
- MCP server exposing tools for agents
- Pydantic schemas for all data models
- Authority middleware (who can call what)

**Key modules:**
```
src/monitor_data/
├── server.py          # MCP server entry point
├── db/                # Database clients
├── tools/             # MCP tool implementations
├── schemas/           # Pydantic models
└── middleware/        # Auth + validation
```

---

### Layer 2: agents (`packages/agents/`)

**Package name:** `monitor-agents`

**Responsibilities:**
- 7 stateless AI agents
- Loop controllers (Main, Story, Scene, Turn)
- LLM prompt construction and parsing
- Agent coordination

**The 7 Agents:**
| Agent | Primary Responsibility | Neo4j Write? |
|-------|------------------------|--------------|
| Orchestrator | Loop management | No* |
| ContextAssembly | Context retrieval | No |
| Narrator | Narrative generation | No |
| Resolver | Rules/dice resolution | No |
| **CanonKeeper** | Canonization | **YES** |
| MemoryManager | Character memories | No |
| Indexer | Background indexing | No |

*Orchestrator can create Story nodes only

**Key modules:**
```
src/monitor_agents/
├── base.py            # BaseAgent class
├── orchestrator.py    # Loop controller
├── narrator.py        # Narrative generation
├── canonkeeper.py     # Neo4j writes (exclusive)
├── resolver.py        # Rules resolution
├── context_assembly.py
├── memory_manager.py
└── indexer.py
```

---

### Layer 3: cli (`packages/cli/`)

**Package name:** `monitor-cli`

**Responsibilities:**
- User-facing CLI commands
- Interactive REPL for gameplay
- Output formatting (rich terminal UI)
- User input handling

**Commands:**
```bash
monitor play      # Start/continue story
monitor ingest    # Upload documents
monitor query     # Query canon
monitor manage    # Entity management
```

**Key modules:**
```
src/monitor_cli/
├── main.py            # Typer app entry
├── commands/          # Command implementations
│   ├── play.py
│   ├── ingest.py
│   ├── query.py
│   └── manage.py
└── repl.py            # Interactive REPL
```

---

## Development Workflow

### Install for development

```bash
# Install each layer in editable mode
cd packages/data-layer && pip install -e ".[dev]"
cd packages/agents && pip install -e ".[dev]"
cd packages/cli && pip install -e ".[dev]"
```

### Run tests

```bash
# Test each layer independently
cd packages/data-layer && pytest
cd packages/agents && pytest
cd packages/cli && pytest
```

### Start services

```bash
# Start databases
cd infra && docker compose up -d

# Start MCP server
monitor-data

# Run CLI
monitor play
```

---

## For AI Agents

If you are an AI agent working on this codebase:

1. **Read `CLAUDE.md`** for specific instructions
2. **Read `docs/AI_DOCS.md`** for quick reference
3. **Respect layer boundaries** - never import upward
4. **Check authority** - only CanonKeeper writes to Neo4j
5. **Follow existing patterns** - look at similar code first

**When adding new code, ask:**
- Which layer does this belong to?
- Does it respect the dependency rules?
- Does it follow the existing patterns?

---

## References

- **Data model:** `docs/ontology/ONTOLOGY.md`
- **Database integration:** `docs/architecture/DATABASE_INTEGRATION.md`
- **Agent orchestration:** `docs/architecture/AGENT_ORCHESTRATION.md`
- **API specification:** `docs/architecture/DATA_LAYER_API.md`
- **Implementation guide:** `docs/IMPLEMENTATION_GUIDE.md`
