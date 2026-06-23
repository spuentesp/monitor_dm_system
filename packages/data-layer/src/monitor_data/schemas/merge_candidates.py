"""
Entity merge candidate detection schemas for I-13 (Cross-Source Synthesis).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid) and base schemas
CALLED BY: mongodb_tools/entities.py, agents/merger_agent.py
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MergeConfidence(str, Enum):
    """Confidence level for merge candidate suggestions."""

    HIGH = "high"  # >0.85 - very likely same entity
    MEDIUM = "medium"  # 0.7-0.85 - probable match
    LOW = "low"  # 0.5-0.7 - possible match, needs review
    UNCERTAIN = "uncertain"  # <0.5 - unlikely, shown only if explicitly requested


class MergeProposalStatus(str, Enum):
    """Status of a merge proposal."""

    PENDING = "pending"  # Awaiting user review
    APPROVED = "approved"  # Approved by user, ready for canonization
    REJECTED = "rejected"  # User rejected this merge
    APPLIED = "applied"  # Successfully merged and canonized


class EntityMergeCandidate(BaseModel):
    """
    Group of entities that likely represent the same thing.

    Produced by similarity detection after ingestion. Used to surface
    duplicate entities to users for manual review before merging.
    """

    candidate_id: UUID = Field(description="Unique identifier for this candidate group")
    universe_id: UUID = Field(description="Which universe these entities belong to")
    entity_ids: List[UUID] = Field(
        min_length=2,
        description="Entities that may be duplicates",
    )
    merge_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence that these are the same entity",
    )
    confidence_level: MergeConfidence = Field(
        description="Human-readable confidence bucket",
    )
    similarity_metrics: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-metric scores: name_similarity, type_match, prop_overlap, "
            "relationship_overlap, shared_context"
        ),
    )
    conflicting_fields: List[str] = Field(
        default_factory=list,
        description="Fields where entities have different values",
    )
    agreed_fields: List[str] = Field(
        default_factory=list,
        description="Fields where all entities have the same value",
    )
    source_pack_ids: List[UUID] = Field(
        default_factory=list,
        description="Knowledge packs that contributed entities to this candidate",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When candidate was generated",
    )
    reviewed_at: Optional[datetime] = Field(
        None,
        description="When user reviewed this candidate",
    )


class MergeDecision(BaseModel):
    """User's decision on a single field during merge review."""

    field_path: str = Field(
        description="Dot-notation path to field (e.g., 'properties.race', 'description')",
    )
    source_entity_id: UUID = Field(
        description="Which entity's value to use for this field",
    )
    custom_value: Optional[Any] = Field(
        None,
        description="If user entered a custom value instead of choosing a source",
    )


class MergeReviewRequest(BaseModel):
    """Request to review and resolve a merge candidate."""

    decisions: List[MergeDecision] = Field(
        description="User's field-level decisions",
    )
    relationship_decisions: Dict[str, bool] = Field(
        default_factory=dict,
        description="Mapping of 'entityId:relType:targetId' -> keep (True) or discard (False)",
    )
    notes: str = Field(
        default="",
        description="User's notes on this merge decision",
    )


class MergeProposal(BaseModel):
    """
    A proposed merge ready for CanonKeeper review.

    Created after user completes merge review. Contains the merged entity
    data and all source entities for traceability.
    """

    proposal_id: UUID = Field(description="Unique proposal identifier")
    candidate_id: UUID = Field(description="Which candidate this proposal came from")
    universe_id: UUID = Field(description="Target universe for the merge")
    status: MergeProposalStatus = Field(
        default=MergeProposalStatus.PENDING,
    )

    # The merged entity data (ready for creation)
    merged_entity_name: str
    merged_entity_type: str
    merged_description: str
    merged_properties: Dict[str, Any] = Field(default_factory=dict)
    merged_tags: List[str] = Field(default_factory=list)

    # Source tracking
    source_entity_ids: List[UUID] = Field(
        description="Entities being merged (for traceability)",
    )
    source_pack_ids: List[UUID] = Field(
        description="Packs that contributed source entities",
    )
    resolution_notes: Dict[str, str] = Field(
        default_factory=dict,
        description="User's notes on each field decision",
    )

    # Confidence
    user_reviewed_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Original confidence boosted after user review",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
