"""
Pydantic schemas for re-ingestion delta detection (P2-6).

LAYER: 1 (data-layer)

When a source is re-ingested, we compare the NEW extraction against the
LAST APPLIED extraction to produce a structured delta. The delta tells
which items are: added (net-new), modified (content changed), unchanged,
or removed (present before, absent now).

The delta drives two flows:
  1. Review  — Show the user what changed so they can confirm/approve
  2. apply   — Only emit ProposedChanges for net-new and modified items,
               skipping unchanged items to avoid duplicate canon entries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DeltaCategory(StrEnum):
    """How an item changed between two extraction versions."""

    ADDED = "added"  # Present in new, absent in current → net new
    MODIFIED = "modified"  # Present in both, content differs
    UNCHANGED = "unchanged"  # Present in both, identical content
    REMOVED = "removed"  # Absent in new, present in current → was extracted, now gone


class DeltaItem(BaseModel):
    """
    A single item in the delta with its change classification.

    item_index allows referring back to the source arrays
    (e.g. pack.axioms[delta.item_index]).
    """

    item_index: int = Field(description="Index in the source array on the new pack")
    delta_category: DeltaCategory
    field_name: str = Field(
        max_length=50,
        description=(
            "Which top-level extraction field this came from: "
            "axioms, entity_archetypes, lore_facts, entity_relationships, "
            "random_tables, agendas, topologies"
        ),
    )
    # Human-readable summary of what changed (or why unchanged/removed)
    summary: str = Field(max_length=300)
    # For MODIFIED items: the specific fields that changed (dot-notation keys)
    changed_fields: list[str] = Field(
        default_factory=list,
        description="List of dot-notation field paths that differ (e.g. 'statement', 'properties.armor_class')",
    )
    # Snapshot of the item (new version for ADDED/MODIFIED, old version for REMOVED)
    item_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="Full item data at the relevant version",
    )
    confidence_delta: float | None = Field(
        None,
        description="Change in confidence score (new - old), signed float",
    )
    # Breadcrumb for locating this item in the source document
    source_ref: str | None = Field(None, max_length=200)


class IngestionDelta(BaseModel):
    """
    Structured comparison between two KnowledgePack extractions.

    The 'current' pack is the last version successfully applied to a multiverse.
    The 'new' pack is the freshly extracted result from re-ingesting the same source.

    Use compute_ingestion_delta(current_pack, new_pack) to produce this.
    """

    source_id: UUID = Field(description="Which source document this delta is for")
    pack_id_current: UUID | None = Field(None, description="KnowledgePack UUID of the currently-applied version")
    pack_id_new: UUID | None = Field(None, description="KnowledgePack UUID of the newly extracted version")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Counts
    total_axioms: int = 0
    total_entities: int = 0
    total_lore_facts: int = 0
    total_relationships: int = 0
    total_random_tables: int = 0
    total_agendas: int = 0
    total_topologies: int = 0
    total_plot_threads: int = 0

    # Per-category breakdowns
    axioms_delta: list[DeltaItem] = Field(default_factory=list)
    entities_delta: list[DeltaItem] = Field(default_factory=list)
    lore_facts_delta: list[DeltaItem] = Field(default_factory=list)
    relationships_delta: list[DeltaItem] = Field(default_factory=list)
    random_tables_delta: list[DeltaItem] = Field(default_factory=list)
    agendas_delta: list[DeltaItem] = Field(default_factory=list)
    topologies_delta: list[DeltaItem] = Field(default_factory=list)
    plot_threads_delta: list[DeltaItem] = Field(default_factory=list)

    # Rollup stats
    net_new_items: int = Field(0, description="Total ADDED items across all categories")
    modified_items: int = Field(0, description="Total MODIFIED items across all categories")
    removed_items: int = Field(0, description="Total REMOVED items across all categories")
    unchanged_items: int = Field(0, description="Total UNCHANGED items across all categories")

    # Heuristic signal
    change_significance: str = Field(
        max_length=50,
        description=(
            "minimal | minor | moderate | significant | major — overall assessment of how much the source changed"
        ),
    )

    # Recommendations for the apply flow
    recommendations: list[str] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """True if there are any net-new, modified, or removed items."""
        return self.net_new_items > 0 or self.modified_items > 0 or self.removed_items > 0

    @property
    def apply_decision(self) -> str:
        """
        Suggested default action for the apply flow.

        - 'approve_review'  — significant changes, human review recommended
        - 'auto_apply'       — only minor additions, safe to apply automatically
        - 'skip'             — no meaningful changes
        """
        if not self.has_changes:
            return "skip"
        if self.change_significance in ("minimal", "minor"):
            return "auto_apply"
        return "approve_review"


class IngestionDeltaApplyRequest(BaseModel):
    """Request to apply a specific delta subset to a multiverse."""

    source_id: UUID
    delta: IngestionDelta
    multiverse_id: UUID
    universe_id: UUID | None = None
    # What categories to include in the apply
    include_added: bool = True
    include_modified: bool = Field(
        default=True,
        description="If True, modified items replace the old version via new proposals",
    )
    proposer: str = Field(default="IngestionPipeline")
    conflict_resolution: str = Field(
        default="merge",
        description="merge | skip | force — passed through to mongodb_apply_knowledge_pack",
    )
