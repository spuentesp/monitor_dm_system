"""
Pydantic schemas for ProposedChange operations in MongoDB.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for ProposedChange CRUD operations.
ProposedChanges are staging documents that CanonKeeper evaluates at scene end.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import Authority, ProposalStatus, ProposalType


# =============================================================================
# PROPOSED CHANGE SCHEMAS
# =============================================================================


class EvidenceRef(BaseModel):
    """Reference to supporting evidence for a proposed change."""

    type: str = Field(
        description="Type of evidence: turn, snippet, source, fact, rule"
    )
    ref_id: UUID = Field(description="UUID of the referenced document/node")


class ProposedChangeCreate(BaseModel):
    """Request to create a ProposedChange document."""

    change_type: ProposalType = Field(
        description="Type of change being proposed"
    )
    content: Dict[str, Any] = Field(
        description="Flexible JSON payload specific to change_type"
    )
    scene_id: Optional[UUID] = Field(
        None,
        description="Scene this change was proposed in (optional for system/ingest)",
    )
    story_id: Optional[UUID] = Field(
        None,
        description="Story this change relates to",
    )
    universe_id: UUID = Field(
        description="Universe this change affects"
    )
    turn_id: Optional[UUID] = Field(
        None,
        description="Turn that proposed this change (if applicable)",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=1.0,
        description="Confidence level in this proposal",
    )
    authority: Authority = Field(
        default=Authority.SYSTEM,
        description="Who is proposing this change",
    )
    evidence_refs: List[EvidenceRef] = Field(
        default_factory=list,
        description="Supporting evidence for this proposal",
    )
    proposed_by: str = Field(
        description="Agent or system component that proposed this change"
    )


class ProposedChangeUpdate(BaseModel):
    """Request to update a ProposedChange (status transitions)."""

    status: ProposalStatus = Field(
        description="New status: accepted or rejected"
    )
    decision_reason: Optional[str] = Field(
        None,
        max_length=2000,
        description="Rationale for accepting/rejecting",
    )
    canonical_ref: Optional[UUID] = Field(
        None,
        description="If accepted, the Neo4j node/edge ID that was created",
    )
    decided_by: str = Field(
        default="CanonKeeper",
        description="Agent that made the decision (usually CanonKeeper)",
    )


class ProposedChangeResponse(BaseModel):
    """Response with ProposedChange document data."""

    proposal_id: UUID
    change_type: ProposalType
    content: Dict[str, Any]
    scene_id: Optional[UUID]
    story_id: Optional[UUID]
    universe_id: UUID
    turn_id: Optional[UUID]
    confidence: float
    authority: Authority
    evidence_refs: List[EvidenceRef]
    proposed_by: str
    status: ProposalStatus
    decision_reason: Optional[str] = None
    canonical_ref: Optional[UUID] = None
    decided_by: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProposedChangeFilter(BaseModel):
    """Filter parameters for listing proposed changes."""

    scene_id: Optional[UUID] = Field(
        None,
        description="Filter by scene ID",
    )
    story_id: Optional[UUID] = Field(
        None,
        description="Filter by story ID",
    )
    universe_id: Optional[UUID] = Field(
        None,
        description="Filter by universe ID",
    )
    status: Optional[ProposalStatus] = Field(
        None,
        description="Filter by status",
    )
    change_type: Optional[ProposalType] = Field(
        None,
        description="Filter by change type",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum number of results",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip",
    )


class ProposedChangeListResponse(BaseModel):
    """Response with list of proposed changes and pagination info."""

    proposals: List[ProposedChangeResponse]
    total: int
    limit: int
    offset: int
