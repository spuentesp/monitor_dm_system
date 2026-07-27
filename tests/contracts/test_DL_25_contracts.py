"""
Contract tests for Combat schemas (DL-25).

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)

pytest --test-run-type=unit tests/contracts/test_DL_25_contracts.py
"""

from datetime import datetime, timezone, UTC
from uuid import UUID, uuid4

import pytest
from monitor_data.schemas.base import CombatSide, CombatStatus
from monitor_data.schemas.combat import (
    AddCombatLogEntry,
    AddCombatParticipant,
    CombatCreate,
    CombatEnvironment,
    CombatFilter,
    CombatListResponse,
    CombatLogEntry,
    CombatOutcome,
    CombatParticipant,
    CombatResponse,
    CombatUpdate,
    Condition,
    RemoveCombatParticipant,
    SetCombatOutcome,
    UpdateCombatParticipant,
)
from pydantic import ValidationError

# =============================================================================
# CONDITION
# =============================================================================


class TestCondition:
    def test_minimal(self):
        c = Condition(
            name="Stunned", source="Monk's Stunning Strike", duration_type="rounds"
        )
        assert c.name == "Stunned"
        assert c.source == "Monk's Stunning Strike"
        assert c.duration_remaining is None
        assert c.metadata == {}

    def test_full(self):
        c = Condition(
            name="Blessed",
            source="Cleric's Bless",
            duration_type="rounds",
            duration_remaining=5,
            metadata={"save_dc": 15},
        )
        assert c.duration_remaining == 5
        assert c.metadata["save_dc"] == 15

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            Condition(name="A" * 101, source="test", duration_type="rounds")

    def test_source_too_long(self):
        with pytest.raises(ValidationError):
            Condition(name="test", source="B" * 201, duration_type="rounds")


# =============================================================================
# COMBAT PARTICIPANT
# =============================================================================


class TestCombatParticipant:
    def test_minimal(self):
        eid = uuid4()
        p = CombatParticipant(entity_id=eid, name="Goblin", side=CombatSide.ENEMY)
        assert p.entity_id == eid
        assert p.side == CombatSide.ENEMY
        assert p.is_active is True
        assert p.conditions == []
        assert p.initiative_value is None

    def test_full(self):
        eid = uuid4()
        p = CombatParticipant(
            entity_id=eid,
            name="Aragorn",
            side=CombatSide.PC,
            initiative_value=18.5,
            resources={"HP": 45, "max_HP": 45},
            position={"x": 10, "y": 20},
        )
        assert p.initiative_value == 18.5
        assert p.resources["HP"] == 45

    def test_invalid_side_raises(self):
        with pytest.raises(ValidationError):
            CombatParticipant(entity_id=uuid4(), name="X", side="INVALID")


class TestAddCombatParticipant:
    def test_minimal(self):
        eid = uuid4()
        r = AddCombatParticipant(
            encounter_id=uuid4(), entity_id=eid, name="Orc", side=CombatSide.ENEMY
        )
        assert r.name == "Orc"
        assert r.initiative_value is None


class TestUpdateCombatParticipant:
    def test_empty_update(self):
        r = UpdateCombatParticipant(encounter_id=uuid4(), entity_id=uuid4())
        assert r.initiative_value is None
        assert r.is_active is None


class TestRemoveCombatParticipant:
    def test_valid(self):
        r = RemoveCombatParticipant(encounter_id=uuid4(), entity_id=uuid4())
        assert isinstance(r.encounter_id, UUID)


# =============================================================================
# ENVIRONMENT
# =============================================================================


class TestCombatEnvironment:
    def test_defaults(self):
        env = CombatEnvironment()
        assert env.terrain == "normal"
        assert env.lighting == "normal"
        assert env.hazards == []

    def test_custom(self):
        env = CombatEnvironment(
            terrain="swamp", lighting="dim", hazards=[{"type": "quicksand"}]
        )
        assert env.terrain == "swamp"
        assert len(env.hazards) == 1


# =============================================================================
# COMBAT LOG
# =============================================================================


