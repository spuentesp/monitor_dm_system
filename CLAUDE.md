# MONITOR - AI Agent Instructions

> **You are working on MONITOR, a persistent narrative AI system for RPGs with a strict layered architecture.**

---

## Before You Do Anything

1. **Read `SYSTEM.md`** - Product vision and epics (START HERE)
2. **Read `STRUCTURE.md`** - Complete folder definitions
3. **Read `ARCHITECTURE.md`** - Layer architecture and rules
4. **Identify which layer** your changes belong to
5. **Respect layer boundaries** - Dependencies flow downward ONLY

---

## Key Documents (Read Order)

| Order | Document | What It Contains |
|-------|----------|------------------|
| 1 | `SYSTEM.md` | Product vision, epics, objectives, system modes |
| 2 | `STRUCTURE.md` | Every folder defined, what goes where |
| 3 | `ARCHITECTURE.md` | Layer rules, dependency diagram |
| 4 | `docs/USE_CASES.md` | All 96 use cases (P-, M-, Q-, I-, SYS-, CF-, ST-, RS-, DL-) |
| 5 | `packages/*/README.md` | Layer-specific instructions |
| 6 | `docs/AI_DOCS.md` | Quick reference for implementation |
| 7 | `docs/architecture/AGENT_ORCHESTRATION.md` | 7 agents, coordination, loops |
| 8 | `docs/architecture/DATA_LAYER_API.md` | 64+ MCP tool specifications |
| 9 | `docs/ontology/ONTOLOGY.md` | Complete data model |

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
# File: packages/data-layer/src/monitor_data/tools/neo4j_tools/core.py
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
3. CanonKeeper evaluates and commits at scene end (scene-level canonization, never per-turn)

**Exception**: Orchestrator can write Story nodes only.

---

## 8 Critical Invariants

1. **CanonKeeper exclusivity** - Only CanonKeeper writes to Neo4j (Orchestrator for Story nodes only)
2. **Evidence required** - All canonical facts must reference a source (evidence_refs field)
3. **Scene-level canonization** - ProposedChanges batch and commit at scene end, not per-turn
4. **State tags on instances only** - EntityArchetype is timeless; EntityInstance has state_tags
5. **Entities never deleted** - Mark as `retconned: true` instead of deleting
6. **UUID primary keys** - Neo4j nodes use UUIDs; never reference external DB primary keys
7. **Dependency direction** - cli → agents → data-layer → external (never reversed, never skipped)
8. **Agents call data-layer via MCP** - Agents never instantiate DB clients directly

---

## The 7 Agents

| Agent | File | Responsibility | Can Write Neo4j? |
|-------|------|----------------|-----------------|
| **Orchestrator** | `orchestrator.py` | Loop management, session lifecycle | Story nodes only |
| **ContextAssembly** | `context_assembly.py` | Context retrieval, read-only queries | No |
| **Narrator** | `narrator.py` | Narrative prose generation | No |
| **Resolver** | `resolver.py` | Rules/dice resolution, skill checks | No |
| **CanonKeeper** | `canonkeeper.py` | Canonization, evaluates ProposedChanges | **YES (exclusive)** |
| **MemoryManager** | `memory_manager.py` | Character and NPC memory management | No |
| **Indexer** | `indexer.py` | Background embedding/indexing | No |

All agents extend `BaseAgent` from `packages/agents/src/monitor_agents/base.py`.

---

## The 4 Nested Loops

```
MainLoop  (packages/agents/src/monitor_agents/loops/main_loop.py)
  └── StoryLoop  (loops/story_loop.py)  - per story arc
        └── SceneLoop  (loops/scene_loop.py)  - per scene
              └── TurnLoop  (loops/turn_loop.py)  - per player action
```

Each loop level has its own lifecycle (start/tick/end). Scene end triggers CanonKeeper canonization.

---

## The 5 Databases

| Database | Role | Authoritative For |
|----------|------|-------------------|
| **Neo4j** | Canonical knowledge graph | Entities, facts, events, relationships, stories |
| **MongoDB** | Narrative documents | Scenes, turns, proposals, memories, outlines |
| **Qdrant** | Vector search | Semantic similarity (1536 dims, OpenAI embeddings) |
| **MinIO** | Object storage | PDFs, images, raw ingested files |
| **OpenSearch** | Full-text search | Keyword queries (optional) |

Database clients live in `packages/data-layer/src/monitor_data/db/`.

---

## The 4 System Modes

| Mode | CLI Commands | Description |
|------|-------------|-------------|
| **Solo Play** | `monitor play` | AI-driven GM runs the full session |
| **Assisted GM** | `monitor copilot` | Human GM gets AI suggestions |
| **World Design** | `monitor manage` | Administer entities, facts, universe |
| **Post-Session Analysis** | `monitor story` | Arc planning, faction modeling |

---

## Use Case Prefixes

