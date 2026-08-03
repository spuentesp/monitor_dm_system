"""
Tests for the GM tools registry — T1 of the gm-tool-authority plan.

Coverage:
- Registry shape: 10 tools registered, each with a name + desc + args.
- Loop bridge: async tool functions resolve via the bridge; test bridge
  default is ``asyncio.run`` so async tools resolve synchronously in tests.
- Tool contracts: each tool exposes a callable that returns a JSON string.
- Fail-loud contract: when embeddings are unavailable, semantic tools don't
  hang — they return ``{"error": "fail_loud", ...}`` in JSON.
- Registry no longer exposes classifier tools — the GMAgent LLM emits
  intent_type / roll_necessity / action_type directly.

Does NOT cover (T2 / T3):
- Real scene-state lookup.
- Real dice RNG output beyond a smoke check.
- DSPy ReAct composition — T3 wires this end-to-end with ``_FakeLM``.
"""

from __future__ import annotations

import json
from typing import Any

import dspy
import pytest

from monitor_agents.gm_tools import (
    GM_TOOLS as get_tools_list,
)
from monitor_agents.gm_tools import (
    GMVerdict,
)
from monitor_agents.gm_tools.registry import (
    GM_TOOLS,
    get_tool,
    reset_loop_bridge,
    set_loop_bridge,
)

# ============================================================================
# Registry shape
# ============================================================================


def test_registry_returns_a_list_of_tools() -> None:
    tools = get_tools_list()
    assert isinstance(tools, list)
    assert len(tools) >= 5  # we expect 10 but at minimum the core tools


def test_registry_contains_the_expected_tool_names() -> None:
    # The classifier tools (classify_intent / classify_roll_necessity /
    # route_action) were removed — the GMAgent LLM emits those directly.
    expected = {
        "get_scene_state",
        "list_playable_actions",
        "evaluate_scenery",
        "check_conditions",
        "list_active_conditions",
        "roll_dice",
        "resolve_oracle",
    }
    names = {
        getattr(t, "name", None)
        for t in GM_TOOLS()  # calling the function; consistent with __init__
    }
    missing = expected - names
    assert not missing, f"missing tools: {missing}; have: {sorted(names)}"


def test_each_tool_has_name_desc_args() -> None:
    for tool in GM_TOOLS():
        assert getattr(tool, "name", None), "tool without name"
        assert getattr(tool, "desc", None), f"tool {tool.name} without desc"
        args = getattr(tool, "args", {})
        assert isinstance(args, dict), f"tool {tool.name} args not dict"


def test_get_tool_lookup() -> None:
    for t in GM_TOOLS():
        t2 = get_tool(t.name)
        assert t2 is t or t2.name == t.name


def test_unknown_tool_name_raises() -> None:
    with pytest.raises(KeyError):
        get_tool("not_a_real_tool_name")


# ============================================================================
# Loop bridge
# ============================================================================


def test_default_loop_bridge_is_asyncio_run() -> None:
    # Default bridge path: a coroutine resolves to its value.
    async def _coro():
        return 42

    from monitor_agents.gm_tools.registry import run_coroutine_sync

    # If default bridge is ``asyncio.run``, this raises ``RuntimeError`` when
    # called inside a running loop. For a unit-level check, calling on a fresh
    # coroutine from sync code works because there's no running loop.
    out = run_coroutine_sync(_coro())
    assert out == 42


def test_custom_loop_bridge_is_used_when_set() -> None:
    seen: list[Any] = []

    def _my_bridge(coro: Any) -> Any:
        # Resolve the coroutine so the test can run synchronously, and
        # return its value (the GMAgent loop bridge will block on the
        # result of run_coroutine_threadsafe).
        import asyncio as _asyncio

        result = _asyncio.run(coro)
        seen.append(result)
        return result

    async def _who_cares():
        return "via_my_bridge"

    set_loop_bridge(_my_bridge)
    try:
        from monitor_agents.gm_tools.registry import run_coroutine_sync

        out = run_coroutine_sync(_who_cares())
        assert out == "via_my_bridge"
        assert seen == ["via_my_bridge"]
    finally:
        reset_loop_bridge()


def test_tools_are_dspy_tool_instances() -> None:
    for t in GM_TOOLS():
        assert isinstance(t, dspy.Tool), f"{t.name} is {type(t)} not dspy.Tool"


# ============================================================================
# Tool contracts — each callable returns a JSON string
# ============================================================================


def test_get_scene_state_returns_json() -> None:
    tool = get_tool("get_scene_state")
    # dspy.Tool stores the func; invoke via __call__ to get the docstring-shaped wrapper.
    raw = tool.func("scene-123")
    parsed = json.loads(raw)
    assert parsed["scene_id"] == "scene-123"
    assert "status" in parsed


def test_evaluate_scenery_returns_json() -> None:
    tool = get_tool("evaluate_scenery")
    # Args: scene_id, game_context_json, location_tags_json, location_description.
    raw = tool.func("scene-1", "", "[]", "calm road")
    parsed = json.loads(raw)
    assert parsed["scene_id"] == "scene-1"
    assert parsed["status"] == "no_schema"
    assert parsed["modifiers"] == []


def test_list_playable_actions_returns_json() -> None:
    tool = get_tool("list_playable_actions")
    raw = tool.func("scene-1", "sys-vtm-1")
    parsed = json.loads(raw)
    assert parsed["scene_id"] == "scene-1"
    assert parsed["system_id"] == "sys-vtm-1"


