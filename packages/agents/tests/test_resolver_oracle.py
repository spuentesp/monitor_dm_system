from uuid import uuid4

import pytest

from monitor_agents.resolver import (
    Resolver,
    _strip_ooc_wrappers,
)


class TestStripOocWrappers:
    def test_strip_ooc_wrappers_removes_parens(self):
        """Test that ((text)) is stripped."""
        result = _strip_ooc_wrappers("((Roll for initiative))")
        assert result == "Roll for initiative"

    def test_strip_ooc_wrappers_handles_plain_text(self):
        """Test that plain text is returned unchanged."""
        result = _strip_ooc_wrappers("Just regular text")
        assert result == "Just regular text"

    def test_strip_ooc_wrappers_nested_parens(self):
        """Test stripping with multiple layers of parens."""
        result = _strip_ooc_wrappers("(((nested)))")
        assert result == "(nested)"


@pytest.mark.asyncio
async def test_resolver_oracle_integration():
    resolver = Resolver()
    scene_id = str(uuid4())

    # "Is there a guard? ((Likely))"
    user_input = "Is there a guard? ((Likely))"
    res, _ = await resolver.resolve_turn(scene_id, user_input, play_mode="dice_standard")

    assert res["resolution_type"] == "oracle"
    assert "oracle_result" in res
    assert res["oracle_result"]["likelihood"] == "likely"
    assert isinstance(res["success"], bool)


@pytest.mark.asyncio
async def test_resolver_oracle_default_likelihood():
    resolver = Resolver()
    scene_id = str(uuid4())

    # "Are the doors locked?" (no marker)
    user_input = "Are the doors locked?"
    res, _ = await resolver.resolve_turn(scene_id, user_input, play_mode="dice_standard")

    assert res["resolution_type"] == "oracle"
    assert res["oracle_result"]["likelihood"] == "50_50"


@pytest.mark.asyncio
async def test_resolver_oracle_with_unlikely_marker():
    """Test oracle with ((Unlikely)) marker."""
    resolver = Resolver()
    scene_id = str(uuid4())

    user_input = "Is the treasure chest trapped? ((Unlikely))"
    res, _ = await resolver.resolve_turn(scene_id, user_input, play_mode="dice_standard")

    assert res["resolution_type"] == "oracle"
    assert res["oracle_result"]["likelihood"] == "unlikely"


@pytest.mark.asyncio
async def test_resolver_oracle_with_certain_marker():
    """Test oracle with ((Certain)) marker."""
    resolver = Resolver()
    scene_id = str(uuid4())

    user_input = "Is the sky blue? ((Certain))"
    res, _ = await resolver.resolve_turn(scene_id, user_input, play_mode="dice_standard")

    assert res["resolution_type"] == "oracle"
    assert res["oracle_result"]["likelihood"] == "certain"


class TestResolver:
    def test_resolver_initialization(self):
        """Resolver should initialize with default agent_id."""
        resolver = Resolver()
        assert resolver.agent_id == "resolver-cli-1"

    def test_resolver_custom_agent_id(self):
        """Resolver should accept custom agent_id."""
        resolver = Resolver(agent_id="test-resolver")
        assert resolver.agent_id == "test-resolver"

    def test_resolver_has_resolve_turn(self):
        """Resolver should have resolve_turn method."""
        resolver = Resolver()
        assert hasattr(resolver, "resolve_turn")

    def test_resolver_has_resolve_opposed_check(self):
        """Resolver should have resolve_opposed_check method."""
        resolver = Resolver()
        assert hasattr(resolver, "resolve_opposed_check")

    def test_resolver_has_run_method(self):
        """Resolver should have run method."""
        resolver = Resolver()
        assert hasattr(resolver, "run")

    @pytest.mark.asyncio
    async def test_resolve_turn_returns_dict(self):
        """resolve_turn should return a dictionary."""
        resolver = Resolver()
        scene_id = str(uuid4())
        result, _ = await resolver.resolve_turn(scene_id, "I look around", play_mode="dice_standard")
        assert isinstance(result, dict)
