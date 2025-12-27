# MONITOR

*Multi-Ontology Narrative Intelligence Through Omniversal Representation*

**An Auto-GM system for tabletop RPGs and narrative games, built on a data-first, canonization-driven architecture.**

---

## What is MONITOR?

MONITOR is a **narrative AI system** that serves as an automated Game Master (Auto-GM) for tabletop role-playing games. Unlike traditional chatbots that generate ephemeral responses, MONITOR maintains **canonical truth** across multiple databases, ensuring consistency, provenance, and graduated canonization.

### Core Philosophy

1. **Data-First**: Databases define the architecture, not code
2. **Canonization-Driven**: Not everything becomes truth—explicit gates control what's canon
3. **Agent-Agnostic**: Stateless agents interact via MCP tools
4. **Provenance-Tracked**: All canonical facts link to evidence
5. **Multi-Database**: Neo4j (canon), MongoDB (narrative), Qdrant (semantic), MinIO (binaries), OpenSearch (text)

---

## Key Features

- **Canonical Graph (Neo4j)**: Single source of truth for universes, entities, facts, and events
- **Narrative Layer (MongoDB)**: Turn-by-turn logs, proposals, character memories
- **Semantic Search (Qdrant)**: Vector embeddings for contextual recall
- **Document Ingestion**: Upload PDFs/manuals and extract entities/axioms
- **Graduated Canonization**: Proposed → Canon → Retconned workflow
- **Two-Tier Entity System**: EntityArchetype (archetypes) vs EntityInstance (instances)
- **State Tags**: Dynamic entity state (alive, wounded, hostile, etc.)
- **Evidence Chain**: All canon linked to sources via SUPPORTED_BY edges
- **Multi-Agent Orchestration**: Orchestrator, Narrator, CanonKeeper, ContextAssembly, etc.
- **MCP Transport**: Agent-agnostic API via Model Context Protocol

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    AGENT LAYER (Stateless)               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │Orchestrator │  │  Narrator   │  │CanonKeeper  │  ... │
│  └─────────────┘  └─────────────┘  └─────────────┘      │
└────────────────────────┬─────────────────────────────────┘
                         │ MCP Protocol
┌────────────────────────▼─────────────────────────────────┐
│              DATA LAYER API (Stateful Service)           │
│  - Authority enforcement (CanonKeeper writes to Neo4j)   │
│  - Schema validation (Pydantic models)                   │
│  - Cross-DB coordination (composite operations)          │
└─┬────────┬────────┬────────┬────────┬────────────────────┘
  │        │        │        │        │
  ▼        ▼        ▼        ▼        ▼
┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐
│Neo4│  │Mongo│  │Qdrant│  │MinIO│  │OpenS│
│j   │  │DB  │  │     │  │    │  │earch│
└────┘  └────┘  └────┘  └────┘  └────┘

Canonical  Narrative  Vectors  Binaries  Text
```

---

## Quick Start

### 1. Start Infrastructure

```bash
cd infra
cp .env.example .env
# Edit .env with your passwords
docker compose up -d
```

### 2. Initialize Databases

Follow the setup instructions in [infra/README.md](infra/README.md) to:
- Create Neo4j constraints and indices
- Initialize MongoDB collections
- Create Qdrant vector collections
- Set up MinIO buckets

### 3. Implement Data Layer (or use pre-built)

Follow [docs/IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md) to build the MCP server.

### 4. Run Agents

```bash
# Start orchestrator
python -m services.agents.orchestrator

# Start other agents as needed
python -m services.agents.narrator
python -m services.agents.canonkeeper
```

---

## Documentation

### Architecture

- **[DATABASE_INTEGRATION.md](docs/architecture/DATABASE_INTEGRATION.md)** - 5-database memory system and canonization rules
- **[CONVERSATIONAL_LOOPS.md](docs/architecture/CONVERSATIONAL_LOOPS.md)** - 4 nested loops (Main, Story, Scene, Turn)
- **[AGENT_ORCHESTRATION.md](docs/architecture/AGENT_ORCHESTRATION.md)** - 7 agents and coordination
- **[DATA_LAYER_API.md](docs/architecture/DATA_LAYER_API.md)** - Complete API specification (41 Neo4j ops, 18 MongoDB ops, 3 Qdrant ops, 2 composite ops)
- **[MCP_TRANSPORT.md](docs/architecture/MCP_TRANSPORT.md)** - MCP tool definitions for all API operations
- **[VALIDATION_SCHEMAS.md](docs/architecture/VALIDATION_SCHEMAS.md)** - Pydantic models for data validation

### Ontology

- **[ONTOLOGY.md](docs/ontology/ONTOLOGY.md)** - Complete data model across all databases
- **[ERD_DIAGRAM.md](docs/ontology/ERD_DIAGRAM.md)** - Entity-Relationship diagrams
- **[ENTITY_TAXONOMY.md](docs/ontology/ENTITY_TAXONOMY.md)** - Two-tier entity classification (Archetype vs Instance)

### Implementation

- **[IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md)** - Step-by-step implementation guide
- **[infra/README.md](infra/README.md)** - Infrastructure setup and maintenance

---

## Data Flow Example: End of Scene Canonization

```
1. USER ACTION (MongoDB)
   └─ Append turn to scene.turns[]

