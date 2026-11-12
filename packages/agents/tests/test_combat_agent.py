"""Tests for CombatAgent (CF-9) — deterministic state ops + optional LLM bits.

Every state transition must reach the ``mongodb_combat_*`` MCP tools with the
right arguments (FakeMCPClient / AsyncMock), never an LLM. The three DSPy
bits are asserted as wiring: the module is invoked with the JSON payload and
its return value is passed through. Tool failures surfaced as text by the
data-layer server must raise, not be swallowed.

Run:
    uv run pytest packages/agents/tests/test_combat_agent.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from monitor_data.schemas.base import CombatSide, CombatStatus
from monitor_data.schemas.combat import (
    CombatEnd,
    CombatNextRound,
    CombatSetInitiative,
    CombatStart,
    CombatUpdateCombatant,
    CombatantCreate,
    CombatSessionState,
    CombatantState,
    CombatInitiativeEntry,
)
from monitor_data.schemas.llm_config import ModelRole
from monitor_agents.combat import CombatAgent, ConditionExplanation, _raise_on_tool_error


def _agent_with_mcp(responses: dict[str, object]) -> tuple[CombatAgent, AsyncMock]:
    """CombatAgent whose MCP calls are an AsyncMock keyed on tool name."""
    agent = CombatAgent(agent_id="test-combat")
    call_tool = AsyncMock(side_effect=lambda name, args: responses[name])
    agent.call_tool = call_tool  # type: ignore[assignment]
    return agent, call_tool


def _state(**over) -> CombatSessionState:
    base = dict(
        universe_id=uuid4(),
        session_id="sess-1",
        status=CombatStatus.ACTIVE,
        round=2,
        turn_order=[],
        combatants=[
            CombatantState(
                id=uuid4(),
                name="Mira",
                side=CombatSide.PC,
                hp=18,
                max_hp=24,
            ),
            CombatantState(
                id=uuid4(),
                name="Goblin",
                side=CombatSide.ENEMY,
                hp=0,
                max_hp=7,
                dead=True,
            ),
        ],
        started_at=datetime.now(UTC),
    )
    base.update(over)
    return CombatSessionState(**base)


class TestToolErrorGuard:
    def test_error_prefix_raises_value_error(self):
        with pytest.raises(ValueError, match="No combat encounter"):
            _raise_on_tool_error("Error executing tool: No combat encounter for session x")

    def test_authorization_error_raises(self):
        with pytest.raises(ValueError, match="Authorization error"):
            _raise_on_tool_error("Authorization error: Agent 'X' is not authorized")

    def test_state_dict_passes_through(self):
        payload = {"session_id": "s"}
        assert _raise_on_tool_error(payload) is payload

    def test_none_passes_through(self):
        assert _raise_on_tool_error(None) is None


class TestDeterministicStateOps:
    @pytest.mark.asyncio
    async def test_start_encounter_calls_tool_with_json_payload(self):
        started = _state(status=CombatStatus.INITIATIVE, round=1)
        agent, call_tool = _agent_with_mcp({"mongodb_combat_start": started.model_dump(mode="json")})
        params = CombatStart(
            universe_id=uuid4(),
            session_id="sess-1",
            combatants=[CombatantCreate(name="Mira", side=CombatSide.PC, hp=24, max_hp=24)],
        )
        result = await agent.start_encounter(params)
        assert result.status == CombatStatus.INITIATIVE
        tool, args = call_tool.call_args.args
        assert tool == "mongodb_combat_start"
        assert args["session_id"] == "sess-1"
        assert isinstance(args["universe_id"], str)  # JSON transport
        assert args["combatants"][0]["name"] == "Mira"

    @pytest.mark.asyncio
    async def test_get_state_returns_none_when_absent(self):
        agent, call_tool = _agent_with_mcp({"mongodb_combat_get": None})
        assert await agent.get_state(uuid4(), "missing") is None
        tool, args = call_tool.call_args.args
        assert tool == "mongodb_combat_get"
        assert set(args) == {"universe_id", "session_id"}

    @pytest.mark.asyncio
    async def test_get_state_parses_rounded_state(self):
        state = _state()
        agent, _ = _agent_with_mcp({"mongodb_combat_get": state.model_dump(mode="json")})
        fetched = await agent.get_state(state.universe_id, state.session_id)
        assert fetched is not None
        assert fetched.round == 2
        assert fetched.combatants[1].dead is True

    @pytest.mark.asyncio
    async def test_update_combatant_is_delegated_not_llm(self):
        state = _state()
        agent, call_tool = _agent_with_mcp({"mongodb_combat_update_combatant": state.model_dump(mode="json")})
        params = CombatUpdateCombatant(
            universe_id=state.universe_id,
            session_id=state.session_id,
            combatant_id=state.combatants[0].id,
            hp_delta=-5,
        )
        result = await agent.update_combatant(params)
        assert result.combatants[0].hp == 18
        tool, args = call_tool.call_args.args
        assert tool == "mongodb_combat_update_combatant"
        assert args["hp_delta"] == -5

    @pytest.mark.asyncio
    async def test_set_initiative_and_next_round_and_end(self):
        state = _state()
        agent, call_tool = _agent_with_mcp(
            {
                "mongodb_combat_set_initiative": state.model_dump(mode="json"),
                "mongodb_combat_next_round": state.model_dump(mode="json"),
                "mongodb_combat_end": state.model_dump(mode="json"),
            }
        )
        uid, sid = state.universe_id, state.session_id
        cid = state.combatants[0].id

        await agent.set_initiative(
            CombatSetInitiative(
                universe_id=uid,
                session_id=sid,
                entries=[CombatInitiativeEntry(combatant_id=cid, initiative=17, tiebreak=2)],
            )
        )
        await agent.next_round(CombatNextRound(universe_id=uid, session_id=sid))
        ended = await agent.end_encounter(CombatEnd(universe_id=uid, session_id=sid))

        assert ended.status == CombatStatus.ACTIVE  # fixture state, not re-resolved
        invoked = [c.args[0] for c in call_tool.call_args_list]
        assert invoked == [
            "mongodb_combat_set_initiative",
            "mongodb_combat_next_round",
            "mongodb_combat_end",
        ]

    @pytest.mark.asyncio
    async def test_tool_failure_text_raises_instead_of_swallowing(self):
        agent, _ = _agent_with_mcp(
            {
                "mongodb_combat_next_round": "Error executing tool: Encounter has already ended",
            }
        )
        with pytest.raises(ValueError, match="already ended"):
            await agent.next_round(CombatNextRound(universe_id=uuid4(), session_id="sess-1"))

    @pytest.mark.asyncio
    async def test_state_ops_never_touch_the_module(self):
        """Deterministic transitions must not reach the DSPy module."""
        state = _state()
        agent, _ = _agent_with_mcp({"mongodb_combat_end": state.model_dump(mode="json")})
        agent.module.summarize_encounter = AsyncMock(  # type: ignore[method-assign]
            side_effect=AssertionError("LLM must not be called for state transitions")
        )
        agent.module.narrate_initiative = AsyncMock(  # type: ignore[method-assign]
            side_effect=AssertionError("LLM must not be called for state transitions")
        )
        await agent.end_encounter(CombatEnd(universe_id=state.universe_id, session_id=state.session_id))


class TestNarrateInitiative:
    @pytest.mark.asyncio
    async def test_narration_receives_turn_order_json(self):
        state = _state()
        first, second = state.combatants
        state.turn_order = [first.id, second.id]
        agent, _ = _agent_with_mcp({})
        seen: dict[str, str] = {}

        def fake_narrate(payload: str, role=None) -> str:  # type: ignore[no-untyped-def]
            seen["payload"] = payload
            return "Mira acts first, then the fallen Goblin."

        agent.module.narrate_initiative = fake_narrate  # type: ignore[method-assign]
        narration = await agent.narrate_initiative(state)

        assert narration == "Mira acts first, then the fallen Goblin."
        order = json.loads(seen["payload"])
        assert [c["name"] for c in order] == ["Mira", "Goblin"]  # turn_order honored

    @pytest.mark.asyncio
    async def test_narration_falls_back_to_list_order_without_turn_order(self):
        state = _state()
        agent, _ = _agent_with_mcp({})
        seen: dict[str, str] = {}

        def fake_narrate(payload: str, role=None) -> str:  # type: ignore[no-untyped-def]
            seen["payload"] = payload
            return "ok"

        agent.module.narrate_initiative = fake_narrate  # type: ignore[method-assign]
        await agent.narrate_initiative(state)
        order = json.loads(seen["payload"])
        assert [c["name"] for c in order] == ["Mira", "Goblin"]


class TestExplainCondition:
    @pytest.mark.asyncio
    async def test_structured_system_definition_wins_without_llm(self):
        system_id = uuid4()
        system_doc = {
            "system_id": str(system_id),
            "name": "Test System",
            "conditions": [
                {
                    "name": "Poisoned",
                    "mechanical_effects": ["-2 to attacks", "lose 5 HP at dawn"],
                    "ends_when": "a successful Constitution save",
                }
            ],
        }
        agent, call_tool = _agent_with_mcp({"mongodb_get_game_system": system_doc})
        agent.module.explain_condition = AsyncMock(  # type: ignore[method-assign]
            side_effect=AssertionError("LLM must not be called when the system defines the condition")
        )
        result = await agent.explain_condition("poisoned", system_id=system_id, system_name="Test System")
        assert result.source == "system"
        assert "-2 to attacks" in result.description
        assert result.ends_when == "a successful Constitution save"
        tool, args = call_tool.call_args.args
        assert tool == "mongodb_get_game_system"
        assert args["system_id"] == str(system_id)

    @pytest.mark.asyncio
    async def test_falls_back_to_free_text_when_system_has_no_definition(self):
        agent, _ = _agent_with_mcp({"mongodb_get_game_system": {"conditions": []}})
        agent.module.explain_condition = lambda condition, context, role=None: (  # type: ignore[method-assign]
            f"{condition} is a generic tag with no structured rule here."
        )
        result = await agent.explain_condition("bloodied", system_id=uuid4())
        assert result.source == "free_text"
        assert "bloodied" in result.description

    @pytest.mark.asyncio
    async def test_falls_back_to_free_text_without_system(self):
        agent, _ = _agent_with_mcp({})
        agent.module.explain_condition = lambda condition, context, role=None: "generic"  # type: ignore[method-assign]
        result = await agent.explain_condition("prone", system_id=None, system_name="none")
        assert result.source == "free_text"
        assert result.description == "generic"
        agent.call_tool.assert_not_called()  # type: ignore[attr-defined]


class TestSummarizeEncounter:
    @pytest.mark.asyncio
    async def test_summary_receives_state_json(self):
        state = _state()
        agent, _ = _agent_with_mcp({})
        seen: dict[str, str] = {}

        def fake_summary(payload: str, role=None) -> str:  # type: ignore[no-untyped-def]
            seen["payload"] = payload
            return "Two rounds; the Goblin fell."

        agent.module.summarize_encounter = fake_summary  # type: ignore[method-assign]
        summary = await agent.summarize_encounter(state)
        assert summary == "Two rounds; the Goblin fell."
        parsed = json.loads(seen["payload"])
        assert parsed["round"] == 2
        assert parsed["combatants"][1]["dead"] is True


class TestAgentWiring:
    def test_default_role_is_light_for_table_speed(self):
        assert CombatAgent()._default_model_role() == ModelRole.LIGHT

    def test_condition_explanation_model_shape(self):
        expl = ConditionExplanation(condition="prone", source="free_text", description="x")
        assert expl.mechanical_effects == []
        assert expl.ends_when is None
