# MONITOR Validation Schemas

*Pydantic models for data validation across the MONITOR system.*

---

## Overview

This document defines **Pydantic models** for all data structures in MONITOR. These schemas:

1. **Validate** API requests and responses
2. **Type-check** data at runtime
3. **Document** data structures with examples
4. **Generate** OpenAPI/JSON Schema for MCP tools

**Key principle:** All data crossing layer boundaries must be validated.

---

## 1. Base Models

### 1.1 Common Enums

```python
from enum import Enum
from typing import Literal

class CanonLevel(str, Enum):
    """Canonization status for most canonical nodes."""
    PROPOSED = "proposed"
    CANON = "canon"
    RETCONNED = "retconned"

class SourceCanonLevel(str, Enum):
    """Canonization status for Source nodes only.

    Sources use 'authoritative' instead of 'retconned' because
    source documents themselves aren't revised—only facts derived
    from them can be retconned.
    """
    PROPOSED = "proposed"
    CANON = "canon"
    AUTHORITATIVE = "authoritative"

class Authority(str, Enum):
    """Who asserted this data (full set for Facts, Events, Entities)."""
    SOURCE = "source"
    GM = "gm"
    PLAYER = "player"
    SYSTEM = "system"

class AxiomAuthority(str, Enum):
    """Authority for Axiom nodes only (excludes 'player').

    World rules (physics, magic systems) cannot be created by player
    actions—only by GM declaration or authoritative sources.
    """
    SOURCE = "source"
    GM = "gm"
    SYSTEM = "system"

class EntityType(str, Enum):
    """Entity classification."""
    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"
    ORGANIZATION = "organization"

class EntityClass(str, Enum):
    """Axiomatic vs Concrete."""
    AXIOMATICA = "EntityArchetype"
    CONCRETA = "EntityInstance"

class StoryType(str, Enum):
    """Story type."""
    CAMPAIGN = "campaign"
    ARC = "arc"
    EPISODE = "episode"
    ONE_SHOT = "one_shot"

class SceneStatus(str, Enum):
    """Scene workflow status."""
    ACTIVE = "active"
    FINALIZING = "finalizing"
    COMPLETED = "completed"

class ProposalStatus(str, Enum):
    """Proposed change status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class ProposalType(str, Enum):
    """Type of proposed change."""
    FACT = "fact"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    STATE_CHANGE = "state_change"
    EVENT = "event"

class Speaker(str, Enum):
    """Who is speaking in a turn."""
    USER = "user"
    GM = "gm"
    ENTITY = "entity"
```

---

### 1.2 Base Canonization Metadata

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from uuid import UUID

class CanonicalMetadata(BaseModel):
    """Base metadata for all canonical nodes."""
    canon_level: CanonLevel
    confidence: float = Field(ge=0.0, le=1.0)
    authority: Authority
    created_at: datetime

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence must be between 0.0 and 1.0')
        return v
```

---

## 2. Neo4j Models

### 2.1 Entity Models

#### EntityArchetypeCreate

```python
class EntityArchetypeCreate(BaseModel):
    """Request to create an EntityArchetype."""
    universe_id: UUID
    name: str = Field(min_length=1, max_length=200)
    entity_type: EntityType
    description: str = Field(min_length=1, max_length=2000)
    properties: dict = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    authority: Authority
    evidence_refs: list[str] = Field(min_items=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "universe_id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Wizard",
                    "entity_type": "character",
                    "description": "Practitioner of arcane magic",
                    "properties": {
                        "archetype": "wizard",
                        "default_abilities": ["spellcasting", "ritual magic"]
                    },
                    "confidence": 1.0,
                    "authority": "source",
                    "evidence_refs": ["source:550e8400-e29b-41d4-a716-446655440001"]
                }
            ]
        }
    }
```

---

#### EntityInstanceCreate

```python
class EntityInstanceCreate(BaseModel):
    """Request to create an EntityInstance."""
    universe_id: UUID
    name: str = Field(min_length=1, max_length=200)
    entity_type: EntityType
    description: str = Field(min_length=1, max_length=2000)
    properties: dict = Field(default_factory=dict)
    state_tags: list[str] = Field(default_factory=list)
    derives_from: UUID | None = None  # Optional archetype reference
    confidence: float = Field(ge=0.0, le=1.0)
    authority: Authority
    evidence_refs: list[str] = Field(min_items=1)

    @field_validator('state_tags')
    @classmethod
    def validate_state_tags(cls, v: list[str]) -> list[str]:
        # Ensure no duplicates
        if len(v) != len(set(v)):
            raise ValueError('state_tags must not contain duplicates')
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "universe_id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Gandalf the Grey",
                    "entity_type": "character",
                    "description": "Istari wizard sent to Middle-earth",
                    "properties": {
                        "role": "NPC",
                        "archetype": "wizard"
                    },
                    "state_tags": ["alive", "traveling", "wielding_staff"],
                    "derives_from": "wizard-archetype-uuid",
                    "confidence": 1.0,
                    "authority": "source",
                    "evidence_refs": ["source:550e8400-e29b-41d4-a716-446655440001"]
                }
            ]
        }
    }
