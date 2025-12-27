# Data Layer Implementation

> Machine-optimized task list for implementing Layer 1.

---

## Prerequisites

```
REQUIRES: Python 3.11+, Docker (for databases)
READS: docs/ontology/ONTOLOGY.md, docs/architecture/DATA_LAYER_API.md
OUTPUTS: MCP server with 64+ tools
```

---

## Phase 1: Project Setup

### T1.1: Initialize Package

```bash
cd packages/data-layer
uv init --name monitor-data-layer
```

**Files to create:**
```
src/monitor_data/
├── __init__.py
├── server.py
├── config.py
├── db/
│   └── __init__.py
├── tools/
│   └── __init__.py
├── schemas/
│   └── __init__.py
└── middleware/
    └── __init__.py
```

### T1.2: Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "mcp>=1.0",
    "neo4j>=5.15",
    "pymongo>=4.6",
    "qdrant-client>=1.7",
    "minio>=7.2",
    "opensearch-py>=2.4",
    "pydantic>=2.5",
    "python-dotenv>=1.0",
]
```

### T1.3: Config Module

**File:** `src/monitor_data/config.py`

```python
# Load from environment:
NEO4J_URI: str
NEO4J_USER: str
NEO4J_PASSWORD: str
MONGODB_URI: str
QDRANT_HOST: str
QDRANT_PORT: int
MINIO_ENDPOINT: str
MINIO_ACCESS_KEY: str
MINIO_SECRET_KEY: str
OPENSEARCH_HOST: str
```

---

## Phase 2: Database Clients

### T2.1: Neo4j Client

**File:** `src/monitor_data/db/neo4j.py`

**Class:** `Neo4jClient`

| Method | Description |
|--------|-------------|
| `__init__(uri, user, password)` | Connect to Neo4j |
| `close()` | Close connection |
| `execute_read(query, params)` | Read transaction |
| `execute_write(query, params)` | Write transaction |

**Test:** `tests/test_db/test_neo4j.py`

### T2.2: MongoDB Client

**File:** `src/monitor_data/db/mongodb.py`

**Class:** `MongoDBClient`

| Method | Description |
|--------|-------------|
| `__init__(uri, database)` | Connect to MongoDB |
| `close()` | Close connection |
| `get_collection(name)` | Get collection |
| `insert_one(collection, doc)` | Insert document |
| `find_one(collection, query)` | Find single document |
| `find(collection, query, limit)` | Find multiple documents |
| `update_one(collection, query, update)` | Update document |

**Collections to verify on init:**
- `scenes`
- `proposed_changes`
- `resolutions`
- `character_memories`
- `documents`
- `snippets`
- `character_sheets`
- `story_outlines`

### T2.3: Qdrant Client

**File:** `src/monitor_data/db/qdrant.py`

**Class:** `QdrantClient`

| Method | Description |
|--------|-------------|
| `__init__(host, port)` | Connect to Qdrant |
| `ensure_collections()` | Create collections if missing |
| `upsert(collection, points)` | Upsert vectors |
| `search(collection, vector, filter, limit)` | Search vectors |
| `delete(collection, ids)` | Delete vectors |

**Collections:**
- `scene_chunks` (dim=1536)
- `memory_chunks` (dim=1536)
- `snippet_chunks` (dim=1536)

### T2.4: MinIO Client

**File:** `src/monitor_data/db/minio.py`

**Class:** `MinIOClient`

| Method | Description |
|--------|-------------|
| `__init__(endpoint, access_key, secret_key)` | Connect |
| `ensure_bucket(name)` | Create bucket if missing |
| `upload_file(bucket, object_name, file_path)` | Upload |
| `download_file(bucket, object_name, file_path)` | Download |
| `get_presigned_url(bucket, object_name)` | Get URL |
| `delete_object(bucket, object_name)` | Delete |

**Buckets:**
- `documents`

### T2.5: OpenSearch Client (Optional)

**File:** `src/monitor_data/db/opensearch.py`

**Class:** `OpenSearchClient`

| Method | Description |
|--------|-------------|
| `__init__(host)` | Connect |
| `index(index_name, doc_id, doc)` | Index document |
| `search(index_name, query)` | Search |
| `delete(index_name, doc_id)` | Delete |

---

## Phase 3: Pydantic Schemas

### T3.1: Base Schemas

**File:** `src/monitor_data/schemas/base.py`

```python
from enum import Enum
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class CanonLevel(str, Enum):
    PROPOSED = "proposed"
    CANON = "canon"
    RETCONNED = "retconned"

class Authority(str, Enum):
    SOURCE = "source"
    GM = "gm"
    PLAYER = "player"
    SYSTEM = "system"

