"""
Tests for the RPG ontology's legacy class registry and sheet validation.

No game is written into the platform as code, so these use invented systems:
a hand-written legacy sheet class here, and the Lantern Drift spec for the
spec-driven path that real systems use.
"""

from typing import ClassVar
from uuid import uuid4

import pytest
from _lantern_drift_spec import LANTERN_DRIFT
from pydantic import Field, ValidationError

from monitor_data.schemas.rpg_ontology import SystemRegistry
from monitor_data.schemas.rpg_ontology.base import (
    AttributeSpec,
    BaseCharacterSheet,
    BaseGameSystem,
    GameSystemRegistry,
)
from monitor_data.schemas.rpg_ontology.factory import clear_model_cache
from monitor_data.tools.rpg_tools import rpg_validate_sheet

# =============================================================================
# An invented legacy system: one hand-written sheet class
# =============================================================================

_LEGACY_ID = "pebble_and_thread"


class _PebbleSheet(BaseCharacterSheet):
    system_id: ClassVar[str] = _LEGACY_ID
    knots: int = Field(ge=0, le=4)


_PEBBLE = BaseGameSystem(
    system_id=_LEGACY_ID,
    system_name="Pebble and Thread",
    publisher=None,
    core_mechanic_formula="2d6 + knots vs 8",
    attributes=[AttributeSpec(name="Knots", abbreviation="KNOT", min_value=0, max_value=4, default_value=1)],
    resources=[],
    schema_class="tests._PebbleSheet",
)


@pytest.fixture
def legacy():
    reg = GameSystemRegistry()
    reg.register(_PEBBLE, _PebbleSheet)
    yield reg
    reg._systems.pop(_LEGACY_ID, None)


@pytest.fixture
def invented():
    reg = SystemRegistry()
    reg.register(LANTERN_DRIFT)
    yield LANTERN_DRIFT.system_id
    reg.unregister(LANTERN_DRIFT.system_id)
    clear_model_cache(LANTERN_DRIFT.system_id)


def _pebble(**overrides) -> dict:
    return {"entity_id": str(uuid4()), "character_name": "Moss", "knots": 2, **overrides}


# =============================================================================
# Legacy GameSystemRegistry
# =============================================================================


class TestGameSystemRegistry:
    def test_no_game_is_registered_by_the_platform(self):
        assert "death_in_space" not in GameSystemRegistry().list_systems()

    def test_registered_system_is_listed_and_found(self, legacy):
        assert _LEGACY_ID in legacy.list_systems()
        assert legacy.get_definition(_LEGACY_ID).system_name == "Pebble and Thread"
        assert legacy.get_sheet_class(_LEGACY_ID) is _PebbleSheet

    def test_parse_sheet_valid(self, legacy):
        assert isinstance(legacy.parse_sheet(_LEGACY_ID, _pebble()), _PebbleSheet)

    def test_parse_sheet_out_of_range_raises(self, legacy):
        with pytest.raises(ValidationError):
            legacy.parse_sheet(_LEGACY_ID, _pebble(knots=9))

    def test_parse_sheet_unknown_system_raises(self):
        with pytest.raises(ValueError, match="Unknown game system: 'nonexistent'"):
            GameSystemRegistry().parse_sheet("nonexistent", {})

    def test_validate_attribute_value(self, legacy):
        defn = legacy.get_definition(_LEGACY_ID)
        assert defn.validate_attribute_value("KNOT", 4) is True
        assert defn.validate_attribute_value("KNOT", 0) is True
        assert defn.validate_attribute_value("KNOT", 5) is False
        assert defn.validate_attribute_value("KNOT", -1) is False

    def test_attribute_lookup_case_insensitive(self, legacy):
        defn = legacy.get_definition(_LEGACY_ID)
        assert defn.attribute_by_abbr("knot") is not None
        assert defn.attribute_by_abbr("KNOT") is not None
        assert defn.attribute_by_abbr("Knot") is not None


# =============================================================================
# rpg_validate_sheet: spec-driven systems first, then legacy classes
# =============================================================================


class TestRPGValidateSheet:
    def test_spec_system_valid_sheet(self, invented):
        result = rpg_validate_sheet(invented, {"character_name": "Wren", "grit": 1, "hp": 7})
        assert result == {"valid": True, "errors": []}

    def test_spec_system_out_of_range_rejected(self, invented):
        result = rpg_validate_sheet(invented, {"character_name": "Wren", "grit": 9})
        assert result["valid"] is False and result["errors"]

    def test_every_builtin_validates_a_sheet_from_data(self):
        # Before, only a game with a hand-written class could be validated at all.
        assert rpg_validate_sheet("fate_core", {"character_name": "Ash"})["valid"] is True

    def test_legacy_class_still_validates(self, legacy):
        assert rpg_validate_sheet(_LEGACY_ID, _pebble())["valid"] is True
        bad = rpg_validate_sheet(_LEGACY_ID, _pebble(knots=9))
        assert bad["valid"] is False and any("knots" in e for e in bad["errors"])

    def test_unknown_system_returns_error(self):
        result = rpg_validate_sheet("nonexistent_system", {})
        assert result["valid"] is False
        assert "Unknown game system" in result["errors"][0]
