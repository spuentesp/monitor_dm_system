"""
Pydantic schemas for Source operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Source CRUD operations.
Sources are canonical references to external knowledge (books, rulebooks, etc.).
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import SourceCanonLevel, SourceType


# =============================================================================
# SOURCE SCHEMAS
# =============================================================================


class SourceCreate(BaseModel):
    """Request to create a Source."""

    universe_id: UUID
    title: str = Field(min_length=1, max_length=500)
    source_type: SourceType
    edition: Optional[str] = Field(None, max_length=100, description="e.g., '5th Edition', 'v2.0'")
    provenance: Optional[str] = Field(
        None, max_length=500, description="URL, ISBN, or other reference"
    )
    doc_id: Optional[str] = Field(
        None, max_length=200, description="MinIO/MongoDB reference to uploaded document"
    )
    canon_level: SourceCanonLevel = Field(default=SourceCanonLevel.PROPOSED)
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (author, publisher, etc.)"
    )


class SourceUpdate(BaseModel):
    """Request to update a Source.

    Only mutable fields can be updated.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    edition: Optional[str] = Field(None, max_length=100)
    provenance: Optional[str] = Field(None, max_length=500)
    doc_id: Optional[str] = Field(None, max_length=200)
    canon_level: Optional[SourceCanonLevel] = None
    metadata: Optional[Dict[str, Any]] = None


class SourceResponse(BaseModel):
    """Response with Source data."""

    id: UUID
    universe_id: UUID
    title: str
    source_type: SourceType
    edition: Optional[str]
    provenance: Optional[str]
    doc_id: Optional[str]
    canon_level: SourceCanonLevel
    metadata: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceFilter(BaseModel):
    """Filter parameters for listing sources."""

    universe_id: Optional[UUID] = None
    source_type: Optional[SourceType] = None
    canon_level: Optional[SourceCanonLevel] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at", description="Field to sort by: created_at, title"
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class SourceListResponse(BaseModel):
    """Response with list of sources and pagination info."""

    sources: list[SourceResponse]
    total: int
    limit: int
    offset: int