class EntityType(str, Enum):
    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"
    ORGANIZATION = "organization"

class StoryType(str, Enum):
    CAMPAIGN = "campaign"
    ARC = "arc"
    EPISODE = "episode"
    ONE_SHOT = "one_shot"

class StoryStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

class SceneStatus(str, Enum):
    ACTIVE = "active"
    FINALIZING = "finalizing"
    COMPLETED = "completed"

class ProposalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class ProposalType(str, Enum):
    FACT = "fact"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    STATE_CHANGE = "state_change"
    EVENT = "event"
```

### T3.2: Entity Schemas

**File:** `src/monitor_data/schemas/entities.py`

| Schema | Purpose |
|--------|---------|
| `UniverseCreate` | Create universe input |
| `UniverseResponse` | Universe output |
| `EntityArchetypeCreate` | Create archetype |
| `EntityInstanceCreate` | Create instance |
| `EntityResponse` | Entity output |

### T3.3: Fact Schemas

**File:** `src/monitor_data/schemas/facts.py`

| Schema | Purpose |
|--------|---------|
| `FactCreate` | Create fact input |
| `FactResponse` | Fact output |
| `EventCreate` | Create event input |
| `EventResponse` | Event output |

### T3.4: Scene Schemas

**File:** `src/monitor_data/schemas/scenes.py`

| Schema | Purpose |
|--------|---------|
| `SceneCreate` | Create scene input |
| `SceneResponse` | Scene output |
| `TurnCreate` | Append turn input |
| `TurnResponse` | Turn output |

### T3.5: Proposal Schemas

**File:** `src/monitor_data/schemas/proposals.py`

| Schema | Purpose |
|--------|---------|
| `ProposedChangeCreate` | Create proposal |
| `ProposedChangeResponse` | Proposal output |
| `ProposalEvaluate` | Accept/reject input |

### T3.6: Memory Schemas

**File:** `src/monitor_data/schemas/memories.py`

| Schema | Purpose |
|--------|---------|
| `CharacterMemoryCreate` | Create memory |
| `CharacterMemoryResponse` | Memory output |
| `CharacterSheetCreate` | Create character sheet |
| `CharacterSheetResponse` | Character sheet output |

### T3.7: Source Schemas

**File:** `src/monitor_data/schemas/sources.py`

| Schema | Purpose |
|--------|---------|
| `SourceCreate` | Create source |
| `SourceResponse` | Source output |
| `DocumentCreate` | Create document |
| `DocumentResponse` | Document output |
| `SnippetCreate` | Create snippet |
| `SnippetResponse` | Snippet output |

### T3.8: Query Schemas

**File:** `src/monitor_data/schemas/queries.py`

| Schema | Purpose |
|--------|---------|
| `UniverseFilter` | Filter universes |
| `EntityFilter` | Filter entities |
| `FactFilter` | Filter facts |
| `SceneFilter` | Filter scenes |

---

## Phase 4: Neo4j Tools

### T4.1: Universe Operations

**File:** `src/monitor_data/tools/neo4j_tools.py`

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_universe` | CanonKeeper | M-4 |
| `neo4j_get_universe` | Any | M-6 |
| `neo4j_list_universes` | Any | M-5 |
| `neo4j_update_universe` | CanonKeeper | M-7 |
| `neo4j_delete_universe` | CanonKeeper | M-8 |

### T4.2: Entity Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_entity_axiomatica` | CanonKeeper | I-3 |
| `neo4j_create_entity_concreta` | CanonKeeper | M-12, M-13 |
| `neo4j_get_entity` | Any | M-16 |
| `neo4j_list_entities` | Any | Q-3 |
| `neo4j_update_entity` | CanonKeeper | M-19 |
| `neo4j_set_state_tags` | CanonKeeper | P-4 |

### T4.3: Relationship Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_relationship` | CanonKeeper | M-21 |
| `neo4j_get_relationships` | Any | M-21, Q-6 |
| `neo4j_delete_relationship` | CanonKeeper | M-21 |

### T4.4: Fact Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_fact` | CanonKeeper | P-8, M-26 |
| `neo4j_get_fact` | Any | Q-4 |
| `neo4j_list_facts` | Any | Q-4 |
| `neo4j_retcon_fact` | CanonKeeper | M-27 |

### T4.5: Event Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_event` | CanonKeeper | P-8 |
| `neo4j_get_event` | Any | Q-5 |
| `neo4j_list_events` | Any | Q-5 |
| `neo4j_link_causal` | CanonKeeper | P-8 |

