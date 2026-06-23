"""
Behavior tests for game_system data extraction and indexing.

Covers:
- _build_attr_by_abbr: index attributes by abbreviation
- _build_named_index: index items by lowercased name
- build_system_data: full extraction from a raw game_systems document
- SystemData.primary_attributes: deduplicated primary attrs

Use Cases: P-3, P-5, P-8 (game system runtime)
"""

from __future__ import annotations

import pytest

from monitor_agents.game_system._types import (
    SystemData,
    _build_attr_by_abbr,
    _build_named_index,
    build_system_data,
)


# =============================================================================
# _build_attr_by_abbr
# =============================================================================


class TestBuildAttrByAbbr:
    """Index attributes by their abbreviation (upper-cased)."""

    def test_simple_attrs(self):
        attrs = [
            {"name": "Strength", "abbreviation": "STR"},
            {"name": "Dexterity", "abbreviation": "DEX"},
        ]
        result = _build_attr_by_abbr(attrs)
        assert "STR" in result
        assert "DEX" in result
        assert result["STR"]["name"] == "Strength"

    def test_uppercases_abbreviation(self):
        attrs = [{"name": "Strength", "abbreviation": "str"}]
        result = _build_attr_by_abbr(attrs)
        # Should be uppercased
        assert "STR" in result
        assert "str" not in result

    def test_missing_abbreviation_uses_name_prefix(self):
        attrs = [{"name": "Strength"}]
        result = _build_attr_by_abbr(attrs)
        # No abbreviation → use first 4 chars of name
        assert "STRE" in result

    def test_empty_attrs(self):
        result = _build_attr_by_abbr([])
        assert result == {}

    def test_duplicate_abbreviations_last_wins(self):
        # Last attribute with same abbreviation wins (dict overwrites)
        attrs = [
            {"name": "First", "abbreviation": "STR"},
            {"name": "Second", "abbreviation": "STR"},
        ]
        result = _build_attr_by_abbr(attrs)
        assert result["STR"]["name"] == "Second"


# =============================================================================
# _build_named_index
# =============================================================================


class TestBuildNamedIndex:
    """Index items by their lowercased name field."""

    def test_simple_index(self):
        items = [
            {"name": "Fireball", "level": 3},
            {"name": "Heal", "level": 2},
        ]
        result = _build_named_index(items)
        assert "fireball" in result
        assert "heal" in result
        assert result["fireball"]["level"] == 3

    def test_skips_items_without_name(self):
        items = [
            {"name": "Fireball", "level": 3},
            {"level": 5},  # no name → skipped
        ]
        result = _build_named_index(items)
        assert "fireball" in result
        assert "" not in result  # empty key not in result

    def test_empty_items(self):
        assert _build_named_index([]) == {}


# =============================================================================
# build_system_data
# =============================================================================


def _minimal_doc(**overrides) -> dict:
    """Build a minimal valid game_systems document for testing."""
    doc = {
        "name": "Test System",
        "attributes": [
            {"name": "Strength", "abbreviation": "STR"},
            {"name": "Agility", "abbreviation": "AGI"},
        ],
        "resources": [
            {"name": "Health", "abbreviation": "HP"},
        ],
        "skills": [],
        "rules": [],
        "tracks": [],
        "conditions": [],
        "tiered_abilities": [],
        "core_mechanic": {"resolution": "dice_roll"},
    }
    doc.update(overrides)
    return doc


class TestBuildSystemData:
    """Extract and index a full game_systems document."""

    def test_minimal_doc(self):
        sd = build_system_data(_minimal_doc())
        assert isinstance(sd, SystemData)
        assert len(sd.attrs) == 2
        assert len(sd.resources) == 1
        assert len(sd.skills) == 0
        assert len(sd.tracks) == 0
        assert len(sd.conditions) == 0
        assert len(sd.tiered_abilities) == 0
        assert sd.core == {"resolution": "dice_roll"}

    def test_attr_by_abbr_built(self):
        sd = build_system_data(_minimal_doc())
        assert "STR" in sd.attr_by_abbr
        assert "AGI" in sd.attr_by_abbr

    def test_track_by_name_built(self):
        doc = _minimal_doc(tracks=[{"name": "Stress"}, {"name": "Humanity"}])
        sd = build_system_data(doc)
        assert "stress" in sd.track_by_name
        assert "humanity" in sd.track_by_name

    def test_condition_by_name_built(self):
        doc = _minimal_doc(conditions=[{"name": "Stunned"}, {"name": "Poisoned"}])
        sd = build_system_data(doc)
        assert "stunned" in sd.condition_by_name
        assert "poisoned" in sd.condition_by_name

    def test_tiered_by_name_built(self):
        doc = _minimal_doc(
            tiered_abilities=[
                {"name": "Fireball"},
                {"name": "Meteor"},
            ]
        )
        sd = build_system_data(doc)
        assert "fireball" in sd.tiered_by_name
        assert "meteor" in sd.tiered_by_name

    def test_routing_tables_built(self):
        """The factory builds skill/attribute/rule routing tables."""
        doc = _minimal_doc(
            skills=[{"name": "Stealth", "attribute": "AGI"}],
        )
        sd = build_system_data(doc)
        # Routing tables should be non-empty lists (they may be empty for minimal doc)
        assert isinstance(sd.skill_routes, list)
        assert isinstance(sd.attribute_routes, list)
        assert isinstance(sd.rule_subject_routes, list)

    def test_empty_doc_handled(self):
        sd = build_system_data({})
        assert isinstance(sd, SystemData)
        assert sd.attrs == []
        assert sd.resources == []
        assert sd.skills == []

    def test_damage_model_optional(self):
        sd = build_system_data(_minimal_doc())
        assert sd.damage_model is None  # not in minimal doc

    def test_damage_model_loaded(self):
        damage = {"formula": "1d6", "type": "slashing"}
        sd = build_system_data(_minimal_doc(damage_model=damage))
        assert sd.damage_model == damage


# =============================================================================
# SystemData.primary_attributes
# =============================================================================


class TestPrimaryAttributes:
    """Deduplicated primary attributes (one per abbreviation)."""

    def test_returns_deduped_list(self):
        sd = build_system_data(_minimal_doc())
        result = sd.primary_attributes
        # 2 attrs in minimal doc
        assert len(result) == 2
        # Should contain both
        names = {a["name"] for a in result}
        assert names == {"Strength", "Agility"}

    def test_handles_duplicate_abbreviations(self):
        # Two attrs with same abbreviation
        doc = _minimal_doc(
            attributes=[
                {"name": "Strength1", "abbreviation": "STR"},
                {"name": "Strength2", "abbreviation": "STR"},
            ]
        )
        sd = build_system_data(doc)
        result = sd.primary_attributes
        # Only one should be returned (last one wins)
        assert len(result) == 1
        assert result[0]["name"] == "Strength2"


# =============================================================================
# SystemData.frozen
# =============================================================================


class TestSystemDataFrozen:
    """SystemData is a frozen dataclass."""

    def test_cannot_modify_attributes(self):
        sd = build_system_data(_minimal_doc())
        with pytest.raises((AttributeError, Exception)):
            sd.attrs = []  # type: ignore[misc]

    def test_cannot_add_field(self):
        sd = build_system_data(_minimal_doc())
        with pytest.raises((AttributeError, Exception)):
            sd.new_field = "x"  # type: ignore[attr-defined]
