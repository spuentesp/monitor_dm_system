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

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import IngestionStatus


class LastErrorCategory(StrEnum):
    """Finite set of failure categories the pipeline records.

    Adding a new category means adding an enum member — ``last_error.category``
    is the canonical signal operators read to know what to fix.
    """

    EMBEDDING_PREFLIGHT_FAILED = "embedding_preflight_failed"
    INDEXER_FAILED = "indexer_failed"
    ANALYZER_FAILED = "analyzer_failed"
    CANONIZER_FAILED = "canonizer_failed"
    PROVIDER_BLOCKED = "provider_blocked"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class LastError(BaseModel):
    """Structured failure record for an IngestionJob.

    ``category`` is the primary signal (``embedding_preflight_failed``,
    etc.). ``message`` is the human-readable failure text. ``detail``
    is the free-form provider-side diagnostic (Ollama /api/show output,
    litellm error class).
    """

    category: LastErrorCategory
    message: str
    failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detail: str | None = None


# =============================================================================
# ENUMS
# =============================================================================


class IngestionStage(StrEnum):
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
    job_id: UUID | None = Field(None, description="Optional explicit Job ID")
    source_id: UUID = Field(description="References Neo4j Source node")
    doc_id: UUID = Field(description="References MongoDB documents collection")
    source_title: str = Field(default="", description="Human-readable title stored at creation to avoid Neo4j lookups")
    pipeline_stages: list[IngestionStage] = Field(
        default_factory=lambda: list(IngestionStage),
        description="Ordered pipeline stages to execute",
    )
    processing_checklist: list[str] = Field(
        default_factory=list,
        description="Selected analysis layers/checklist items for this ingestion run",
    )


class IngestionJobUpdate(BaseModel):
    """Request to update ingestion job progress."""

    status: IngestionStatus | None = None
    current_stage: IngestionStage | None = None
    progress: float | None = Field(None, ge=0.0, le=1.0)
    stages_completed: list[IngestionStage] | None = None
    # Extraction counters
    snippet_count: int | None = Field(None, ge=0)
    entities_extracted: int | None = Field(None, ge=0)
    axioms_extracted: int | None = Field(None, ge=0)
    game_system_found: bool | None = None
    world_template_found: bool | None = None
    # Canonization counters
    proposals_generated: int | None = Field(None, ge=0)
    proposals_accepted: int | None = Field(None, ge=0)
    proposals_rejected: int | None = Field(None, ge=0)
    # Reliability / LLM timeline
    total_batches: int | None = Field(None, ge=0)
    succeeded_batches: int | None = Field(None, ge=0)
    failed_batches: int | None = Field(None, ge=0)
    retried_batches: int | None = Field(None, ge=0)
    # Total LLM attempts (>= total_batches because retries count).
    total_attempts: int | None = Field(None, ge=0)
    current_provider: str | None = None
    current_model: str | None = None
    last_error: LastError | None = None
    next_retry_at: datetime | None = None
    partial: bool | None = None
    kill_reason: str | None = None
    # Error tracking
    errors: list[str] | None = None
    warnings: list[str] | None = None
    activity_log: list[str] | None = None
    processing_checklist: list[str] | None = None
    # Per-section failure list — which sections failed extraction and why.
    # Capped at 200 entries in the analyzer to bound growth on large books.
    failed_sections: list[dict[str, str]] | None = Field(
        None,
        description=(
            "List of {section_path, stage, reason} dicts for sections that "
            "failed LLM extraction. Truncated to first 200 entries."
        ),
    )
    # Completion
    completed_at: datetime | None = None
    pack_id: UUID | None = Field(None, description="KnowledgePack created by this job (set by analyzer)")


class IngestionJobResponse(BaseModel):
    """Response with IngestionJob data."""

    job_id: UUID
    universe_id: UUID
    source_id: UUID
    doc_id: UUID
    source_title: str = ""
    status: IngestionStatus
    current_stage: IngestionStage | None = None
    pipeline_stages: list[IngestionStage]
    stages_completed: list[IngestionStage] = Field(default_factory=list)
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
    total_attempts: int = 0
    current_provider: str | None = None
    current_model: str | None = None
    last_error: LastError | None = None
    next_retry_at: datetime | None = None
    partial: bool = False
    kill_reason: str | None = None
    # Audit
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    activity_log: list[str] = Field(default_factory=list)
    processing_checklist: list[str] = Field(default_factory=list)
    failed_sections: list[dict[str, str]] = Field(default_factory=list)
    # Timing
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    created_at: datetime
    pack_id: UUID | None = Field(None, description="KnowledgePack created by this job (navigable link)")

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class IngestionJobFilter(BaseModel):
    """Filter for listing ingestion jobs."""

    universe_id: UUID | None = None
    source_id: UUID | None = None
    status: IngestionStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort_order: str = Field(
        default="desc",
        description="Sort by started_at: desc=newest first",
        pattern="^(asc|desc)$",
    )


class IngestionJobListResponse(BaseModel):
    """Response for list operations."""

    jobs: list[IngestionJobResponse]
    total: int
    limit: int
    offset: int
