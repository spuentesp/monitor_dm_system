"""Unit tests for the canonkeeper's relationship type maps.

Sub-plan 1 of docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md.
"""

from __future__ import annotations

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_data.schemas.relationships import RelationshipType


def test_rel_type_map_covers_every_relationship_type():
    """Every enum value must have a canonical Neo4j mapping. The map key
    is lowercase (the LLM's input), the value is the canonical
    uppercase enum value (what we write to Neo4j)."""
    for t in RelationshipType:
        # The canonkeeper map keys are lowercase aliases; the canonical
        # value is the uppercase enum value. Either the lowercase
        # canonical OR a known alias must be present.
        canonical_lower = t.value.lower()
        assert canonical_lower in CanonKeeper._REL_TYPE_MAP, (
            f"{t.name}: _REL_TYPE_MAP missing lowercase '{canonical_lower}' (and no alias covers it)"
        )
        assert CanonKeeper._REL_TYPE_MAP[canonical_lower] == t.value, (
            f"{t.name}: _REL_TYPE_MAP['{canonical_lower}'] = "
            f"{CanonKeeper._REL_TYPE_MAP[canonical_lower]!r}, expected {t.value!r}"
        )


def test_rel_category_map_covers_every_relationship_type():
    for t in RelationshipType:
        category = CanonKeeper._REL_CATEGORY_MAP.get(t.value)
        assert category, f"{t.name}: missing from _REL_CATEGORY_MAP"


def test_group_types_map_to_membership_category():
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
        assert CanonKeeper._REL_CATEGORY_MAP[t.value] == "membership"


def test_place_types_map_to_spatial_category():
    place_types = [
        RelationshipType.LOCATED_IN_PLACE,
        RelationshipType.CONTAINS_PLACE,
    ]
    for t in place_types:
        assert CanonKeeper._REL_CATEGORY_MAP[t.value] == "spatial"


def test_aliases_resolve_to_canonical_type():
    """LLM may emit game-system-specific aliases; the canonkeeper must
    resolve them to the canonical game-system-agnostic type. Note: the
    legacy aliases (member_of, located_in, contains, etc.) are kept for
    backward compatibility and resolve to the legacy enum values. The
    new game-system-agnostic aliases (member_of_sect, based_in, etc.)
    resolve to the new generic types."""
    alias_expectations = {
        "member_of_sect": "MEMBER_OF_GROUP",
        "member_of_clan": "MEMBER_OF_GROUP",
        "belongs_to": "MEMBER_OF_GROUP",
        "serves_in": "MEMBER_OF_GROUP",
        "subclan_of": "SUBGROUP_OF_GROUP",
        "leads_sect": "LEADS_GROUP",
        "rules_over": "LEADS_GROUP",
        "grants": "GRANTS_POWER",
        "has_power": "PRACTICES_DISCIPLINE",
        "practices": "PRACTICES_DISCIPLINE",
        "has_merit": "IS_BACKGROUND",
        "has_flaw": "IS_BACKGROUND",
        "has_edge": "IS_BACKGROUND",
        "has_touchstone": "IS_TOUCHSTONE",
        # Legacy aliases resolve to legacy enum values for backward
        # compat. The new generic aliases are separate entries.
        "located_in": "LOCATED_IN",
        "contains": "CONTAINS",
        "based_in": "LOCATED_IN_PLACE",
        "in_city": "LOCATED_IN_PLACE",
        "in_world": "LOCATED_IN_PLACE",
    }
    for alias, canonical in alias_expectations.items():
        assert CanonKeeper._REL_TYPE_MAP.get(alias) == canonical, (
            f"alias '{alias}' should resolve to '{canonical}', got {CanonKeeper._REL_TYPE_MAP.get(alias)!r}"
        )
