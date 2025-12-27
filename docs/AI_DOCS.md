# MONITOR - AI Agent Reference

*Concise reference for AI agents working on the MONITOR codebase.*

> **FIRST:** Read `ARCHITECTURE.md` and `CLAUDE.md` at the repo root.

---

## Monorepo Structure (CRITICAL)

```
monitor2/
├── ARCHITECTURE.md      ← READ FIRST: Layer rules
├── CLAUDE.md            ← READ FIRST: AI instructions
├── docs/                # Documentation
├── infra/               # Docker infrastructure
├── packages/            # THE THREE LAYERS
│   ├── data-layer/      # Layer 1: MCP Server + DB clients
│   ├── agents/          # Layer 2: AI Agents
│   └── cli/             # Layer 3: User Interface
└── scripts/             # Dev utilities
```

### Layer Dependency Rules

```
┌─────────────────────────────┐
│  Layer 3: CLI               │  packages/cli/
│  Depends on: agents ONLY    │
└──────────────┬──────────────┘
               │ imports
               ▼
┌─────────────────────────────┐
│  Layer 2: AGENTS            │  packages/agents/
│  Depends on: data-layer     │
└──────────────┬──────────────┘
               │ imports
               ▼
┌─────────────────────────────┐
│  Layer 1: DATA-LAYER        │  packages/data-layer/
│  Depends on: external only  │
└─────────────────────────────┘
```

**RULES:**
1. Dependencies flow DOWNWARD only
2. No skip-layer imports (CLI cannot import data-layer directly)
3. Each layer has its own `pyproject.toml`

---

## Project Overview

**MONITOR** = Multi-Ontology Narrative Intelligence Through Omniversal Representation

An **Auto-GM system** for tabletop RPGs that maintains canonical truth across multiple databases.

### Core Philosophy

1. **Data-First** - Databases define architecture, not code
2. **Canonization-Driven** - Explicit gates control what becomes truth
3. **Agent-Agnostic** - Stateless agents interact via MCP tools
4. **Provenance-Tracked** - All canonical facts link to evidence
5. **Multi-Database** - Each database serves a specific purpose

---

## Architecture Summary

### 5 Databases

| Database | Role | Authoritative For |
|----------|------|-------------------|
| **Neo4j** | Canonical truth | Entities, facts, events, relationships |
| **MongoDB** | Narrative layer | Scenes, turns, proposals, memories |
| **Qdrant** | Semantic search | Vector embeddings (1536 dims, OpenAI) |
| **MinIO** | Binary storage | PDFs, images, raw files |
| **OpenSearch** | Full-text search | Precision keyword queries (optional) |

### 7 Agents

| Agent | Responsibility | Neo4j Write? |
|-------|---------------|--------------|
| **Orchestrator** | Loop management | Limited (Story only) |
| **ContextAssembly** | Context retrieval | No (read-only) |
| **Narrator** | Narrative generation | No |
| **Resolver** | Rules/dice resolution | No |
| **CanonKeeper** | Canonization | **Yes (exclusive)** |
| **MemoryManager** | Character memories | No |
| **Indexer** | Background indexing | No |

### Data Flow

```
User Input → MongoDB (Turn) → Proposals → [Canonization Gate] → Neo4j (Facts) → Qdrant (Embeddings)
```

---

## Key Concepts

### Canonization Gate

Not everything becomes truth. The canonization gate is the explicit decision point where narrative (MongoDB) becomes canon (Neo4j).

**When:** End of scene (primary), mid-scene for critical events (optional)

**What gets canonized:**
- Facts/Events
- Entity creation
- Relationship changes
- State transitions

**What stays narrative:**
- Turn transcripts
- GM/player notes
- Rejected proposals

### Two-Tier Entity System

| Type | Description | Has state_tags? |
|------|-------------|-----------------|
| **EntityAxiomatica** | Archetypes, concepts ("Wizard", "Orc") | No |
| **EntityConcreta** | Specific instances ("Gandalf", "The One Ring") | Yes |

EntityConcreta can derive from EntityAxiomatica via `DERIVA_DE` relationship.

### Authority Hierarchy

| Authority | Weight | Example |
|-----------|--------|---------|
| `source` | Highest | D&D PHB, official lore |
| `gm` | High | GM declarations |
| `player` | Medium | Player actions via resolution |
| `system` | Lowest | System inferences |

### Canon Levels

| Level | Meaning |
|-------|---------|
| `proposed` | Suggested, awaiting approval |
| `canon` | Accepted as truth |
| `retconned` | Superseded by newer fact |

