"""
Contract tests for CharacterSheet schemas.

LAYER: 1 (data-layer)
TESTS: Schema validation (unit)

pytest --test-run-type=unit tests/contracts/test_DL_26_contracts.py
"""

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.character_sheets import (
    CharacterSheetCreate,
    CharacterSheetFilter,
    CharacterSheetListResponse,
    CharacterSheetResponse,
    CharacterSheetUpdate,
    SheetHistoryEntry,
)
from pydantic import ValidationError

# =============================================================================
# SHEET HISTORY ENTRY
# =============================================================================


class TestSheetHistoryEntry:
    def test_minimal(self):
        now = datetime.now(UTC)
        e = SheetHistoryEntry(timestamp=now, change="Leveled up to 5")
        assert e.change == "Leveled up to 5"
        assert e.scene_id is None
        assert e.old_value is None

    def test_full(self):
        now = datetime.now(UTC)
        sid = uuid4()
        e = SheetHistoryEntry(
            timestamp=now,
            change="HP reduced",
            scene_id=sid,
            old_value=45,
            new_value=30,
            field="resources.HP",
        )
        assert e.scene_id == sid
        assert e.new_value == 30


# =============================================================================
# CHARACTER SHEET CREATE
# =============================================================================


class TestCharacterSheetCreate:
    def test_minimal(self):
        eid = uuid4()
        s = CharacterSheetCreate(entity_id=eid)
        assert s.entity_id == eid
        assert s.stats == {}
        assert s.resources == {}
        assert s.skills == {}
        assert s.class_levels == {}
        assert s.total_level == 1
        assert s.experience_points == 0

    def test_full(self):
        eid = uuid4()
        gsid = uuid4()
        s = CharacterSheetCreate(
            entity_id=eid,
            game_system_id=gsid,
            system_source_type="generic_library",
            system_source_id=str(gsid),
            system_name="D&D 5e",
            stats={"STR": 16, "DEX": 12, "CON": 14},
            resources={"HP": 45, "max_HP": 45},
            skills={"Stealth": 5, "Arcana": 8},
            class_levels={"Fighter": 3, "Rogue": 2},
            total_level=5,
            experience_points=6500,
            background="Soldier",
            alignment="Lawful Good",
            equipment=[{"name": "Longsword", "quantity": 1}],
            special_abilities=["Action Surge", "Sneak Attack"],
            spells_known=["Shield", "Magic Missile"],
            notes="Multiclass build",
        )
        assert s.stats["STR"] == 16
        assert s.class_levels["Fighter"] == 3
        assert s.total_level == 5

    def test_total_level_defaults_to_1(self):
        s = CharacterSheetCreate(entity_id=uuid4())
        assert s.total_level == 1

    def test_experience_points_defaults_to_0(self):
        s = CharacterSheetCreate(entity_id=uuid4())
        assert s.experience_points == 0


# =============================================================================
# CHARACTER SHEET UPDATE
# =============================================================================


class TestCharacterSheetUpdate:
    def test_empty_update(self):
        u = CharacterSheetUpdate()
        assert u.stats is None
        assert u.resources is None

    def test_partial_update(self):
        u = CharacterSheetUpdate(
            resources={"HP": 20, "max_HP": 45},
            change_description="Took damage from trap",
        )
        assert u.resources["HP"] == 20

    def test_experience_points_ge_0(self):
        with pytest.raises(ValidationError):
            CharacterSheetUpdate(experience_points=-1)

    def test_total_level_ge_1(self):
        with pytest.raises(ValidationError):
            CharacterSheetUpdate(total_level=0)


# =============================================================================
# CHARACTER SHEET RESPONSE
# =============================================================================


class TestCharacterSheetResponse:
    def test_minimal(self):
        now = datetime.now(UTC)
        r = CharacterSheetResponse(
            sheet_id=uuid4(),
            entity_id=uuid4(),
            stats={},
            resources={},
            skills={},
            class_levels={},
            total_level=1,
            experience_points=0,
            equipment=[],
            special_abilities=[],
            spells_known=[],
            is_active=True,
            created_at=now,
        )
        assert r.is_active is True
        assert r.history_log == []

    def test_full(self):
        now = datetime.now(UTC)
        r = CharacterSheetResponse(
            sheet_id=uuid4(),
            entity_id=uuid4(),
            game_system_id=uuid4(),
            system_source_type="generic_library",
            system_source_id="abc",
            system_name="D&D 5e",
            stats={"STR": 10},
            resources={"HP": 10},
            skills={},
            class_levels={"Fighter": 1},
            total_level=1,
            experience_points=0,
            background="Acolyte",
            alignment="Neutral",
            equipment=[],
            special_abilities=[],
            spells_known=[],
            is_active=True,
            history_log=[SheetHistoryEntry(timestamp=now, change="Created")],
            created_at=now,
        )
        assert r.background == "Acolyte"
        assert len(r.history_log) == 1


# =============================================================================
# QUERY
# =============================================================================


class TestCharacterSheetFilter:
    def test_defaults(self):
        f = CharacterSheetFilter()
        assert f.limit == 20
        assert f.offset == 0

    def test_filter_by_entity(self):
        eid = uuid4()
        f = CharacterSheetFilter(entity_id=eid)
        assert f.entity_id == eid

    def test_limit_bounds(self):
        with pytest.raises(ValidationError):
            CharacterSheetFilter(limit=0)
        with pytest.raises(ValidationError):
            CharacterSheetFilter(limit=101)


class TestCharacterSheetListResponse:
    def test_valid(self):
        r = CharacterSheetListResponse(sheets=[], total=0, limit=20, offset=0)
        assert r.sheets == []