### T4.6: Story Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_story` | CanonKeeper, Orchestrator | P-1 |
| `neo4j_get_story` | Any | M-10 |
| `neo4j_list_stories` | Any | M-9 |
| `neo4j_update_story` | CanonKeeper | M-11 |

### T4.7: Source Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_source` | CanonKeeper | I-1 |
| `neo4j_get_source` | Any | I-5 |
| `neo4j_list_sources` | Any | I-5 |
| `neo4j_link_evidence` | CanonKeeper | P-8, I-3 |

### T4.8: Axiom Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_axiom` | CanonKeeper | M-23 |
| `neo4j_get_axiom` | Any | M-24 |
| `neo4j_list_axioms` | Any | M-24 |

### T4.9: Plot Thread Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `neo4j_create_plot_thread` | CanonKeeper | P-1 |
| `neo4j_update_plot_thread` | CanonKeeper | P-8 |
| `neo4j_list_plot_threads` | Any | M-10 |

---

## Phase 5: MongoDB Tools

### T5.1: Scene Operations

**File:** `src/monitor_data/tools/mongodb_tools.py`

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_create_scene` | Orchestrator | P-2 |
| `mongodb_get_scene` | Any | P-3 |
| `mongodb_update_scene` | Orchestrator | P-8 |
| `mongodb_list_scenes` | Any | M-28 |

### T5.2: Turn Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_append_turn` | Narrator | P-3 |
| `mongodb_get_turns` | Any | P-3, P-7 |
| `mongodb_undo_turn` | Orchestrator | P-7 |

### T5.3: Proposal Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_create_proposal` | Narrator, Resolver | P-4, I-3 |
| `mongodb_get_proposals` | Any | P-8, I-4 |
| `mongodb_update_proposal` | CanonKeeper | P-8 |
| `mongodb_list_pending_proposals` | Any | I-4 |

### T5.4: Resolution Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_create_resolution` | Resolver | P-4 |
| `mongodb_get_resolution` | Any | P-3 |

### T5.5: Memory Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_create_memory` | MemoryManager | P-5 |
| `mongodb_get_memories` | Any | M-22 |
| `mongodb_update_memory` | MemoryManager | M-22 |
| `mongodb_search_memories` | Any | P-5, P-11 |

### T5.6: Character Sheet Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_create_character_sheet` | Orchestrator | M-13 |
| `mongodb_get_character_sheet` | Any | M-16, P-7 |
| `mongodb_update_character_sheet` | Orchestrator, CanonKeeper | M-19 |

### T5.7: Document Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_create_document` | Indexer | I-1 |
| `mongodb_get_document` | Any | I-5 |
| `mongodb_list_documents` | Any | I-5 |
| `mongodb_update_document_status` | Indexer | I-2 |

### T5.8: Snippet Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_create_snippets` | Indexer | I-2 |
| `mongodb_get_snippets` | Any | I-4 |

### T5.9: Story Outline Operations

| Tool | Authority | Use Case |
|------|-----------|----------|
| `mongodb_create_story_outline` | Orchestrator | P-1 |
| `mongodb_get_story_outline` | Any | M-10 |
| `mongodb_update_story_outline` | Orchestrator | M-11 |

---

## Phase 6: Qdrant Tools

### T6.1: Vector Operations

**File:** `src/monitor_data/tools/qdrant_tools.py`

| Tool | Authority | Use Case |
|------|-----------|----------|
| `qdrant_embed_scene` | Indexer | P-8 |
| `qdrant_embed_memory` | Indexer | P-5 |
| `qdrant_embed_snippet` | Indexer | I-2 |
| `qdrant_search` | Any | Q-1 |
| `qdrant_search_memories` | Any | P-5, P-11 |
| `qdrant_delete_vectors` | Indexer | - |

---

## Phase 7: Composite Tools

### T7.1: Cross-Database Operations

**File:** `src/monitor_data/tools/composite_tools.py`

| Tool | Authority | Use Case |
|------|-----------|----------|
| `composite_get_entity_full` | Any | M-16, Q-2 |
| `composite_get_scene_context` | Any | P-3 |

### T7.2: Dice Module

**File:** `src/monitor_data/tools/dice.py`

**Use Case:** P-9, P-4, P-10

**Notation:**
```
[count]d[sides][modifier][keep]

count    = number of dice (default 1)
sides    = die type (4, 6, 8, 10, 12, 20, 100)
modifier = +N or -N
keep     = kh[N] (keep highest N) or kl[N] (keep lowest N)
```

**Schema:**

```python
@dataclass
class DiceRoll:
    formula: str              # Original formula
    individual_rolls: list[int]  # All dice rolled
    kept_rolls: list[int]     # Dice kept after kh/kl
    modifier: int             # Sum of modifiers
    total: int                # Final result

class DiceNotation(BaseModel):
    count: int = 1
    sides: int
    modifier: int = 0
    keep_highest: int | None = None
    keep_lowest: int | None = None
```

