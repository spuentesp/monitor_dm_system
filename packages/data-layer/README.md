# MONITOR Data Layer (Layer 1 of 3)

> **This is the BOTTOM layer. It has NO dependencies on other MONITOR packages.**

---

## What This Package Does

- Provides database clients for Neo4j, MongoDB, Qdrant, MinIO, OpenSearch
- Exposes MCP tools for agents to interact with data
- Defines Pydantic schemas for all data types
- Enforces authority rules (who can write what)

---

## Folder Structure

```
src/monitor_data/
├── __init__.py           # Package root
├── server.py             # MCP server entry point
│
├── db/                   # Database clients
│   ├── neo4j.py          # Neo4jClient
│   ├── mongodb.py        # MongoDBClient
│   ├── qdrant.py         # QdrantClient
│   ├── minio.py          # MinIOClient
│   └── opensearch.py     # OpenSearchClient
│
├── tools/                # MCP tools (called by agents)
│   ├── neo4j_tools.py    # 41 Neo4j operations
│   ├── mongodb_tools.py  # 18 MongoDB operations
│   ├── qdrant_tools.py   # 3 Qdrant operations
│   └── composite_tools.py # 2 composite operations
│
├── schemas/              # Pydantic models
│   ├── base.py           # Base models, enums
│   ├── entities.py       # Entity schemas
│   ├── facts.py          # Fact, Event schemas
│   ├── scenes.py         # Scene, Turn schemas
│   ├── proposals.py      # ProposedChange schemas
│   ├── memories.py       # CharacterMemory schemas
│   ├── sources.py        # Source, Document schemas
│   └── queries.py        # Query/filter schemas
│
└── middleware/           # Request processing
    ├── auth.py           # Authority enforcement
    └── validation.py     # Request validation
```

---

## Dependency Rules

```python
# ✅ ALLOWED imports in this package:
from neo4j import GraphDatabase
from pymongo import MongoClient
from qdrant_client import QdrantClient
from pydantic import BaseModel
import anthropic

# ❌ FORBIDDEN imports in this package:
from monitor_agents import ...   # NEVER import Layer 2
from monitor_cli import ...      # NEVER import Layer 3
```

---

## Who Calls This Package

Only `packages/agents/` (Layer 2) imports from this package.

```python
# In packages/agents/src/monitor_agents/canonkeeper.py
from monitor_data.tools import neo4j_create_fact  # ✅ Correct
```

---

## Key Files to Implement

1. `db/neo4j.py` - Neo4j connection and queries
2. `tools/neo4j_tools.py` - MCP tools for Neo4j (see docs/architecture/MCP_TRANSPORT.md)
3. `schemas/entities.py` - Entity Pydantic models (see docs/architecture/VALIDATION_SCHEMAS.md)
4. `middleware/auth.py` - Authority matrix enforcement

---

## Running

```bash
# Install for development
pip install -e ".[dev]"

# Run MCP server
monitor-data

# Run tests
pytest
```
