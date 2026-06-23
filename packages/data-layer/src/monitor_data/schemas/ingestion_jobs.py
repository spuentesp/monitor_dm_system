"""
Pydantic schemas for IngestionJob operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

An IngestionJob tracks the full pipeline when a document is uploaded and
processed into the knowledge graph.

Pipeline stages (in order):
  1. upload       — File stored in MinIO
  2. extract      — Text/chunks extracted from binary (PDF/EPUB/etc.)
  3. embed        — Snippets embedded in Qdrant snippet_chunks
  4. analyze      — LLM analyzes content: identifies entities, axioms, game system
  5. propose      — ProposedChanges written to MongoDB
  6. canonize     — CanonKeeper evaluates proposals → Neo4j nodes created
  7. index        — Entity/knowledge chunks indexed in Qdrant

The job gives the user visibility into progress:
  "Your Pathfinder 2e Core Rulebook is 73% processed —
   extracted 2,847 snippets, found 412 entities, 89 axioms,
   1 game system definition, 1 world template."
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import IngestionStatus


# =============================================================================
# ENUMS
# =============================================================================


class IngestionStage(str, Enum):
    """Individual stages of the ingestion pipeline."""

    UPLOAD = "upload"
    EXTRACT = "extract"
    EMBED = "embed"
    ANALYZE = "analyze"
    PROPOSE = "propose"
    CANONIZE = "canonize"
    INDEX = "index"


# =============================================================================
# INGESTION JOB CRUD SCHEMAS
# =============================================================================


class IngestionJobCreate(BaseModel):
    """Request to create/start an ingestion job."""

    universe_id: UUID
    job_id: Optional[UUID] = Field(None, description="Optional explicit Job ID")
    source_id: UUID = Field(description="References Neo4j Source node")
    doc_id: UUID = Field(description="References MongoDB documents collection")
    source_title: str = Field(
        default="", description="Human-readable title stored at creation to avoid Neo4j lookups"
    )
    pipeline_stages: List[IngestionStage] = Field(
        default_factory=lambda: list(IngestionStage),
        description="Ordered pipeline stages to execute",
    )
    processing_checklist: List[str] = Field(
        default_factory=list,
        description="Selected analysis layers/checklist items for this ingestion run",
    )


class IngestionJobUpdate(BaseModel):
    """Request to update ingestion job progress."""

    status: Optional[IngestionStatus] = None
    current_stage: Optional[IngestionStage] = None
    progress: Optional[float] = Field(None, ge=0.0, le=1.0)
    stages_completed: Optional[List[IngestionStage]] = None
    # Extraction counters
    snippet_count: Optional[int] = Field(None, ge=0)
    entities_extracted: Optional[int] = Field(None, ge=0)
    axioms_extracted: Optional[int] = Field(None, ge=0)
    game_system_found: Optional[bool] = None
    world_template_found: Optional[bool] = None
    # Canonization counters
    proposals_generated: Optional[int] = Field(None, ge=0)
    proposals_accepted: Optional[int] = Field(None, ge=0)
    proposals_rejected: Optional[int] = Field(None, ge=0)
    # Reliability / LLM timeline
    total_batches: Optional[int] = Field(None, ge=0)
    succeeded_batches: Optional[int] = Field(None, ge=0)
    failed_batches: Optional[int] = Field(None, ge=0)
    retried_batches: Optional[int] = Field(None, ge=0)
    current_provider: Optional[str] = None
    current_model: Optional[str] = None
    last_error: Optional[str] = None
    next_retry_at: Optional[datetime] = None
    partial: Optional[bool] = None
    kill_reason: Optional[str] = None
    # Error tracking
    errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    activity_log: Optional[List[str]] = None
    processing_checklist: Optional[List[str]] = None
    # Completion
    completed_at: Optional[datetime] = None
    pack_id: Optional[UUID] = Field(
        None, description="KnowledgePack created by this job (set by analyzer)"
    )


class IngestionJobResponse(BaseModel):
    """Response with IngestionJob data."""

    job_id: UUID
    universe_id: UUID
    source_id: UUID
    doc_id: UUID
    source_title: str = ""
    status: IngestionStatus
    current_stage: Optional[IngestionStage] = None
    pipeline_stages: List[IngestionStage]
    stages_completed: List[IngestionStage] = Field(default_factory=list)
    progress: float = Field(default=0.0, description="Overall progress 0.0-1.0")
    # Extraction results
    snippet_count: int = 0
    entities_extracted: int = 0
    axioms_extracted: int = 0
    game_system_found: bool = False
    world_template_found: bool = False
    # Canonization results
    proposals_generated: int = 0
    proposals_accepted: int = 0
    proposals_rejected: int = 0
    # Reliability / LLM timeline
    total_batches: int = 0
    succeeded_batches: int = 0
    failed_batches: int = 0
    retried_batches: int = 0
    current_provider: Optional[str] = None
    current_model: Optional[str] = None
    last_error: Optional[str] = None
    next_retry_at: Optional[datetime] = None
    partial: bool = False
    kill_reason: Optional[str] = None
    # Audit
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    activity_log: List[str] = Field(default_factory=list)
    processing_checklist: List[str] = Field(default_factory=list)
    # Timing
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    created_at: datetime
    pack_id: Optional[UUID] = Field(
        None, description="KnowledgePack created by this job (navigable link)"
    )

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class IngestionJobFilter(BaseModel):
    """Filter for listing ingestion jobs."""

    universe_id: Optional[UUID] = None
    source_id: Optional[UUID] = None
    status: Optional[IngestionStatus] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort_order: str = Field(
        default="desc",
        description="Sort by started_at: desc=newest first",
        pattern="^(asc|desc)$",
    )


class IngestionJobListResponse(BaseModel):
    """Response for list operations."""

    jobs: List[IngestionJobResponse]
    total: int
    limit: int
    offset: int
