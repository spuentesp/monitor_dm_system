"""Unit tests for the GroupType and PlaceType enums.

Sub-plan 1 of docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md.
"""
from __future__ import annotations

from monitor_data.schemas.entity_subtypes import (
    GroupType,
    PlaceType,
    ALL_GROUP_TYPES,
    ALL_PLACE_TYPES,
    coerce_group_subtype,
    coerce_place_subtype,
)


def test_group_type_has_universal_values():
    expected = {
        "clan", "sect", "organization", "race", "species",
        "faction", "party", "team", "crew", "house", "tribe",
        "brood", "coven", "cult", "band", "gang", "dynasty",
        "cabal", "fellowship", "alliance", "other",
    }
    actual = {t.value for t in GroupType}
    assert actual == expected


def test_place_type_has_universal_values():
    expected = {
        "world", "plane", "dimension", "continent", "region",
        "kingdom", "country", "city", "town", "district",
        "neighborhood", "structure", "building", "room", "landmark",
        "dungeon", "wilderness", "other",
    }
    actual = {t.value for t in PlaceType}
    assert actual == expected


def test_coerce_group_subtype_passes_through_known_value():
    assert coerce_group_subtype("clan") == GroupType.CLAN
    assert coerce_group_subtype("coven") == GroupType.COVEN
    assert coerce_group_subtype("dynasty") == GroupType.DYNASTY


def test_coerce_group_subtype_lowercases_input():
    assert coerce_group_subtype("Clan") == GroupType.CLAN
    assert coerce_group_subtype("DYNASTY") == GroupType.DYNASTY


def test_coerce_group_subtype_normalises_whitespace_and_dashes():
    """Spaces and dashes normalise to underscores; capitalisation
    lowercases. But semantic mapping (e.g. 'Free Cities League' →
    ALLIANCE) is NOT done — unknown terms go to OTHER."""
    assert coerce_group_subtype("Free Cities League") == GroupType.OTHER
    assert coerce_group_subtype("free-cities-league") == GroupType.OTHER
    assert coerce_group_subtype("ALLIANCE") == GroupType.ALLIANCE
    assert coerce_group_subtype("coven") == GroupType.COVEN


def test_coerce_group_subtype_returns_other_for_unknown():
    """Unknown group terms map to OTHER, never raise — the LLM may
    invent a game-system-specific term we haven't enumerated."""
    assert coerce_group_subtype("warp_council") == GroupType.OTHER
    assert coerce_group_subtype("") == GroupType.OTHER
    assert coerce_group_subtype(None) == GroupType.OTHER


def test_coerce_place_subtype_passes_through_known_value():
    assert coerce_place_subtype("city") == PlaceType.CITY
    assert coerce_place_subtype("wilderness") == PlaceType.WILDERNESS
    assert coerce_place_subtype("plane") == PlaceType.PLANE


def test_coerce_place_subtype_returns_other_for_unknown():
    assert coerce_place_subtype("astral_plane") == PlaceType.OTHER
    assert coerce_place_subtype(None) == PlaceType.OTHER
    assert coerce_place_subtype("") == PlaceType.OTHER


def test_all_lists_include_other():
    assert GroupType.OTHER in ALL_GROUP_TYPES
    assert PlaceType.OTHER in ALL_PLACE_TYPES


def test_enums_are_strenum():
    assert isinstance(GroupType.CLAN, str)
    assert isinstance(PlaceType.CITY, str)
    assert GroupType.CLAN == "clan"
    assert PlaceType.CITY == "city"
