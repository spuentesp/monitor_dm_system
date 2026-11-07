"""
Tests for the Combat Loop state machine.

All LLM calls and MCP tool calls are mocked — pure unit tests.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Lazy import
# ---------------------------------------------------------------------------


def _import_combat_loop():
    from monitor_agents.loops.combat_loop import (
        CombatantState,
        CombatLoop,
        CombatState,
        _apply_damage,
        _format_combat_context,
        _pick_npc_target,
        check_victory,
        choose_combatant,
        roll_initiative,
    )

    return (
        CombatLoop,
        CombatState,
        CombatantState,
        roll_initiative,
        choose_combatant,
        check_victory,
        _format_combat_context,
        _apply_damage,
        _pick_npc_target,
    )


# ===========================================================================
# CombatantState
# ===========================================================================


class TestCombatantState:
    def test_minimal_construction(self):
        (_, _, CombatantState, *_) = _import_combat_loop()
        c = CombatantState(
            entity_id=uuid4(),
            name="Goblin",
            initiative=15,
            is_pc=False,
            hp_current=10,
            hp_max=10,
        )
        assert c.name == "Goblin"
        assert c.initiative == 15
        assert c.is_active is True
        assert c.conditions == []

    def test_pc_combatant(self):
        (_, _, CombatantState, *_) = _import_combat_loop()
        c = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=20,
            is_pc=True,
            hp_current=25,
            hp_max=30,
        )
        assert c.is_pc is True
        assert c.hp_current == 25
        assert c.hp_max == 30


# ===========================================================================
# CombatState
# ===========================================================================


class TestCombatState:
    def test_default_values(self):
        (_, CombatState, _, *_) = _import_combat_loop()
        state = CombatState(scene_id=uuid4(), story_id=uuid4())
        assert state.combat_active is True
        assert state.round_number == 1
        assert state.current_index == 0
        assert state.combatants == []
        assert state.combat_log == []


# ===========================================================================
# Initiative
# ===========================================================================


class TestInitiative:
    @pytest.mark.asyncio
    async def test_roll_initiative_orders_combatants(self):
        (_, CombatState, CombatantState, roll_initiative, *_) = _import_combat_loop()
        c1 = CombatantState(
            entity_id=uuid4(),
            name="Alice",
            initiative=0,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        c2 = CombatantState(
            entity_id=uuid4(),
            name="Bob",
            initiative=0,
            is_pc=False,
            hp_current=15,
            hp_max=15,
        )
        c3 = CombatantState(
            entity_id=uuid4(),
            name="Carol",
            initiative=0,
            is_pc=True,
            hp_current=18,
            hp_max=18,
        )

        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[c1, c2, c3],
        )

        # Patch dice to give different rolls
        with patch(
            "monitor_data.utils.dice.random.randint",
            side_effect=[18, 5, 12],
        ):
            result = await roll_initiative(state)

        order = result["initiative_order"]
        assert len(order) == 3
        # First should be the one with highest roll
        assert order[0] == c1.entity_id  # 18 + DEX mod
        # combat_log is on state, not returned by node
        assert len(state.combat_log) == 3

    @pytest.mark.asyncio
    async def test_roll_initiative_sets_round_one(self):
        (_, CombatState, CombatantState, roll_initiative, *_) = _import_combat_loop()
        c1 = CombatantState(
            entity_id=uuid4(),
            name="Alice",
            initiative=0,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[c1],
        )
        with patch("monitor_data.utils.dice.random.randint", return_value=15):
            result = await roll_initiative(state)
        assert result["round_number"] == 1


# ===========================================================================
# Choose Combatant
# ===========================================================================


class TestChooseCombatant:
    @pytest.mark.asyncio
    async def test_pc_combatant_sets_awaiting_input(self):
        (_, CombatState, CombatantState, _, choose_combatant, *_) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[pc],
            initiative_order=[pc.entity_id],
            current_index=0,
        )
        result = await choose_combatant(state)
        assert result["awaiting_pc_input"] is True
        assert result["current_combatant_id"] == pc.entity_id

    @pytest.mark.asyncio
    async def test_npc_combatant_auto_actions(self):
        (_, CombatState, CombatantState, _, choose_combatant, *_) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        npc = CombatantState(
            entity_id=uuid4(),
            name="Goblin",
            initiative=12,
            is_pc=False,
            hp_current=10,
            hp_max=10,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[pc, npc],
            initiative_order=[npc.entity_id, pc.entity_id],
            current_index=0,
        )
        result = await choose_combatant(state)
        assert result["awaiting_pc_input"] is False
        assert result["user_input"] is not None

    @pytest.mark.asyncio
    async def test_inactive_combatant_skipped(self):
        (_, CombatState, CombatantState, _, choose_combatant, *_) = _import_combat_loop()
        dead = CombatantState(
            entity_id=uuid4(),
            name="DeadGoblin",
            initiative=10,
            is_pc=False,
            hp_current=0,
            hp_max=10,
            is_active=False,
        )
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[dead, pc],
            initiative_order=[dead.entity_id, pc.entity_id],
            current_index=0,
        )
        result = await choose_combatant(state)
        # Dead NPC skipped, index advances past them
        assert result["current_index"] == 1


# ===========================================================================
# Victory Check
# ===========================================================================


class TestVictoryCheck:
    @pytest.mark.asyncio
    async def test_all_enemies_down_is_victory(self):
        (_, CombatState, CombatantState, _, _, check_victory, *_) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=20,
            hp_max=20,
            is_active=True,
        )
        enemy = CombatantState(
            entity_id=uuid4(),
            name="Goblin",
            initiative=10,
            is_pc=False,
            hp_current=0,
            hp_max=10,
            is_active=False,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[pc, enemy],
            initiative_order=[pc.entity_id, enemy.entity_id],
            current_index=0,
        )
        result = await check_victory(state)
        assert result["combat_active"] is False
        assert result["victory_side"] == "pc"

    @pytest.mark.asyncio
    async def test_all_pcs_down_is_defeat(self):
        (_, CombatState, CombatantState, _, _, check_victory, *_) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=0,
            hp_max=20,
            is_active=False,
        )
        enemy = CombatantState(
            entity_id=uuid4(),
            name="Goblin",
            initiative=10,
            is_pc=False,
            hp_current=10,
            hp_max=10,
            is_active=True,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[pc, enemy],
            initiative_order=[pc.entity_id, enemy.entity_id],
            current_index=0,
        )
        result = await check_victory(state)
        assert result["combat_active"] is False
        assert result["victory_side"] == "enemy"

    @pytest.mark.asyncio
    async def test_combat_continues_when_both_sides_active(self):
        (_, CombatState, CombatantState, _, _, check_victory, *_) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=20,
            hp_max=20,
            is_active=True,
        )
        enemy = CombatantState(
            entity_id=uuid4(),
            name="Goblin",
            initiative=10,
            is_pc=False,
            hp_current=5,
            hp_max=10,
            is_active=True,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[pc, enemy],
            initiative_order=[pc.entity_id, enemy.entity_id],
            current_index=0,
        )
        result = await check_victory(state)
        assert result["combat_active"] is True
        assert result["current_index"] == 1  # advances to next combatant


# ===========================================================================
# Damage
# ===========================================================================


class TestDamage:
    def test_apply_damage_reduces_hp(self):
        (_, CombatState, CombatantState, _, _, _, _, _apply_damage, *_) = _import_combat_loop()
        eid = uuid4()
        c = CombatantState(
            entity_id=eid,
            name="Goblin",
            initiative=10,
            is_pc=False,
            hp_current=10,
            hp_max=10,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[c],
        )
        _apply_damage(state, eid, 5)
        assert state.combatants[0].hp_current == 5
        assert state.combatants[0].is_active is True

    def test_apply_lethal_damage_kills(self):
        (_, CombatState, CombatantState, _, _, _, _, _apply_damage, *_) = _import_combat_loop()
        eid = uuid4()
        c = CombatantState(
            entity_id=eid,
            name="Goblin",
            initiative=10,
            is_pc=False,
            hp_current=3,
            hp_max=10,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[c],
        )
        _apply_damage(state, eid, 10)
        assert state.combatants[0].hp_current == 0
        assert state.combatants[0].is_active is False
        assert "unconscious" in state.combatants[0].conditions


# ===========================================================================
# NPC Target Selection
# ===========================================================================


class TestNPCTarget:
    def test_pick_npc_target_prefers_pcs(self):
        (_, CombatState, CombatantState, _, _, _, _, _, _pick_npc_target) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        npc_ally = CombatantState(
            entity_id=uuid4(),
            name="AllyNPC",
            initiative=12,
            is_pc=False,
            hp_current=15,
            hp_max=15,
        )
        npc_id = uuid4()
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[pc, npc_ally],
        )
        target = _pick_npc_target(state, npc_id)
        assert target is not None
        assert target.is_pc is True

    def test_pick_npc_target_no_valid_returns_none(self):
        (_, CombatState, CombatantState, _, _, _, _, _, _pick_npc_target) = _import_combat_loop()
        npc_id = uuid4()
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[],
        )
        target = _pick_npc_target(state, npc_id)
        assert target is None


# ===========================================================================
# Combat Context Formatting
# ===========================================================================


class TestCombatContext:
    def test_format_shows_initiative_order(self):
        (_, CombatState, CombatantState, _, _, _, _format_combat_context, *_) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        enemy = CombatantState(
            entity_id=uuid4(),
            name="Goblin",
            initiative=10,
            is_pc=False,
            hp_current=5,
            hp_max=10,
        )
        state = CombatState(
            scene_id=uuid4(),
            story_id=uuid4(),
            combatants=[pc, enemy],
            initiative_order=[pc.entity_id, enemy.entity_id],
            current_combatant_id=pc.entity_id,
            combat_log=[
                {"event": "initiative", "combatant": "Player", "total": 18},
                {"event": "initiative", "combatant": "Goblin", "total": 10},
            ],
        )
        ctx = _format_combat_context(state)
        assert "COMBAT" in ctx
        assert "Player" in ctx
        assert "Goblin" in ctx
        assert "HP" in ctx


# ===========================================================================
# CombatLoop full flow
# ===========================================================================


class TestCombatLoopFull:
    @pytest.mark.asyncio
    async def test_start_rolls_initiative_and_awaits_pc(self):
        (CombatLoop, _, CombatantState, *_) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=0,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        enemy = CombatantState(
            entity_id=uuid4(),
            name="Goblin",
            initiative=0,
            is_pc=False,
            hp_current=10,
            hp_max=10,
        )

        with patch("monitor_data.utils.dice.random.randint", side_effect=[18, 5]):
            loop = CombatLoop(
                scene_id=uuid4(),
                story_id=uuid4(),
                combatants=[pc, enemy],
            )
            result = await loop.start()

        assert result["combat_active"] is True
        assert "combat_log" in result
        # First combatant is PC (rolled 18 vs 5)
        assert result["awaiting_pc_input"] is True

    @pytest.mark.asyncio
    async def test_step_executes_pc_turn(self):
        """Combat step resolves PC action and advances NPC turns."""
        (CombatLoop, _, CombatantState, *_) = _import_combat_loop()
        pc = CombatantState(
            entity_id=uuid4(),
            name="Player",
            initiative=18,
            is_pc=True,
            hp_current=20,
            hp_max=20,
            attributes={"Strength": 16},
        )
        enemy = CombatantState(
            entity_id=uuid4(),
            name="Goblin",
            initiative=5,
            is_pc=False,
            hp_current=10,
            hp_max=10,
            attributes={"Strength": 12},
        )

        # Mock Narrator and Resolver
        class _FakeNarrator:
            async def narrate_turn(self, **kwargs):
                return {"narrative_text": "Combat action resolved.", "proposals": []}

        class _FakeResolver:
            async def resolve_opposed_check(self, **kwargs):
                return {
                    "winner": "actor",
                    "margin": 4,
                    "actor_roll": {"total": 18, "natural": 15, "modifier": 3, "rolls": [15]},
                    "target_roll": {"total": 14, "natural": 12, "modifier": 2, "rolls": [12]},
                    "opposed_stat": "Strength",
                    "success_level": "success",
                }

            async def resolve_turn(self, **kwargs):
                return {
                    "resolution_type": "dice",
                    "success_level": "success",
                    "effects": ["fiction_advances"],
                }

        with patch("monitor_data.utils.dice.random.randint", side_effect=[18, 5, 15, 8]):
            with (
                patch("monitor_agents.narrator.agent.Narrator", return_value=_FakeNarrator()),
                patch("monitor_agents.resolver.Resolver", return_value=_FakeResolver()),
            ):
                loop = CombatLoop(
                    scene_id=uuid4(),
                    story_id=uuid4(),
                    combatants=[pc, enemy],
                )
                await loop.start()
                result = await loop.step("I attack the goblin with my sword")

        assert result["combat_active"] is True
        assert len(result.get("combat_log", [])) >= 2
        assert "Combat action resolved." in result.get("narrative_text", "")

    @pytest.mark.asyncio
    async def test_large_npc_group_never_leaves_active_combat_without_pc_turn(self):
        """Regression for >=21 NPC combatants: _advance_npc_turns must scale with
        initiative_order and never return active-and-not-awaiting (which previously
        froze _run_combat in a non-awaiting while loop)."""
        from monitor_agents.loops import combat_loop as cl

        (CombatLoop, _, CombatantState, *_) = _import_combat_loop()

        async def _noop(state):
            return {"narrative_text": "npc swing"}

        pc = CombatantState(
            entity_id=uuid4(),
            name="Hero",
            initiative=0,
            is_pc=True,
            hp_current=20,
            hp_max=20,
        )
        npcs = [
            CombatantState(
                entity_id=uuid4(),
                name=f"Raider-{i}",
                initiative=0,
                is_pc=False,
                hp_current=10,
                hp_max=10,
            )
            for i in range(35)
        ]

        with (
            patch.object(cl, "resolve_combat_action", _noop),
            patch.object(cl, "narrate_combat", _noop),
        ):
            loop = CombatLoop(
                scene_id=uuid4(),
                story_id=uuid4(),
                combatants=[pc, *npcs],
            )
            await loop.start()
            result = await loop.step("I strike")

        assert not (result["combat_active"] and not result["awaiting_pc_input"])

    @pytest.mark.asyncio
    async def test_run_combat_filters_locations_and_objects_and_computes_negative_hp_delta(self):
        from monitor_agents.loops import combat_loop as cl
        from monitor_agents.loops import scene_loop as sl

        pc_id = str(uuid4())
        loc_id = str(uuid4())
        obj_id = str(uuid4())
        orc_id = str(uuid4())

        # Only locations + objects alongside PC -> combat must be skipped.
        only_scenery = [
            {"id": pc_id, "name": "Hero", "properties": {"role": "PC"}},
            {"id": loc_id, "name": "Docking Bay", "entity_type": "location", "properties": {}},
            {"id": obj_id, "name": "Cargo Crate", "entity_type": "object", "properties": {}},
        ]
        assert await sl._run_combat(uuid4(), uuid4(), "I attack", only_scenery, {}, {}) is None

        # Add a real character enemy alongside scenery -> only Hero + Raider enter combat.
        captured_names: list[str] = []
        orig_init = cl.CombatLoop.__init__

        def _spy_init(self, *args, **kwargs):
            captured_names.extend(c.name for c in kwargs["combatants"])
            orig_init(self, *args, **kwargs)

        async def _noop(state):
            return {"narrative_text": "clashed"}

        entities = [
            *only_scenery,
            {"id": orc_id, "name": "Raider", "entity_type": "character", "properties": {"hp": 8}},
        ]
        with (
            patch.object(cl.CombatLoop, "__init__", _spy_init),
            patch.object(cl, "resolve_combat_action", _noop),
            patch.object(cl, "narrate_combat", _noop),
        ):
            out = await sl._run_combat(uuid4(), uuid4(), "I attack", entities, {}, {})

        assert out is not None
        assert captured_names == ["Hero", "Raider"]

        # PC without explicit hp property starts at default 10 and ends at 7 -> delta must be -3, not +7.
        deltas = sl._extract_combat_resource_deltas(
            {"combatants": [{"entity_id": pc_id, "is_pc": True, "hp_current": 7}]},
            [{"id": pc_id, "properties": {}}],
        )
        assert len(deltas) == 1
        assert deltas[0]["delta"] == -3
