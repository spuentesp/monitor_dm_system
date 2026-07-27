"""
Pydantic schemas for KnowledgePack completeness validation.

LAYER: 1 (data-layer)

Provides a completeness score and per-category breakdown for any KnowledgePack,
enabling the UI to show "pack health" indicators and the pipeline to gate
`status: ready` on minimum coverage thresholds.

Thresholds are type-aware — a RULEBOOK needs game-system mechanics,
a SETTING_SUPPLEMENT needs lore and entities, an ADVENTURE_MODULE needs
encounters and maps.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Score components
# ---------------------------------------------------------------------------


class CompletenessCategory(BaseModel):
    """Score for one category of extracted content."""

    category: str = Field(description="Category name: axioms, entities, lore, tables, agendas, game_system, topologies")
    present: int = Field(description="Number of items found")
    expected: int = Field(description="Target number for this pack type (0 = not required)")
    score: float = Field(description="present/expected if expected > 0, else 1.0 if present > 0 else 0.0")
    status: str = Field(description="missing | partial | complete")


class CompletenessScores(BaseModel):
    """Per-category completeness breakdown."""

    axioms: CompletenessCategory
    entities: CompletenessCategory
    lore: CompletenessCategory
    tables: CompletenessCategory
    agendas: CompletenessCategory
    game_system: CompletenessCategory
    topologies: CompletenessCategory


# ---------------------------------------------------------------------------
# Main validation output
# ---------------------------------------------------------------------------


class KnowledgePackCompleteness(BaseModel):
    """
    Completeness assessment for a KnowledgePack.

    Returned by compute_knowledge_pack_completeness() — used by:
    - The UI pack library (show "78% complete — missing tables")
    - The ingestion pipeline (gate status=ready on minimum thresholds)
    - Audit trails (log completeness on apply)
    """

    pack_id: UUID
    pack_name: str
    pack_type: str

    overall_score: float = Field(
        description="Weighted 0.0-1.0 overall completeness",
        ge=0.0,
        le=1.0,
    )
    overall_status: str = Field(
        description="complete | partial | minimal | empty",
    )

    categories: CompletenessScores

    missing_categories: list[str] = Field(
        default_factory=list,
        description="Categories with score of 0",
    )
    partial_categories: list[str] = Field(
        default_factory=list,
        description="Categories with score between 0 and 1",
    )

    # Human-readable summary
    summary: str = Field(
        max_length=500,
        description="One-line summary: '85% complete — missing random tables and agendas'",
    )

    # Thresholds used
    thresholds_applied: dict[str, int] = Field(
        default_factory=dict,
        description="Map of category → minimum expected count for this pack type",
    )

    recommendations: list[str] = Field(
        default_factory=list,
        description="What to do to improve completeness",
    )