```

---

#### EntityCreate (Union)

```python
from typing import Annotated
from pydantic import Discriminator

class EntityCreate(BaseModel):
    """Polymorphic entity creation request."""
    entity_class: EntityClass
    data: Annotated[
        EntityArchetypeCreate | EntityInstanceCreate,
        Discriminator('entity_class')
    ]
```

---

#### EntityResponse

```python
class EntityResponse(BaseModel):
    """Response from entity creation."""
    entity_id: UUID
    canon_level: CanonLevel
    created_at: datetime

class EntityFull(CanonicalMetadata):
    """Complete entity data."""
    id: UUID
    entity_class: EntityClass
    universe_id: UUID
    name: str
    entity_type: EntityType
    description: str
    properties: dict
    state_tags: list[str] = Field(default_factory=list)  # Only for Instance
    updated_at: datetime | None = None  # Only for Instance
```

---

#### EntityStateUpdate

```python
class StateTagChanges(BaseModel):
    """State tag modifications."""
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)

    @field_validator('add', 'remove')
    @classmethod
    def no_duplicates(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError('no duplicate tags allowed')
        return v

class EntityStateUpdate(BaseModel):
    """Update entity state tags."""
    entity_id: UUID
    state_tag_changes: StateTagChanges
    authority: Literal[Authority.GM, Authority.PLAYER, Authority.SYSTEM]
    evidence_refs: list[str] = Field(min_items=1)

class EntityStateUpdateResponse(BaseModel):
    """Response from state update."""
    entity_id: UUID
    new_state_tags: list[str]
    fact_ids: list[UUID]  # Facts documenting the changes
```

---

### 2.2 Fact & Event Models

#### FactCreate

```python
class FactCreate(BaseModel):
    """Create a canonical fact."""
    universe_id: UUID
    statement: str = Field(min_length=1, max_length=1000)
    time_ref: datetime | None = None
    duration: int | None = Field(None, ge=0)  # seconds
    involved_entity_ids: list[UUID] = Field(min_items=1)
    confidence: float = Field(ge=0.0, le=1.0)
    authority: Authority
    evidence_refs: list[str] = Field(min_items=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "universe_id": "550e8400-e29b-41d4-a716-446655440000",
                    "statement": "Gandalf defeated the Balrog",
                    "time_ref": "3019-01-15T12:00:00Z",
                    "involved_entity_ids": [
                        "gandalf-uuid",
                        "balrog-uuid"
                    ],
                    "confidence": 1.0,
                    "authority": "source",
                    "evidence_refs": ["source:lotr-fellowship"]
                }
            ]
        }
    }

class FactResponse(BaseModel):
    """Response from fact creation."""
    fact_id: UUID
    canon_level: CanonLevel
    created_at: datetime
```

---

#### EventCreate

```python
class EventCreate(BaseModel):
    """Create a canonical event."""
    scene_id: UUID | None = None
    universe_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    time_ref: datetime | None = None
    severity: int = Field(ge=0, le=10)
    involved_entity_ids: list[UUID] = Field(min_items=1)
    causes_event_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    authority: Authority
    evidence_refs: list[str] = Field(min_items=1)

class EventResponse(BaseModel):
    """Response from event creation."""
    event_id: UUID
    canon_level: CanonLevel
    created_at: datetime
```

---

### 2.3 Story & Source Models

#### StoryCreate

```python
class StoryCreate(BaseModel):
    """Create a canonical story container."""
    universe_id: UUID
    title: str = Field(min_length=1, max_length=200)
    story_type: StoryType
    theme: str | None = None
    premise: str | None = None
    parent_story_id: UUID | None = None
    start_time_ref: datetime | None = None

class StoryResponse(BaseModel):
    """Response from story creation."""
    story_id: UUID
    created_at: datetime
```

---

#### SourceCreate

```python
class SourceType(str, Enum):
    MANUAL = "manual"
    RULEBOOK = "rulebook"
    LORE = "lore"
    SESSION = "session"

