# MONITOR Implementation Guide

*Step-by-step guide to implementing the MONITOR system.*

---

## Overview

This guide walks you through implementing MONITOR from the ground up, following the architecture defined in the documentation.

**Prerequisites:**
- Docker and Docker Compose
- Python 3.11+
- Node.js 18+ (if building web UIs)
- Basic understanding of Neo4j, MongoDB, and vector databases

---

## Architecture Summary

MONITOR is built on a **data-first, agent-agnostic architecture**:

```
┌────────────────────────────────────────────┐
│         AGENT LAYER (Stateless)            │
│  Orchestrator, Narrator, CanonKeeper, etc. │
└────────────────┬───────────────────────────┘
                 │
                 ▼ MCP Protocol
┌────────────────────────────────────────────┐
│      DATA LAYER API (Stateful Service)     │
│  - Authority enforcement                   │
│  - Validation                              │
│  - Cross-DB coordination                   │
└─┬───────┬────────┬────────┬────────┬───────┘
  │       │        │        │        │
  ▼       ▼        ▼        ▼        ▼
Neo4j  MongoDB  Qdrant  MinIO  OpenSearch
```

**Key principles:**
1. Neo4j is the **single source of truth** (canonical layer)
2. MongoDB stages proposals and stores narrative artifacts
3. Qdrant provides semantic search (derived, rebuildable)
4. Agents interact **only via MCP tools**, never directly with DBs
5. CanonKeeper has **exclusive write access** to Neo4j

---

## Phase 1: Infrastructure Setup

### 1.1 Start Database Stack

```bash
cd infra
cp .env.example .env
# Edit .env with your passwords
docker compose up -d
```

Verify all services are running:
```bash
docker compose ps
```

### 1.2 Initialize Databases

**Neo4j constraints and indices:**
```bash
# Access Neo4j Browser at http://localhost:7474
# Run the Cypher commands from infra/README.md
```

**MongoDB collections:**
```bash
# Create infra/mongodb/init/01-init.js (see infra/README.md)
# Restart MongoDB to apply:
docker compose restart mongodb
```

**Qdrant collections:**
```bash
# Run the curl commands from infra/README.md to create collections
```

---

## Phase 2: Data Layer API Implementation

### 2.1 Project Structure

Create the following structure:

```
monitor2/
├── docs/                  # Documentation (already exists)
├── infra/                 # Infrastructure (already exists)
├── services/
│   ├── data-layer/        # MCP server for data layer
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── mcp_server.py
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── entities.py
│   │   │   │   ├── facts.py
│   │   │   │   ├── scenes.py
│   │   │   │   └── ...
│   │   │   ├── db/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── neo4j_client.py
│   │   │   │   ├── mongodb_client.py
│   │   │   │   ├── qdrant_client.py
│   │   │   │   └── minio_client.py
│   │   │   ├── tools/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── neo4j_tools.py
│   │   │   │   ├── mongodb_tools.py
│   │   │   │   ├── qdrant_tools.py
│   │   │   │   └── composite_tools.py
│   │   │   ├── middleware/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py
│   │   │   │   └── validation.py
│   │   │   └── utils/
│   │   │       ├── __init__.py
│   │   │       └── logging.py
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── README.md
│   │
│   └── agents/            # Agent implementations
│       ├── orchestrator/
│       ├── narrator/
│       ├── canonkeeper/
│       ├── context_assembly/
│       └── ...
│
└── README.md
```

### 2.2 Install Dependencies

Create `services/data-layer/pyproject.toml`:

