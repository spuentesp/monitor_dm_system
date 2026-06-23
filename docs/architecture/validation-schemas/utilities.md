## 6. Validation Utilities

### 6.1 Custom Validators

```python
from pydantic import field_validator

class EvidenceRefValidator:
    """Validate evidence reference format."""

    @field_validator('evidence_refs')
    @classmethod
    def validate_evidence_refs(cls, v: list[str]) -> list[str]:
        """Ensure evidence refs are in correct format: 'type:uuid'."""
        import re
        pattern = re.compile(r'^(source|turn|scene|snippet|rule):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

        for ref in v:
            if not pattern.match(ref):
                raise ValueError(f'Invalid evidence_ref format: {ref}. Expected "type:uuid"')

        return v
```

---

### 6.2 UUID Validation

```python
from uuid import UUID as StdUUID

def validate_uuid(value: str) -> UUID:
    """Validate UUID string."""
    try:
        return StdUUID(value)
    except ValueError as e:
        raise ValueError(f'Invalid UUID format: {value}') from e
```

---

## 7. Error Models

### 7.1 API Error Response

```python
class ErrorDetail(BaseModel):
    """Error detail structure."""
    code: int
    message: str
    data: dict | None = None

class APIError(BaseModel):
    """API error response."""
    error: ErrorDetail

# Standard errors
class UnauthorizedError(APIError):
    """Agent lacks authority."""
    error: ErrorDetail = Field(
        default_factory=lambda: ErrorDetail(
            code=-32001,
            message="Unauthorized: Agent lacks authority for this operation"
        )
    )

class NotFoundError(APIError):
    """Resource not found."""
    error: ErrorDetail = Field(
        default_factory=lambda: ErrorDetail(
            code=-32002,
            message="Not Found: Requested resource does not exist"
        )
    )

class ValidationError(APIError):
    """Validation failed."""
    error: ErrorDetail = Field(
        default_factory=lambda: ErrorDetail(
            code=-32003,
            message="Validation Error: Request data is invalid"
        )
    )
```

---

## 8. Agent Authority Matrix

This matrix defines which agents can execute which operations.

### 8.1 Neo4j Write Operations

| Operation | Allowed Agents | Notes |
|-----------|----------------|-------|
| CreateUniverse | CanonKeeper | World creation |
| CreateMultiverse | CanonKeeper | World creation |
| CreateStory | CanonKeeper | Canonical write |
| CreateEntity | CanonKeeper | All entity types |
| UpdateEntity | CanonKeeper | Property/state changes |
| CreateFact | CanonKeeper | Canonization only |
| CreateEvent | CanonKeeper | Canonization only |
| CreateAxiom | CanonKeeper | World rules |
| CreateSource | CanonKeeper, IngestionPipeline | Document registration |
| CreateRelationship | CanonKeeper | Entity relationships |
| LinkEvidence | CanonKeeper | SUPPORTED_BY edges |

### 8.2 MongoDB Write Operations

| Operation | Allowed Agents | Notes |
|-----------|----------------|-------|
| CreateScene | CanonKeeper, Narrator | Scene lifecycle |
| UpdateScene | CanonKeeper, Narrator | Status changes |
| FinalizeScene | CanonKeeper | After canonization |
| AppendTurn | All | Turn transcription |
| UndoTurn | All | Meta-command |
| CreateProposedChange | All | Proposing canonical changes |
| EvaluateProposal | CanonKeeper | Accept/reject |
| CreateMemory | All | Character memories |
| UpdateMemory | All | Memory updates |
| CreateDocument | Indexer, IngestionPipeline | Document ingestion |
| CreateSnippet | Indexer | Text chunking |
| CreateStoryOutline | WorldArchitect, Narrator | Story structure |
| CreateResolution | Resolver, CanonKeeper | Dice/action results |

### 8.3 Qdrant Write Operations

| Operation | Allowed Agents | Notes |
|-----------|----------------|-------|
| EmbedScene | Indexer | Scene vectorization |
| EmbedMemory | Indexer | Memory vectorization |
| EmbedSnippet | Indexer | Document vectorization |
| DeleteVectors | Indexer | Cleanup |

### 8.4 Read Operations

All read operations are available to **all agents**.

### 8.5 Authority Enforcement

