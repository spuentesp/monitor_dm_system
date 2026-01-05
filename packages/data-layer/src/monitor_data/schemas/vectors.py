"""
Vector embedding schemas for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic)
USED BY: qdrant_tools.py

These schemas define the contracts for Qdrant vector operations.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


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

    collection: str = Field(description="Collection name (scenes, memories, snippets)")
    id: UUID = Field(description="Unique identifier for the vector point")
    vector: List[float] = Field(description="Embedding vector")
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Metadata payload"
    )


class VectorBatchUpsertRequest(BaseModel):
    """Request to upsert multiple vectors in batch."""

    collection: str = Field(description="Collection name (scenes, memories, snippets)")
    points: List[VectorPoint] = Field(
        description="List of vector points to upsert", min_length=1
    )


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
    """Filter for vector search operations."""

    story_id: Optional[UUID] = Field(
        default=None, description="Filter by story_id in payload"
    )
    scene_id: Optional[UUID] = Field(
        default=None, description="Filter by scene_id in payload"
    )
    entity_id: Optional[UUID] = Field(
        default=None, description="Filter by entity_id in payload"
    )
    type: Optional[str] = Field(
        default=None, description="Filter by type in payload (scene, memory, snippet)"
    )
    custom: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Custom Qdrant filter conditions (for advanced filtering)",
    )


class VectorSearchRequest(BaseModel):
    """Request to search for similar vectors."""

    collection: str = Field(description="Collection name (scenes, memories, snippets)")
    query_vector: List[float] = Field(description="Query embedding vector")
    top_k: int = Field(default=10, description="Number of results to return", ge=1)
    score_threshold: Optional[float] = Field(
        default=None,
        description="Minimum similarity score threshold (0-1 for cosine)",
        ge=0.0,
        le=1.0,
    )
    filter: Optional[VectorFilter] = Field(
        default=None, description="Optional payload filters"
    )


class ScoredVector(BaseModel):
    """Single search result with score."""

    id: UUID = Field(description="Vector point ID")
    score: float = Field(description="Similarity score")
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Metadata payload"
    )


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

    collection: str = Field(description="Collection name (scenes, memories, snippets)")
    id: UUID = Field(description="ID of the vector point to delete")


class VectorDeleteByFilterRequest(BaseModel):
    """Request to delete vectors by filter."""

    collection: str = Field(description="Collection name (scenes, memories, snippets)")
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
    distance: str = Field(
        description="Distance metric (Cosine, Dot, Euclidean, Manhattan)"
    )
    status: str = Field(description="Collection status")


class CollectionInfoRequest(BaseModel):
    """Request to get collection information."""

    collection: str = Field(description="Collection name (scenes, memories, snippets)")


class CollectionInfoResponse(BaseModel):
    """Response with collection information."""

    collection: CollectionInfo = Field(description="Collection metadata and stats")