```toml
[tool.poetry]
name = "monitor-data-layer"
version = "1.0.0"
description = "MONITOR Data Layer API via MCP"

[tool.poetry.dependencies]
python = "^3.11"
pydantic = "^2.5"
neo4j = "^5.15"
pymongo = "^4.6"
qdrant-client = "^1.7"
minio = "^7.2"
opensearch-py = "^2.4"
anthropic = "^0.39"  # For MCP SDK
fastapi = "^0.108"  # Optional: REST API alongside MCP
uvicorn = "^0.25"
python-dotenv = "^1.0"

[tool.poetry.dev-dependencies]
pytest = "^7.4"
pytest-asyncio = "^0.21"
black = "^23.12"
mypy = "^1.7"
ruff = "^0.1"
```

Install:
```bash
cd services/data-layer
poetry install
```

### 2.3 Implement Pydantic Schemas

Copy the schemas from `docs/architecture/VALIDATION_SCHEMAS.md` into `src/schemas/`.

Example `src/schemas/entities.py`:

```python
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from enum import Enum

class EntityType(str, Enum):
    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"
    ORGANIZATION = "organization"

class EntityConcretaCreate(BaseModel):
    """Request to create an EntityConcreta."""
    universe_id: UUID
    name: str = Field(min_length=1, max_length=200)
    entity_type: EntityType
    description: str
    properties: dict = Field(default_factory=dict)
    state_tags: list[str] = Field(default_factory=list)
    derives_from: UUID | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    authority: str
    evidence_refs: list[str] = Field(min_items=1)

# ... etc (see VALIDATION_SCHEMAS.md)
```

### 2.4 Implement Database Clients

**Neo4j Client** (`src/db/neo4j_client.py`):

```python
from neo4j import GraphDatabase
from typing import Any
import os

class Neo4jClient:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def create_entity(self, entity_data: dict) -> dict:
        """Create an entity node."""
        with self.driver.session() as session:
            result = session.execute_write(self._create_entity_tx, entity_data)
            return result

    @staticmethod
    def _create_entity_tx(tx, data):
        query = """
        CREATE (e:EntityConcreta {
            id: $id,
            universe_id: $universe_id,
            name: $name,
            entity_type: $entity_type,
            description: $description,
            properties: $properties,
            state_tags: $state_tags,
            canon_level: $canon_level,
            confidence: $confidence,
            authority: $authority,
            created_at: datetime()
        })
        RETURN e
        """
        result = tx.run(query, **data)
        return result.single()[0]

# ... etc
```

**MongoDB Client** (`src/db/mongodb_client.py`):

```python
from pymongo import MongoClient
from uuid import UUID
import os

class MongoDBClient:
    def __init__(self):
        uri = os.getenv("MONGODB_URI", "mongodb://monitor:monitor2024@localhost:27017/monitor")
        self.client = MongoClient(uri)
        self.db = self.client.monitor

    def close(self):
        self.client.close()

    def create_scene(self, scene_data: dict) -> dict:
        """Create a scene document."""
        result = self.db.scenes.insert_one(scene_data)
        scene_data['_id'] = result.inserted_id
        return scene_data

    def append_turn(self, scene_id: UUID, turn_data: dict) -> dict:
        """Append a turn to a scene."""
        result = self.db.scenes.update_one(
            {"scene_id": str(scene_id)},
            {"$push": {"turns": turn_data}}
        )
        return turn_data

# ... etc
```

**Qdrant Client** (`src/db/qdrant_client.py`):

```python
from qdrant_client import QdrantClient as QdrantSDK
from qdrant_client.models import PointStruct
import os

class QdrantClient:
    def __init__(self):
        uri = os.getenv("QDRANT_URI", "http://localhost:6333")
        self.client = QdrantSDK(url=uri)

    def search(self, collection: str, query_vector: list[float], filters: dict, limit: int = 10):
        """Semantic search."""
        results = self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=filters,
            limit=limit
        )
        return results

# ... etc
```

### 2.5 Implement MCP Tools

**Neo4j Tools** (`src/tools/neo4j_tools.py`):

