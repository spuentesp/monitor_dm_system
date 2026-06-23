"""
Vector embedding schemas for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic)
USED BY: qdrant_tools.py

These schemas define the contracts for Qdrant vector operations.

Collections (5 total):
  scenes    — Scene summaries and turn text for narrative retrieval
  memories  — Character memory embeddings (subjective, per-entity)
  snippets  — Chunked text from ingested source documents
  entities  — EntityInstance/Archetype embeddings for NPC/location discovery
  knowledge — Axioms, lore facts, and world rules from the knowledge graph
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


# =============================================================================
# COLLECTION REGISTRY
# =============================================================================


class VectorCollection(str, Enum):
    """Valid Qdrant collection names."""

    SCENES = "scenes"
    MEMORIES = "memories"
    SNIPPETS = "snippets"
    ENTITIES = "entities"
    KNOWLEDGE = "knowledge"


VALID_COLLECTIONS = {c.value for c in VectorCollection}


# =============================================================================
# TYPED PAYLOAD SCHEMAS (what each collection stores)
# =============================================================================


class SceneChunkPayload(BaseModel):
    """Payload stored with each scene/turn vector in the 'scenes' collection."""

    scene_id: str
    story_id: str
    universe_id: str
    text: str
    type: str = Field(description="'scene_summary' or 'turn'")
    play_session_id: Optional[str] = Field(
        None, description="Real-world session that produced this scene"
    )
    temporal_mode: Optional[str] = Field(
        None, description="present | flashback | flash_forward | dream"
    )
    timestamp: str = Field(description="ISO 8601 in-universe or wall-clock time")


class MemoryChunkPayload(BaseModel):
    """Payload stored with each memory vector in the 'memories' collection."""

    memory_id: str
    entity_id: str
    universe_id: Optional[str] = None
    text: str
    importance: float
    emotional_valence: float = Field(description="-1.0 (negative) to 1.0 (positive)")
    certainty: float = Field(description="0.0 (false memory) to 1.0 (certain)")
    timestamp: str


class SnippetChunkPayload(BaseModel):
    """Payload stored with each document snippet in the 'snippets' collection."""

    snippet_id: str
    doc_id: str
    source_id: str
    universe_id: str
    text: str
    page: Optional[int] = None
    section: Optional[str] = None
    ingestion_job_id: Optional[str] = Field(
        None, description="IngestionJob that produced this snippet"
    )


class EntityChunkPayload(BaseModel):
    """Payload stored with each entity vector in the 'entities' collection.

    Enables semantic NPC/location discovery:
      'find me a gruff dwarf blacksmith near the docks'
    """

    entity_id: str
    universe_id: str
    name: str
    entity_type: str = Field(
        description="character | faction | location | object | concept | organization"
    )
    is_archetype: bool
    detail_level: Optional[str] = Field(None, description="stub | sketched | detailed | elaborated")
    tags: List[str] = Field(default_factory=list, description="State tags + trait tags")
    text: str = Field(description="Embedding source: name + description + traits")
    timestamp: str


class KnowledgeChunkPayload(BaseModel):
    """Payload stored with each knowledge vector in the 'knowledge' collection.

    Covers axioms, lore facts, setting events — what the GM needs to recall
    rules and world truths during play:
      'what are the grappling rules'
      'who started the Horus Heresy'
    """

    node_id: str = Field(description="Neo4j UUID of the Axiom, Fact, or LoreEvent")
    node_type: str = Field(description="axiom | fact | lore_event")
    universe_id: str
    domain: Optional[str] = Field(
        None, description="physics | magic | society | history | religion | etc."
    )
    text: str = Field(description="Embedding source: statement or description")
    canon_level: str = Field(description="proposed | canon | retconned")
    timestamp: str


# =============================================================================
# VECTOR POINT SCHEMAS
# =============================================================================


class VectorPoint(BaseModel):
    """Single vector point for storage."""

    id: UUID = Field(description="Unique identifier for the vector point")
    vector: List[float] = Field(
        description="Embedding vector (typically 1536 dimensions for OpenAI)"
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata payload (id, type, story_id, scene_id, entity_id, etc.)",
    )


class VectorUpsertRequest(BaseModel):
    """Request to upsert a single vector."""

    collection: str = Field(
        description="Collection name: scenes | memories | snippets | entities | knowledge"
    )
    id: UUID = Field(description="Unique identifier for the vector point")
    vector: List[float] = Field(description="Embedding vector")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Metadata payload")


class VectorBatchUpsertRequest(BaseModel):
    """Request to upsert multiple vectors in batch."""

    collection: str = Field(
        description="Collection name: scenes | memories | snippets | entities | knowledge"
    )
    points: List[VectorPoint] = Field(description="List of vector points to upsert", min_length=1)


class VectorUpsertResponse(BaseModel):
    """Response from vector upsert operation."""

    success: bool = Field(description="Whether the operation succeeded")
    collection: str = Field(description="Collection name")
    upserted_count: int = Field(description="Number of points upserted")
    ids: List[UUID] = Field(description="IDs of upserted points")


# =============================================================================
# VECTOR SEARCH SCHEMAS
# =============================================================================


class VectorFilter(BaseModel):
    """Filter for vector search operations.

    All fields are ANDed together. Only set the fields relevant to the
    target collection — irrelevant fields are ignored by Qdrant.
    """

    # Shared across multiple collections
    story_id: Optional[UUID] = Field(default=None, description="Filter by story_id (scenes)")
    scene_id: Optional[UUID] = Field(
        default=None, description="Filter by scene_id (scenes, memories)"
    )
    entity_id: Optional[UUID] = Field(
        default=None, description="Filter by entity_id (memories, entities)"
    )
    universe_id: Optional[UUID] = Field(
        default=None, description="Filter by universe_id (all collections)"
    )

    # scenes collection
    temporal_mode: Optional[str] = Field(
        default=None,
        description="Filter scenes by temporal mode: present | flashback | flash_forward | dream",
    )
    play_session_id: Optional[UUID] = Field(
        default=None, description="Filter scenes by real-world play session"
    )

    # entities collection
    entity_type: Optional[str] = Field(
        default=None,
        description="Filter entities by type: character | faction | location | object | concept | organization",
    )
    is_archetype: Optional[bool] = Field(
        default=None, description="Filter entities: True=archetypes, False=instances"
    )
    detail_level: Optional[str] = Field(
        default=None,
        description="Filter entities by detail level: stub | sketched | detailed | elaborated",
    )

    # knowledge collection
    node_type: Optional[str] = Field(
        default=None, description="Filter knowledge by node type: axiom | fact | lore_event"
    )
    domain: Optional[str] = Field(
        default=None,
        description="Filter knowledge by domain: physics | magic | society | history | etc.",
    )
    canon_level: Optional[str] = Field(
        default=None, description="Filter by canon level: proposed | canon | retconned"
    )

    # snippets collection
    doc_id: Optional[UUID] = Field(default=None, description="Filter snippets by source document")
    ingestion_job_id: Optional[UUID] = Field(
        default=None, description="Filter snippets by ingestion job"
    )

    # Generic type discriminator (used in scenes: 'scene_summary' | 'turn')
    type: Optional[str] = Field(default=None, description="Filter by 'type' field in payload")

    # Escape hatch for advanced Qdrant filter expressions
    custom: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Raw Qdrant filter dict — merged with the structured fields above",
    )


class VectorSearchRequest(BaseModel):
    """Request to search for similar vectors."""

    collection: str = Field(
        description="Collection name: scenes | memories | snippets | entities | knowledge"
    )
    query_vector: List[float] = Field(
        default_factory=list,
        description="Query embedding vector; optional when `query_text` is provided",
    )
    query_text: Optional[str] = Field(
        default=None,
        description="Raw text query to embed on demand for semantic search",
    )
    top_k: int = Field(default=10, description="Number of results to return", ge=1)
    limit: Optional[int] = Field(
        default=None,
        description="Alias for top_k used by runtime agent/tool callers",
        ge=1,
    )
    score_threshold: Optional[float] = Field(
        default=None,
        description="Minimum similarity score threshold (0-1 for cosine)",
        ge=0.0,
        le=1.0,
    )
    filter: Optional[VectorFilter] = Field(default=None, description="Optional payload filters")
    keyword_filter: Optional[str] = Field(
        default=None,
        description=(
            "Optional keyword to match against the 'text' payload field using Qdrant's "
            "full-text (MatchText) index. Applied as an additional AND pre-filter before "
            "vector ranking. Requires a TextIndexParams payload index on 'text' (created "
            "automatically by ensure_collection for the snippets collection). "
            "Use for entity-name-aware retrieval: 'Ventrue', 'Obfuscate', etc."
        ),
    )

    @model_validator(mode="after")
    def _normalize_limit_alias(self) -> "VectorSearchRequest":
        if self.limit is not None:
            self.top_k = self.limit
        return self


class ScoredVector(BaseModel):
    """Single search result with score."""

    id: UUID = Field(description="Vector point ID")
    score: float = Field(description="Similarity score")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Metadata payload")


class VectorSearchResponse(BaseModel):
    """Response from vector search operation."""

    collection: str = Field(description="Collection name")
    results: List[ScoredVector] = Field(description="Ranked search results")
    count: int = Field(description="Number of results returned")


# =============================================================================
# VECTOR DELETE SCHEMAS
# =============================================================================


class VectorDeleteRequest(BaseModel):
    """Request to delete a single vector by ID."""

    collection: str = Field(
        description="Collection name: scenes | memories | snippets | entities | knowledge"
    )
    id: UUID = Field(description="ID of the vector point to delete")


class VectorDeleteByFilterRequest(BaseModel):
    """Request to delete vectors by filter."""

    collection: str = Field(
        description="Collection name: scenes | memories | snippets | entities | knowledge"
    )
    filter: VectorFilter = Field(description="Filter to match points for deletion")


class VectorDeleteResponse(BaseModel):
    """Response from vector delete operation."""

    success: bool = Field(description="Whether the operation succeeded")
    collection: str = Field(description="Collection name")
    deleted_count: int = Field(description="Number of points deleted")


# =============================================================================
# COLLECTION INFO SCHEMAS
# =============================================================================


class CollectionInfo(BaseModel):
    """Information about a vector collection."""

    name: str = Field(description="Collection name")
    vector_size: int = Field(description="Dimension of vectors in the collection")
    points_count: int = Field(description="Number of points in the collection")
    indexed_vectors_count: Optional[int] = Field(
        default=None, description="Number of indexed vectors"
    )
    distance: str = Field(description="Distance metric (Cosine, Dot, Euclidean, Manhattan)")
    status: str = Field(description="Collection status")


class CollectionInfoRequest(BaseModel):
    """Request to get collection information."""

    collection: str = Field(description="Collection name (scenes, memories, snippets)")


class CollectionInfoResponse(BaseModel):
    """Response with collection information."""

    collection: CollectionInfo = Field(description="Collection metadata and stats")