class TestCombatLogEntry:
    def test_valid(self):
        now = datetime.now(UTC)
        entry = CombatLogEntry(
            round=1,
            turn=1,
            actor_id=uuid4(),
            action="Attack",
            summary="Goblin attacks",
            timestamp=now,
        )
        assert entry.round == 1
        assert entry.action == "Attack"

    def test_round_must_be_ge_1(self):
        with pytest.raises(ValidationError):
            CombatLogEntry(
                round=0,
                turn=1,
                actor_id=uuid4(),
                action="X",
                summary="Y",
                timestamp=datetime.now(UTC),
            )


class TestAddCombatLogEntry:
    def test_valid(self):
        r = AddCombatLogEntry(
            encounter_id=uuid4(),
            round=2,
            turn=3,
            actor_id=uuid4(),
            action="Cast Fireball",
            summary="BOOM",
        )
        assert r.round == 2


# =============================================================================
# COMBAT OUTCOME
# =============================================================================


class TestCombatOutcome:
    def test_victory(self):
        o = CombatOutcome(result="victory", winning_side=CombatSide.PC)
        assert o.result == "victory"
        assert o.winning_side == CombatSide.PC

    def test_defaults(self):
        o = CombatOutcome(result="retreat")
        assert o.survivors == []
        assert o.casualties == []
        assert o.xp_awarded is None


class TestSetCombatOutcome:
    def test_valid(self):
        r = SetCombatOutcome(encounter_id=uuid4(), result="victory")
        assert r.result == "victory"


# =============================================================================
# COMBAT CRUD
# =============================================================================


class TestCombatCreate:
    def test_minimal(self):
        sid = uuid4()
        c = CombatCreate(scene_id=sid, story_id=uuid4())
        assert c.scene_id == sid
        assert c.participants == []

    def test_with_participants(self):
        p = CombatParticipant(entity_id=uuid4(), name="Hero", side=CombatSide.PC)
        c = CombatCreate(scene_id=uuid4(), story_id=uuid4(), participants=[p])
        assert len(c.participants) == 1


class TestCombatUpdate:
    def test_empty(self):
        u = CombatUpdate()
        assert u.status is None
        assert u.round is None

    def test_set_status(self):
        u = CombatUpdate(status=CombatStatus.ACTIVE)
        assert u.status == CombatStatus.ACTIVE


class TestCombatResponse:
    def test_minimal(self):
        now = datetime.now(UTC)
        eid = uuid4()
        p = CombatParticipant(entity_id=eid, name="Fighter", side=CombatSide.PC)
        r = CombatResponse(
            id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            status=CombatStatus.INITIALIZING,
            participants=[p],
            environment=CombatEnvironment(),
            created_at=now,
        )
        assert r.status == CombatStatus.INITIALIZING
        assert len(r.participants) == 1
        assert r.combat_log == []


# =============================================================================
# ENUMS
# =============================================================================


class TestCombatStatusEnum:
    def test_values(self):
        assert CombatStatus.INITIALIZING.value == "initializing"
        assert CombatStatus.INITIATIVE.value == "initiative"
        assert CombatStatus.ACTIVE.value == "active"
        assert CombatStatus.PAUSED.value == "paused"
        assert CombatStatus.RESOLVED.value == "resolved"


class TestCombatSideEnum:
    def test_values(self):
        assert CombatSide.PC.value == "pc"
        assert CombatSide.ALLY.value == "ally"
        assert CombatSide.ENEMY.value == "enemy"
        assert CombatSide.NEUTRAL.value == "neutral"


# =============================================================================
# QUERY
# =============================================================================


class TestCombatFilter:
    def test_defaults(self):
        f = CombatFilter()
        assert f.limit == 50
        assert f.offset == 0

    def test_limit_bounds(self):
        with pytest.raises(ValidationError):
            CombatFilter(limit=0)
        with pytest.raises(ValidationError):
            CombatFilter(limit=101)


class TestCombatListResponse:
    def test_valid(self):
        r = CombatListResponse(combats=[], total=0, limit=50, offset=0)
        assert r.total == 0
