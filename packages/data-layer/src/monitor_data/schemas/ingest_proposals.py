"""
Pydantic schemas for IngestProposal operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for IngestProposal CRUD operations.
IngestProposals represent AI-extracted knowledge awaiting review and canonization.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import IngestProposalType, IngestProposalStatus


# =============================================================================
# INGEST PROPOSAL SCHEMAS
# =============================================================================


class IngestProposalCreate(BaseModel):
    """Request to create an IngestProposal."""

    proposal_type: IngestProposalType
    universe_id: UUID
    content: Dict[str, Any] = Field(
        description="Extracted knowledge content (entity data, fact statement, etc.)"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="AI confidence in extraction")
    evidence_snippet_ids: List[UUID] = Field(
        default_factory=list, description="Snippet IDs supporting this proposal"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (model version, extraction params, etc.)"
    )


class IngestProposalUpdate(BaseModel):
    """Request to update an IngestProposal (primarily status transitions)."""

    status: IngestProposalStatus
    decision_reason: Optional[str] = Field(
        None, max_length=1000, description="Reason for acceptance/rejection"
    )
    canonical_id: Optional[UUID] = Field(
        None, description="ID of created canonical entity/fact if accepted"
    )


class IngestProposalResponse(BaseModel):
    """Response with IngestProposal data."""

    proposal_id: UUID
    proposal_type: IngestProposalType
    universe_id: UUID
    content: Dict[str, Any]
    confidence: float
    evidence_snippet_ids: List[UUID]
    status: IngestProposalStatus
    decision_reason: Optional[str]
    canonical_id: Optional[UUID]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IngestProposalFilter(BaseModel):
    """Filter parameters for listing ingest proposals."""

    universe_id: Optional[UUID] = None
    proposal_type: Optional[IngestProposalType] = None
    status: Optional[IngestProposalStatus] = None
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at", description="Field to sort by: created_at, confidence, status"
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class IngestProposalListResponse(BaseModel):
    """Response with list of ingest proposals and pagination info."""

    proposals: list[IngestProposalResponse]
    total: int
    limit: int
    offset: int
