"""Behavior tests for CombatLoop choreography (Phase 2-3).

Exercises pure logic only — no LLM, no DB.

Covers:
- _calculate_modifier_from_attributes
- _pick_npc_target (prefers PCs, falls back to other active)
- _find_target_in_action (returns opposing-side active combatant)
- _apply_damage (HP subtraction, incapacitation at 0)
- _get_hp
- _format_combat_context
- CombatantState / CombatState defaults
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# _calculate_modifier_from_attributes
# =============================================================================


class TestCalculateModifierFromAttributes:
    def test_lowercase_key(self):
        from monitor_agents.loops.combat_loop import _calculate_modifier_from_attributes

        # DEX 14 -> modifier = (14-10)//2 = 2
        assert _calculate_modifier_from_attributes({"dex": 14}, "DEX") == 2

    def test_uppercase_key(self):
        from monitor_agents.loops.combat_loop import _calculate_modifier_from_attributes

        assert _calculate_modifier_from_attributes({"STR": 16}, "str") == 3

    def test_title_case_key(self):
        from monitor_agents.loops.combat_loop import _calculate_modifier_from_attributes

        assert (
            _calculate_modifier_from_attributes({"Intelligence": 8}, "intelligence")
            == -1
        )

    def test_missing_key_returns_default_modifier_for_zero(self):
        from monitor_agents.loops.combat_loop import _calculate_modifier_from_attributes

        # value defaults to 0 -> modifier = (0-10)//2 = -5
        assert _calculate_modifier_from_attributes({}, "DEX") == -5

    def test_gsr_overrides_default(self):
        from monitor_agents.loops.combat_loop import _calculate_modifier_from_attributes

        class FakeGSR:
            def calc_modifier(self, stat, value):
                return 99  # sentinel

        assert (
            _calculate_modifier_from_attributes({"DEX": 14}, "DEX", gsr=FakeGSR()) == 99
        )

    def test_gsr_failure_falls_back_to_default(self):
        from monitor_agents.loops.combat_loop import _calculate_modifier_from_attributes

        class BrokenGSR:
            def calc_modifier(self, stat, value):
                raise ValueError("nope")

        # Falls back to (14-10)//2 = 2
        assert (
            _calculate_modifier_from_attributes({"DEX": 14}, "DEX", gsr=BrokenGSR())
            == 2
        )


# =============================================================================
# Helpers
# =============================================================================


def _make_combatant(
    *,
    is_pc: bool = True,
    name: str = "Test",
    hp: int = 20,
    is_active: bool = True,
    attributes: dict[str, int] = None,
) -> Any:
    from monitor_agents.loops.combat_loop import CombatantState

    return CombatantState(
        entity_id=uuid4(),
        name=name,
        initiative=0,
        is_pc=is_pc,
        hp_current=hp,
        hp_max=hp,
        is_active=is_active,
        attributes=attributes or {},
    )


def _make_state(combatants: list = None) -> Any:
    from monitor_agents.loops.combat_loop import CombatState

    return CombatState(
        scene_id=uuid4(),
        story_id=uuid4(),
        combatants=combatants or [],
        initiative_order=[c.entity_id for c in combatants or []],
    )


# =============================================================================
# _pick_npc_target
# =============================================================================


class TestPickNpcTarget:
    def test_prefers_pc_target(self):
        from monitor_agents.loops.combat_loop import _pick_npc_target

        npc = _make_combatant(is_pc=False, name="NPC")
        pc1 = _make_combatant(is_pc=True, name="PC1")
        pc2 = _make_combatant(is_pc=True, name="PC2")
        other_npc = _make_combatant(is_pc=False, name="OtherNPC")
        state = _make_state([npc, pc1, pc2, other_npc])

        target = _pick_npc_target(state, npc.entity_id)
        assert target is not None
        assert target.is_pc is True
        # Returns the first PC
        assert target.name == "PC1"

    def test_falls_back_to_other_active(self):
        from monitor_agents.loops.combat_loop import _pick_npc_target

        npc1 = _make_combatant(is_pc=False, name="NPC1")
        npc2 = _make_combatant(is_pc=False, name="NPC2")
        inactive_pc = _make_combatant(is_pc=True, name="DownPC", is_active=False)
        state = _make_state([npc1, npc2, inactive_pc])

        target = _pick_npc_target(state, npc1.entity_id)
        # Should return the OTHER npc, not the one we're asking for
        assert target is not None
        assert target.entity_id == npc2.entity_id

    def test_no_valid_target_returns_none(self):
        from monitor_agents.loops.combat_loop import _pick_npc_target

        npc = _make_combatant(is_pc=False, name="Solo")
        state = _make_state([npc])

        target = _pick_npc_target(state, npc.entity_id)
        assert target is None


# =============================================================================
# _find_target_in_action
# =============================================================================


class TestFindTargetInAction:
    def test_pc_attacker_targets_npc(self):
        from monitor_agents.loops.combat_loop import _find_target_in_action

        pc = _make_combatant(is_pc=True, name="PC")
        npc = _make_combatant(is_pc=False, name="NPC")
        state = _make_state([pc, npc])

        target = _find_target_in_action(state, pc)
        assert target is npc

    def test_npc_attacker_targets_pc(self):
        from monitor_agents.loops.combat_loop import _find_target_in_action

        pc = _make_combatant(is_pc=True, name="PC")
        npc = _make_combatant(is_pc=False, name="NPC")
        state = _make_state([pc, npc])

        target = _find_target_in_action(state, npc)
        assert target is pc

    def test_no_enemies_returns_none(self):
        from monitor_agents.loops.combat_loop import _find_target_in_action

        pc1 = _make_combatant(is_pc=True, name="PC1")
        pc2 = _make_combatant(is_pc=True, name="PC2")
        state = _make_state([pc1, pc2])

        target = _find_target_in_action(state, pc1)
        assert target is None

    def test_skips_inactive(self):
        from monitor_agents.loops.combat_loop import _find_target_in_action

        pc = _make_combatant(is_pc=True, name="PC")
        inactive_npc = _make_combatant(is_pc=False, name="DownNPC", is_active=False)
        active_npc = _make_combatant(is_pc=False, name="LiveNPC")
        state = _make_state([pc, inactive_npc, active_npc])

        target = _find_target_in_action(state, pc)
        assert target is active_npc


# =============================================================================
# _apply_damage
# =============================================================================


class TestApplyDamage:
    def test_subtracts_hp(self):
        from monitor_agents.loops.combat_loop import _apply_damage

        c = _make_combatant(hp=20)
        state = _make_state([c])
        _apply_damage(state, c.entity_id, 5)
        assert _get_hp_helper(state, c.entity_id) == 15

    def test_zero_hp_marks_inactive(self):
        from monitor_agents.loops.combat_loop import _apply_damage

        c = _make_combatant(hp=5)
        state = _make_state([c])
        _apply_damage(state, c.entity_id, 10)
        assert c.hp_current == 0
        assert c.is_active is False
        assert "unconscious" in c.conditions

    def test_negative_damage_does_not_go_below_zero(self):
        from monitor_agents.loops.combat_loop import _apply_damage

        c = _make_combatant(hp=5)
        state = _make_state([c])
        _apply_damage(state, c.entity_id, 100)
        assert c.hp_current == 0

    def test_no_match_does_nothing(self):
        from monitor_agents.loops.combat_loop import _apply_damage

        c = _make_combatant(hp=20)
        state = _make_state([c])
        # Apply to nonexistent id
        _apply_damage(state, uuid4(), 5)
        # Original combatant unchanged
        assert c.hp_current == 20


def _get_hp_helper(state, entity_id):
    from monitor_agents.loops.combat_loop import _get_hp

    return _get_hp(state, entity_id)


# =============================================================================
# _get_hp
# =============================================================================


class TestGetHp:
    def test_returns_current_hp(self):
        from monitor_agents.loops.combat_loop import _get_hp

        c = _make_combatant(hp=12)
        state = _make_state([c])
        assert _get_hp(state, c.entity_id) == 12

    def test_returns_zero_for_unknown(self):
        from monitor_agents.loops.combat_loop import _get_hp

        state = _make_state([])
        assert _get_hp(state, uuid4()) == 0


# =============================================================================
# _format_combat_context
# =============================================================================


class TestFormatCombatContext:
    def test_includes_round_and_initiative(self):
        from monitor_agents.loops.combat_loop import _format_combat_context

        pc = _make_combatant(is_pc=True, name="Hero", hp=15)
        npc = _make_combatant(is_pc=False, name="Goblin", hp=8)
        state = _make_state([pc, npc])
        state.initiative_order = [pc.entity_id, npc.entity_id]
        state.current_combatant_id = pc.entity_id
        state.round_number = 2

        text = _format_combat_context(state)
        assert "COMBAT — Round 2" in text
        assert "Hero" in text
        assert "Goblin" in text
        assert "HP 15/15" in text
        assert "HP 8/8" in text
        assert "→" in text  # current combatant marker

    def test_marks_down_combatant(self):
        from monitor_agents.loops.combat_loop import _format_combat_context

        down = _make_combatant(is_pc=False, name="DeadGuy", hp=0, is_active=False)
        state = _make_state([down])
        state.initiative_order = [down.entity_id]
        state.current_combatant_id = down.entity_id
        state.round_number = 1

        text = _format_combat_context(state)
        assert "DOWN" in text

    def test_includes_recent_events(self):
        from monitor_agents.loops.combat_loop import _format_combat_context

        state = _make_state()
        state.combat_log = [
            {"event": "initiative", "combatant": "Hero", "total": 18},
            {"event": "hit", "attacker": "Hero", "target": "Goblin", "damage": 5},
            {"event": "miss", "attacker": "Goblin", "target": "Hero"},
        ]

        text = _format_combat_context(state)
        assert "Hero initiative 18" in text
        assert "Hero hits Goblin for 5 damage" in text
        assert "Goblin misses Hero" in text


# =============================================================================
# CombatantState / CombatState defaults
# =============================================================================


class TestCombatStateDefaults:
    def test_combatant_state_minimal(self):
        from monitor_agents.loops.combat_loop import CombatantState

        eid = uuid4()
        c = CombatantState(
            entity_id=eid,
            name="Hero",
            initiative=0,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        assert c.entity_id == eid
        assert c.name == "Hero"
        assert c.hp_current == 20
        assert c.hp_max == 20
        assert c.conditions == []
        assert c.is_active is True
        assert c.attributes == {}

    def test_combat_state_minimal(self):
        from monitor_agents.loops.combat_loop import CombatState

        state = CombatState(scene_id=uuid4(), story_id=uuid4())
        assert state.combatants == []
        assert state.initiative_order == []
        assert state.current_index == 0
        assert state.current_combatant_id is None
        assert state.round_number == 1
        assert state.combat_log == []
        assert state.pending_proposals == []
        assert state.combat_active is True
        assert state.victory_side is None
        assert state.entity_context == []
        assert state.game_context == {}
        assert state.source_profile == {}
        assert state.gm_profile is None
        assert state.session_tone == "dramatic"
        assert state.user_input is None
        assert state.resolution is None
        assert state.narrative_text is None
        assert state.awaiting_pc_input is False