**Functions:**

| Function | Description |
|----------|-------------|
| `parse_dice_formula(formula: str) -> DiceNotation` | Parse "2d6+3kh1" |
| `roll_dice(formula: str) -> DiceRoll` | Execute roll |
| `roll_single(sides: int) -> int` | Roll one die |
| `evaluate_advantage(formula: str) -> DiceRoll` | Handle "adv" shorthand |
| `evaluate_disadvantage(formula: str) -> DiceRoll` | Handle "dis" shorthand |

**Tool:**

| Tool | Authority | Use Case |
|------|-----------|----------|
| `dice_roll` | Any | P-9 |

**Examples:**

| Formula | Description | Algorithm |
|---------|-------------|-----------|
| `d20` | Roll 1d20 | roll(20) |
| `2d6` | Roll 2d6, sum | sum(roll(6), roll(6)) |
| `1d20+5` | Roll + modifier | roll(20) + 5 |
| `4d6kh3` | Roll 4d6, keep highest 3 | sorted(rolls)[-3:].sum() |
| `2d20kl1` | Roll 2d20, keep lowest | min(roll(20), roll(20)) |
| `1d20adv` | Advantage | max(roll(20), roll(20)) |
| `1d20dis` | Disadvantage | min(roll(20), roll(20)) |
| `8d6` | Multiple dice | sum([roll(6) for _ in 8]) |

**Regex Pattern:**
```python
DICE_PATTERN = r'^(\d+)?d(\d+)([+-]\d+)?(kh\d+|kl\d+|adv|dis)?$'
```

---

## Phase 8: Middleware

### T8.1: Authority Enforcement

**File:** `src/monitor_data/middleware/auth.py`

```python
AUTHORITY_MATRIX = {
    "neo4j_create_fact": ["CanonKeeper"],
    "neo4j_create_entity_concreta": ["CanonKeeper"],
    "neo4j_create_story": ["CanonKeeper", "Orchestrator"],
    "mongodb_create_scene": ["Orchestrator"],
    "mongodb_append_turn": ["Narrator"],
    # ... etc
}

def check_authority(tool_name: str, agent_type: str) -> bool:
    allowed = AUTHORITY_MATRIX.get(tool_name, [])
    return agent_type in allowed or not allowed
```

### T8.2: Request Validation

**File:** `src/monitor_data/middleware/validation.py`

```python
def validate_request(tool_name: str, params: dict) -> ValidationResult:
    # 1. Get schema for tool
    # 2. Validate params against schema
    # 3. Return validation result
```

---

## Phase 9: MCP Server

### T9.1: Server Entry Point

**File:** `src/monitor_data/server.py`

```python
from mcp import Server

server = Server("monitor-data-layer")

# Register all tools
@server.tool()
async def neo4j_create_universe(params: UniverseCreate) -> UniverseResponse:
    ...

# Run server
if __name__ == "__main__":
    server.run()
```

### T9.2: Tool Registration

1. Import all tool modules
2. Register each tool with MCP server
3. Apply middleware (auth, validation)
4. Handle errors uniformly

---

## Phase 10: Testing

### T10.1: Unit Tests

```
tests/
├── conftest.py           # Fixtures: mock clients, test data
├── test_db/
│   ├── test_neo4j.py
│   ├── test_mongodb.py
│   ├── test_qdrant.py
│   └── test_minio.py
├── test_tools/
│   ├── test_neo4j_tools.py
│   ├── test_mongodb_tools.py
│   └── test_qdrant_tools.py
├── test_schemas/
│   └── test_validation.py
└── test_middleware/
    ├── test_auth.py
    └── test_validation.py
```

### T10.2: Integration Tests

- Test tool chains (create entity → create fact → link evidence)
- Test authority enforcement
- Test cross-database operations

---

## Completion Checklist

```
[ ] T1: Package setup
[ ] T2: Database clients (5)
[ ] T3: Pydantic schemas (8 files)
[ ] T4: Neo4j tools (41)
[ ] T5: MongoDB tools (18)
[ ] T6: Qdrant tools (6)
[ ] T7.1: Composite tools (2)
[ ] T7.2: Dice module (1 tool, 5 functions)
[ ] T8: Middleware (2)
[ ] T9: MCP server
[ ] T10: Tests
```

---

## Dependencies

```
NONE (Layer 1 has no internal dependencies)
EXTERNAL: neo4j, pymongo, qdrant-client, minio, opensearch-py, pydantic, mcp
```
