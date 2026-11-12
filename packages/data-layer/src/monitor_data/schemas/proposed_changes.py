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
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from monitor_data.schemas.base import (
    Authority,
    PromotionIntent,
    ProposalStatus,
    ProposalType,
)

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
    canonical_ref: UUID | None = Field(
        None,
        description="UUID of the created canonical entity in Neo4j (if accepted)",
    )
    override_reason: str | None = Field(
        None,
        max_length=2000,
        description=(
            "Why the GM accepted a proposal that carried a contradiction flag. "
            "Set only when a flagged proposal is accepted with an explicit override."
        ),
    )


class ProposalReviewFlag(BaseModel):
    """One recorded reason a proposal needs a human's eyes (G08).

    A proposal can carry several: a deterministic transition-rule violation
    and a contradiction the model found are different kinds of warning, and
    the review queue shows both.
    """

    kind: str = Field(
        description=("direct_contradiction | implication_contradiction | transition_rule"),
        max_length=64,
    )
    severity: str = Field(default="high", max_length=32)
    explanation: str = Field(default="", max_length=2000)
    implications: str = Field(default="", max_length=2000)
    rule: str = Field(default="", max_length=200)
    detected_at: datetime | None = None


# =============================================================================
# PROPOSED CHANGE SCHEMAS
# =============================================================================


class ProposedChangeCreate(BaseModel):
    """Request to create a ProposedChange."""

    scene_id: UUID | None = Field(None, description="Scene ID (required for scene-based proposals)")
    story_id: UUID | None = Field(None, description="Story ID (for story-level proposals)")
    turn_id: UUID | None = Field(None, description="Turn ID that proposed this (if from a turn)")
    change_type: ProposalType = Field(description="Type of proposed change")
    content: dict[str, Any] = Field(description="Flexible JSON payload for the proposed change")
    evidence: list[Evidence] = Field(default_factory=list, description="Supporting evidence for this proposal")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence level for this proposal (0.0-1.0)",
    )
    authority: Authority = Field(default=Authority.SYSTEM, description="Who asserted this change")
    proposer: str = Field(default="Unknown", description="Agent or user who created this proposal")
    source: str | None = Field(
        default=None,
        max_length=200,
        description="Attribution tag, e.g. 'capture_entry:<id>' or 'ingestion_job:<id>'",
    )
    proposal_type: str | None = Field(
        default=None,
        max_length=100,
        description="Raw extraction subtype, e.g. 'capture_candidate_fact'",
    )
    # G-9 Phase 2 — advisory review flag. Set by CanonKeeper's deterministic
    # transition rules; it never blocks acceptance on its own.
    needs_review: bool = Field(default=False, description="Flagged for human review")
    review_reason: str | None = Field(None, max_length=2000, description="Why it was flagged")
    review_source: str | None = Field(
        None,
        max_length=100,
        description="Which rule flagged it (e.g. 'transition_rule')",
    )
    # G08 — the structured flags behind the advisory review flag. The CF-8
    # queue shows them, and the accept path refuses a flagged proposal
    # without an explicit override reason.
    review_flags: list[ProposalReviewFlag] = Field(default_factory=list)

    # --- Entity promotion (ENTITY proposals only; see docs/2_architecture/data_model_workflow.md) ---
    promotion_intent: PromotionIntent | None = Field(
        None,
        description="'anchor' or 'flavor', tagged inline by the Narrator. None for non-ENTITY proposals.",
    )
    interaction_count: int = Field(
        default=1,
        ge=1,
        description="Number of turns this entity has been mentioned/interacted with in the scene.",
    )
    is_mechanically_bound: bool = Field(
        default=False,
        description="True if this entity was referenced in a resolved mechanical action (combat, trade, etc).",
    )

    @field_validator("scene_id", "story_id")
    @classmethod
    def validate_scene_or_story(cls, v: UUID | None, info: ValidationInfo) -> UUID | None:
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
            "UI",
            # Conversatory proposals carry universe_id instead of scene/story.
            "NPCVoice",
            "CharacterChat",
        }
        if self.scene_id is None and self.story_id is None and self.proposer not in scope_free_proposers:
            raise ValueError("Either scene_id or story_id must be provided")


class ProposedChangeUpdate(BaseModel):
    """Request to update a ProposedChange.

    Only CanonKeeper can update status from pending to accepted/rejected.
    """

    status: ProposalStatus = Field(description="New status for the proposal")
    decision_metadata: DecisionMetadata = Field(description="Decision metadata (required when updating status)")


class ProposedChangeResponse(BaseModel):
    """Response with ProposedChange data."""

    proposal_id: UUID
    scene_id: UUID | None = None
    story_id: UUID | None = None
    turn_id: UUID | None = None
    change_type: ProposalType
    content: dict[str, Any]
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float
    authority: Authority
    proposer: str
    status: ProposalStatus
    decision_metadata: DecisionMetadata | None = None
    promotion_intent: PromotionIntent | None = None
    interaction_count: int = 1
    is_mechanically_bound: bool = False
    # Source lineage: how this proposal entered the system.
    # source is the attribution tag (e.g. 'knowledge_pack:<uuid>',
    # 'ingestion_job:<uuid>'); proposal_type is the raw extraction subtype
    # (e.g. 'create_axiom', 'create_entity_archetype') — change_type is the
    # normalized ProposalType category.
    source: str | None = None
    proposal_type: str | None = None
    # CF-8 review disposition. Deferred proposals remain pending and can still
    # be edited, accepted, or rejected later.
    deferred: bool = False
    defer_reason: str | None = None
    edit_reason: str | None = None
    # G-9 Phase 2 — advisory review flag (see ProposedChangeCreate).
    needs_review: bool = False
    review_reason: str | None = None
    review_source: str | None = None
    # G08 — the structured flags behind the advisory review flag.
    review_flags: list[ProposalReviewFlag] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CanonOverrideRecord(BaseModel):
    """One override: a flagged proposal the GM accepted anyway (G08).

    The audit trail answers "who let this contradiction into canon, and why".
    """

    proposal_id: UUID
    owner_id: str = Field(max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    universe_id: UUID | None = None
    story_id: UUID | None = None
    scene_id: UUID | None = None
    flag_kinds: list[str] = Field(default_factory=list)
    hard_mode: bool = Field(
        default=False,
        description="Whether the owner's hard-rejection mode was on when this was overridden",
    )


class ProposedChangeFilter(BaseModel):
    """Filter parameters for listing proposed changes."""

    scene_id: UUID | None = None
    story_id: UUID | None = None
    status: ProposalStatus | None = None
    change_type: ProposalType | None = None
    source: str | None = Field(
        None,
        description="Filter by source tag (e.g. 'knowledge_pack:<uuid>')",
    )
    needs_review: bool | None = Field(
        None,
        description="Filter by the advisory review flag (G-9 Phase 2)",
    )
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at",
        description="Field to sort by: created_at, confidence",
    )
    sort_order: str = Field(default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$")


class ProposedChangeListResponse(BaseModel):
    """Response with list of proposed changes and pagination info."""

    proposed_changes: list[ProposedChangeResponse]
    total: int
    limit: int
    offset: int
