"""
Pydantic schemas for Snippet operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for Snippet CRUD operations.
Snippets represent extracted text chunks from documents.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# SNIPPET SCHEMAS
# =============================================================================


class SnippetCreate(BaseModel):
    """Request to create a Snippet."""

    doc_id: UUID = Field(description="References MongoDB Document")
    source_id: UUID = Field(description="References Neo4j Source node")
    text: str = Field(min_length=1, description="Extracted text content")
    page: Optional[int] = Field(None, ge=1, description="Page number (if applicable)")
    section: Optional[str] = Field(None, max_length=500, description="Section or chapter name")
    chunk_index: int = Field(ge=0, description="Index of this chunk within the document")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (location hints, etc.)"
    )


class SnippetResponse(BaseModel):
    """Response with Snippet data."""

    snippet_id: UUID
    doc_id: UUID
    source_id: UUID
    text: str
    page: Optional[int]
    section: Optional[str]
    chunk_index: int
    metadata: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class SnippetFilter(BaseModel):
    """Filter parameters for listing snippets."""

    doc_id: Optional[UUID] = None
    source_id: Optional[UUID] = None
    page: Optional[int] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="chunk_index", description="Field to sort by: chunk_index, created_at"
    )
    sort_order: str = Field(
        default="asc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class SnippetListResponse(BaseModel):
    """Response with list of snippets and pagination info."""

    snippets: list[SnippetResponse]
    total: int
    limit: int
    offset: int