```python
from anthropic import MCP
from src.schemas.entities import EntityConcretaCreate, EntityResponse
from src.db.neo4j_client import Neo4jClient
from uuid import uuid4
from datetime import datetime

mcp = MCP()
neo4j_client = Neo4jClient()

@mcp.tool()
async def neo4j_create_entity(request: EntityConcretaCreate) -> EntityResponse:
    """Create a new entity (EntityConcreta) in the canonical graph."""

    # Validate authority (CanonKeeper only)
    # (handled by middleware)

    # Generate UUID
    entity_id = uuid4()

    # Prepare data
    entity_data = {
        "id": str(entity_id),
        "universe_id": str(request.universe_id),
        "name": request.name,
        "entity_type": request.entity_type.value,
        "description": request.description,
        "properties": request.properties,
        "state_tags": request.state_tags,
        "canon_level": "canon",
        "confidence": request.confidence,
        "authority": request.authority
    }

    # Create in Neo4j
    neo4j_client.create_entity(entity_data)

    return EntityResponse(
        entity_id=entity_id,
        canon_level="canon",
        created_at=datetime.utcnow()
    )

# ... etc (see MCP_TRANSPORT.md for all tools)
```

**MongoDB Tools** (`src/tools/mongodb_tools.py`):

```python
from anthropic import MCP
from src.schemas.scenes import SceneCreate, SceneResponse
from src.db.mongodb_client import MongoDBClient
from uuid import uuid4
from datetime import datetime

mcp = MCP()
mongodb_client = MongoDBClient()

@mcp.tool()
async def mongodb_create_scene(request: SceneCreate) -> SceneResponse:
    """Create a new scene in MongoDB."""

    scene_id = uuid4()

    scene_data = {
        "scene_id": str(scene_id),
        "story_id": str(request.story_id),
        "universe_id": str(request.universe_id),
        "title": request.title,
        "purpose": request.purpose,
        "status": "active",
        "location_ref": str(request.location_ref) if request.location_ref else None,
        "participating_entities": [str(e) for e in request.participating_entities],
        "turns": [],
        "proposed_changes": [],
        "canonical_outcomes": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    mongodb_client.create_scene(scene_data)

    return SceneResponse(
        scene_id=scene_id,
        status="active",
        created_at=datetime.utcnow()
    )

# ... etc
```

### 2.6 Implement Authority Middleware

**Authority Enforcement** (`src/middleware/auth.py`):

```python
from functools import wraps
from typing import Callable

# Authority matrix from AGENT_ORCHESTRATION.md
AUTHORITY_MATRIX = {
    "neo4j_create_entity": ["CanonKeeper"],
    "neo4j_update_entity_state": ["CanonKeeper"],
    "neo4j_get_entity": ["*"],
    "mongodb_create_scene": ["Orchestrator"],
    "mongodb_append_turn": ["Narrator", "Orchestrator"],
    "composite_canonize_scene": ["CanonKeeper"],
    # ... etc
}

def require_authority(allowed_agents: list[str]):
    """Decorator to enforce agent authority."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get agent context from MCP request
            agent_type = kwargs.get('agent_type')  # Passed by MCP server

            if "*" not in allowed_agents and agent_type not in allowed_agents:
                raise PermissionError(
                    f"Agent type '{agent_type}' is not authorized to call '{func.__name__}'. "
                    f"Allowed types: {allowed_agents}"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage:
# @require_authority(["CanonKeeper"])
# async def neo4j_create_entity(...):
#     ...
```

### 2.7 Implement MCP Server

**Main Server** (`src/mcp_server.py`):

```python
from anthropic import MCP
from src.tools import neo4j_tools, mongodb_tools, qdrant_tools, composite_tools
import os

async def main():
    # Initialize MCP server
    mcp = MCP(
        name="monitor-data-layer",
        version="1.0.0",
        description="MONITOR Data Layer API"
    )

    # Register all tools
    mcp.register_tools([
        neo4j_tools,
        mongodb_tools,
        qdrant_tools,
        composite_tools
    ])

    # Start server
    port = int(os.getenv("MCP_SERVER_PORT", 8080))
    await mcp.run(port=port)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

## Phase 3: Agent Implementation

### 3.1 Agent Base Class

Create `services/agents/base_agent.py`:

```python
from anthropic import Anthropic
from typing import Any
import os

