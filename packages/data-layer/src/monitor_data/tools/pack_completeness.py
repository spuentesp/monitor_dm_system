"""
KnowledgePack completeness validation logic.

LAYER: 1 (data-layer)
IMPORTS FROM: monitor_data.schemas

Provides compute_knowledge_pack_completeness() — a pure function that
assesses any KnowledgePackResponse against type-aware thresholds and
returns a KnowledgePackCompleteness with per-category scores and
overall status.

Thresholds:
  RULEBOOK          — needs axioms, entities, game_system, plus lore or tables
  SETTING_SUPPLEMENT — needs entities, lore, plus topologies
  ADVENTURE_MODULE  — needs entities, tables, agendas, plus game_system
  HOMEBREW          — needs entities, lore (lenient)
  SESSION_NOTES     — needs entities, agendas (minimum bar)
  WIKI              — needs entities, lore
  CUSTOM            — needs entities
"""

from monitor_data.schemas.knowledge_packs import KnowledgePackResponse, KnowledgePackType
from monitor_data.schemas.pack_completeness import (
    CompletenessCategory,
    CompletenessScores,
    KnowledgePackCompleteness,
)

# ---------------------------------------------------------------------------
# Type-aware thresholds: minimum items required per category per pack type
# ---------------------------------------------------------------------------

_MINIMUM_THRESHOLDS: dict[KnowledgePackType, dict[str, int]] = {
    # Core rulebook: needs mechanics + world scaffolding
    KnowledgePackType.RULEBOOK: {
        "axioms": 1,
        "entities": 2,
        "lore": 0,
        "tables": 0,
        "agendas": 0,
        "game_system": 1,
        "topologies": 0,
    },
    # Setting supplement: needs world-building content
    KnowledgePackType.SETTING_SUPPLEMENT: {
        "axioms": 0,
        "entities": 3,
        "lore": 3,
        "tables": 0,
        "agendas": 0,
        "game_system": 0,
        "topologies": 1,
    },
    # Adventure module: needs encounters + NPCs + goals
    KnowledgePackType.ADVENTURE_MODULE: {
        "axioms": 0,
        "entities": 2,
        "lore": 0,
        "tables": 2,
        "agendas": 1,
        "game_system": 0,
        "topologies": 0,
    },
    # User homebrew: lenient, just needs some content
    KnowledgePackType.HOMEBREW: {
        "axioms": 0,
        "entities": 1,
        "lore": 1,
        "tables": 0,
        "agendas": 0,
        "game_system": 0,
        "topologies": 0,
    },
    # Session notes: player-driven, minimum bar
    KnowledgePackType.SESSION_NOTES: {
        "axioms": 0,
        "entities": 1,
        "lore": 0,
        "tables": 0,
        "agendas": 1,
        "game_system": 0,
        "topologies": 0,
    },
    # Wiki: needs entities and lore
    KnowledgePackType.WIKI: {
        "axioms": 0,
        "entities": 2,
        "lore": 2,
        "tables": 0,
        "agendas": 0,
        "game_system": 0,
        "topologies": 0,
    },
    # Custom: very lenient
    KnowledgePackType.CUSTOM: {
        "axioms": 0,
        "entities": 1,
        "lore": 0,
        "tables": 0,
        "agendas": 0,
        "game_system": 0,
        "topologies": 0,
    },
}

# Weight for overall score (must sum to 1.0)
_CATEGORY_WEIGHTS: dict[str, float] = {
    "axioms": 0.10,
    "entities": 0.20,
    "lore": 0.15,
    "tables": 0.15,
    "agendas": 0.10,
    "game_system": 0.20,
    "topologies": 0.10,
}


def _score_category(present: int, expected: int) -> tuple[float, str]:
    """Return (score, status) for a category."""
    if expected == 0:
        return (1.0 if present > 0 else 0.0, "complete" if present > 0 else "missing")
    if present == 0:
        return (0.0, "missing")
    ratio = present / expected
    if ratio >= 1.0:
        return (min(1.0, ratio), "complete")
    if ratio >= 0.5:
        return (ratio, "partial")
    return (ratio, "partial")