| Prefix | Count | Domain |
|--------|-------|--------|
| `DL-` | 14 | Data Layer Access (DB operations) |
| `P-` | 12 | Play (core gameplay loop) |
| `M-` | 30 | Manage (world administration) |
| `Q-` | 9 | Query (canon exploration) |
| `I-` | 6 | Ingest (document import/extraction) |
| `SYS-` | 10 | System (lifecycle, config, session) |
| `CF-` | 5 | Co-Pilot (human GM assistant) |
| `ST-` | 5 | Story (planning, meta-narrative) |
| `RS-` | 4 | Rules (game system definition) |
| `DOC-` | 1 | Documentation publishing |

Full catalog: `docs/USE_CASES.md` (206k bytes). Data-layer specifics: `docs/DATA_LAYER_USE_CASES.md`.

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
- Pydantic v2 models for all schemas
- `async/await` throughout (all agents and tools are async)
- `structlog` for logging (not stdlib `logging`)

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
| MinIO client | `packages/data-layer/src/monitor_data/db/minio.py` | 1 |
| OpenSearch client | `packages/data-layer/src/monitor_data/db/opensearch.py` | 1 |
| Neo4j MCP tools | `packages/data-layer/src/monitor_data/tools/neo4j_tools/` | 1 |
| MongoDB MCP tools | `packages/data-layer/src/monitor_data/tools/mongodb_tools.py` | 1 |
| Qdrant MCP tools | `packages/data-layer/src/monitor_data/tools/qdrant_tools.py` | 1 |
| Composite tools | `packages/data-layer/src/monitor_data/tools/composite_tools.py` | 1 |
| MCP server entry | `packages/data-layer/src/monitor_data/server.py` | 1 |
| Entity schemas | `packages/data-layer/src/monitor_data/schemas/entities.py` | 1 |
| Fact schemas | `packages/data-layer/src/monitor_data/schemas/facts.py` | 1 |
| Scene schemas | `packages/data-layer/src/monitor_data/schemas/scenes.py` | 1 |
| Universe schemas | `packages/data-layer/src/monitor_data/schemas/universe.py` | 1 |
| Story schemas | `packages/data-layer/src/monitor_data/schemas/stories.py` | 1 |
| ProposedChange schema | `packages/data-layer/src/monitor_data/schemas/proposed_changes.py` | 1 |
| Authority rules | `packages/data-layer/src/monitor_data/middleware/auth.py` | 1 |
| Base agent | `packages/agents/src/monitor_agents/base.py` | 2 |
| Orchestrator agent | `packages/agents/src/monitor_agents/orchestrator.py` | 2 |
| Narrator agent | `packages/agents/src/monitor_agents/narrator.py` | 2 |
| CanonKeeper agent | `packages/agents/src/monitor_agents/canonkeeper.py` | 2 |
| Resolver agent | `packages/agents/src/monitor_agents/resolver.py` | 2 |
| ContextAssembly agent | `packages/agents/src/monitor_agents/context_assembly.py` | 2 |
| MemoryManager agent | `packages/agents/src/monitor_agents/memory_manager.py` | 2 |
| Indexer agent | `packages/agents/src/monitor_agents/indexer.py` | 2 |
| Main loop | `packages/agents/src/monitor_agents/loops/main_loop.py` | 2 |
| Story loop | `packages/agents/src/monitor_agents/loops/story_loop.py` | 2 |
| Scene loop | `packages/agents/src/monitor_agents/loops/scene_loop.py` | 2 |
| Turn loop | `packages/agents/src/monitor_agents/loops/turn_loop.py` | 2 |
| LLM prompts | `packages/agents/src/monitor_agents/prompts/` | 2 |
| Play command | `packages/cli/src/monitor_cli/commands/play.py` | 3 |
| Query command | `packages/cli/src/monitor_cli/commands/query.py` | 3 |
| Manage command | `packages/cli/src/monitor_cli/commands/manage.py` | 3 |
| Ingest command | `packages/cli/src/monitor_cli/commands/ingest.py` | 3 |
| Copilot command | `packages/cli/src/monitor_cli/commands/copilot.py` | 3 |
| Story command | `packages/cli/src/monitor_cli/commands/story.py` | 3 |
| Rules command | `packages/cli/src/monitor_cli/commands/rules.py` | 3 |
| REPL session | `packages/cli/src/monitor_cli/repl/session.py` | 3 |
| Terminal output | `packages/cli/src/monitor_cli/ui/output.py` | 3 |
| CLI entry point | `packages/cli/src/monitor_cli/main.py` | 3 |

### Documentation

