---
description: Implement a data-layer feature (Layer 1)
---

# Implement Data Layer Feature

Step-by-step guide for implementing features in Layer 1 (data-layer).

## What Goes in Data Layer

- Database client methods (Neo4j, MongoDB, Qdrant, MinIO, OpenSearch)
- MCP tool implementations
- Pydantic schemas for data validation
- Authority/validation middleware

## What Does NOT Go Here

- AI/LLM logic (that's Layer 2: agents)
- User interface code (that's Layer 3: cli)
- Business logic beyond data access

## Steps

### 1. Review API Specification

Read `docs/architecture/DATA_LAYER_API.md` to understand:
- Existing API operations
- Naming conventions
- Request/response patterns

### 2. Create Pydantic Schema

Location: `packages/data-layer/src/monitor_data/schemas/`

Example:
```python
# packages/data-layer/src/monitor_data/schemas/entities.py
from pydantic import BaseModel, Field

class EntityCreate(BaseModel):
    """Schema for creating a new entity."""
    name: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(..., pattern="^(character|location|object|faction)$")
    universe_id: str = Field(..., description="UUID of parent universe")
    properties: dict[str, Any] = Field(default_factory=dict)
```

### 3. Implement Database Client Method

Location: `packages/data-layer/src/monitor_data/db/`

Example for Neo4j:
```python
# packages/data-layer/src/monitor_data/db/neo4j.py
async def create_entity(self, data: EntityCreate) -> EntityResponse:
    """Create a new entity in Neo4j."""
    query = """
    CREATE (e:EntityInstance {
        id: $id,
        name: $name,
        entity_type: $entity_type,
        universe_id: $universe_id,
        properties: $properties,
        created_at: datetime()
    })
    RETURN e
    """
    result = await self.session.run(query, **data.dict(), id=str(uuid4()))
    # ... process result
```

### 4. Create MCP Tool

Location: `packages/data-layer/src/monitor_data/tools/`

Example:
```python
# packages/data-layer/src/monitor_data/tools/neo4j_tools.py
@mcp_tool("neo4j_create_entity")
async def neo4j_create_entity(request: EntityCreate) -> EntityResponse:
    """
    Create a new entity in Neo4j.
    
    Authority: CanonKeeper only
    """
    client = get_neo4j_client()
    return await client.create_entity(request)
```

### 5. Add Authority Check

Location: `packages/data-layer/src/monitor_data/middleware/auth.py`

```python
AUTHORITY_MATRIX = {
    # ... existing entries
    "neo4j_create_entity": ["CanonKeeper"],  # Only CanonKeeper can create entities
    "neo4j_get_entity": ["*"],              # Any agent can read
}
```

**Authority levels**:
- `["CanonKeeper"]` - Only CanonKeeper
- `["CanonKeeper", "Orchestrator"]` - Multiple agents
- `["*"]` - Any agent (read-only operations)

### 6. Write Tests

Location: `packages/data-layer/tests/test_tools/` or `tests/test_db/`

Example:
```python
# packages/data-layer/tests/test_tools/test_neo4j_tools.py
import pytest
from monitor_data.schemas.entities import EntityCreate
from monitor_data.tools.neo4j_tools import neo4j_create_entity

@pytest.mark.unit
async def test_create_entity_success():
    """Test successful entity creation."""
    request = EntityCreate(
        name="Test Entity",
        entity_type="character",
        universe_id="test-universe-id"
    )
    response = await neo4j_create_entity(request)
    assert response.name == "Test Entity"
    assert response.id is not None
```

### 7. Update Documentation

After implementation, update:
- `docs/architecture/DATA_LAYER_API.md` - Add your new operation
- `docs/architecture/MCP_TRANSPORT.md` - Add MCP tool definition
- `docs/architecture/VALIDATION_SCHEMAS.md` - Add your schemas

## Testing Requirements

**Unit tests** (required):
- Schema validation (valid and invalid inputs)
- Database client method (mocked database)
- MCP tool (mocked client)

**Integration tests** (optional):
- End-to-end with real database
- Mark with `@pytest.mark.integration`

## Authority Guidelines

| Operation Type | Authority |
|----------------|-----------|
| Create/Update/Delete in Neo4j | `["CanonKeeper"]` |
| Read from Neo4j | `["*"]` |
| Create/Update in MongoDB | Depends on collection |
| Composite operations | Most restrictive participant |

## Common Patterns

**Read operation** (any agent):
```python
@mcp_tool("neo4j_get_entity")
async def neo4j_get_entity(entity_id: str) -> EntityResponse:
    # Authority: ["*"] in middleware
```

**Write operation** (CanonKeeper only):
```python
@mcp_tool("neo4j_create_fact")
async def neo4j_create_fact(request: FactCreate) -> FactResponse:
    # Authority: ["CanonKeeper"] in middleware
```

**Composite operation** (most restrictive):
```python
@mcp_tool("composite_canonize_scene")
async def composite_canonize_scene(scene_id: str) -> CanonizationResult:
    # Writes to Neo4j, so Authority: ["CanonKeeper"]
```

## Before Committing

Run checks:
```bash
# Layer dependency check
python scripts/check_layer_dependencies.py

# Tests
cd packages/data-layer && pytest

# Linting
ruff check packages/data-layer
black --check packages/data-layer
mypy packages/data-layer
```

## Next Steps

After data-layer implementation:
1. Implement agent logic: `/implement-agent`
2. Implement CLI: `/implement-cli`
3. Run full test suite: `/run-tests`
4. Pre-commit checks: `/pre-commit-checks`
