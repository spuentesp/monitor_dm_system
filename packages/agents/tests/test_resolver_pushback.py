import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4

from monitor_agents.gm_awareness import (
    ActionType, IntentType, RollNecessity, Severity, CausalityAction, GMAwareness,
)
from monitor_agents.resolver import Resolver


@pytest.mark.asyncio
async def test_forced_narrative_pushback_high_stakes():
    """When the LLM-driven causality check decides the declared outcome violates
    causality (PUSH_BACK), the resolver must request a roll from the player."""
    resolver = Resolver()
    scene_id = str(uuid4())

    pushback_verdict = GMAwareness(
        intent_type=IntentType.ACTION,
        action_type=ActionType.COMBAT,
        roll_necessity=RollNecessity.PROPOSE_ROLL,
        declares_outcome=True,
        violates_causality=True,
        severity=Severity.MAJOR,
        reasons=["Killing without a roll requires a check."],
        action=CausalityAction.PUSH_BACK,
        suggested_stat="Strength",
        suggested_dc=15,
        pushback_prompt="Roll Strength (DC 15) to land the killing blow.",
        reasoning="Combat declaration requires a roll.",
    )

    with patch(
        "monitor_agents.resolver.check_gm_awareness",
        new_callable=AsyncMock,
        return_value=pushback_verdict,
    ):
        user_input = "I kill the boss"
        res = await resolver.resolve_turn(scene_id, user_input, play_mode="dice_standard")

    assert res["resolution_type"] == "forced_narrative_pushback"
    assert res["requires_player_choice"] is True
    assert "pushback_prompt" in res
    assert res["narrative_pressure"] == "spiking"


@pytest.mark.asyncio
async def test_forced_narrative_no_pushback_low_stakes():
    """When the LLM-driven causality check decides the declared outcome is fine
    (ACCEPT), the resolver must advance the fiction without requesting a roll."""
    resolver = Resolver()
    scene_id = str(uuid4())

    accept_verdict = GMAwareness(
        intent_type=IntentType.ACTION,
        action_type=ActionType.MOVEMENT,
        roll_necessity=RollNecessity.TRIVIAL,
        declares_outcome=True,
        violates_causality=False,
        severity=Severity.NONE,
        action=CausalityAction.ACCEPT,
        reasoning="Entering an empty room is a declared low-stakes outcome.",
    )

    with patch(
        "monitor_agents.resolver.check_gm_awareness",
        new_callable=AsyncMock,
        return_value=accept_verdict,
    ):
        user_input = "I enter the room"
        res = await resolver.resolve_turn(scene_id, user_input, play_mode="dice_standard")

    assert res["resolution_type"] == "forced_narrative"
    assert res["success"] is True


class TestResolverPublicMethods:
    def test_resolver_has_resolve_check(self):
        """Resolver should have resolve_check method."""
        resolver = Resolver()
        assert hasattr(resolver, "resolve_check")

    def test_resolver_has_resolve_opposed_check(self):
        """Resolver should have resolve_opposed_check method."""
        resolver = Resolver()
        assert hasattr(resolver, "resolve_opposed_check")

    def test_resolver_has_run_method(self):
        """Resolver should have run method."""
        resolver = Resolver()
        assert hasattr(resolver, "run")

    def test_resolver_initialization(self):
        """Resolver should initialize with default agent_id."""
        resolver = Resolver()
        assert resolver.agent_id == "resolver-cli-1"

    def test_resolver_initialization_custom_id(self):
        """Resolver should initialize with custom agent_id."""
        resolver = Resolver(agent_id="test-resolver")
        assert resolver.agent_id == "test-resolver"

    @pytest.mark.asyncio
    async def test_resolve_check_returns_dict(self):
        """resolve_check should return a dictionary."""
        resolver = Resolver()
        result = await resolver.resolve_check(str(uuid4()), "strength", dc=15)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_resolve_check_with_custom_dc(self):
        """resolve_check should accept custom DC."""
        resolver = Resolver()
        result = await resolver.resolve_check(str(uuid4()), "strength", dc=20)
        # May return error due to entity not found, but should be a dict
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_resolve_turn_returns_dict(self):
        """resolve_turn should return a dictionary."""
        resolver = Resolver()
        scene_id = str(uuid4())
        result = await resolver.resolve_turn(scene_id, "I look around", play_mode="dice_standard")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_resolve_turn_with_tension_score(self):
        """resolve_turn should accept tension_score parameter."""
        resolver = Resolver()
        scene_id = str(uuid4())
        result = await resolver.resolve_turn(
            scene_id, "I open the chest", play_mode="dice_standard", tension_score=0.8
        )
        assert isinstance(result, dict)
