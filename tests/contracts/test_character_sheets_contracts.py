"""Contract tests for the CharacterSheet schemas.

Verifies that character_sheets Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce numeric / length constraints,
- reject invalid enum values where applicable.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.character_sheets import (
    ApplyXPRequest,
    CharacterSheetCreate,
    CharacterSheetFilter,
    CharacterSheetListResponse,
    CharacterSheetResponse,
    CharacterSheetUpdate,
    SetActiveSheetRequest,
    SheetHistoryEntry,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# =============================================================================
# SheetHistoryEntry
# =============================================================================


class TestSheetHistoryEntry:
    def test_minimal_entry(self):
        ts = datetime.now(UTC)
        entry = SheetHistoryEntry(timestamp=ts, change="created sheet")
        assert entry.timestamp == ts
        assert entry.change == "created sheet"
        assert entry.scene_id is None
        assert entry.old_value is None
        assert entry.new_value is None
        assert entry.field is None

    def test_full_entry(self):
        ts = datetime.now(UTC)
        scene_id = uuid4()
        entry = SheetHistoryEntry(
            timestamp=ts,
            change="increased STR",
            scene_id=scene_id,
            old_value=14,
            new_value=16,
            field="stats.STR",
        )
        assert entry.scene_id == scene_id
        assert entry.old_value == 14
        assert entry.new_value == 16
        assert entry.field == "stats.STR"

    def test_change_required(self):
        with pytest.raises(ValidationError):
            SheetHistoryEntry(timestamp=datetime.now(UTC))  # type: ignore[call-arg]

    def test_change_too_long(self):
        with pytest.raises(ValidationError):
            SheetHistoryEntry(
                timestamp=datetime.now(UTC),
                change="x" * 501,
            )

    def test_field_too_long(self):
        with pytest.raises(ValidationError):
            SheetHistoryEntry(
                timestamp=datetime.now(UTC),
                change="x",
                field="y" * 201,
            )


# =============================================================================
# CharacterSheetCreate
# =============================================================================


class TestCharacterSheetCreate:
    def test_minimal_create(self):
        entity_id = uuid4()
        sheet = CharacterSheetCreate(entity_id=entity_id)
        assert sheet.entity_id == entity_id
        assert sheet.game_system_id is None
        assert sheet.system_source_type is None
        assert sheet.system_source_id is None
        assert sheet.system_name is None
        assert sheet.stats == {}
        assert sheet.resources == {}
        assert sheet.skills == {}
        assert sheet.class_levels == {}
        assert sheet.total_level == 1
        assert sheet.experience_points == 0
        assert sheet.background is None
        assert sheet.alignment is None
        assert sheet.equipment == []
        assert sheet.special_abilities == []
        assert sheet.spells_known == []
        assert sheet.notes is None

    def test_full_create(self):
        sheet = CharacterSheetCreate(
            entity_id=uuid4(),
            game_system_id=uuid4(),
            system_source_type="pack_embedded",
            system_source_id="pack-123",
            system_name="D&D 5e",
            stats={"STR": 16, "DEX": 12},
            resources={"HP": 45, "max_HP": 45},
            skills={"Stealth": 5},
            class_levels={"Fighter": 3, "Rogue": 2},
            total_level=5,
            experience_points=6500,
            background="Soldier",
            alignment="Lawful Good",
            equipment=[{"name": "Sword", "qty": 1}],
            special_abilities=["Second Wind", "Action Surge"],
            spells_known=["Magic Missile"],
            notes="Frontline fighter",
        )
        assert sheet.system_name == "D&D 5e"
        assert sheet.total_level == 5
        assert sheet.class_levels == {"Fighter": 3, "Rogue": 2}
        assert "Second Wind" in sheet.special_abilities

    def test_entity_id_required(self):
        with pytest.raises(ValidationError):
            CharacterSheetCreate()  # type: ignore[call-arg]

    def test_total_level_min(self):
        with pytest.raises(ValidationError):
            CharacterSheetCreate(entity_id=uuid4(), total_level=0)

    def test_xp_negative_rejected(self):
        with pytest.raises(ValidationError):
            CharacterSheetCreate(entity_id=uuid4(), experience_points=-1)

    def test_system_name_too_long(self):
        with pytest.raises(ValidationError):
            CharacterSheetCreate(entity_id=uuid4(), system_name="x" * 201)

    def test_notes_too_long(self):
        with pytest.raises(ValidationError):
            CharacterSheetCreate(entity_id=uuid4(), notes="x" * 5001)


# =============================================================================
# CharacterSheetUpdate
# =============================================================================


class TestCharacterSheetUpdate:
    def test_empty_update(self):
        upd = CharacterSheetUpdate()
        assert upd.stats is None
        assert upd.resources is None
        assert upd.total_level is None
        assert upd.experience_points is None

    def test_partial_update(self):
        upd = CharacterSheetUpdate(total_level=2, experience_points=300)
        assert upd.total_level == 2
        assert upd.experience_points == 300

    def test_total_level_min(self):
        with pytest.raises(ValidationError):
            CharacterSheetUpdate(total_level=0)

    def test_xp_negative_rejected(self):
        with pytest.raises(ValidationError):
            CharacterSheetUpdate(experience_points=-1)

    def test_change_description_too_long(self):
        with pytest.raises(ValidationError):
            CharacterSheetUpdate(change_description="x" * 501)


# =============================================================================
# CharacterSheetResponse
# =============================================================================


class TestCharacterSheetResponse:
    def _response_kwargs(self, **overrides):
        base = {
            "sheet_id": uuid4(),
            "entity_id": uuid4(),
            "stats": {"STR": 14},
            "resources": {"HP": 30},
            "skills": {},
            "class_levels": {"Fighter": 1},
            "total_level": 1,
            "experience_points": 0,
            "equipment": [],
            "special_abilities": [],
            "spells_known": [],
            "is_active": True,
            "created_at": datetime.now(UTC),
        }
        base.update(overrides)
        return base

    def test_minimal_response(self):
        resp = CharacterSheetResponse(**self._response_kwargs())
        assert resp.is_active is True
        assert resp.history_log == []
        assert resp.updated_at is None

    def test_with_history(self):
        ts = datetime.now(UTC)
        entry = SheetHistoryEntry(timestamp=ts, change="created")
        resp = CharacterSheetResponse(
            **self._response_kwargs(history_log=[entry], updated_at=ts)
        )
        assert len(resp.history_log) == 1
        assert resp.history_log[0].change == "created"

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            CharacterSheetResponse()  # type: ignore[call-arg]


# =============================================================================
# CharacterSheetFilter
# =============================================================================


class TestCharacterSheetFilter:
    def test_defaults(self):
        f = CharacterSheetFilter()
        assert f.entity_id is None
        assert f.game_system_id is None
        assert f.is_active is None
        assert f.limit == 20
        assert f.offset == 0

    def test_with_entity(self):
        eid = uuid4()
        f = CharacterSheetFilter(entity_id=eid, is_active=True, limit=50)
        assert f.entity_id == eid
        assert f.is_active is True
        assert f.limit == 50

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            CharacterSheetFilter(limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            CharacterSheetFilter(limit=101)

    def test_offset_min(self):
        with pytest.raises(ValidationError):
            CharacterSheetFilter(offset=-1)


# =============================================================================
# CharacterSheetListResponse
# =============================================================================


class TestCharacterSheetListResponse:
    def test_empty_list(self):
        resp = CharacterSheetListResponse(sheets=[], total=0, limit=20, offset=0)
        assert resp.sheets == []
        assert resp.total == 0
        assert resp.limit == 20
        assert resp.offset == 0

    def test_with_sheet(self):
        sheet = CharacterSheetResponse(
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
            created_at=datetime.now(UTC),
        )
        resp = CharacterSheetListResponse(sheets=[sheet], total=1, limit=20, offset=0)
        assert len(resp.sheets) == 1
        assert resp.total == 1


# =============================================================================
# SetActiveSheetRequest
# =============================================================================


class TestSetActiveSheetRequest:
    def test_minimal(self):
        eid = uuid4()
        sid = uuid4()
        req = SetActiveSheetRequest(entity_id=eid, sheet_id=sid)
        assert req.entity_id == eid
        assert req.sheet_id == sid

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            SetActiveSheetRequest(entity_id=uuid4())  # type: ignore[call-arg]


# =============================================================================
# ApplyXPRequest
# =============================================================================


class TestApplyXPRequest:
    def test_minimal(self):
        sid = uuid4()
        req = ApplyXPRequest(sheet_id=sid, xp_amount=100, source="combat victory")
        assert req.sheet_id == sid
        assert req.xp_amount == 100
        assert req.source == "combat victory"
        assert req.scene_id is None

    def test_with_scene(self):
        req = ApplyXPRequest(
            sheet_id=uuid4(),
            xp_amount=50,
            source="quest completion",
            scene_id=uuid4(),
        )
        assert req.scene_id is not None

    def test_xp_zero_rejected(self):
        with pytest.raises(ValidationError):
            ApplyXPRequest(sheet_id=uuid4(), xp_amount=0, source="x")

    def test_xp_negative_rejected(self):
        with pytest.raises(ValidationError):
            ApplyXPRequest(sheet_id=uuid4(), xp_amount=-10, source="x")

    def test_source_too_long(self):
        with pytest.raises(ValidationError):
            ApplyXPRequest(sheet_id=uuid4(), xp_amount=10, source="x" * 201)

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ApplyXPRequest()  # type: ignore[call-arg]
