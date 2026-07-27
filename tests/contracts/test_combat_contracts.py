"""
Contract tests for Combat schemas.

Covers:
- Condition: temporary condition affecting a combatant
- CombatParticipant: participant in combat
- AddCombatParticipant / UpdateCombatParticipant / RemoveCombatParticipant
- CombatEnvironment: environmental factors
- CombatLogEntry / AddCombatLogEntry: combat log
- CombatOutcome / SetCombatOutcome: final outcome

Use Cases: Phase 1 Combat system
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from monitor_data.schemas.base import CombatSide
from monitor_data.schemas.combat import (
    AddCombatLogEntry,
    AddCombatParticipant,
    CombatEnvironment,
    CombatLogEntry,
    CombatOutcome,
    CombatParticipant,
    Condition,
    RemoveCombatParticipant,
    SetCombatOutcome,
    UpdateCombatParticipant,
)

# =============================================================================
# Condition
# =============================================================================


class TestCondition:
    def test_minimal(self):
        c = Condition(
            name="Stunned",
            source="Stunning blow",
            duration_type="rounds",
        )
        assert c.name == "Stunned"
        assert c.duration_remaining is None  # default
        assert c.metadata == {}  # default

    def test_with_duration(self):
        c = Condition(
            name="Blessed",
            source="Bless spell",
            duration_type="rounds",
            duration_remaining=10,
        )
        assert c.duration_remaining == 10

    def test_with_metadata(self):
        c = Condition(
            name="Charmed",
            source="Charm person",
            duration_type="concentration",
            duration_remaining=100,
            metadata={"save_dc": 15, "caster": "Aria"},
        )
        assert c.metadata["save_dc"] == 15

    def test_negative_duration_fails(self):
        with pytest.raises(Exception):
            Condition(
                name="X",
                source="Y",
                duration_type="rounds",
                duration_remaining=-1,
            )


# =============================================================================
# CombatParticipant
# =============================================================================


class TestCombatParticipant:
    def test_minimal(self):
        p = CombatParticipant(
            entity_id=uuid4(),
            name="Goblin Scout",
            side=CombatSide.ENEMY,
        )
        assert p.is_active is True  # default
        assert p.conditions == []  # default
        assert p.resources == {}  # default
        assert p.initiative_value is None  # default

    def test_with_initiative(self):
        p = CombatParticipant(
            entity_id=uuid4(),
            name="Hero",
            side=CombatSide.PC,
            initiative_value=18.5,
        )
        assert p.initiative_value == 18.5

    def test_with_conditions(self):
        p = CombatParticipant(
            entity_id=uuid4(),
            name="Wizard",
            side=CombatSide.PC,
            conditions=[
                Condition(
                    name="Concentrating", source="Spell", duration_type="concentration"
                ),
            ],
        )
        assert len(p.conditions) == 1

    def test_inactive(self):
        p = CombatParticipant(
            entity_id=uuid4(),
            name="KO'd Fighter",
            side=CombatSide.PC,
            is_active=False,
        )
        assert p.is_active is False


# =============================================================================
# AddCombatParticipant
# =============================================================================


class TestAddCombatParticipant:
    def test_minimal(self):
        req = AddCombatParticipant(
            encounter_id=uuid4(),
            entity_id=uuid4(),
            name="Orc",
            side=CombatSide.ENEMY,
        )
        assert req.encounter_id is not None
        assert req.initiative_value is None

    def test_with_resources(self):
        req = AddCombatParticipant(
            encounter_id=uuid4(),
            entity_id=uuid4(),
            name="Hero",
            side=CombatSide.PC,
            initiative_value=15,
            resources={"hp": 30, "mp": 10},
        )
        assert req.resources["hp"] == 30


# =============================================================================
# UpdateCombatParticipant
# =============================================================================


class TestUpdateCombatParticipant:
    def test_empty(self):
        u = UpdateCombatParticipant(
            encounter_id=uuid4(),
            entity_id=uuid4(),
        )
        assert u.is_active is None
        assert u.conditions is None
        assert u.resources is None

    def test_partial(self):
        u = UpdateCombatParticipant(
            encounter_id=uuid4(),
            entity_id=uuid4(),
            is_active=False,
            initiative_value=10,
        )
        assert u.is_active is False
        assert u.initiative_value == 10


# =============================================================================
# RemoveCombatParticipant
# =============================================================================


class TestRemoveCombatParticipant:
    def test_basic(self):
        req = RemoveCombatParticipant(
            encounter_id=uuid4(),
            entity_id=uuid4(),
        )
        assert req.encounter_id is not None
        assert req.entity_id is not None


# =============================================================================
# CombatEnvironment
# =============================================================================


class TestCombatEnvironment:
    def test_minimal(self):
        e = CombatEnvironment()
        assert e.terrain == "normal"  # default
        assert e.lighting == "normal"  # default
        assert e.hazards == []  # default
        assert e.cover_positions == []  # default

    def test_with_hazards(self):
        e = CombatEnvironment(
            terrain="difficult",
            lighting="dim",
            hazards=[{"type": "fire", "damage": "2d6"}],
        )
        assert e.terrain == "difficult"
        assert len(e.hazards) == 1


# =============================================================================
# CombatLogEntry
# =============================================================================


class TestCombatLogEntry:
    def test_minimal(self):
        e = CombatLogEntry(
            round=1,
            turn=1,
            actor_id=uuid4(),
            action="Attack",
            summary="Hero swings at goblin",
            timestamp=datetime.utcnow(),
        )
        assert e.round == 1
        assert e.resolution_id is None  # default

    def test_with_resolution(self):
        e = CombatLogEntry(
            round=2,
            turn=3,
            actor_id=uuid4(),
            action="Cast Fireball",
            resolution_id=uuid4(),
            summary="Explosion damages 3 goblins",
            timestamp=datetime.utcnow(),
        )
        assert e.resolution_id is not None


# =============================================================================
# AddCombatLogEntry
# =============================================================================


class TestAddCombatLogEntry:
    def test_minimal(self):
        req = AddCombatLogEntry(
            encounter_id=uuid4(),
            round=1,
            turn=1,
            actor_id=uuid4(),
            action="Attack",
            summary="Hero swings at goblin",
        )
        assert req.resolution_id is None

    def test_round_bounds(self):
        with pytest.raises(Exception):
            AddCombatLogEntry(
                encounter_id=uuid4(),
                round=0,  # < 1
                turn=1,
                actor_id=uuid4(),
                action="x",
                summary="x",
            )


# =============================================================================
# CombatOutcome
# =============================================================================


class TestCombatOutcome:
    def test_minimal(self):
        o = CombatOutcome(result="victory")
        assert o.result == "victory"
        assert o.winning_side is None
        assert o.survivors == []
        assert o.casualties == []
        assert o.xp_awarded is None

    def test_with_xp(self):
        o = CombatOutcome(
            result="victory",
            winning_side=CombatSide.PC,
            xp_awarded=500,
            survivors=[uuid4()],
        )
        assert o.xp_awarded == 500

    def test_negative_xp_fails(self):
        with pytest.raises(Exception):
            CombatOutcome(result="defeat", xp_awarded=-1)


# =============================================================================
# SetCombatOutcome
# =============================================================================


class TestSetCombatOutcome:
    def test_minimal(self):
        req = SetCombatOutcome(
            encounter_id=uuid4(),
            result="retreat",
        )
        assert req.winning_side is None
        assert req.survivors is None

    def test_full(self):
        req = SetCombatOutcome(
            encounter_id=uuid4(),
            result="negotiated",
            survivors=[uuid4()],
            casualties=[uuid4()],
            loot=[{"item": "gold", "amount": 100}],
            xp_awarded=50,
        )
        assert req.loot[0]["item"] == "gold"
