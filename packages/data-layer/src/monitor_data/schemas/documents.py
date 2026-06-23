"""
Pydantic schemas for Source, Document, and Snippet operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py (Source), mongodb_tools.py (Document, Snippet)

The ingestion pipeline entry point:

  [User uploads PDF/EPUB/text]
         |
         v
  MinIO  ──── stores binary ────────────────────────────→  MinIO bucket
         |
         v
  MongoDB documents  ─── tracks extraction status
         |
         v
  MongoDB snippets   ─── chunked text passages
         |
         v
  Qdrant snippet_chunks  ─── semantic embeddings
         |
         v
  ProposedChanges ─── entities/axioms/facts extracted
         |
         v
  CanonKeeper ──── Neo4j (Source node + EntityInstances + Axioms)

Source node lives in Neo4j (canonical provenance).
Document + Snippet records live in MongoDB (operational).
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import (
    ExtractionStatus,
    KnowledgeTreeType,
    SourceCanonLevel,
    SourcePriority,
    SourceType,
)


# =============================================================================
# SOURCE SCHEMAS  (Neo4j node — canonical provenance)
# =============================================================================


class SourceCreate(BaseModel):
    """Request to create a Source node in Neo4j."""

    universe_id: UUID = Field(description="Universe this source contributes to")
    id: Optional[UUID] = Field(None, description="Optional explicit Source ID")
    title: str = Field(min_length=1, max_length=500, description="Document title")
    edition: Optional[str] = Field(
        None, max_length=100, description="Edition or version (e.g., '5th Edition')"
    )
    provenance: Optional[str] = Field(
        None,
        max_length=500,
        description="URL, ISBN, publisher, or other external identifier",
    )
    source_type: SourceType = Field(description="manual, rulebook, lore, session, etc.")
    priority: SourcePriority = Field(
        default=SourcePriority.CUSTOM,
        description="Trust level: CORE > SUPPLEMENT > ADVENTURE > FAN > CUSTOM",
    )
    knowledge_tree_type: KnowledgeTreeType = Field(
        default=KnowledgeTreeType.DYNAMIC,
        description="STATIC=locked lore; DYNAMIC=can change; TEMPLATE=blueprint",
    )
    canon_level: SourceCanonLevel = Field(default=SourceCanonLevel.PROPOSED)


class SourceUpdate(BaseModel):
    """Request to update a Source node."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    edition: Optional[str] = Field(None, max_length=100)
    provenance: Optional[str] = Field(None, max_length=500)
    priority: Optional[SourcePriority] = None
    knowledge_tree_type: Optional[KnowledgeTreeType] = None
    canon_level: Optional[SourceCanonLevel] = None
    doc_id: Optional[str] = Field(
        None, description="MongoDB/MinIO document reference (set after upload)"
    )


class SourceResponse(BaseModel):
    """Response with Source node data."""

    id: UUID
    universe_id: UUID
    doc_id: Optional[str] = None
    title: str
    edition: Optional[str] = None
    provenance: Optional[str] = None
    source_type: SourceType
    priority: SourcePriority
    knowledge_tree_type: KnowledgeTreeType
    canon_level: SourceCanonLevel
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceFilter(BaseModel):
    """Filter parameters for listing sources."""

    universe_id: Optional[UUID] = None
    source_type: Optional[SourceType] = None
    priority: Optional[SourcePriority] = None
    canon_level: Optional[SourceCanonLevel] = None
    knowledge_tree_type: Optional[KnowledgeTreeType] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class SourceListResponse(BaseModel):
    """Response for list operations."""

    sources: List[SourceResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# DOCUMENT SCHEMAS  (MongoDB — file tracking record)
# =============================================================================


class DocumentCreate(BaseModel):
    """Request to create a Document record in MongoDB."""

    source_id: UUID = Field(description="References Neo4j Source node")
    universe_id: UUID
    doc_id: Optional[UUID] = Field(None, description="Optional explicit Document ID")
    title: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=500)
    file_type: str = Field(
        min_length=1,
        max_length=20,
        description="File extension: pdf, epub, txt, md, docx",
    )
    minio_ref: str = Field(
        min_length=1, max_length=1000, description="MinIO object key (path in bucket)"
    )
    file_size_bytes: Optional[int] = Field(None, ge=0)


class DocumentUpdate(BaseModel):
    """Request to update a Document record."""

    extraction_status: Optional[ExtractionStatus] = None
    extracted_at: Optional[datetime] = None
    snippet_count: Optional[int] = Field(None, ge=0)
    extraction_error: Optional[str] = Field(None, max_length=2000)


class DocumentResponse(BaseModel):
    """Response with Document data."""

    doc_id: UUID
    source_id: UUID
    universe_id: UUID
    title: str
    filename: str
    file_type: str
    minio_ref: str
    file_size_bytes: Optional[int] = None
    extraction_status: ExtractionStatus
    snippet_count: int = 0
    extraction_error: Optional[str] = None
    created_at: datetime
    extracted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentFilter(BaseModel):
    """Filter for listing documents."""

    universe_id: Optional[UUID] = None
    source_id: Optional[UUID] = None
    extraction_status: Optional[ExtractionStatus] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class DocumentListResponse(BaseModel):
    """Response for list operations."""

    documents: List[DocumentResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# SNIPPET SCHEMAS  (MongoDB — chunked text passages)
# =============================================================================


class SnippetCreate(BaseModel):
    """Request to create a Snippet record in MongoDB.

    Snippets are chunked text passages extracted from documents.
    Each snippet is independently embeddable in Qdrant's snippet_chunks collection.
    """

    doc_id: UUID = Field(description="Parent document")
    source_id: UUID = Field(description="Neo4j Source node for SUPPORTED_BY edges")
    universe_id: UUID
    text: str = Field(min_length=1, max_length=10000, description="Chunk text")
    page: Optional[int] = Field(None, ge=1, description="Page number in source document")
    section: Optional[str] = Field(None, max_length=500, description="Section/chapter heading")
    chunk_index: int = Field(ge=0, description="Sequential chunk index within document")


class SnippetResponse(BaseModel):
    """Response with Snippet data."""

    snippet_id: UUID
    doc_id: UUID
    source_id: UUID
    universe_id: UUID
    text: str
    page: Optional[int] = None
    section: Optional[str] = None
    chunk_index: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SnippetFilter(BaseModel):
    """Filter for listing snippets."""

    doc_id: Optional[UUID] = None
    source_id: Optional[UUID] = None
    universe_id: Optional[UUID] = None
    section: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class SnippetListResponse(BaseModel):
    """Response for list operations."""

    snippets: List[SnippetResponse]
    total: int
    limit: int
    offset: int
