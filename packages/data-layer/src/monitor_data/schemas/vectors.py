"""
Vector embedding schemas for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and base schemas only
CALLED BY: qdrant_tools.py

These schemas define the structure for vector embeddings stored in Qdrant.
"""

from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field


# =============================================================================
# VECTOR PAYLOAD SCHEMAS
# =============================================================================


class VectorPayload(BaseModel):
    """
    Metadata payload for a vector point in Qdrant.
    
    This payload enables filtering during search operations.
    All fields are optional to support different embedding types.
    """
    
    id: str = Field(..., description="Unique identifier for the vector point")
    type: str = Field(..., description="Type of embedding: scene, memory, snippet, etc.")
    story_id: Optional[str] = Field(None, description="Associated story UUID")
    scene_id: Optional[str] = Field(None, description="Associated scene UUID")
    entity_id: Optional[str] = Field(None, description="Associated entity UUID")
    universe_id: Optional[str] = Field(None, description="Associated universe UUID")
    text: Optional[str] = Field(None, description="Original text that was embedded")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# =============================================================================
# UPSERT OPERATION SCHEMAS
# =============================================================================


class VectorUpsert(BaseModel):
    """Single vector upsert operation."""
    
    collection: str = Field(..., description="Collection name (e.g., 'scenes', 'memories')")
    id: str = Field(..., description="Unique point ID")
    vector: List[float] = Field(..., description="Dense vector embedding")
    payload: VectorPayload = Field(..., description="Metadata payload")


class VectorPoint(BaseModel):
    """Single point for batch upsert."""
    
    id: str = Field(..., description="Unique point ID")
    vector: List[float] = Field(..., description="Dense vector embedding")
    payload: Dict[str, Any] = Field(..., description="Metadata payload")


class VectorUpsertBatch(BaseModel):
    """Batch vector upsert operation."""
    
    collection: str = Field(..., description="Collection name")
    points: List[VectorPoint] = Field(..., description="List of points to upsert")


# =============================================================================
# SEARCH OPERATION SCHEMAS
# =============================================================================


class VectorSearchFilter(BaseModel):
    """
    Filter for vector search operations.
    
    Uses Qdrant's filter syntax. All specified filters use AND logic.
    """
    
    story_id: Optional[str] = Field(None, description="Filter by story_id")
    scene_id: Optional[str] = Field(None, description="Filter by scene_id")
    entity_id: Optional[str] = Field(None, description="Filter by entity_id")
    universe_id: Optional[str] = Field(None, description="Filter by universe_id")
    type: Optional[str] = Field(None, description="Filter by embedding type")


class VectorSearch(BaseModel):
    """Vector similarity search operation."""
    
    collection: str = Field(..., description="Collection name to search")
    query_vector: List[float] = Field(..., description="Query vector for similarity search")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")
    filter: Optional[VectorSearchFilter] = Field(None, description="Optional payload filter")
    score_threshold: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0, 
        description="Minimum similarity score threshold"
    )


class VectorSearchResult(BaseModel):
    """Single search result with score."""
    
    id: str = Field(..., description="Point ID")
    score: float = Field(..., description="Similarity score")
    payload: Dict[str, Any] = Field(..., description="Point payload")
    vector: Optional[List[float]] = Field(None, description="Vector (if requested)")


class VectorSearchResponse(BaseModel):
    """Response from vector search operation."""
    
    results: List[VectorSearchResult] = Field(..., description="Search results")
    collection: str = Field(..., description="Collection searched")
    count: int = Field(..., description="Number of results returned")


# =============================================================================
# DELETE OPERATION SCHEMAS
# =============================================================================


class VectorDelete(BaseModel):
    """Delete a single vector point."""
    
    collection: str = Field(..., description="Collection name")
    id: str = Field(..., description="Point ID to delete")


class VectorDeleteByFilter(BaseModel):
    """Delete multiple points by filter."""
    
    collection: str = Field(..., description="Collection name")
    filter: VectorSearchFilter = Field(..., description="Filter for points to delete")


class VectorDeleteResponse(BaseModel):
    """Response from delete operation."""
    
    deleted: bool = Field(..., description="Whether deletion was successful")
    count: int = Field(default=1, description="Number of points deleted")


# =============================================================================
# COLLECTION OPERATION SCHEMAS
# =============================================================================


class CollectionInfo(BaseModel):
    """Information about a Qdrant collection."""
    
    name: str = Field(..., description="Collection name")
    vector_size: int = Field(..., description="Dimension of vectors")
    points_count: int = Field(..., description="Number of points in collection")
    exists: bool = Field(..., description="Whether collection exists")
    config: Optional[Dict[str, Any]] = Field(None, description="Collection configuration")


class CollectionCreate(BaseModel):
    """Parameters for creating a collection."""
    
    name: str = Field(..., description="Collection name")
    vector_size: int = Field(..., ge=1, description="Dimension of vectors")
    distance: str = Field(default="Cosine", description="Distance metric: Cosine, Euclid, or Dot")
