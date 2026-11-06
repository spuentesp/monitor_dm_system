"""On a dice turn the GM picks the stat and DC, and the roll uses the actor's sheet."""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents import resolver as rmod
from monitor_agents.gm_awareness import ActionType, CausalityAction, IntentType, RollNecessity
from monitor_agents.gm_tools.contracts import GMVerdict
from monitor_agents.loops import scene_orchestrator as so
from monitor_agents.loops.scene_orchestrator_support import _dice_request_from_resolution


def _verdict(**over: Any) -> GMVerdict:
    fields: dict[str, Any] = {
        "intent_type": IntentType.ACTION,
        "action_type": ActionType.STEALTH,
        "roll_necessity": RollNecessity.PROPOSE_ROLL,
        "causality_action": CausalityAction.ACCEPT,
        "declares_outcome": False,
        "suggested_stat": "Dexterity",
        "suggested_dc": 25,
    }
    fields.update(over)
    return GMVerdict(**fields)


def _resolver(verdict: GMVerdict | None) -> rmod.Resolver:
    return rmod.Resolver(gm_agent=types.SimpleNamespace(decide=AsyncMock(return_value=verdict)))


def _gsr(core: dict[str, Any] | None = None) -> Any:
    attrs = {"STR": {"name": "Strength", "abbreviation": "STR"}, "DEX": {"name": "Dexterity", "abbreviation": "DEX"}}
    return types.SimpleNamespace(
        _sd=types.SimpleNamespace(core=core or {"type": "d20"}),
        _attr_by_abbr=attrs,
        calc_modifier=lambda _stat, value: (value - 10) // 2,
        infer_action_context=AsyncMock(
            return_value={"action_type": "action", "stat_name": "STR", "difficulty_class": 14, "subsystem_hint": None}
        ),
        evaluate_scenery_and_conditions=AsyncMock(
            return_value={"total_modifier": 0, "roll_mode": "normal", "cond_modifier": 0, "scenery_modifier": 0}
        ),
    )


@pytest.fixture(autouse=True)
def _generic_stat():
    with patch.object(rmod, "_infer_generic_stat", AsyncMock(return_value="Strength")) as mocked:
        yield mocked