class BaseAgent:
    def __init__(self, agent_type: str, agent_id: str):
        self.agent_type = agent_type
        self.agent_id = agent_id
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20250929")

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call an MCP tool via the data layer."""
        # Add agent context
        context = {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type
        }

        # Call MCP server (implementation depends on MCP SDK)
        # ...
        pass

    async def run_loop(self):
        """Main agent loop (to be overridden)."""
        raise NotImplementedError
```

### 3.2 Orchestrator Agent

Create `services/agents/orchestrator/orchestrator.py`:

```python
from services.agents.base_agent import BaseAgent

class Orchestrator(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type="Orchestrator",
            agent_id="orchestrator-001"
        )

    async def run_main_loop(self):
        """Main loop from CONVERSATIONAL_LOOPS.md."""
        while True:
            # Display menu
            choice = await self.display_menu()

            if choice == "start_story":
                await self.start_new_story()
            elif choice == "continue_story":
                await self.continue_story()
            elif choice == "ingest":
                await self.run_ingest_pipeline()
            elif choice == "query":
                await self.run_query_mode()
            elif choice == "exit":
                break

    async def start_new_story(self):
        """Story setup flow."""
        # 1. Ensure universe exists
        universe_id = await self.ensure_universe()

        # 2. Create Story
        story = await self.call_tool("neo4j_create_story", {
            "universe_id": universe_id,
            "title": "New Campaign",
            "story_type": "campaign"
        })

        # 3. Start story loop
        await self.run_story_loop(story['story_id'])

    async def run_story_loop(self, story_id: str):
        """Story loop from CONVERSATIONAL_LOOPS.md."""
        # Create first scene
        scene = await self.call_tool("mongodb_create_scene", {
            "story_id": story_id,
            "universe_id": self.universe_id,
            "title": "Opening Scene",
            "participating_entities": []
        })

        # Start scene loop
        await self.run_scene_loop(scene['scene_id'])

# ... etc (see CONVERSATIONAL_LOOPS.md for all loops)
```

### 3.3 CanonKeeper Agent

Create `services/agents/canonkeeper/canonkeeper.py`:

```python
from services.agents.base_agent import BaseAgent

class CanonKeeper(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type="CanonKeeper",
            agent_id="canonkeeper-001"
        )

    async def canonize_scene(self, scene_id: str):
        """Canonize a scene (end-of-scene commit)."""

        # 1. Get pending proposals
        proposals = await self.call_tool("mongodb_get_pending_proposals", {
            "scene_id": scene_id
        })

        accepted = []
        rejected = []

        # 2. Evaluate each proposal
        for proposal in proposals:
            if await self.evaluate_proposal(proposal):
                # Accept: create canonical node
                canonical_id = await self.commit_to_neo4j(proposal)
                accepted.append(proposal['proposal_id'])

                # Update proposal status
                await self.call_tool("mongodb_evaluate_proposal", {
                    "proposal_id": proposal['proposal_id'],
                    "decision": "accepted",
                    "canonical_id": canonical_id
                })
            else:
                # Reject
                rejected.append(proposal['proposal_id'])
                await self.call_tool("mongodb_evaluate_proposal", {
                    "proposal_id": proposal['proposal_id'],
                    "decision": "rejected"
                })

        # 3. Finalize scene
        await self.call_tool("mongodb_finalize_scene", {
            "scene_id": scene_id,
            "canonical_outcome_ids": accepted,
            "summary": await self.generate_summary(scene_id)
        })

        return {"accepted": accepted, "rejected": rejected}

    async def evaluate_proposal(self, proposal: dict) -> bool:
        """Evaluate a proposal (authority + confidence checks)."""
        # Check authority
        if proposal['authority'] == 'source' and proposal['confidence'] > 0.9:
            return True
        elif proposal['authority'] == 'gm':
            return True
        elif proposal['authority'] == 'player' and proposal['confidence'] > 0.7:
            return True
        else:
            # Ask LLM to evaluate
            return await self.llm_evaluate(proposal)

# ... etc
```

---

## Phase 4: Testing

### 4.1 Unit Tests

Create `services/data-layer/tests/test_neo4j_tools.py`:

```python
import pytest
from src.tools.neo4j_tools import neo4j_create_entity
from src.schemas.entities import EntityConcretaCreate
from uuid import uuid4

@pytest.mark.asyncio
async def test_create_entity():
    request = EntityConcretaCreate(
        universe_id=uuid4(),
        name="Test Entity",
        entity_type="character",
        description="Test description",
        properties={},
        state_tags=["alive"],
        confidence=1.0,
        authority="gm",
        evidence_refs=["source:test-uuid"]
    )

    response = await neo4j_create_entity(request)

    assert response.entity_id is not None
    assert response.canon_level == "canon"

# ... etc
```

### 4.2 Integration Tests

Create `services/data-layer/tests/test_use_cases.py`:

```python
import pytest
from src.tools import *
from uuid import uuid4

@pytest.mark.asyncio
async def test_uc3_end_scene_canonization():
    """Test UC-3: End Scene (Canonization) from DATA_LAYER_API.md."""

    # Setup: create scene with proposals
    scene_id = uuid4()
    # ... create scene and proposals

    # Execute canonization
    result = await composite_canonize_scene({
        "scene_id": scene_id,
        "evaluate_proposals": True
    })

    # Verify
    assert len(result['accepted_proposals']) > 0
    assert len(result['canonical_fact_ids']) > 0

# ... etc (test all 5 use cases from DATA_LAYER_API.md)
```

---

## Phase 5: Deployment

### 5.1 Build Docker Image

Create `services/data-layer/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

# Copy source
COPY src/ ./src/

# Run server
CMD ["poetry", "run", "python", "-m", "src.mcp_server"]
```

Build:
```bash
docker build -t monitor-data-layer:latest .
```

### 5.2 Update docker-compose.yml

Uncomment the `mcp-server` service in `infra/docker-compose.yml`.

### 5.3 Deploy

```bash
docker compose up -d
```

---

## Phase 6: CLI & UI

### 6.1 CLI Tool

Create a simple CLI that talks to the Orchestrator:

```bash
poetry new monitor-cli
cd monitor-cli
# Implement CLI that calls Orchestrator agent
```

### 6.2 Web UI (Optional)

Create a web interface using Next.js or similar:
- Character management
- Scene viewer
- Canon query interface
- Document upload

---

## References

- [DATABASE_INTEGRATION.md](architecture/DATABASE_INTEGRATION.md) - Data layer architecture
- [CONVERSATIONAL_LOOPS.md](architecture/CONVERSATIONAL_LOOPS.md) - Loop state machines
- [AGENT_ORCHESTRATION.md](architecture/AGENT_ORCHESTRATION.md) - Agent coordination
- [DATA_LAYER_API.md](architecture/DATA_LAYER_API.md) - Complete API spec
- [MCP_TRANSPORT.md](architecture/MCP_TRANSPORT.md) - MCP tool definitions
- [VALIDATION_SCHEMAS.md](architecture/VALIDATION_SCHEMAS.md) - Pydantic models
- [ONTOLOGY.md](ontology/ONTOLOGY.md) - Data model
- [ERD_DIAGRAM.md](ontology/ERD_DIAGRAM.md) - ERD diagrams
- [ENTITY_TAXONOMY.md](ontology/ENTITY_TAXONOMY.md) - Entity classification