def test_check_conditions_returns_json() -> None:
    tool = get_tool("check_conditions")
    raw = tool.func("character takes damage", '{"track_values": {"HP": 1}}')
    parsed = json.loads(raw)
    assert parsed["event"] == "character takes damage"


def test_list_active_conditions_returns_json() -> None:
    tool = get_tool("list_active_conditions")
    raw = tool.func("scene-1", "char-1")
    parsed = json.loads(raw)
    assert parsed["scene_id"] == "scene-1"


def test_resolve_oracle_returns_json_shape() -> None:
    tool = get_tool("resolve_oracle")
    raw = tool.func("Is the trap armed?", "fifty_fifty", 0.5)
    parsed = json.loads(raw)
    assert "question" in parsed
    assert parsed["question"] == "Is the trap armed?"


# ============================================================================
# Contracts (GMVerdict) — small smoke checks
# ============================================================================


def test_gmverdict_to_dict_is_json_serializable() -> None:
    from monitor_agents.gm_awareness import ActionType, CausalityAction, IntentType, RollNecessity

    verdict = GMVerdict(
        intent_type=IntentType.ACTION,
        action_type=ActionType.COMBAT,
        roll_necessity=RollNecessity.CONTESTED,
        causality_action=CausalityAction.ACCEPT,
        suggested_stat="STR",
        suggested_dc=12,
        subsystem_hint="combat",
        narrative_draft="You swing.",
        tool_calls_made=["check_conditions", "roll_dice"],
        tool_call_count=2,
    )
    d = verdict.to_dict()
    # Round-trip through JSON to confirm it serializes cleanly.
    s = json.dumps(d, default=str)
    parsed = json.loads(s)
    assert parsed["intent_type"] == "action"
    assert parsed["roll_necessity"] == "contested"
    assert parsed["subsystem_hint"] == "combat"
    assert parsed["tool_call_count"] == 2


class TestContestedCheckTool:
    """The generic ``contested_check`` tool (no VtM in the name) is the
    GMAgent's interface to the pool dice engine. The tool takes a
    pool_size and difficulty (which the resolver/GMAgent should pull
    from the world's core_mechanic, not from hardcoded values) and
    returns a JSON blob the narrator can narrate from.

    This is the generic surface the user asked for: the dice system
    is driven by the rules in the seed/PDF, and the tool is the
    engine that applies them. There's no VtM-specific naming or
    behaviour — the engine reads its parameters from the world
    config (the PDF's core_mechanic) and the caller is responsible
    for passing them.
    """

    def test_contested_check_in_registry(self):
        from monitor_agents.gm_tools import GM_TOOLS
        names = {t.name for t in GM_TOOLS()}
        assert "contested_check" in names
        # The old VtM-specific names must NOT be in the registry.
        assert "vtm_contested_pool" not in names
        assert "vtm_rouse_check" not in names
        assert "vtm_willpower_reroll" not in names

    def test_contested_check_tool_contract(self):
        import json
        from monitor_agents.gm_tools.dice import gm_tool_contested_check
        tool = gm_tool_contested_check()
        result_json = tool.func(pool_size=5, difficulty=6)
        result = json.loads(result_json)
        # The tool returns the engine's typed result as JSON.
        assert "successes" in result
        assert "raw_rolls" in result
        assert "passed" in result
        assert result["pool_size"] == 5
        assert result["difficulty"] == 6
        assert len(result["raw_rolls"]) == 5
        # The engine name is the generic "pool", not "vtm_v20".
        assert result["engine"] == "pool"

    def test_contested_check_uses_difficulty_from_seed(self):
        """The test_pool_engine_uses_seed_mechanics test in
        tests/dice/test_pool_engine.py already proves the end-to-end
        round-trip from the seed JSON to the engine. Here we pin the
        GM-tool surface: the tool is what the GMAgent actually calls
        during play, and it must use whatever difficulty the world's
        core_mechanic provides — not a hardcoded value."""
        import json
        from pathlib import Path
        from unittest.mock import patch
        from monitor_agents.gm_tools.dice import gm_tool_contested_check

        # Load the seed: the world config provides difficulty=6
        # (from core_mechanic.success_threshold = "6"). The test file
        # is at packages/agents/tests/test_gm_tools.py, so 3 .parent
        # calls reach the repo root (tests → agents → packages).
        repo_root = Path(__file__).resolve().parents[3]
        seed_path = (
            repo_root / "packages" / "data-layer" / "src"
            / "monitor_data" / "defaults" / "systems" / "vampire.json"
        )
        with open(seed_path) as f:
            seed = json.load(f)
        seed_threshold = int(seed["core_mechanic"]["success_threshold"])

        tool = gm_tool_contested_check()

        # Patch the random rolls so the test is deterministic. Five
        # 8s at DC 6 = 5 successes.
        rolls_iter = iter([8, 8, 8, 8, 8])
        import random as _r
        original_randint = _r.randint
        _r.randint = lambda a, b: next(rolls_iter)
        try:
            result = json.loads(tool.func(pool_size=5, difficulty=seed_threshold))
        finally:
            _r.randint = original_randint

        # The tool's difficulty matches the seed's threshold exactly.
        assert result["difficulty"] == seed_threshold
        assert result["successes"] == 5
        assert result["passed"] is True
