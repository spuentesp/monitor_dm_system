"""
Contract tests for Character Working State schemas (DL-26).

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)

pytest --test-run-type=unit tests/contracts/test_DL_27_contracts.py
"""

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.working_state import (
    AddStatModification,
    AddTemporaryEffect,
    CharacterWorkingState,
    DurationType,
    InventoryChange,
    InventoryChangeType,
    StatModification,
    TemporaryEffect,
    WorkingStateCreate,
    WorkingStateFilter,
    WorkingStateListResponse,
    WorkingStateResponse,
    WorkingStateUpdate,
)
from pydantic import ValidationError

# =============================================================================
# ENUMS
# =============================================================================


class TestDurationType:
    def test_values(self):
        assert DurationType.ROUNDS.value == "rounds"
        assert DurationType.MINUTES.value == "minutes"
        assert DurationType.HOURS.value == "hours"
        assert DurationType.SCENE.value == "scene"
        assert DurationType.UNTIL_REST.value == "until_rest"
        assert DurationType.PERMANENT.value == "permanent"
        assert DurationType.CONCENTRATION.value == "concentration"


class TestInventoryChangeType:
    def test_values(self):
        assert InventoryChangeType.ADD.value == "add"
        assert InventoryChangeType.REMOVE.value == "remove"
        assert InventoryChangeType.USE.value == "use"
        assert InventoryChangeType.EQUIP.value == "equip"
        assert InventoryChangeType.UNEQUIP.value == "unequip"


# =============================================================================
# STAT MODIFICATION
# =============================================================================


class TestStatModification:
    def test_valid(self):
        now = datetime.now(UTC)
        m = StatModification(
            mod_id=uuid4(),
            stat_or_resource="HP",
            change=-10,
            source="Fireball",
            timestamp=now,
        )
        assert m.stat_or_resource == "HP"
        assert m.change == -10
        assert m.source == "Fireball"

    def test_source_id_optional(self):
        now = datetime.now(UTC)
        m = StatModification(
            mod_id=uuid4(),
            stat_or_resource="STR",
            change=2,
            source="Potion",
            timestamp=now,
        )
        assert m.source_id is None


# =============================================================================
# TEMPORARY EFFECT
# =============================================================================


class TestTemporaryEffect:
    def test_valid(self):
        now = datetime.now(UTC)
        e = TemporaryEffect(
            effect_id=uuid4(),
            name="Bless",
            source="Cleric",
            stat_modifiers={"attack": 1, "saves": 1},
            duration_type=DurationType.ROUNDS,
            duration_remaining=10,
            applied_at=now,
        )
        assert e.name == "Bless"
        assert e.stat_modifiers["attack"] == 1
        assert e.duration_type == DurationType.ROUNDS


# =============================================================================
# INVENTORY CHANGE
# =============================================================================


class TestInventoryChange:
    def test_valid(self):
        now = datetime.now(UTC)
        c = InventoryChange(
            change_type=InventoryChangeType.ADD,
            item="Potion of Healing",
            quantity=1,
            timestamp=now,
        )
        assert c.change_type == InventoryChangeType.ADD
        assert c.item == "Potion of Healing"


# =============================================================================
# CHARACTER WORKING STATE
# =============================================================================


class TestCharacterWorkingState:
    def test_minimal(self):
        now = datetime.now(UTC)
        sid = uuid4()
        state = CharacterWorkingState(
            id=sid,
            state_id=sid,
            entity_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            created_at=now,
            updated_at=now,
        )
        assert state.base_stats == {}
        assert state.current_stats == {}
        assert state.resources == {}
        assert state.canonized is False

    def test_with_resources(self):
        now = datetime.now(UTC)
        sid = uuid4()
        state = CharacterWorkingState(
            id=sid,
            state_id=sid,
            entity_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            resources={"HP": 30, "max_HP": 45, "spell_slots": {"1": 2, "2": 1}},
            created_at=now,
            updated_at=now,
        )
        assert state.resources["HP"] == 30


# =============================================================================
# WORKING STATE CREATE
# =============================================================================


class TestWorkingStateCreate:
    def test_minimal(self):
        w = WorkingStateCreate(
            entity_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            base_stats={"STR": 10},
            resources={"HP": 20},
        )
        assert w.base_stats["STR"] == 10
        assert w.current_stats is None

    def test_with_current_stats(self):
        w = WorkingStateCreate(
            entity_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            base_stats={"STR": 10},
            current_stats={"STR": 12},
            resources={"HP": 20},
        )
        assert w.current_stats["STR"] == 12


# =============================================================================
# WORKING STATE UPDATE
# =============================================================================


class TestWorkingStateUpdate:
    def test_empty(self):
        u = WorkingStateUpdate()
        assert u.current_stats is None
        assert u.resources is None

    def test_update_resources(self):
        u = WorkingStateUpdate(resources={"HP": 15})
        assert u.resources["HP"] == 15


# =============================================================================
# ADD STAT MODIFICATION / ADD TEMPORARY EFFECT
# =============================================================================


class TestAddStatModification:
    def test_valid(self):
        a = AddStatModification(
            state_id=uuid4(), stat_or_resource="HP", change=-5, source="Sword"
        )
        assert a.stat_or_resource == "HP"


class TestAddTemporaryEffect:
    def test_valid(self):
        a = AddTemporaryEffect(
            state_id=uuid4(),
            name="Stunned",
            source="Monk",
            duration_type=DurationType.ROUNDS,
            duration_remaining=1,
        )
        assert a.name == "Stunned"


# =============================================================================
# FILTER
# =============================================================================


class TestWorkingStateFilter:
    def test_defaults(self):
        f = WorkingStateFilter()
        assert f.limit == 50
        assert f.offset == 0

    def test_limit_bounds(self):
        with pytest.raises(ValidationError):
            WorkingStateFilter(limit=0)
        with pytest.raises(ValidationError):
            WorkingStateFilter(limit=101)


# =============================================================================
# RESPONSE
# =============================================================================


class TestWorkingStateResponse:
    def test_valid(self):
        now = datetime.now(UTC)
        sid = uuid4()
        state = CharacterWorkingState(
            id=sid,
            state_id=sid,
            entity_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            created_at=now,
            updated_at=now,
        )
        r = WorkingStateResponse(state=state)
        assert r.state.state_id == sid


class TestWorkingStateListResponse:
    def test_valid(self):
        r = WorkingStateListResponse(states=[], total=0, limit=50, offset=0)
        assert r.total == 0