class SourceCreate(BaseModel):
    """Create a canonical source."""
    universe_id: UUID
    doc_id: str  # MongoDB reference
    title: str = Field(min_length=1, max_length=200)
    edition: str | None = None
    provenance: str | None = None  # ISBN, URL, etc.
    source_type: SourceType
    canon_level: Literal[CanonLevel.PROPOSED, CanonLevel.CANON, "authoritative"]

class SourceResponse(BaseModel):
    """Response from source creation."""
    source_id: UUID
    created_at: datetime
```

---

### 2.4 Query Models

#### EntityQuery

```python
class StateTagFilter(BaseModel):
    """State tag filtering."""
    all_of: list[str] = Field(default_factory=list)
    any_of: list[str] = Field(default_factory=list)
    none_of: list[str] = Field(default_factory=list)

class EntityQuery(BaseModel):
    """Query entities by filters."""
    universe_id: UUID | None = None
    entity_type: EntityType | None = None
    entity_class: EntityClass | None = None
    canon_level: CanonLevel | None = None
    state_tags: StateTagFilter | None = None
    name_pattern: str | None = None
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)

class EntityQueryResponse(BaseModel):
    """Response from entity query."""
    entities: list[EntityFull]
    total: int
```

---

#### FactQuery

```python
class TimeRange(BaseModel):
    """Time range filter."""
    start: datetime
    end: datetime

class FactQuery(BaseModel):
    """Query facts by filters."""
    universe_id: UUID | None = None
    entity_id: UUID | None = None
    time_range: TimeRange | None = None
    canon_level: CanonLevel | None = None
    authority: Authority | None = None
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)

class FactFull(CanonicalMetadata):
    """Complete fact data."""
    id: UUID
    universe_id: UUID
    statement: str
    time_ref: datetime | None
    duration: int | None
    replaces: UUID | None

class FactQueryResponse(BaseModel):
    """Response from fact query."""
    facts: list[FactFull]
    total: int
```

---

## 3. MongoDB Models

### 3.1 Scene Models

#### SceneCreate

```python
class SceneCreate(BaseModel):
    """Create a new scene."""
    story_id: UUID
    universe_id: UUID
    title: str = Field(min_length=1, max_length=200)
    purpose: str | None = None
    order: int | None = Field(default=None, ge=0)
    location_ref: UUID | None = None  # EntityInstance location
    participating_entities: list[UUID] = Field(default_factory=list)

class SceneResponse(BaseModel):
    """Response from scene creation."""
    scene_id: UUID
    status: Literal[SceneStatus.ACTIVE]
    created_at: datetime
```

---

#### TurnAppend

```python
class TurnAppend(BaseModel):
    """Append a turn to a scene."""
    scene_id: UUID
    speaker: Speaker
    entity_id: UUID | None = None  # Required if speaker is 'entity'
    text: str = Field(min_length=1, max_length=10000)
    resolution_ref: UUID | None = None

    @field_validator('entity_id')
    @classmethod
    def entity_id_required_for_entity_speaker(cls, v, info):
        if info.data.get('speaker') == Speaker.ENTITY and v is None:
            raise ValueError('entity_id required when speaker is "entity"')
        return v

class TurnResponse(BaseModel):
    """Response from turn append."""
    turn_id: UUID
    timestamp: datetime

class Turn(BaseModel):
    """Turn data structure."""
    turn_id: UUID
    speaker: Speaker
    entity_id: UUID | None = None
    text: str
    timestamp: datetime
    resolution_ref: UUID | None = None
```

---

#### SceneGet

```python
class SceneGet(BaseModel):
    """Get scene request."""
    scene_id: UUID
    include_turns: bool = True
    include_proposals: bool = False
    turn_limit: int | None = None  # Last N turns

class SceneFull(BaseModel):
    """Complete scene data."""
    scene_id: UUID
    story_id: UUID
    universe_id: UUID
    title: str
    status: SceneStatus
    order: int | None = None
    location_ref: UUID | None
    participating_entities: list[UUID]
    turns: list[Turn] = Field(default_factory=list)
    proposed_changes: list[UUID] = Field(default_factory=list)
    canonical_outcomes: list[UUID] = Field(default_factory=list)
    summary: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
```

---

#### SceneFinalize

```python
class SceneFinalize(BaseModel):
    """Finalize a scene."""
    scene_id: UUID
    canonical_outcome_ids: list[UUID]  # Neo4j Fact/Event IDs
    summary: str = Field(min_length=1, max_length=2000)

