"""
Pydantic schemas for Document operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for Document CRUD operations.
Documents represent uploaded files stored in MinIO, with metadata in MongoDB.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import DocumentStatus


# =============================================================================
# DOCUMENT SCHEMAS
# =============================================================================


class DocumentCreate(BaseModel):
    """Request to create a Document."""

    source_id: UUID = Field(description="References Neo4j Source node")
    universe_id: UUID
    minio_ref: str = Field(
        min_length=1, max_length=500, description="MinIO object reference (bucket/key)"
    )
    title: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=255)
    file_type: str = Field(
        min_length=1, max_length=50, description="e.g., 'pdf', 'epub', 'docx'"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (page count, size, etc.)"
    )


class DocumentResponse(BaseModel):
    """Response with Document data."""

    doc_id: UUID
    source_id: UUID
    universe_id: UUID
    minio_ref: str
    title: str
    filename: str
    file_type: str
    extraction_status: DocumentStatus
    metadata: Dict[str, Any]
    created_at: datetime
    extracted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentFilter(BaseModel):
    """Filter parameters for listing documents."""

    source_id: Optional[UUID] = None
    universe_id: Optional[UUID] = None
    file_type: Optional[str] = None
    extraction_status: Optional[DocumentStatus] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at", description="Field to sort by: created_at, title"
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class DocumentListResponse(BaseModel):
    """Response with list of documents and pagination info."""

    documents: list[DocumentResponse]
    total: int
    limit: int
    offset: int
