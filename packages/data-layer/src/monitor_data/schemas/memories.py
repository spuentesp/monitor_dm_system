"""
Pydantic schemas for CharacterMemory operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py, qdrant_tools.py

These schemas define the data contracts for memory CRUD and vector operations.
Memories are subjective records belonging to specific entities (characters).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# MEMORY SCHEMAS
# =============================================================================


class MemoryCreate(BaseModel):
    """Request to create a CharacterMemory document."""

    universe_id: UUID = Field(description="Universe ID where this memory exists")
    entity_id: UUID = Field(description="Entity (character) who owns this memory")
    text: str = Field(min_length=1, max_length=5000, description="Memory content")
    scene_id: UUID | None = Field(None, description="Scene where memory originated")
    linked_fact_id: UUID | None = Field(None, description="Optional anchor to canonical Fact")
    emotional_valence: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Emotional charge: -1.0 (negative) to 1.0 (positive)",
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Importance for recall: 0.0 (trivial) to 1.0 (critical)",
    )
    certainty: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Certainty of memory: 0.0 (false) to 1.0 (certain)",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional memory metadata")


class MemoryUpdate(BaseModel):
    """Request to update a CharacterMemory document."""

    importance: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Update importance (affects recall priority)",
    )
    certainty: float | None = Field(None, ge=0.0, le=1.0, description="Update certainty")
    emotional_valence: float | None = Field(None, ge=-1.0, le=1.0, description="Update emotional charge")
    metadata: dict[str, Any] | None = Field(None, description="Update metadata")


class MemoryFilter(BaseModel):
    """Filter for listing/searching memories."""

    universe_id: UUID | None = Field(None, description="Filter by universe")
    entity_id: UUID | None = Field(None, description="Filter by entity")
    scene_id: UUID | None = Field(None, description="Filter by scene")
    min_importance: float | None = Field(None, ge=0.0, le=1.0, description="Minimum importance threshold")
    max_importance: float | None = Field(None, ge=0.0, le=1.0, description="Maximum importance threshold")
    min_emotional_valence: float | None = Field(None, ge=-1.0, le=1.0, description="Minimum emotional valence")
    max_emotional_valence: float | None = Field(None, ge=-1.0, le=1.0, description="Maximum emotional valence")
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class MemoryResponse(BaseModel):
    """Response with CharacterMemory data."""

    memory_id: UUID
    universe_id: UUID
    entity_id: UUID
    text: str
    scene_id: UUID | None
    linked_fact_id: UUID | None
    emotional_valence: float
    importance: float
    certainty: float
    metadata: dict[str, Any]
    created_at: datetime
    last_accessed: datetime
    access_count: int


class MemoryListResponse(BaseModel):
    """Response with list of memories."""

    memories: list[MemoryResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# MEMORY VECTOR SCHEMAS (QDRANT)
# =============================================================================


class MemoryEmbedRequest(BaseModel):
    """Request to embed a memory in Qdrant."""

    memory_id: UUID = Field(description="Memory UUID")
    universe_id: UUID = Field(description="Universe ID")
    text: str = Field(min_length=1, max_length=5000, description="Memory text to embed")
    entity_id: UUID = Field(description="Entity who owns this memory")
    scene_id: UUID | None = Field(None, description="Scene where memory originated")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryEmbedResponse(BaseModel):
    """Response after embedding a memory."""

    memory_id: UUID
    point_id: str  # Qdrant point ID (typically str(memory_id))
    collection: str = "memories"
    success: bool


class MemorySearchRequest(BaseModel):
    """Request to search memories semantically."""

    query_text: str = Field(min_length=1, max_length=5000, description="Search query")
    universe_id: UUID | None = Field(None, description="Filter by universe")
    entity_id: UUID | None = Field(None, description="Filter by entity")
    scene_id: UUID | None = Field(None, description="Filter by scene")
    min_importance: float | None = Field(None, ge=0.0, le=1.0)
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results")


class MemorySearchResult(BaseModel):
    """Single memory search result with score."""

    memory_id: UUID
    entity_id: UUID
    text: str | None = Field(
        None,
        description="Memory text (not stored in Qdrant, requires MongoDB fetch)",
    )
    scene_id: UUID | None
    importance: float
    score: float = Field(description="Similarity score (higher = more relevant)")
    metadata: dict[str, Any]


class MemorySearchResponse(BaseModel):
    """Response with semantic search results."""

    results: list[MemorySearchResult]
    query: str
    top_k: int
