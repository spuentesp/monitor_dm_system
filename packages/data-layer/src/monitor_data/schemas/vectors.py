"""
Vector embedding schemas for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, uuid, datetime)
CALLED BY: qdrant_tools.py

These schemas define the structure for vector embeddings and payloads
stored in Qdrant for semantic search across scenes, memories, and snippets.
"""

from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


# =============================================================================
# CONSTANTS
# =============================================================================

# Collection names for Qdrant
COLLECTION_SCENES = "scenes"
COLLECTION_MEMORIES = "memories"
COLLECTION_SNIPPETS = "snippets"

# Default vector dimensions (e.g., OpenAI text-embedding-3-small: 1536)
DEFAULT_VECTOR_SIZE = 1536


# =============================================================================
# PAYLOAD MODELS
# =============================================================================


class VectorPayload(BaseModel):
    """
    Base payload structure for all vector embeddings.

    This metadata is stored alongside each vector in Qdrant
    to enable filtered semantic search.
    """

    id: str  # String version of UUID for Qdrant compatibility
    type: str  # "scene", "memory", "snippet"
    story_id: Optional[str] = None  # Filter by story
    scene_id: Optional[str] = None  # Filter by scene
    entity_id: Optional[str] = None  # Filter by entity
    created_at: str  # ISO format timestamp

    model_config = {"from_attributes": True}


class ScenePayload(VectorPayload):
    """Payload for scene embeddings."""

    type: str = Field(default="scene", frozen=True)
    story_id: str  # Required for scenes
    scene_id: str  # Required for scenes
    universe_id: str  # Filter by universe
    title: str  # Scene title for display


class MemoryPayload(VectorPayload):
    """Payload for memory embeddings."""

    type: str = Field(default="memory", frozen=True)
    entity_id: str  # Required for memories (whose memory)
    memory_id: str  # Unique memory identifier
    story_id: Optional[str] = None  # May or may not be story-specific


class SnippetPayload(VectorPayload):
    """Payload for document snippet embeddings."""

    type: str = Field(default="snippet", frozen=True)
    snippet_id: str  # Unique snippet identifier
    doc_id: str  # Parent document ID
    universe_id: Optional[str] = None  # May be universe-specific
    chunk_index: int  # Position in document


# =============================================================================
# REQUEST MODELS
# =============================================================================


class VectorUpsert(BaseModel):
    """Request to upsert a single vector."""

    collection: str
    id: str  # Point ID
    vector: List[float]
    payload: Dict[str, Any]  # Generic payload dict


class VectorUpsertBatch(BaseModel):
    """Request to upsert multiple vectors."""

    collection: str
    points: List[Dict[str, Any]]  # List of {id, vector, payload}


class VectorSearch(BaseModel):
    """Request to search for similar vectors."""

    collection: str
    query_vector: List[float]
    top_k: int = Field(default=10, ge=1, le=100)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    filter: Optional[Dict[str, Any]] = None  # Qdrant filter dict


class VectorDelete(BaseModel):
    """Request to delete a vector by ID."""

    collection: str
    id: str


class VectorDeleteByFilter(BaseModel):
    """Request to delete vectors matching a filter."""

    collection: str
    filter: Dict[str, Any]  # Qdrant filter dict


class CollectionInfoRequest(BaseModel):
    """Request collection information."""

    collection: str


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class VectorSearchResult(BaseModel):
    """Single search result with score."""

    id: str
    score: float
    payload: Dict[str, Any]


class VectorSearchResponse(BaseModel):
    """Response from vector search."""

    results: List[VectorSearchResult]
    collection: str
    top_k: int


class VectorUpsertResponse(BaseModel):
    """Response from vector upsert."""

    success: bool
    collection: str
    id: str


class VectorUpsertBatchResponse(BaseModel):
    """Response from batch vector upsert."""

    success: bool
    collection: str
    count: int  # Number of points upserted


class VectorDeleteResponse(BaseModel):
    """Response from vector delete."""

    success: bool
    collection: str
    id: str


class VectorDeleteByFilterResponse(BaseModel):
    """Response from filtered vector delete."""

    success: bool
    collection: str
    count: int  # Number of points deleted


class CollectionInfo(BaseModel):
    """Collection information and statistics."""

    collection: str
    vector_count: int
    vector_size: int
    distance: str  # "Cosine", "Euclid", "Dot"
