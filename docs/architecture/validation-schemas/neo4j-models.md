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

#### EntityCreate

```python
class EntityCreate(BaseModel):
    """Flat entity creation request (archetype or instance)."""
    universe_id: UUID
    name: str
    entity_type: EntityType
    is_archetype: bool = False  # True → EntityArchetype, False → EntityInstance
    description: str = ""
    properties: dict = {}
    state_tags: list[str] = []  # EntityInstance only
    archetype_id: UUID | None = None  # link via DERIVES_FROM if set
    authority: Authority = Authority.SYSTEM
    canon_level: CanonLevel = CanonLevel.CANON
    confidence: float = 1.0
    detail_level: DetailLevel = DetailLevel.STUB
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
    is_archetype: bool  # True → EntityArchetype, False → EntityInstance
    universe_id: UUID
    name: str
    entity_type: EntityType
    description: str
    properties: dict
    state_tags: list[str] = Field(default_factory=list)  # EntityInstance only
    updated_at: datetime | None = None  # EntityInstance only
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
    is_archetype: bool | None = None  # True → archetypes only, False → instances only, None → all
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

