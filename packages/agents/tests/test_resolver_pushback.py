import pytest
from uuid import uuid4
from monitor_agents.resolver import Resolver


@pytest.mark.asyncio
async def test_forced_narrative_pushback_high_stakes():
    resolver = Resolver()
    scene_id = str(uuid4())

    # "I kill the boss" should trigger pushback because it's high stakes (combat/kill)
    user_input = "I kill the boss"
    res = await resolver.resolve_turn(scene_id, user_input, play_mode="dice_standard")

    assert res["resolution_type"] == "forced_narrative_pushback"
    assert res["requires_player_choice"] is True
    assert "pushback_prompt" in res
    assert res["narrative_pressure"] == "spiking"


@pytest.mark.asyncio
async def test_forced_narrative_no_pushback_low_stakes():
    resolver = Resolver()
    scene_id = str(uuid4())

    # "I enter the room" is forced narrative but low stakes
    user_input = "I enter the room"
    res = await resolver.resolve_turn(scene_id, user_input, play_mode="dice_standard")

    # Heuristic check: "enter" is in forced narrative list.
    # But is it high stakes? _classify_roll_necessity for "enter" returns "trivial"
    # unless danger keywords are present.
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
