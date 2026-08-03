"""Cross-field validation: ExtractedEntityArchetype sub_type by entity_type.

Sub-plan 1 of docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md.
"""
from __future__ import annotations

from monitor_data.schemas.entity_subtypes import GroupType, PlaceType
from monitor_data.schemas.knowledge_packs import (
    ExtractedEntityArchetype,
    ExtractedRelationship,
)
from monitor_data.schemas.relationships import RelationshipType


def test_organization_sub_type_coerced_to_group_type():
    e = ExtractedEntityArchetype(
        name="Camarilla",
        entity_type="organization",
        sub_type="sect",
    )
    assert e.sub_type == "sect"
    assert e.group_type == GroupType.SECT


def test_organization_unknown_sub_type_becomes_other():
    e = ExtractedEntityArchetype(
        name="Warp Council",
        entity_type="organization",
        sub_type="warp_council",
    )
    assert e.sub_type == "warp_council"  # preserved
    assert e.group_type == GroupType.OTHER
    assert e.properties.get("_original_sub_type") == "warp_council"


def test_location_sub_type_coerced_to_place_type():
    e = ExtractedEntityArchetype(
        name="New York",
        entity_type="location",
        sub_type="city",
    )
    assert e.sub_type == "city"
    assert e.place_type == PlaceType.CITY


def test_location_unknown_sub_type_becomes_other():
    e = ExtractedEntityArchetype(
        name="Astral Plane",
        entity_type="location",
        sub_type="astral_plane",
    )
    assert e.sub_type == "astral_plane"  # preserved
    assert e.place_type == PlaceType.OTHER


def test_concept_sub_type_unchanged():
    """Concepts (Discipline, Feat, etc.) keep free-text sub_type."""
    e = ExtractedEntityArchetype(
        name="Auspex",
        entity_type="concept",
        sub_type="discipline",
    )
    assert e.sub_type == "discipline"
    assert e.group_type is None
    assert e.place_type is None


def test_character_sub_type_unchanged():
    e = ExtractedEntityArchetype(
        name="Toreador Elder",
        entity_type="character",
        sub_type="vampire",
    )
    assert e.sub_type == "vampire"
    assert e.group_type is None


def test_organization_without_sub_type_uses_other():
    e = ExtractedEntityArchetype(
        name="Unknown Cabal",
        entity_type="organization",
    )
    assert e.group_type == GroupType.OTHER


def test_location_without_sub_type_uses_other():
    e = ExtractedEntityArchetype(
        name="Somewhere",
        entity_type="location",
    )
    assert e.place_type == PlaceType.OTHER


def test_organization_known_group_term_preserved_unchanged():
    """Known terms like 'clan' pass through the validator unchanged
    (the sub_type is already canonical, so no need to record an
    _original_sub_type)."""
    e = ExtractedEntityArchetype(
        name="Toreador",
        entity_type="organization",
        sub_type="clan",
    )
    assert e.sub_type == "clan"
    assert e.group_type == GroupType.CLAN
    assert "_original_sub_type" not in e.properties


# === Task 4: ExtractedRelationship.rel_type normalisation ===

def test_relationship_rel_type_accepts_new_canonical_value():
    r = ExtractedRelationship(
        from_entity="Toreador",
        to_entity="Presence",
        rel_type="GRANTS_POWER",
    )
    assert r.rel_type == "GRANTS_POWER"


def test_relationship_rel_type_normalises_member_of_clan_to_group():
    """LLM may emit game-system-specific terms; the schema normalises
    them to the canonical game-system-agnostic type."""
    r = ExtractedRelationship(
        from_entity="Toreador Elder",
        to_entity="Camarilla",
        rel_type="member_of_clan",
    )
    assert r.rel_type == "MEMBER_OF_GROUP"


def test_relationship_rel_type_normalises_serves_in():
    r = ExtractedRelationship(
        from_entity="Soldier",
        to_entity="Army",
        rel_type="serves_in",
    )
    assert r.rel_type == "MEMBER_OF_GROUP"


def test_relationship_rel_type_normalises_has_merit_to_background():
    r = ExtractedRelationship(
        from_entity="Hero",
        to_entity="Natural Leader",
        rel_type="has_merit",
    )
    assert r.rel_type == "IS_BACKGROUND"


def test_relationship_rel_type_lowercases_canonical():
    """The canonical values are uppercase enum values. The normaliser
    passes them through unchanged (uppercase)."""
    r = ExtractedRelationship(
        from_entity="A",
        to_entity="B",
        rel_type="MEMBER_OF_GROUP",
    )
    assert r.rel_type == "MEMBER_OF_GROUP"


def test_relationship_rel_type_preserves_unknown_value():
    """Unknown rel_type values pass through unchanged so the canonkeeper
    can decide what to do with them (or so we surface the new term in
    future enum additions)."""
    r = ExtractedRelationship(
        from_entity="X",
        to_entity="Y",
        rel_type="some_weird_relationship",
    )
    assert r.rel_type == "some_weird_relationship"


def test_relationship_default_rel_type_is_related_to():
    r = ExtractedRelationship(from_entity="A", to_entity="B")
    assert r.rel_type == "related_to"


def test_relationship_rel_type_empty_string_defaults_to_related_to():
    r = ExtractedRelationship(from_entity="A", to_entity="B", rel_type="")
    assert r.rel_type == "related_to"


def test_relationship_rel_type_normalises_whitespace_and_case():
    r = ExtractedRelationship(
        from_entity="A",
        to_entity="B",
        rel_type="  Member Of Clan  ",
    )
    assert r.rel_type == "MEMBER_OF_GROUP"


def test_relationship_rel_type_normalises_live_ingest_aliases():
    """Aliases the LLM actually emitted during the VtM 20th Anniversary
    ingest (2026-08-02) get normalised to the canonical game-system-
    agnostic types. Captures the empirical coverage gap that the
    next ingest needs to close."""
    cases = [
        ("power_of", "AFFECTED_BY"),
        ("powers", "AFFECTED_BY"),
        ("powered_by", "AFFECTED_BY"),
        ("granted_by", "GRANTS_POWER"),
        ("grants_access_to", "GRANTS_POWER"),
        ("is_example_of", "SUBTYPE_OF"),
        ("has_example", "SUBTYPE_OF"),
        ("example_of", "SUBTYPE_OF"),
        ("has_member", "MEMBER_OF_GROUP"),
        ("possesses", "MEMBER_OF_GROUP"),
        ("works_with", "ALLIED_WITH_GROUP"),
        ("defined_by", "AFFECTED_BY"),
        ("causes", "AFFECTED_BY"),
        ("subject_to", "AFFECTED_BY"),
        ("involved_in", "AFFECTED_BY"),
        ("leads_to", "AFFECTED_BY"),
        ("uses", "PRACTICES_DISCIPLINE"),
        ("used_by", "PRACTICES_DISCIPLINE"),
        ("used_in", "PRACTICES_DISCIPLINE"),
        ("uses_ability", "PRACTICES_DISCIPLINE"),
        ("applies_to", "PRACTICES_DISCIPLINE"),
        ("available_to", "PRACTICES_DISCIPLINE"),
        ("leader_of", "LEADS_GROUP"),
        ("also_known_as", "SUBTYPE_OF"),
    ]
    for llm_emitted, expected_canonical in cases:
        r = ExtractedRelationship(
            from_entity="X",
            to_entity="Y",
            rel_type=llm_emitted,
        )
        assert r.rel_type == expected_canonical, (
            f"LLM-emitted '{llm_emitted}' should normalise to "
            f"'{expected_canonical}', got '{r.rel_type}'"
        )
