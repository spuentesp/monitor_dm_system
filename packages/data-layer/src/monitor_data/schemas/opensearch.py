"""
OpenSearch schemas for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only
CALLED BY: opensearch_tools.py

Pydantic models for OpenSearch operations including indexing,
searching, and document management.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# DOCUMENT OPERATIONS
# =============================================================================


class DocumentIndexRequest(BaseModel):
    """Request to index a document."""

    index: str = Field(..., description="Index name (e.g., 'snippets', 'facts')")
    id: str = Field(..., description="Document ID")
    body: Dict[str, Any] = Field(..., description="Document body")
    refresh: bool = Field(
        default=False, description="Refresh index immediately after indexing"
    )


class DocumentIndexResponse(BaseModel):
    """Response from indexing a document."""

    id: str = Field(..., description="Document ID")
    index: str = Field(..., description="Index name")
    result: str = Field(..., description="Operation result (created/updated)")
    version: int = Field(..., description="Document version")


class DocumentGetRequest(BaseModel):
    """Request to get a document."""

    index: str = Field(..., description="Index name")
    id: str = Field(..., description="Document ID")


class DocumentGetResponse(BaseModel):
    """Response from getting a document."""

    id: str = Field(..., description="Document ID")
    index: str = Field(..., description="Index name")
    found: bool = Field(..., description="Whether document was found")
    source: Optional[Dict[str, Any]] = Field(
        default=None, description="Document source"
    )
    version: Optional[int] = Field(default=None, description="Document version")


class DocumentDeleteRequest(BaseModel):
    """Request to delete a document."""

    index: str = Field(..., description="Index name")
    id: str = Field(..., description="Document ID")


class DocumentDeleteResponse(BaseModel):
    """Response from deleting a document."""

    id: str = Field(..., description="Document ID")
    index: str = Field(..., description="Index name")
    result: str = Field(..., description="Operation result (deleted/not_found)")
    version: Optional[int] = Field(default=None, description="Document version")


# =============================================================================
# SEARCH OPERATIONS
# =============================================================================


class SearchRequest(BaseModel):
    """Request to search documents."""

    index: str = Field(..., description="Index name (can use wildcards)")
    query: str = Field(..., description="Search query (text)")
    query_type: str = Field(
        default="match",
        description="Query type: match (keyword), match_phrase (exact), multi_match",
    )
    fields: Optional[List[str]] = Field(
        default=None, description="Fields to search (default: ['text'])"
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None, description="Field filters (e.g., {'universe_id': 'uuid', 'type': 'snippet'})"
    )
    highlight: bool = Field(default=True, description="Enable highlighting")
    highlight_fields: Optional[List[str]] = Field(
        default=None, description="Fields to highlight (default: ['text'])"
    )
    from_: int = Field(default=0, ge=0, description="Offset for pagination", alias="from")
    size: int = Field(default=10, ge=1, le=100, description="Number of results")

    model_config = {"populate_by_name": True}


class SearchHit(BaseModel):
    """A single search result."""

    id: str = Field(..., description="Document ID")
    index: str = Field(..., description="Index name")
    score: float = Field(..., description="Relevance score")
    source: Dict[str, Any] = Field(..., description="Document source")
    highlight: Optional[Dict[str, List[str]]] = Field(
        default=None, description="Highlighted snippets by field"
    )


class SearchResponse(BaseModel):
    """Response from a search query."""

    total: int = Field(..., description="Total number of matching documents")
    max_score: Optional[float] = Field(
        default=None, description="Maximum relevance score"
    )
    hits: List[SearchHit] = Field(..., description="Search results")
    took: int = Field(..., description="Time taken in milliseconds")


# =============================================================================
# BULK OPERATIONS
# =============================================================================


class DeleteByQueryRequest(BaseModel):
    """Request to delete documents by query."""

    index: str = Field(..., description="Index name")
    query: str = Field(..., description="Query to match documents for deletion")
    query_type: str = Field(
        default="match",
        description="Query type: match, match_phrase, term",
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional filters"
    )


class DeleteByQueryResponse(BaseModel):
    """Response from delete by query."""

    deleted: int = Field(..., description="Number of documents deleted")
    total: int = Field(..., description="Total documents matched")
    took: int = Field(..., description="Time taken in milliseconds")


# =============================================================================
# COMMON DOCUMENT TYPES
# =============================================================================


class SnippetDocument(BaseModel):
    """Document model for snippet indexing."""

    id: str = Field(..., description="Snippet ID")
    type: str = Field(default="snippet", description="Document type")
    universe_id: Optional[str] = Field(default=None, description="Universe ID")
    source_id: Optional[str] = Field(default=None, description="Source ID")
    text: str = Field(..., description="Snippet text content")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional metadata"
    )
    created_at: Optional[datetime] = Field(default=None, description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Update time")


class FactDocument(BaseModel):
    """Document model for fact indexing."""

    id: str = Field(..., description="Fact ID")
    type: str = Field(default="fact", description="Document type")
    universe_id: str = Field(..., description="Universe ID")
    text: str = Field(..., description="Fact description")
    fact_type: Optional[str] = Field(default=None, description="Fact type")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional metadata"
    )
    created_at: Optional[datetime] = Field(default=None, description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Update time")


class SceneDocument(BaseModel):
    """Document model for scene indexing."""

    id: str = Field(..., description="Scene ID")
    type: str = Field(default="scene", description="Document type")
    universe_id: str = Field(..., description="Universe ID")
    story_id: Optional[str] = Field(default=None, description="Story ID")
    text: str = Field(..., description="Scene narrative content")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional metadata (recap, notes)"
    )
    created_at: Optional[datetime] = Field(default=None, description="Creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Update time")