2. PROPOSAL (MongoDB)
   └─ Create ProposedChange (type: state_change, entity: "wounded")

3. SCENE END (Orchestrator signals)
   └─ Call CanonKeeper.canonize_scene(scene_id)

4. CANONIZATION (CanonKeeper)
   ├─ Fetch pending proposals (MongoDB)
   ├─ Evaluate each (authority + confidence checks)
   ├─ Write accepted to Neo4j:
   │  ├─ Create Fact node
   │  ├─ Create INVOLVES edge
   │  ├─ Create SUPPORTED_BY edge
   │  └─ Update EntityInstance.state_tags
   ├─ Update proposal.status = "accepted" (MongoDB)
   └─ Finalize scene.status = "completed" (MongoDB)

5. INDEXING (Indexer)
   └─ Embed scene summary (Qdrant)

6. RESULT
   ├─ Neo4j: Canonical fact "Gandalf was wounded" with evidence
   ├─ MongoDB: Scene marked completed with canonical_outcomes[]
   └─ Qdrant: Scene summary embedded for future recall
```

---

## Key Concepts

### Canonization Levels

| Level | Meaning | When |
|-------|---------|------|
| `proposed` | Suggested, awaiting approval | Extracted from PDF, player action pending resolution |
| `canon` | Accepted as truth | GM confirmed, source authoritative, player action resolved |
| `retconned` | Superseded by newer fact | World lore changed, mistake corrected |

### Authority Hierarchy

| Authority | Weight | Examples |
|-----------|--------|----------|
| `source` | Highest | D&D Player's Handbook, Star Wars canon documents |
| `gm` | High | GM explicit declarations |
| `player` | Medium | Player actions via resolution |
| `system` | Lowest | System inferences |

### Two-Tier Entities

**EntityArchetype** (archetypes):
- "Wizard" (character class)
- "Lightsaber" (object type)
- "The Force" (concept)

**EntityInstance** (instances):
- "Gandalf the Grey" (specific wizard)
- "Luke's Lightsaber" (specific object)
- "The Force as wielded by Luke" (specific manifestation)

**Key difference**: Instance has `state_tags` that change over time ("alive", "wounded", "at_location").

---

## Use Cases

### P-1: Start New Story

```python
# User selects "Start New Story"
# → Orchestrator.run_main_loop()
#   → Orchestrator.start_new_story()
#     → neo4j_create_story()
#     → mongodb_create_scene()
#     → Orchestrator.run_scene_loop()
```

### P-3: User Turn in Active Scene

```python
# User inputs: "I attack the orc"
# → Narrator.handle_user_input()
#   → mongodb_append_turn()
#   → Resolver.resolve_action()
#     → mongodb_create_proposed_change(type="state_change", content={tag: "dead"})
#   → Narrator.generate_response()
#     → mongodb_append_turn(speaker="gm")
```

### P-8: End Scene (Canonization)

```python
# Scene ends (user or Orchestrator signals)
# → CanonKeeper.canonize_scene()
#   → mongodb_get_pending_proposals()
#   → For each proposal:
#       → evaluate_proposal()
#       → If accepted:
#           → neo4j_create_fact() / neo4j_create_event()
#           → mongodb_evaluate_proposal(status="accepted")
#   → mongodb_finalize_scene()
#   → Indexer.embed_scene_summary()
```

### I-1: Upload Document

```python
# User uploads D&D Player's Handbook
# → IngestPipeline.process_document()
#   → neo4j_create_source()
#   → mongodb_create_document()
#   → Extract text → mongodb_create_snippet() × N
#   → Indexer.embed_snippets() → qdrant
#   → LLM extracts entities → mongodb_create_proposed_change() × M
#   → User reviews proposals
#   → CanonKeeper.evaluate_proposals()
#     → Accepted → neo4j_create_entity()
```

### Q-1: Semantic Search

```python
# User asks: "What is Gandalf's current status?"
# → QueryAgent.semantic_search("Gandalf status")
#   → qdrant_semantic_search()
#     → Returns entity_id + fact_ids
#   → neo4j_get_entity(entity_id)
#     → Returns EntityInstance with state_tags: ["alive", "wielding_staff"]
#   → neo4j_query_facts(entity_id=gandalf)
#     → Returns recent facts about Gandalf
#   → Present to user
```

---

## Agent Roles

| Agent | Authority | Responsibilities |
|-------|-----------|------------------|
| **Orchestrator** | Loop management | Runs Main/Story/Scene loops, coordinates agents |
| **Narrator** | Narrative generation | Writes GM turns, generates descriptions |
| **CanonKeeper** | Neo4j writes only | Evaluates proposals, commits to canon |
| **ContextAssembly** | Read-only | Retrieves context from Neo4j + MongoDB + Qdrant |
| **Resolver** | Rules/dice | Resolves player actions, creates proposals |
| **MemoryManager** | Character memories | Manages NPC/PC memories in MongoDB |
| **Indexer** | Background indexing | Embeds scene summaries and memories in Qdrant |

---

## Performance Targets

| Loop | Latency Target | Canonization Cost |
|------|---------------|-------------------|
| Main | < 100ms | None (delegates) |
| Story | Hours-days | 1 closure write (Story complete) |
| Scene | 5-30 min | **1 batch write** (all proposals) |
| Turn | < 2s | None (deferred to Scene end) |

**Key insight**: Canonization happens **once per scene**, not per turn. This keeps costs low while maintaining consistency.

---

## Database Responsibilities

| Database | Role | Write Authority | Rebuild Strategy |
|----------|------|----------------|------------------|
| **Neo4j** | Canonical truth | CanonKeeper only | Never (source of truth) |
| **MongoDB** | Narrative + staging | Any agent | From Neo4j + manual export |
| **Qdrant** | Semantic index | Indexer only | From MongoDB scenes/memories |
| **MinIO** | Binary storage | Ingest pipeline | From backups |
| **OpenSearch** | Text search | Indexer only | From Neo4j + MongoDB |

---

## Technology Stack

### Core

- **Python 3.11+** - Data layer and agents
- **Anthropic Claude** - LLM for agents (via Anthropic SDK)
- **Model Context Protocol (MCP)** - Agent-to-data-layer communication

### Databases

- **Neo4j 5.15** - Graph database for canonical layer
- **MongoDB 7.0** - Document store for narrative layer
- **Qdrant 1.7** - Vector database for semantic search
- **MinIO** - S3-compatible object storage
- **OpenSearch 2.11** - Full-text search (optional)

### Infrastructure

- **Docker Compose** - Local development
- **Pydantic 2.5** - Schema validation
- **Poetry** - Python dependency management

---

## Project Structure

```
monitor2/
├── docs/
│   ├── architecture/
│   │   ├── DATABASE_INTEGRATION.md
│   │   ├── CONVERSATIONAL_LOOPS.md
│   │   ├── AGENT_ORCHESTRATION.md
│   │   ├── DATA_LAYER_API.md
│   │   ├── MCP_TRANSPORT.md
│   │   └── VALIDATION_SCHEMAS.md
│   ├── ontology/
│   │   ├── ONTOLOGY.md
│   │   ├── ERD_DIAGRAM.md
│   │   └── ENTITY_TAXONOMY.md
│   └── IMPLEMENTATION_GUIDE.md
│
├── infra/
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── README.md
│   ├── neo4j/
│   ├── mongodb/
│   ├── qdrant/
│   ├── minio/
│   └── opensearch/
│
├── services/
│   ├── data-layer/        # MCP server (to be implemented)
│   └── agents/            # Agent implementations (to be implemented)
│
└── README.md (this file)
```

---

## Development Status

**Current Phase**: Architecture & Documentation (Complete)

- [x] Architecture documentation
- [x] Ontology specification
- [x] API specification
- [x] MCP transport layer spec
- [x] Validation schemas
- [x] Infrastructure setup (Docker Compose)
- [x] Implementation guide
- [ ] Data layer implementation
- [ ] Agent implementation
- [ ] Testing
- [ ] CLI tool
- [ ] Web UI

---

## Contributing

1. Read the [IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md)
2. Set up infrastructure (see [infra/README.md](infra/README.md))
3. Implement features following the architecture
4. Write tests for all API operations
5. Submit PRs with clear descriptions

---

## Design Principles

1. **Explicit is better than implicit**: Canonization is an explicit gate, not automatic
2. **Databases are services, not libraries**: Interact via APIs, not direct connections
3. **Evidence is mandatory**: No canonical fact without provenance
4. **State is in the database, not the code**: Agents are stateless workers
5. **Optimize for correctness, not speed**: Better to be slow and correct than fast and wrong
6. **Batch over stream**: Canonize once per scene, not per turn
7. **Read-heavy, write-light**: Most operations query, few write to Neo4j

---

## License

[To be determined]

---

## Acknowledgments

Built on the shoulders of giants:
- Neo4j for graph database excellence
- MongoDB for document flexibility
- Qdrant for vector search performance
- Anthropic for Claude and MCP

---

## Contact

[To be determined]

---

## Further Reading

- **Neo4j Graph Data Science**: https://neo4j.com/docs/graph-data-science/current/
- **MongoDB Schema Design**: https://www.mongodb.com/docs/manual/data-modeling/
- **Qdrant Vector Search**: https://qdrant.tech/documentation/
- **Model Context Protocol**: https://modelcontextprotocol.io/
- **Anthropic Claude**: https://docs.anthropic.com/