| Topic | Read... |
|-------|---------|
| Product vision & epics | `SYSTEM.md` |
| Complete use case catalog | `docs/USE_CASES.md` |
| Data-layer use cases (DL-1..DL-14) | `docs/DATA_LAYER_USE_CASES.md` |
| Architecture overview | `ARCHITECTURE.md` |
| Data model | `docs/ontology/ONTOLOGY.md` |
| Entity taxonomy | `docs/ontology/ENTITY_TAXONOMY.md` |
| Entity-relationship diagrams | `docs/ontology/ERD_DIAGRAM.md` |
| Database integration | `docs/architecture/DATABASE_INTEGRATION.md` |
| Agent orchestration | `docs/architecture/AGENT_ORCHESTRATION.md` |
| Conversation loops | `docs/architecture/CONVERSATIONAL_LOOPS.md` |
| MCP tool specifications | `docs/architecture/MCP_TRANSPORT.md` |
| API specification (64+ ops) | `docs/architecture/DATA_LAYER_API.md` |
| Pydantic validation schemas | `docs/architecture/VALIDATION_SCHEMAS.md` |
| Quick reference | `docs/AI_DOCS.md` |
| Implementation guide | `docs/IMPLEMENTATION_GUIDE.md` |
| Current implementation status | `docs/IMPLEMENTATION_STATUS.md` |

---

## Common Tasks

### Adding a new MCP tool

1. Add Pydantic schema to `packages/data-layer/src/monitor_data/schemas/`
2. Implement tool in `packages/data-layer/src/monitor_data/tools/` (use the correct sub-module)
3. Add authority check in `packages/data-layer/src/monitor_data/middleware/auth.py`
4. Register the tool in `packages/data-layer/src/monitor_data/server.py`
5. Update `docs/architecture/MCP_TRANSPORT.md`

### Adding a new agent capability

1. Implement in `packages/agents/src/monitor_agents/<agent>.py`
2. Agent calls data-layer tools via MCP (never instantiate DB clients directly)
3. If writes are needed, create ProposedChange docs → route through CanonKeeper
4. Update `docs/architecture/AGENT_ORCHESTRATION.md`

### Adding a new CLI command

1. Create command in `packages/cli/src/monitor_cli/commands/`
2. Command calls agents, never data-layer directly
3. Register in `packages/cli/src/monitor_cli/main.py`
4. Map to matching use case prefix (P-, M-, Q-, etc.)

### Adding a new schema

1. Create Pydantic v2 model in `packages/data-layer/src/monitor_data/schemas/<domain>.py`
2. All UUIDs as `uuid.UUID`, all datetimes as `datetime` with timezone
3. Entities use `EntityArchetype` + `EntityInstance` two-tier pattern
4. Export from `packages/data-layer/src/monitor_data/schemas/__init__.py`

---

## Infrastructure

### Start databases

```bash
cd infra && docker compose up -d
```

### Stop databases

```bash
cd infra && docker compose down
```

### Services and ports

| Service | Port | Admin UI |
|---------|------|----------|
| Neo4j | 7687 (bolt), 7474 (HTTP) | http://localhost:7474 |
| MongoDB | 27017 | - |
| Qdrant | 6333 | http://localhost:6333/dashboard |
| MinIO | 9000 (API), 9001 (console) | http://localhost:9001 |
| OpenSearch | 9200 | - |

### Environment setup

```bash
cp .env.example .env
# Fill in credentials, API keys (Anthropic, OpenAI), DB URIs
```

Required env vars: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `MONGODB_URI`, `MONGODB_DATABASE`, `QDRANT_HOST`, `QDRANT_PORT`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.

---

## Testing

```bash
# Run tests for each layer independently
cd packages/data-layer && pytest
cd packages/agents && pytest
cd packages/cli && pytest

# Test markers (pytest.ini)
pytest -m unit           # Fast, isolated tests (always run)
pytest -m integration    # Cross-component (requires RUN_INTEGRATION=1)
pytest -m e2e            # End-to-end (requires RUN_E2E=1)

# Run integration tests
RUN_INTEGRATION=1 pytest -m integration
```

Tests live in `tests/` subdirectories within each package. Shared fixtures in root `tests/conftest.py`.

---

## Code Quality

Pre-commit hooks are configured in `.pre-commit-config.yaml`. Tools used per layer:

```bash
# Format
black packages/

# Lint
ruff check packages/

# Type check
mypy packages/

# All at once via pre-commit
pre-commit run --all-files
```

Python 3.11 required (see `.python-version`).

---

## CI/CD Workflows

| Workflow | File | Trigger |
|----------|------|---------|
| PR gate | `.github/workflows/pr-gate.yml` | All PRs |
| Auto-label | `.github/workflows/auto-label.yml` | PR open/update |
| CI failure handler | `.github/workflows/ci-failure-handler.yml` | CI failure |
| Copilot automation | `.github/workflows/copilot-automation.yml` | Scheduled |
| Project automation | `.github/workflows/project-automation.yml` | Issue/PR events |

---

## Summary

1. **Three layers**: data-layer → agents → cli
2. **Dependencies flow down**: Never import from a higher layer
3. **No skip-layer imports**: CLI never imports data-layer
4. **CanonKeeper writes Neo4j**: All other agents use ProposedChange proposals
5. **Scene-level commits**: CanonKeeper canonizes at scene end only
6. **Agents call MCP**: Never instantiate DB clients directly in agents
7. **Pydantic v2 + async**: All schemas use Pydantic v2; all I/O is async
8. **Follow existing patterns**: Look at similar code in the same layer first