class SceneFinalizeResponse(BaseModel):
    """Response from scene finalization."""
    scene_id: UUID
    status: Literal[SceneStatus.COMPLETED]
    completed_at: datetime
```

---

### 3.2 ProposedChange Models

#### ProposedChangeCreate

```python
class EvidenceRef(BaseModel):
    """Evidence reference."""
    type: Literal["turn", "snippet", "source", "rule"]
    ref_id: UUID

class ProposedChangeCreate(BaseModel):
    """Create a proposed change."""
    scene_id: UUID
    turn_id: UUID | None = None
    type: ProposalType
    content: dict  # Type-specific structure
    evidence: list[EvidenceRef] = Field(min_items=1)
    confidence: float = Field(ge=0.0, le=1.0)
    authority: Authority

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "scene_id": "scene-uuid",
                    "turn_id": "turn-uuid",
                    "type": "state_change",
                    "content": {
                        "entity_id": "gandalf-uuid",
                        "tag": "wounded",
                        "action": "add"
                    },
                    "evidence": [
                        {"type": "turn", "ref_id": "turn-uuid"}
                    ],
                    "confidence": 0.9,
                    "authority": "gm"
                }
            ]
        }
    }

class ProposedChangeResponse(BaseModel):
    """Response from proposal creation."""
    proposal_id: UUID
    status: Literal[ProposalStatus.PENDING]
    created_at: datetime
```

---

#### ProposalEvaluate

```python
class ProposalEvaluate(BaseModel):
    """Evaluate a proposal."""
    proposal_id: UUID
    decision: Literal[ProposalStatus.ACCEPTED, ProposalStatus.REJECTED]
    rationale: str | None = None
    canonical_id: UUID | None = None  # If accepted

    @field_validator('canonical_id')
    @classmethod
    def canonical_id_required_for_accepted(cls, v, info):
        if info.data.get('decision') == ProposalStatus.ACCEPTED and v is None:
            raise ValueError('canonical_id required when decision is "accepted"')
        return v

class ProposalEvaluateResponse(BaseModel):
    """Response from proposal evaluation."""
    proposal_id: UUID
    status: ProposalStatus
    evaluated_at: datetime
```

---

#### ProposedChangeFull

```python
class ProposedChangeFull(BaseModel):
    """Complete proposed change data."""
    proposal_id: UUID
    scene_id: UUID
    turn_id: UUID | None
    type: ProposalType
    content: dict
    evidence: list[EvidenceRef]
    confidence: float
    authority: Authority
    status: ProposalStatus
    rationale: str | None
    canonical_id: UUID | None
    created_at: datetime
    evaluated_at: datetime | None
