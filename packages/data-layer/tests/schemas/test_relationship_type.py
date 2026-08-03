"""Unit tests for the RelationshipType enum after graph-schema expansion.

Sub-plan 1 of docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md.
"""
from __future__ import annotations

from monitor_data.schemas.relationships import (
    RelationshipType,
    RELATIONSHIP_CATEGORIES,
)


def test_new_relationship_types_exist():
    """All game-system-agnostic types added in sub-plan 1 must be present."""
    expected = {
        "MEMBER_OF_GROUP", "SUBGROUP_OF_GROUP", "LEADS_GROUP",
        "FOUNDED_GROUP", "CONTROLS_GROUP", "ALLIED_WITH_GROUP",
        "HOSTILE_TO_GROUP", "AFFECTED_BY", "GRANTS_POWER",
        "PRACTICES_DISCIPLINE", "LOCATED_IN_PLACE", "CONTAINS_PLACE",
        "IS_BACKGROUND", "IS_TOUCHSTONE", "IS_RESOURCE",
    }
    actual = {t.name for t in RelationshipType}
    missing = expected - actual
    assert not missing, f"Missing relationship types: {missing}"


def test_legacy_relationship_types_still_exist():
    """Adding new types must not break the existing schema."""
    expected_legacy = {
        "MEMBER_OF", "SUBTYPE_OF", "RELATED_TO", "ALLIED_WITH",
        "HOSTILE_TO", "PART_OF", "LOCATED_IN", "CONTAINS",
        "INSTANCE_OF", "KNOWS", "OWNS", "CONTROLLED_BY",
        "CONTROLS", "REVERES", "LEADS", "WORKS_FOR",
        "PARTICIPATES_IN", "AFFILIATED_WITH", "DERIVES_FROM",
    }
    actual = {t.name for t in RelationshipType}
    missing = expected_legacy - actual
    assert not missing, f"Legacy types removed: {missing}"


def test_relationship_categories_groups_membership():
    """All group-related types must be classified as 'membership'."""
    group_types = [
        RelationshipType.MEMBER_OF_GROUP,
        RelationshipType.SUBGROUP_OF_GROUP,
        RelationshipType.LEADS_GROUP,
        RelationshipType.FOUNDED_GROUP,
        RelationshipType.CONTROLS_GROUP,
        RelationshipType.ALLIED_WITH_GROUP,
        RelationshipType.HOSTILE_TO_GROUP,
    ]
    for t in group_types:
        assert RELATIONSHIP_CATEGORIES[t] == "membership", (
            f"{t.name} expected 'membership', got {RELATIONSHIP_CATEGORIES[t]!r}"
        )


def test_relationship_categories_place_types_spatial():
    place_types = [
        RelationshipType.LOCATED_IN_PLACE,
        RelationshipType.CONTAINS_PLACE,
    ]
    for t in place_types:
        assert RELATIONSHIP_CATEGORIES[t] == "spatial"


def test_relationship_categories_power_types_taxonomic():
    power_types = [
        RelationshipType.GRANTS_POWER,
        RelationshipType.PRACTICES_DISCIPLINE,
        RelationshipType.AFFECTED_BY,
        RelationshipType.IS_BACKGROUND,
        RelationshipType.IS_TOUCHSTONE,
        RelationshipType.IS_RESOURCE,
    ]
    for t in power_types:
        assert RELATIONSHIP_CATEGORIES[t] == "taxonomic"


def test_relationship_type_is_strenum():
    """StrEnum so values can serialize to Neo4j / Mongo without coercion."""
    assert RelationshipType.MEMBER_OF_GROUP == "MEMBER_OF_GROUP"
    assert isinstance(RelationshipType.MEMBER_OF_GROUP, str)
