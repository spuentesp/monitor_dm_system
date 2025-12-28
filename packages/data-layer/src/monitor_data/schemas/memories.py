"""
Pydantic schemas for Memory operations (CharacterMemory).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py, qdrant_tools.py

These schemas define the data contracts for Memory CRUD operations.
CharacterMemory represents subjective memories belonging to entities.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# MEMORY SCHEMAS
# =============================================================================


class MemoryCreate(BaseModel):
    """Request to create a CharacterMemory document."""

    entity_id: UUID = Field(
        description="UUID of the entity (character) who owns this memory"
    )
    text: str = Field(
        min_length=1,
        max_length=10000,
        description="The memory text content",
    )
    scene_id: Optional[UUID] = Field(
        None,
        description="Optional reference to the scene where memory originated",
    )
    fact_id: Optional[UUID] = Field(
        None,
        description="Optional reference to a canonical fact this memory relates to",
    )
    importance: float = Field(
        ge=0.0,
        le=1.0,
        default=0.5,
        description="Importance score (0.0-1.0) affecting recall priority",
    )
    emotional_valence: float = Field(
        ge=-1.0,
        le=1.0,
        default=0.0,
        description="Emotional valence (-1.0=negative, 0.0=neutral, 1.0=positive)",
    )
    certainty: float = Field(
        ge=0.0,
        le=1.0,
        default=1.0,
        description="How certain the entity is about this memory (can misremember)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for the memory",
    )


class MemoryUpdate(BaseModel):
    """Request to update a CharacterMemory.

    Only mutable fields can be updated: importance, emotional_valence,
    certainty, and metadata.
    """

    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    emotional_valence: Optional[float] = Field(None, ge=-1.0, le=1.0)
    certainty: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: Optional[Dict[str, Any]] = None


class MemoryResponse(BaseModel):
    """Response with CharacterMemory data."""

    memory_id: UUID
    entity_id: UUID
    text: str
    scene_id: Optional[UUID] = None
    fact_id: Optional[UUID] = None
    importance: float
    emotional_valence: float
    certainty: float
    metadata: Dict[str, Any]
    created_at: datetime
    last_accessed: datetime
    access_count: int

    model_config = {"from_attributes": True}


class MemoryFilter(BaseModel):
    """Filter parameters for listing memories."""

    entity_id: Optional[UUID] = Field(
        None,
        description="Filter by entity (character) who owns the memories",
    )
    scene_id: Optional[UUID] = Field(
        None,
        description="Filter by scene where memory originated",
    )
    min_importance: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Filter by minimum importance threshold",
    )
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="importance",
        description="Field to sort by: importance, created_at, last_accessed",
    )
    sort_order: str = Field(
        default="desc",
        description="Sort order: asc, desc",
        pattern="^(asc|desc)$",
    )

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        """Validate sort_by field is allowed."""
        allowed = ["importance", "created_at", "last_accessed"]
        if v not in allowed:
            raise ValueError(f"sort_by must be one of {allowed}")
        return v


class MemoryListResponse(BaseModel):
    """Response with list of memories and pagination info."""

    memories: List[MemoryResponse]
    total: int
    limit: int
    offset: int


class MemorySearchQuery(BaseModel):
    """Query parameters for semantic memory search."""

    query_text: str = Field(
        min_length=1,
        description="Text query for semantic search",
    )
    entity_id: Optional[UUID] = Field(
        None,
        description="Filter search to specific entity's memories",
    )
    min_importance: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Filter by minimum importance threshold",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return",
    )


class MemorySearchResult(BaseModel):
    """Single memory search result with score."""

    memory_id: UUID
    entity_id: UUID
    text: str
    importance: float
    score: float = Field(
        description="Semantic similarity score",
    )
    scene_id: Optional[UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemorySearchResponse(BaseModel):
    """Response with semantic search results."""

    results: List[MemorySearchResult]
    query_text: str
    total_results: int