```

---

### 3.3 Memory Models

#### CharacterMemoryCreate

```python
class CharacterMemoryCreate(BaseModel):
    """Create a character memory."""
    entity_id: UUID
    text: str = Field(min_length=1, max_length=2000)
    linked_fact_id: UUID | None = None
    scene_id: UUID | None = None
    emotional_valence: float = Field(ge=-1.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    certainty: float = Field(ge=0.0, le=1.0)

class CharacterMemoryResponse(BaseModel):
    """Response from memory creation."""
    memory_id: UUID
    created_at: datetime

class CharacterMemoryFull(BaseModel):
    """Complete character memory data."""
    memory_id: UUID
    entity_id: UUID
    text: str
    linked_fact_id: UUID | None
    scene_id: UUID | None
    emotional_valence: float
    importance: float
    certainty: float
    created_at: datetime
    last_accessed: datetime
    access_count: int
```

---

### 3.4 Document Models

#### DocumentCreate

```python
class DocumentCreate(BaseModel):
    """Create a document record."""
    source_id: UUID  # Neo4j Source
    universe_id: UUID
    minio_ref: str
    title: str = Field(min_length=1, max_length=200)
    filename: str
    file_type: str

class DocumentResponse(BaseModel):
    """Response from document creation."""
    doc_id: UUID
    extraction_status: Literal["pending"]
    created_at: datetime
```

---

#### SnippetCreate

```python
class SnippetCreate(BaseModel):
    """Create a snippet."""
    doc_id: UUID
    source_id: UUID
    text: str = Field(min_length=1, max_length=10000)
    page: int | None = None
    section: str | None = None
    chunk_index: int = Field(ge=0)

class SnippetResponse(BaseModel):
    """Response from snippet creation."""
    snippet_id: UUID
    created_at: datetime
```

---

## 4. Qdrant Models

### 4.1 Search Models

#### SemanticSearchRequest

```python
class QdrantCollection(str, Enum):
    SCENE_CHUNKS = "scene_chunks"
    MEMORY_CHUNKS = "memory_chunks"
    SNIPPET_CHUNKS = "snippet_chunks"

class SemanticSearchFilters(BaseModel):
    """Qdrant payload filters."""
    universe_id: UUID | None = None
    entity_id: UUID | None = None
    source_id: UUID | None = None

class SemanticSearchRequest(BaseModel):
    """Semantic search request."""
    query_text: str = Field(min_length=1, max_length=1000)
    collection: QdrantCollection
    filters: SemanticSearchFilters | None = None
    limit: int = Field(10, ge=1, le=100)
    min_score: float = Field(0.0, ge=0.0, le=1.0)

class SemanticSearchResult(BaseModel):
    """Single search result."""
    id: UUID
    score: float
    payload: dict
    text: str

class SemanticSearchResponse(BaseModel):
    """Response from semantic search."""
    results: list[SemanticSearchResult]
```

---

## 5. Composite Models

### 5.1 Context Assembly

#### AssembleSceneContextRequest

```python
class AssembleSceneContextRequest(BaseModel):
    """Request to assemble scene context."""
    scene_id: UUID
    include_canonical: bool = True
    include_narrative: bool = True
    include_semantic: bool = True
    semantic_query: str | None = None

class CanonicalContext(BaseModel):
    """Canonical data from Neo4j."""
    entities: list[EntityFull]
    facts: list[FactFull]
    relations: list[dict]  # Relationship data

class NarrativeContext(BaseModel):
    """Narrative data from MongoDB."""
    prior_turns: list[Turn]
    scene_summary: str | None
    gm_notes: str | None

class RecalledContext(BaseModel):
    """Semantic recall from Qdrant."""
    similar_scenes: list[dict]
    character_memories: list[CharacterMemoryFull]
    rule_excerpts: list[dict]

class ContextMetadata(BaseModel):
    """Context metadata."""
    universe_id: UUID
    story_id: UUID
    scene_id: UUID
    timestamp: datetime

class AssembleSceneContextResponse(BaseModel):
    """Response from context assembly."""
    canonical: CanonicalContext
    narrative: NarrativeContext
    recalled: RecalledContext
    metadata: ContextMetadata
```

---

### 5.2 Canonization

#### CanonizeSceneRequest

```python
class CanonizeSceneRequest(BaseModel):
    """Request to canonize a scene."""
    scene_id: UUID
    evaluate_proposals: bool = True

class CanonizeSceneResponse(BaseModel):
    """Response from scene canonization."""
    scene_id: UUID
    accepted_proposals: list[UUID]
    rejected_proposals: list[UUID]
    canonical_fact_ids: list[UUID]
    canonical_event_ids: list[UUID]
    canonical_entity_ids: list[UUID]
```

---

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
| CreateStory | CanonKeeper, Orchestrator | Orchestrator for story setup only |
| CreateEntity | CanonKeeper | All entity types |
| UpdateEntity | CanonKeeper | Property/state changes |
| CreateFact | CanonKeeper | Canonization only |
| CreateEvent | CanonKeeper | Canonization only |
| CreateAxiom | CanonKeeper | World rules |
| CreateSource | CanonKeeper | Document registration |
| CreateRelationship | CanonKeeper | Entity relationships |
| LinkEvidence | CanonKeeper | SUPPORTED_BY edges |

### 8.2 MongoDB Write Operations

| Operation | Allowed Agents | Notes |
|-----------|----------------|-------|
| CreateScene | Orchestrator | Scene lifecycle |
| UpdateScene | Orchestrator | Status changes |
| FinalizeScene | Orchestrator | After canonization |
| AppendTurn | Narrator | Turn transcription |
| UndoTurn | Orchestrator | Meta-command |
| CreateProposedChange | Narrator, Resolver | Proposing canonical changes |
| EvaluateProposal | CanonKeeper | Accept/reject |
| CreateMemory | MemoryManager | Character memories |
| UpdateMemory | MemoryManager | Memory updates |
| CreateDocument | Indexer | Document ingestion |
| CreateSnippet | Indexer | Text chunking |
| CreateStoryOutline | Orchestrator | Story structure |
| CreateResolution | Resolver | Dice/action results |

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
        "neo4j_create_story": ["CanonKeeper", "Orchestrator"],
        "mongodb_append_turn": ["Narrator"],
        "mongodb_create_proposal": ["Narrator", "Resolver"],
        "mongodb_evaluate_proposal": ["CanonKeeper"],
        "mongodb_create_memory": ["MemoryManager"],
        "qdrant_embed_scene": ["Indexer"],
        # ... etc
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
