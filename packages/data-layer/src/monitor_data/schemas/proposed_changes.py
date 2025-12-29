"""
Pydantic schemas for ProposedChange operations (MongoDB).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for ProposedChange CRUD operations.
ProposedChanges are staging documents for canonical changes that CanonKeeper
evaluates at scene end.

USE CASE: DL-5
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from monitor_data.schemas.base import ProposalStatus, ProposalType, Authority


# =============================================================================
# EVIDENCE SCHEMAS
# =============================================================================


class Evidence(BaseModel):
    """Evidence supporting a proposed change."""

    type: str = Field(
        description="Evidence type: turn, snippet, source, rule",
        pattern="^(turn|snippet|source|rule)$",
    )
    ref_id: UUID = Field(description="Reference to the evidence source")


# =============================================================================
# DECISION METADATA SCHEMAS
# =============================================================================


class DecisionMetadata(BaseModel):
    """Metadata about CanonKeeper's decision on a proposal."""

    decided_by: str = Field(description="Agent that made the decision (e.g., CanonKeeper)")
    decided_at: datetime = Field(description="When the decision was made")
    reason: str = Field(
        description="Rationale for accepting or rejecting the proposal",
        max_length=2000,
    )
    canonical_ref: Optional[UUID] = Field(
        None,
        description="UUID of the created canonical entity in Neo4j (if accepted)",
    )


# =============================================================================
# PROPOSED CHANGE SCHEMAS
# =============================================================================


class ProposedChangeCreate(BaseModel):
    """Request to create a ProposedChange."""

    scene_id: Optional[UUID] = Field(
        None, description="Scene ID (required for scene-based proposals)"
    )
    story_id: Optional[UUID] = Field(
        None, description="Story ID (for story-level proposals)"
    )
    turn_id: Optional[UUID] = Field(
        None, description="Turn ID that proposed this (if from a turn)"
    )
    change_type: ProposalType = Field(description="Type of proposed change")
    content: Dict[str, Any] = Field(
        description="Flexible JSON payload for the proposed change"
    )
    evidence: List[Evidence] = Field(
        default_factory=list, description="Supporting evidence for this proposal"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence level for this proposal (0.0-1.0)",
    )
    authority: Authority = Field(
        default=Authority.SYSTEM, description="Who asserted this change"
    )
    proposer: str = Field(
        default="Unknown", description="Agent or user who created this proposal"
    )

    @field_validator("scene_id", "story_id")
    @classmethod
    def validate_scene_or_story(cls, v: Optional[UUID], info) -> Optional[UUID]:
        """Validate that at least one of scene_id or story_id is provided."""
        # If this is scene_id being validated and it's None, check if story_id exists
        if info.field_name == "scene_id" and v is None:
            # We can't check story_id here as it might not be set yet
            pass
        return v

    def model_post_init(self, __context):
        """Post-initialization validation to ensure scene_id or story_id is provided."""
        if self.scene_id is None and self.story_id is None:
            raise ValueError("Either scene_id or story_id must be provided")


class ProposedChangeUpdate(BaseModel):
    """Request to update a ProposedChange.

    Only CanonKeeper can update status from pending to accepted/rejected.
    """

    status: ProposalStatus = Field(description="New status for the proposal")
    decision_metadata: DecisionMetadata = Field(
        description="Decision metadata (required when updating status)"
    )


class ProposedChangeResponse(BaseModel):
    """Response with ProposedChange data."""

    proposal_id: UUID
    scene_id: Optional[UUID] = None
    story_id: Optional[UUID] = None
    turn_id: Optional[UUID] = None
    change_type: ProposalType
    content: Dict[str, Any]
    evidence: List[Evidence] = Field(default_factory=list)
    confidence: float
    authority: Authority
    proposer: str
    status: ProposalStatus
    decision_metadata: Optional[DecisionMetadata] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProposedChangeFilter(BaseModel):
    """Filter parameters for listing proposed changes."""

    scene_id: Optional[UUID] = None
    story_id: Optional[UUID] = None
    status: Optional[ProposalStatus] = None
    change_type: Optional[ProposalType] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at",
        description="Field to sort by: created_at, confidence",
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class ProposedChangeListResponse(BaseModel):
    """Response with list of proposed changes and pagination info."""

    proposed_changes: List[ProposedChangeResponse]
    total: int
    limit: int
    offset: int
