"""
Pydantic schemas for cross-pack deduplication (P2-7).

LAYER: 1 (data-layer)

Before a KnowledgePack is applied to the multiverse, we check its items against
all previously-applied packs for the same universe/multiverse to detect
duplicate or near-duplicate content. Duplicates are flagged for review or
auto-resolved based on strategy.

This prevents:
- The same axiom getting canonized twice
- Conflicting entity archetypes from different source books
- Duplicate lore facts from overlapping sources (e.g., a PHB and a campaign setting)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DeduplicationStrategy(str, Enum):
    """How to resolve a set of duplicate items."""

    KEEP_NEW = "keep_new"  # New item supersedes existing — auto-apply
    KEEP_EXISTING = "keep_existing"  # Existing canon is authoritative — skip new
    MERGE = "merge"  # Suggest merging content from both items
    REVIEW = "review"  # Requires manual decision (conflict, ambiguity)


class DuplicateCategory(str, Enum):
    """What kind of duplication was detected."""

    EXACT = "exact"  # Identical identity field (case-insensitive)
    SEMANTIC = "semantic"  # Similar content (fuzzy match above threshold)
    SUBSUMED = "subsumed"  # New is a more general version of existing, or vice versa
    CONFLICTING = "conflicting"  # Same identity, different content (possible conflict)


class DuplicateItemRef(BaseModel):
    """A reference to one item in a duplicate group."""

    item_index: int = Field(ge=0, description="Index within its source list")
    pack_id: Optional[UUID] = Field(None, description="Pack it belongs to (None = new pack)")
    identity_value: str = Field(max_length=500, description="Value of the identity field")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    content_hash: Optional[str] = Field(
        None, max_length=64, description="MD5 of item content for EXACT detection"
    )
    item_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="Full item snapshot for review UI",
    )
    source_ref: Optional[str] = Field(None, max_length=200, description="Page/section cite")


class DuplicateGroup(BaseModel):
    """
    A set of 2+ items detected as duplicates of each other.

    The first item in `items` is always the NEW candidate.
    Subsequent items are the existing canon items it would conflict with.
    """

    duplicate_id: str = Field(
        max_length=64,
        description="Stable ID for this duplicate group (hash of identity fields)",
    )
    category: DuplicateCategory = Field(description="Type of duplication detected")
    field_name: str = Field(
        max_length=50,
        description="Which KnowledgePack field this affects (axioms, entity_archetypes, etc.)",
    )
    identity_field: str = Field(
        max_length=50,
        description="The identity field used (statement, name, title, etc.)",
    )
    strategy: DeduplicationStrategy = Field(description="Recommended resolution strategy")
    strategy_reason: str = Field(
        max_length=300,
        description="Why this strategy was recommended",
    )
    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Similarity score (1.0 = identical, 0.0 = completely different)",
    )
    items: List[DuplicateItemRef] = Field(
        description="All items in this duplicate group (new first, then existing)",
    )
    merged_content: Optional[Dict[str, Any]] = Field(
        None,
        description="Suggested merged content if strategy=MERGE",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class DeduplicationResult(BaseModel):
    """
    Result of cross-pack deduplication check for a new KnowledgePack.

    Returned when the pack is being reviewed before application.
    """

    new_pack_id: UUID = Field(description="KnowledgePack being applied")
    universe_id: Optional[UUID] = Field(None, description="Universe being applied to")
    multiverse_id: UUID = Field(description="Multiverse being applied to")
    duplicate_groups: List[DuplicateGroup] = Field(
        default_factory=list,
        description="All detected duplicate groups, newest first",
    )
    auto_resolvable_count: int = Field(
        description="Number of groups where auto-resolution is safe",
    )
    review_required_count: int = Field(
        description="Number of groups requiring manual review",
    )
    total_items_checked: int = Field(
        description="Total items from the new pack that were checked",
    )
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def has_duplicates(self) -> bool:
        return len(self.duplicate_groups) > 0

    @property
    def all_auto_resolvable(self) -> bool:
        return self.review_required_count == 0


class DeduplicationApplyRequest(BaseModel):
    """Request to apply deduplication decisions to a pack."""

    new_pack_id: UUID
    multiverse_id: UUID
    universe_id: Optional[UUID] = None
    decisions: Dict[str, DeduplicationStrategy] = Field(
        description="Map of duplicate_id → strategy decision",
    )
    author: str = Field(default="IngestionPipeline", max_length=100)
