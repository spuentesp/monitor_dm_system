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