**Exception:** Source nodes use `authoritative` instead of `retconned` (sources aren't revised, only facts from them).

---

## Critical Invariants

1. **CanonKeeper is the only agent with Neo4j write access** (except Orchestrator for Story)
2. **All canonical facts must have evidence** - via `SUPPORTED_BY` edges or `evidence_refs` property
3. **Scenes are canonization boundaries, not turns** - batch writes at scene end
4. **Neo4j never references external DB primary keys** - only UUIDs
5. **Qdrant is never authoritative** - derived index only, rebuildable
6. **Entities are never deleted** - marked `retconned` instead
7. **State tags are only on EntityConcreta** - EntityAxiomatica is timeless

---

## Directory Structure

```
monitor2/
├── ARCHITECTURE.md           # Layer rules (READ FIRST)
├── CLAUDE.md                 # AI agent instructions (READ FIRST)
├── README.md                 # Project overview
│
├── docs/
│   ├── architecture/         # System design (6 files)
│   │   ├── DATABASE_INTEGRATION.md
│   │   ├── CONVERSATIONAL_LOOPS.md
│   │   ├── AGENT_ORCHESTRATION.md
│   │   ├── DATA_LAYER_API.md
│   │   ├── MCP_TRANSPORT.md
│   │   └── VALIDATION_SCHEMAS.md
│   ├── ontology/             # Data model (3 files)
│   │   ├── ONTOLOGY.md
│   │   ├── ENTITY_TAXONOMY.md
│   │   └── ERD_DIAGRAM.md
│   ├── IMPLEMENTATION_GUIDE.md
│   └── AI_DOCS.md            # This file
│
├── infra/                    # Docker infrastructure
│   ├── docker-compose.yml
│   └── README.md
│
├── packages/                 # THE THREE LAYERS
│   ├── data-layer/           # Layer 1: MCP server + DB clients
│   │   ├── pyproject.toml
│   │   └── src/monitor_data/
│   │       ├── db/           # Database clients
│   │       ├── tools/        # MCP tools
│   │       ├── schemas/      # Pydantic models
│   │       └── middleware/   # Auth enforcement
│   │
│   ├── agents/               # Layer 2: AI agents
│   │   ├── pyproject.toml
│   │   └── src/monitor_agents/
│   │       ├── orchestrator.py
│   │       ├── narrator.py
│   │       ├── canonkeeper.py
│   │       └── ...
│   │
│   └── cli/                  # Layer 3: User interface
│       ├── pyproject.toml
│       └── src/monitor_cli/
│           ├── main.py
│           └── commands/
│
└── scripts/                  # Dev utilities
```

---

## Quick Reference Tables

### Neo4j Node Types

| Node | Key Properties |
|------|----------------|
| `Omniverse` | id, name |
| `Multiverse` | id, omniverse_id, system_name |
| `Universe` | id, multiverse_id, genre, tone |
| `Source` | id, universe_id, doc_id, source_type |
| `Axiom` | id, universe_id, statement, domain |
| `EntityAxiomatica` | id, universe_id, name, entity_type, properties |
| `EntityConcreta` | id, universe_id, name, entity_type, properties, **state_tags** |
| `Story` | id, universe_id, title, story_type, status |
| `Scene` | id, story_id, title, purpose |
| `Fact` | id, universe_id, statement, time_ref, confidence, authority |
| `Event` | id, scene_id, title, severity |
| `PlotThread` | id, story_id, title, thread_type |

### MongoDB Collections

| Collection | Purpose |
|------------|---------|
| `scenes` | Narrative scenes with turns array |
| `proposed_changes` | Canonization staging |
| `resolutions` | Dice/rules outcomes |
| `character_memories` | NPC/PC subjective memories |
| `documents` | Ingested source metadata |
| `snippets` | Document chunks |
| `character_sheets` | Character sheets |
| `story_outlines` | Narrative planning |

### Entity Types

`character`, `faction`, `location`, `object`, `concept`, `organization`

### State Tags (EntityConcreta only)

- **Life:** alive, dead, unconscious, dying
- **Health:** healthy, wounded, poisoned
- **Position:** standing, prone, flying, hidden
- **Social:** hostile, friendly, allied, enemy

---

## Common Implementation Tasks

### Adding a New Entity Type

1. Add to `entity_type` enum in `VALIDATION_SCHEMAS.md`
2. Define type-specific properties in `ENTITY_TAXONOMY.md`
3. Update Neo4j constraints if needed
4. Add to MongoDB schema validation

### Modifying Canonization Flow

1. Review `DATABASE_INTEGRATION.md` § Canonization Gate
2. Update `CanonKeeper` in `AGENT_ORCHESTRATION.md`
3. Modify `composite_canonize_scene` in `MCP_TRANSPORT.md`

### Adding an API Operation

1. Define schema in `VALIDATION_SCHEMAS.md`
2. Add to appropriate section in `DATA_LAYER_API.md`
3. Create MCP tool in `MCP_TRANSPORT.md`
4. Update authority matrix in `AGENT_ORCHESTRATION.md`

### Extending the Data Model

1. Start with `ONTOLOGY.md` (canonical model)
2. Update `ERD_DIAGRAM.md` (visual representation)
3. If entity-related, update `ENTITY_TAXONOMY.md`
4. Add Pydantic models to `VALIDATION_SCHEMAS.md`

---

## Key Code Patterns (When Implementing)

### CanonKeeper Exclusive Write

```python
# Only CanonKeeper can write to Neo4j
@require_authority(["CanonKeeper"])
async def neo4j_create_fact(request: FactCreate) -> FactResponse:
    ...
```

### Evidence is Mandatory

```python
# Every fact needs evidence
class FactCreate(BaseModel):
    evidence_refs: list[str] = Field(min_items=1)  # Required!
```

### Scene-Level Batching

```python
# Canonization happens at scene end, not per-turn
async def finalize_scene(scene_id: str):
    proposals = await get_pending_proposals(scene_id)
    for p in proposals:
        if evaluate(p):
            await neo4j_create_fact(p)  # Batch write
```

---

## Performance Targets

| Loop | Latency | Canonization |
|------|---------|--------------|
| Main | < 100ms | None |
| Story | Hours-days | 1 write (Story) |
| Scene | 5-30 min | **1 batch write** |
| Turn | < 2s | None (deferred) |

---

## References

- **Primary design:** `docs/architecture/DATABASE_INTEGRATION.md`
- **Data model:** `docs/ontology/ONTOLOGY.md`
- **API spec:** `docs/architecture/DATA_LAYER_API.md`
- **Implementation:** `docs/IMPLEMENTATION_GUIDE.md`