```python
class AuthorityEnforcer:
    """Middleware for authority enforcement."""

    WRITE_PERMISSIONS = {
        "neo4j_create_fact": ["CanonKeeper"],
        "neo4j_create_entity": ["CanonKeeper"],
        "neo4j_create_story": ["CanonKeeper"],
        "neo4j_create_source": ["CanonKeeper", "IngestionPipeline"],
        "mongodb_create_scene": ["CanonKeeper", "Narrator"],
        "mongodb_append_turn": ["*"],  # All agents may append turns
        "mongodb_create_proposed_change": ["*"],  # Any agent may propose
        "mongodb_update_proposal": ["CanonKeeper"],
        "mongodb_create_memory": ["*"],  # Open — any agent may record memories
        "mongodb_create_story_outline": ["WorldArchitect", "Narrator"],
        "mongodb_create_resolution": ["Resolver", "CanonKeeper"],
        "qdrant_upsert": ["Indexer"],
        # ... see auth.py for full matrix
    }

    def check_authority(self, agent: str, operation: str) -> bool:
        allowed = self.WRITE_PERMISSIONS.get(operation, [])
        if not allowed:  # Read operation
            return True
        return agent in allowed
```

---

## 9. Usage Examples

### 9.1 Creating an Entity

```python
from monitor.schemas import EntityInstanceCreate, EntityType, Authority

# Create request
request = EntityInstanceCreate(
    universe_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
    name="Gandalf the Grey",
    entity_type=EntityType.CHARACTER,
    description="Istari wizard sent to Middle-earth",
    properties={
        "role": "NPC",
        "archetype": "wizard"
    },
    state_tags=["alive", "traveling"],
    confidence=1.0,
    authority=Authority.SOURCE,
    evidence_refs=["source:550e8400-e29b-41d4-a716-446655440001"]
)

# Validate automatically via Pydantic
assert request.confidence == 1.0
assert "alive" in request.state_tags

# Serialize to JSON for MCP call
request_json = request.model_dump_json()
```

---

### 9.2 Querying Entities

```python
from monitor.schemas import EntityQuery, EntityType, StateTagFilter

# Build query
query = EntityQuery(
    universe_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
    entity_type=EntityType.CHARACTER,
    state_tags=StateTagFilter(
        all_of=["alive"],
        none_of=["dead", "unconscious"]
    ),
    limit=50
)

# Validation happens automatically
# Query for living characters
```

---

### 9.3 Proposing a Change

```python
from monitor.schemas import ProposedChangeCreate, ProposalType, EvidenceRef

proposal = ProposedChangeCreate(
    scene_id=UUID("scene-uuid"),
    turn_id=UUID("turn-uuid"),
    type=ProposalType.STATE_CHANGE,
    content={
        "entity_id": str(UUID("gandalf-uuid")),
        "tag": "wounded",
        "action": "add"
    },
    evidence=[
        EvidenceRef(type="turn", ref_id=UUID("turn-uuid"))
    ],
    confidence=0.9,
    authority=Authority.GM
)

# Automatically validated
assert proposal.type == ProposalType.STATE_CHANGE
assert len(proposal.evidence) >= 1
```

---

## 9. Schema Generation

### 9.1 Generate JSON Schema

```python
from monitor.schemas import EntityInstanceCreate

# Generate JSON Schema for MCP tool registration
schema = EntityInstanceCreate.model_json_schema()

# Output:
{
  "type": "object",
  "properties": {
    "universe_id": {"type": "string", "format": "uuid"},
    "name": {"type": "string", "minLength": 1, "maxLength": 200},
    ...
  },
  "required": ["universe_id", "name", ...]
}
```

---

### 9.2 Generate OpenAPI Spec

```python
from fastapi import FastAPI
from monitor.schemas import *

app = FastAPI()

@app.post("/neo4j/entity", response_model=EntityResponse)
def create_entity(request: EntityInstanceCreate):
    ...

# FastAPI auto-generates OpenAPI spec from Pydantic models
```

---

## 10. Implementation Checklist

- [ ] Create base enums and metadata models
- [ ] Implement Neo4j request/response models
- [ ] Implement MongoDB request/response models
- [ ] Implement Qdrant request/response models
- [ ] Implement composite operation models
- [ ] Add custom validators (UUID, evidence_refs, etc.)
- [ ] Add error models
- [ ] Generate JSON Schema for all models
- [ ] Create unit tests for validation logic
- [ ] Document all model fields with descriptions
- [ ] Set up JSON schema export for MCP tools

---

## References

- [DATA_LAYER_API.md](DATA_LAYER_API.md) - API operation specifications
- [MCP_TRANSPORT.md](MCP_TRANSPORT.md) - MCP tool definitions
- [ONTOLOGY.md](../ontology/ONTOLOGY.md) - Data model specification
- Pydantic Documentation: https://docs.pydantic.dev/
