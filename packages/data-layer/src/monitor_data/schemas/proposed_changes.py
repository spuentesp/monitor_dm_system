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
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

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


class PromotionIntent(str, Enum):
    """Author-supplied hint for whether a transient entity deserves canonisation.

    Populated by the entity parser when the narrator tags a new entity with
    ``[Name](entity:anchor)`` or ``[Name](entity:flavor)``. CanonKeeper reads
    this field at scene-end to apply the anchor / flavor promotion rules
    (see CanonKeeper.evaluate_proposals).
    """

    ANCHOR = "anchor"
    FLAVOR = "flavor"


class ProposedChangeCreate(BaseModel):
    """Request to create a ProposedChange."""

    scene_id: Optional[UUID] = Field(
        None, description="Scene ID (required for scene-based proposals)"
    )
    story_id: Optional[UUID] = Field(None, description="Story ID (for story-level proposals)")
    turn_id: Optional[UUID] = Field(None, description="Turn ID that proposed this (if from a turn)")
    change_type: ProposalType = Field(description="Type of proposed change")
    content: Dict[str, Any] = Field(description="Flexible JSON payload for the proposed change")
    evidence: List[Evidence] = Field(
        default_factory=list, description="Supporting evidence for this proposal"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence level for this proposal (0.0-1.0)",
    )
    authority: Authority = Field(default=Authority.SYSTEM, description="Who asserted this change")
    proposer: str = Field(default="Unknown", description="Agent or user who created this proposal")
    # Entity-promotion metadata (DL-2 promotion gate)
    promotion_intent: Optional[PromotionIntent] = Field(
        None,
        description=(
            "Entity promotion intent. 'anchor' means the LLM tagged this entity "
            "as structurally important; 'flavor' means it was environmental "
            "set-dressing. None if not applicable to this change_type."
        ),
    )
    interaction_count: int = Field(
        default=1,
        ge=0,
        description=(
            "How many turns this entity has been referenced in. Incremented by "
            "the scene-loop entity parser each turn the [Name] tag appears. "
            "Defaults to 1 for newly proposed entities."
        ),
    )
    is_mechanically_bound: bool = Field(
        default=False,
        description=(
            "True if the entity was referenced by a mechanical payload "
            "(combat, inventory, state_change) at least once. Promotes flavor "
            "entities to anchor regardless of interaction count."
        ),
    )

    @field_validator("scene_id", "story_id")
    @classmethod
    def validate_scene_or_story(cls, v: Optional[UUID], info: ValidationInfo) -> Optional[UUID]:
        """Validate that at least one of scene_id or story_id is provided."""
        # If this is scene_id being validated and it's None, check if story_id exists
        if info.field_name == "scene_id" and v is None:
            # We can't check story_id here as it might not be set yet
            pass
        return v

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization validation.

        Scene-based proposals require scene_id or story_id.
        System-level proposals (e.g., snapshot_restore) may omit both.
        Conversatory proposals (NPCVoice / CharacterChat) are universe-scoped
        rather than scene-scoped, so they don't need either. They also pass
        a conversation_id in evidence — CanonKeeper correlates by universe.
        """
        scope_free_proposers = {
            "snapshot_restore",
            "system",
            "world_architect",
            # Conversatory proposals carry universe_id instead of scene/story.
            "NPCVoice",
            "CharacterChat",
        }
        if (
            self.scene_id is None
            and self.story_id is None
            and self.proposer not in scope_free_proposers
        ):
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
    # Entity-promotion metadata
    promotion_intent: Optional[PromotionIntent] = None
    interaction_count: int = 1
    is_mechanically_bound: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProposedChangeFilter(BaseModel):
    """Filter parameters for listing proposed changes."""

    scene_id: Optional[UUID] = None
    story_id: Optional[UUID] = None
    status: Optional[ProposalStatus] = None
    change_type: Optional[ProposalType] = None
    source: Optional[str] = Field(
        None,
        description="Filter by source tag (e.g. 'knowledge_pack:<uuid>')",
    )
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
