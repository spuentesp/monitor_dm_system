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
    id: UUID | None = Field(None, description="Optional explicit Source ID")
    title: str = Field(min_length=1, max_length=500, description="Document title")
    edition: str | None = Field(None, max_length=100, description="Edition or version (e.g., '5th Edition')")
    provenance: str | None = Field(
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

    title: str | None = Field(None, min_length=1, max_length=500)
    edition: str | None = Field(None, max_length=100)
    provenance: str | None = Field(None, max_length=500)
    priority: SourcePriority | None = None
    knowledge_tree_type: KnowledgeTreeType | None = None
    canon_level: SourceCanonLevel | None = None
    doc_id: str | None = Field(None, description="MongoDB/MinIO document reference (set after upload)")


class SourceResponse(BaseModel):
    """Response with Source node data."""

    id: UUID
    universe_id: UUID
    doc_id: str | None = None
    title: str
    edition: str | None = None
    provenance: str | None = None
    source_type: SourceType
    priority: SourcePriority
    knowledge_tree_type: KnowledgeTreeType
    canon_level: SourceCanonLevel
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceFilter(BaseModel):
    """Filter parameters for listing sources."""

    universe_id: UUID | None = None
    source_type: SourceType | None = None
    priority: SourcePriority | None = None
    canon_level: SourceCanonLevel | None = None
    knowledge_tree_type: KnowledgeTreeType | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class SourceListResponse(BaseModel):
    """Response for list operations."""

    sources: list[SourceResponse]
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
    doc_id: UUID | None = Field(None, description="Optional explicit Document ID")
    title: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=500)
    file_type: str = Field(
        min_length=1,
        max_length=20,
        description="File extension: pdf, epub, txt, md, docx",
    )
    minio_ref: str = Field(min_length=1, max_length=1000, description="MinIO object key (path in bucket)")
    file_size_bytes: int | None = Field(None, ge=0)
    content_hash: str | None = Field(
        None,
        max_length=64,
        description=(
            "sha256 hex digest of the raw file bytes. Used to detect "
            "identical-content re-uploads regardless of filename/universe — "
            "see INGESTION_PIPELINE_AUDIT.md Finding 7."
        ),
    )


class DocumentUpdate(BaseModel):
    """Request to update a Document record."""

    extraction_status: ExtractionStatus | None = None
    extracted_at: datetime | None = None
    snippet_count: int | None = Field(None, ge=0)
    extraction_error: str | None = Field(None, max_length=2000)


class DocumentResponse(BaseModel):
    """Response with Document data."""

    doc_id: UUID
    source_id: UUID
    universe_id: UUID
    title: str
    filename: str
    file_type: str
    minio_ref: str
    file_size_bytes: int | None = None
    content_hash: str | None = None
    extraction_status: ExtractionStatus
    snippet_count: int = 0
    extraction_error: str | None = None
    created_at: datetime
    extracted_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentFilter(BaseModel):
    """Filter for listing documents."""

    universe_id: UUID | None = None
    source_id: UUID | None = None
    extraction_status: ExtractionStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class DocumentListResponse(BaseModel):
    """Response for list operations."""

    documents: list[DocumentResponse]
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
    page: int | None = Field(None, ge=1, description="Page number in source document")
    section: str | None = Field(None, max_length=500, description="Section/chapter heading")
    chunk_index: int = Field(ge=0, description="Sequential chunk index within document")


class SnippetResponse(BaseModel):
    """Response with Snippet data."""

    snippet_id: UUID
    doc_id: UUID
    source_id: UUID
    universe_id: UUID
    text: str
    page: int | None = None
    section: str | None = None
    chunk_index: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SnippetFilter(BaseModel):
    """Filter for listing snippets."""

    doc_id: UUID | None = None
    source_id: UUID | None = None
    universe_id: UUID | None = None
    section: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class SnippetListResponse(BaseModel):
    """Response for list operations."""

    snippets: list[SnippetResponse]
    total: int
    limit: int
    offset: int