async def _resolve(resolver: rmod.Resolver, ctx: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
    result, _ = await resolver.resolve_turn(
        "scene", kw.pop("text", "I sneak past the guard"), {"entities": [], **(ctx or {})}, **{"play_mode": "dice_standard", **kw}
    )
    return result


# --- GM authority ---------------------------------------------------------


@pytest.mark.asyncio
async def test_real_verdict_sets_stat_and_dc() -> None:
    result = await _resolve(_resolver(_verdict()))
    assert (result["stat"], result["difficulty_class"]) == ("Dexterity", 25)


@pytest.mark.asyncio
async def test_real_verdict_sets_intent_and_non_combat_action() -> None:
    verdict = _verdict(intent_type=IntentType.DIALOGUE, action_type=ActionType.DIALOGUE)
    result = await _resolve(_resolver(verdict), text="I convince the guard")
    assert (result["intent_type"], result["action_type"]) == ("dialogue", "dialogue")


@pytest.mark.asyncio
async def test_fallback_verdict_does_not_set_stat_or_dc() -> None:
    result = await _resolve(_resolver(_verdict(action_type=ActionType.NONE)))
    assert (result["stat"], result["difficulty_class"]) == ("Strength", 12)


@pytest.mark.asyncio
async def test_gm_cannot_start_combat_on_its_own() -> None:
    verdict = _verdict(action_type=ActionType.COMBAT, subsystem_hint="combat", intent_type=IntentType.ACTION)
    result = await _resolve(_resolver(verdict), text="I swing at him")
    assert result["action_type"] != "combat"
    assert result["subsystem_hint"] is None


@pytest.mark.asyncio
async def test_game_system_accepts_a_gm_stat_it_knows_by_name() -> None:
    with patch.object(rmod, "GameSystemRuntime", lambda _ctx: _gsr()):
        result = await _resolve(_resolver(_verdict()), game_context={"x": 1}, play_mode="dice_game_system")
    assert (result["stat"], result["difficulty_class"]) == ("DEX", 25)


@pytest.mark.asyncio
async def test_game_system_ignores_a_gm_stat_it_does_not_have() -> None:
    with patch.object(rmod, "GameSystemRuntime", lambda _ctx: _gsr()):
        result = await _resolve(
            _resolver(_verdict(suggested_stat="Moxie", suggested_dc=None)),
            game_context={"x": 1},
            play_mode="dice_game_system",
        )
    assert (result["stat"], result["difficulty_class"]) == ("STR", 14)


# --- Modifiers ------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_stat_is_a_neutral_modifier() -> None:
    result = await _resolve(_resolver(_verdict()))
    assert result["modifier"] == 0
    assert result["attribute_value"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["Dexterity", "dexterity", "DEX", "dex"])
async def test_stat_lookup_tolerates_case_and_abbreviation(key: str) -> None:
    ctx = {"entities": [{"id": "pc", "properties": {"attributes": {key: 18}}}]}
    result = await _resolve(_resolver(_verdict()), ctx)
    assert (result["attribute_value"], result["modifier"]) == (18, 4)


@pytest.mark.asyncio
async def test_a_real_zero_stat_keeps_its_penalty() -> None:
    ctx = {"entities": [{"id": "pc", "properties": {"attributes": {"Dexterity": 0}}}]}
    assert (await _resolve(_resolver(_verdict()), ctx))["modifier"] == -5


OGRE = {"id": "ogre", "name": "Ogre", "properties": {"attributes": {"Dexterity": 24}}}
HERO = {"id": "pc", "name": "Hero", "properties": {"attributes": {"Dexterity": 8}}}


@pytest.mark.asyncio
async def test_actor_stats_are_used_rather_than_the_first_entity() -> None:
    result = await _resolve(_resolver(_verdict()), {"entities": [OGRE, HERO], "actor_id": "pc"})
    assert result["modifier"] == -1


@pytest.mark.asyncio
async def test_actor_context_sheet_wins() -> None:
    ctx = {"entities": [OGRE], "actor_id": "pc", "actor": {"id": "pc", "attributes": {"DEX": 16}}}
    assert (await _resolve(_resolver(_verdict()), ctx))["modifier"] == 3


@pytest.mark.asyncio
async def test_known_actor_without_stats_never_borrows_an_npcs() -> None:
    result = await _resolve(_resolver(_verdict()), {"entities": [OGRE], "actor_id": "pc"})
    assert result["modifier"] == 0


@pytest.mark.asyncio
async def test_proposed_roll_includes_conditions_and_scenery() -> None:
    gsr = _gsr()
    gsr.evaluate_scenery_and_conditions = AsyncMock(
        return_value={"total_modifier": -2, "roll_mode": "normal", "cond_modifier": -2, "scenery_modifier": 0}
    )
    ctx = {"entities": [{"id": "pc", "properties": {"attributes": {"DEX": 14}}}], "actor_id": "pc"}
    with patch.object(rmod, "GameSystemRuntime", lambda _ctx: gsr):
        result = await _resolve(_resolver(_verdict()), ctx, game_context={"x": 1}, play_mode="dice_game_system")
    assert result["modifier"] == 0  # +2 from DEX 14, -2 from conditions
    assert _dice_request_from_resolution(result, "x")["spec"] == "1d20"


@pytest.mark.asyncio
async def test_proposed_roll_threads_advantage_and_disadvantage_into_dice_spec() -> None:
    gsr = _gsr()
    gsr.evaluate_scenery_and_conditions = AsyncMock(
        return_value={"total_modifier": -1, "roll_mode": "disadvantage", "cond_modifier": -1, "scenery_modifier": 0}
    )
    ctx = {"entities": [{"id": "pc", "properties": {"attributes": {"DEX": 14}}}], "actor_id": "pc"}
    with patch.object(rmod, "GameSystemRuntime", lambda _ctx: gsr):
        result = await _resolve(_resolver(_verdict()), ctx, game_context={"x": 1}, play_mode="dice_game_system")
    assert result["roll_mode"] == "disadvantage"
    assert result["modifier"] == 1  # +2 from DEX 14, -1 from conditions
    req = _dice_request_from_resolution(result, "I sneak")
    assert req is not None
    assert req["spec"] == "2d20kl1+1"
    assert req["roll_mode"] == "disadvantage"


@pytest.mark.asyncio
async def test_proposed_roll_emits_pool_spec_for_dice_pool_systems() -> None:
    gsr = _gsr(core={"type": "dice_pool", "formula": "Attribute + Skill d10", "success_threshold": 7})
    ctx = {"entities": [{"id": "pc", "properties": {"attributes": {"DEX": 4}}}], "actor_id": "pc"}
    with patch.object(rmod, "GameSystemRuntime", lambda _ctx: gsr):
        # DEX 4 with (v-10)//2 modifier in stub _gsr would be -3; override calc_modifier to 0 as pool systems do
        gsr.calc_modifier = lambda _stat, _val: 0
        result = await _resolve(_resolver(_verdict()), ctx, game_context={"x": 1}, play_mode="dice_game_system")
    assert result["mechanic_type"] == "dice_pool"
    assert result["pool_size"] == 4
    assert result["success_threshold"] == 7
    req = _dice_request_from_resolution(result, "I dodge")
    assert req is not None
    assert req["spec"] == "4d10"
    assert req["mechanic_type"] == "dice_pool"
    assert req["success_threshold"] == 7


def test_conditions_come_from_the_actor_not_the_first_entity() -> None:
    from monitor_agents.game_system._tracks_conditions import _collect_actor_conditions

    npc = {"id": "npc", "entity_type": "character", "properties": {"conditions": ["stunned"]}}
    pc = {"id": "pc", "entity_type": "character", "properties": {"conditions": ["poisoned"]}}
    assert _collect_actor_conditions({"entities": [npc, pc], "actor_id": "pc"}) == ["poisoned"]
    assert _collect_actor_conditions({"entities": [npc], "actor_id": "pc"}) == []
    assert _collect_actor_conditions({"entities": [npc, pc]}) == ["stunned"]


# --- Pushback -------------------------------------------------------------


@pytest.mark.asyncio
async def test_pushback_offers_the_roll_it_asks_for() -> None:
    verdict = _verdict(
        declares_outcome=True,
        causality_action=CausalityAction.PUSH_BACK,
        pushback_prompt="Bold claim. Roll Dexterity.",
    )
    ctx = {"entities": [{"id": "pc", "properties": {"attributes": {"Dexterity": 16}}}]}
    result = await _resolve(_resolver(verdict), ctx, text="I kill the dragon")

    request = _dice_request_from_resolution(result, "I kill the dragon")
    assert request is not None
    assert request["spec"] == "1d20+3"
    assert request["difficulty_class"] == 25
    assert request["reason"] == "Bold claim. Roll Dexterity."
    assert request["original_action"] == "I kill the dragon"


@pytest.mark.asyncio
async def test_player_sees_the_pushback_prompt_and_can_roll() -> None:
    session: dict[str, Any] = {"id": "s"}
    loop = types.SimpleNamespace(
        run=AsyncMock(
            return_value={
                "resolution": {
                    "resolution_type": "forced_narrative_pushback",
                    "stat": "Dexterity",
                    "difficulty_class": 25,
                    "modifier": 3,
                    "pushback_prompt": "Bold claim. Roll Dexterity.",
                    "requires_player_choice": True,
                },
                "narrative_text": None,
            }
        )
    )
    callbacks = types.SimpleNamespace(
        now_iso=lambda: "now",
        db_save_session=lambda _s: None,
        get_scene_loop=lambda *_a, **_k: loop,
        messages={},
        get_story_state=None,
    )
    state = so.SceneOrchestratorState(
        session_id="s", user_content="I kill the dragon", session=session, callbacks=callbacks, story_id="t", scene_id="c"
    )
    out = await so.run_core_scene_loop(state)

    assert out.response_text == "Bold claim. Roll Dexterity."
    assert out.metadata["dice_request"]["spec"] == "1d20+3"
    assert session["pending_dice_request"]["difficulty_class"] == 25


def test_roll_under_advantage_and_disadvantage_invert_keep_direction():
    """F2: In roll-under systems (lower is better), advantage keeps lowest (2d20kl1)."""
    from monitor_agents.loops.scene_orchestrator_support import _format_dice_spec

    assert _format_dice_spec(0, roll_under=True, roll_mode="advantage") == "2d20kl1"
    assert _format_dice_spec(0, roll_under=True, roll_mode="disadvantage") == "2d20kh1"

    r = _resolver(None)
    gsr_under = _gsr(core={"type": "roll_under", "formula": "1d20 <= STAT"})
    roll_kw: dict[str, Any] = {
        "scene_id": "s",
        "user_input": "u",
        "action_type": "action",
        "roll_type": "check",
        "intent_target": "",
        "requires_clarification": False,
        "subsystem_hint": None,
        "roll_necessity": "roll",
    }
    with patch("monitor_data.utils.dice.random.randint", side_effect=[15, 4]):
        res = r._execute_roll(
            **roll_kw,
            stat_name="BODY",
            stat_value=13,
            base_modifier=0,
            modifier=0,
            dc=13,
            gsr=gsr_under,
            actual_roll_mode="advantage",
        )
    assert res["roll_total"] == 4
    assert res["roll_detail"]["spec"] == "2d20kl1"
    assert res["success"] is True


def test_dice_pool_does_not_double_stat_or_concatenate_pbta_bands():
    """F3: vampire.json-style 1..5 attributes do not double pool_size; PbtA bands don't become threshold 10796."""
    from monitor_agents.resolver import (
        _is_count_successes_pool,
        _parse_pool_threshold,
        _pool_proposal_fields,
    )

    # PbtA / Apocalypse World 2d6+stat with multi-band string is not a count-successes pool
    pbta_cm = {
        "type": "dice_pool",
        "formula": "2d6 + stat",
        "success_threshold": "10+ full success, 7-9 partial/mixed, 6- fail",
    }
    assert _is_count_successes_pool(pbta_cm) is False
    assert _parse_pool_threshold(pbta_cm["success_threshold"], die_sides=6) == 6

    # Vampire-style d10 pool where calc_modifier returns stat_value (base_modifier == stat_value == 4)
    vtm_gsr = _gsr(
        core={
            "type": "dice_pool",
            "formula": "Pool of d10s (Attribute + Skill)",
            "success_threshold": "6+ on each die is a success",
        }
    )
    fields = _pool_proposal_fields(vtm_gsr, stat_value=4, pool_bonus=0)
    assert fields["pool_size"] == 4
    assert fields["success_threshold"] == 6

    r = _resolver(None)
    with patch("monitor_agents.dice.pool.random.randint", side_effect=[8, 6, 3, 9]):
        res = r._execute_roll(
            scene_id="s",
            user_input="u",
            action_type="action",
            roll_type="check",
            intent_target="",
            requires_clarification=False,
            subsystem_hint=None,
            roll_necessity="roll",
            stat_name="DEX",
            stat_value=4,
            base_modifier=4,
            modifier=4,
            dc=2,
            gsr=vtm_gsr,
            actual_roll_mode="normal",
        )
    assert len(res["roll_detail"]["rolls"]) == 4
    assert res["roll_total"] == 3  # 8, 6, 9 are >= 6
    assert res["success"] is True

