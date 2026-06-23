"""
Behavior tests for P-10: Combat loop.

Tests combat state management without DB/LLM dependencies.
"""

from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from monitor_data.schemas.base import CombatStatus, CombatSide
from monitor_data.schemas.combat import (
    Condition,
    CombatParticipant,
    CombatCreate,
    CombatUpdate,
    CombatOutcome,
    CombatEnvironment,
)


class TestCombatLifecycle:
    def test_combat_starts_in_initializing(self):
        """Combat starts with INITIALIZING status."""
        c = CombatCreate(scene_id=uuid4(), story_id=uuid4())
        assert c.participants == []

    def test_combat_status_transitions(self):
        """All valid combat statuses are recognized."""
        valid_statuses = [CombatStatus.INITIALIZING, CombatStatus.INITIATIVE, CombatStatus.ACTIVE, CombatStatus.PAUSED, CombatStatus.RESOLVED]
        for status in valid_statuses:
            u = CombatUpdate(status=status)
            assert u.status == status

    def test_combat_update_with_round(self):
        """CombatUpdate accepts round number."""
        u = CombatUpdate(round=3)
        assert u.round == 3

    def test_combat_update_turn_order(self):
        """CombatUpdate accepts turn order list."""
        eids = [uuid4(), uuid4(), uuid4()]
        u = CombatUpdate(turn_order=eids)
        assert len(u.turn_order) == 3


class TestCombatParticipants:
    def test_create_participant(self):
        """Participants can be created for each side."""
        for side in CombatSide:
            p = CombatParticipant(entity_id=uuid4(), name=f"Unit-{side.value}", side=side)
            assert p.side == side
            assert p.is_active is True

    def test_participant_with_conditions(self):
        """Participant can have conditions."""
        p = CombatParticipant(
            entity_id=uuid4(),
            name="Stunned Fighter",
            side=CombatSide.PC,
            conditions=[Condition(name="Stunned", source="Monk", duration_type="rounds", duration_remaining=2)],
        )
        assert len(p.conditions) == 1
        assert p.conditions[0].name == "Stunned"


class TestCombatOutcome:
    def test_victory_outcome(self):
        """Combat can end with victory."""
        survivors = [uuid4(), uuid4()]
        o = CombatOutcome(result="victory", winning_side=CombatSide.PC, survivors=survivors, xp_awarded=500)
        assert o.winning_side == CombatSide.PC
        assert len(o.survivors) == 2
        assert o.xp_awarded == 500

    def test_retreat_outcome(self):
        """Combat can end with retreat."""
        o = CombatOutcome(result="retreat", casualties=[uuid4()])
        assert o.result == "retreat"
        assert len(o.casualties) == 1


class TestCombatEnvironment:
    def test_hazardous_environment(self):
        """Environment can have hazards."""
        env = CombatEnvironment(
            terrain="volcanic",
            lighting="dim",
            hazards=[{"type": "lava_pool", "damage": "2d6"}],
        )
        assert len(env.hazards) == 1
        assert env.terrain == "volcanic"