def _build_category(name: str, present: int, expected: int) -> CompletenessCategory:
    score, status = _score_category(present, expected)
    return CompletenessCategory(
        category=name,
        present=present,
        expected=expected,
        score=round(score, 3),
        status=status,
    )


def compute_knowledge_pack_completeness(
    pack: KnowledgePackResponse,
) -> KnowledgePackCompleteness:
    """
    Compute completeness score and per-category breakdown for a KnowledgePack.

    Args:
        pack: KnowledgePackResponse (from mongodb_get_knowledge_pack or similar)

    Returns:
        KnowledgePackCompleteness with overall score, per-category breakdown,
        and recommendations.
    """
    pack_type = KnowledgePackType(
        pack.pack_type.value if hasattr(pack.pack_type, "value") else pack.pack_type
    )
    thresholds = _MINIMUM_THRESHOLDS.get(pack_type, _MINIMUM_THRESHOLDS[KnowledgePackType.CUSTOM])

    # Count items in each category
    present = {
        "axioms": len(pack.axioms),
        "entities": len(pack.entity_archetypes),
        "lore": len(pack.lore_facts),
        "tables": len(pack.random_tables),
        "agendas": len(pack.agendas),
        "game_system": 1 if (pack.game_system_id or pack.game_system_data) else 0,
        "topologies": len(pack.topologies),
    }

    categories = CompletenessScores(
        axioms=_build_category("axioms", present["axioms"], thresholds["axioms"]),
        entities=_build_category("entities", present["entities"], thresholds["entities"]),
        lore=_build_category("lore", present["lore"], thresholds["lore"]),
        tables=_build_category("tables", present["tables"], thresholds["tables"]),
        agendas=_build_category("agendas", present["agendas"], thresholds["agendas"]),
        game_system=_build_category(
            "game_system", present["game_system"], thresholds["game_system"]
        ),
        topologies=_build_category("topologies", present["topologies"], thresholds["topologies"]),
    )

    # Compute overall weighted score (only count categories with a threshold > 0)
    total_weight = 0.0
    weighted_sum = 0.0
    for cat_name in CompletenessScores.model_fields:
        threshold = thresholds.get(cat_name, 0)
        cat_score = getattr(categories, cat_name).score
        if threshold > 0:
            weight = _CATEGORY_WEIGHTS.get(cat_name, 0.0)
            weighted_sum += weight * cat_score
            total_weight += weight
    # Normalize by actual total weight used
    overall_score = round(weighted_sum / total_weight, 3) if total_weight > 0 else 0.0

    # Determine overall status based on normalized score
    if total_weight == 0:
        overall_status = "empty"
    elif overall_score >= 1.0:
        overall_status = "complete"
    elif overall_score >= 0.5:
        overall_status = "partial"
    elif overall_score >= 0.2:
        overall_status = "minimal"
    else:
        overall_status = "empty"

    # Collect missing/partial categories (only categories with threshold > 0)
    cat_fields = CompletenessScores.model_fields
    missing = [
        name
        for name in cat_fields
        if thresholds.get(name, 0) > 0 and getattr(categories, name).status == "missing"
    ]
    partial = [
        name
        for name in cat_fields
        if thresholds.get(name, 0) > 0 and getattr(categories, name).status == "partial"
    ]

    # Build summary and recommendations
    pct = int(overall_score * 100)
    partial_names = ", ".join(partial) if partial else None
    summary = f"{pct}% complete — missing {partial_names}" if partial_names else f"{pct}% complete"

    recommendations: list[str] = []
    for cat_name in CompletenessScores.model_fields:
        cat = getattr(categories, cat_name)
        if cat.status == "missing":
            recommendations.append(f"Add {cat_name} content to this pack")
        elif cat.status == "partial" and cat.expected > 0:
            recommendations.append(f"Expand {cat_name}: {cat.present}/{cat.expected} items")

    return KnowledgePackCompleteness(
        pack_id=pack.id,
        pack_name=pack.name,
        pack_type=pack.pack_type.value if hasattr(pack.pack_type, "value") else pack.pack_type,
        overall_score=overall_score,
        overall_status=overall_status,
        categories=categories,
        missing_categories=missing,
        partial_categories=partial,
        summary=summary,
        thresholds_applied=thresholds,
        recommendations=recommendations,
    )
