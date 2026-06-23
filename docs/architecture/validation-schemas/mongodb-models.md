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

