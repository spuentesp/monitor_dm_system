"""Cross-field validation: ExtractedEntityArchetype sub_type by entity_type.

Sub-plan 1 of docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md.
"""
from __future__ import annotations

from monitor_data.schemas.entity_subtypes import GroupType, PlaceType
from monitor_data.schemas.knowledge_packs import ExtractedEntityArchetype


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
