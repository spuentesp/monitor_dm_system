"""Tests for the ``infer_action_stat`` / ``infer_subsystem_hint`` wrapper
functions in ``_action_routing.py``.

These are explicitly-labeled "backward-compatible" reshaping wrappers
around ``infer_action_context`` (see their docstrings) — no independent
routing logic of their own, just tuple/string extraction from the dict
``infer_action_context`` returns. Real semantic-routing accuracy is out
of scope for hermetic unit tests (it depends on live embeddings — see
``_router_helpers.py``'s note); this file only proves the reshaping is
correct and that both wrappers delegate through the same
``infer_action_context`` call `GameSystemRuntime` and callers
(``combat_loop.py``, ``chat_loops.py``) actually use.

Use Cases: P-3, P-8, P-10 (game system runtime).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.game_system._types import build_system_data


def _minimal_system_data():
    return build_system_data(
        {
            "name": "Test System",
            "attributes": [{"name": "Strength", "abbreviation": "STR"}],
            "skills": [],
            "resources": [],
        }
    )


@pytest.mark.asyncio
async def test_infer_action_stat_reshapes_context_into_tuple() -> None:
    from monitor_agents.game_system._action_routing import infer_action_stat

    sd = _minimal_system_data()
    fake_context = {"action_type": "dialogue", "stat_name": "CHA", "difficulty_class": 14}

    with patch(
        "monitor_agents.game_system._action_routing.infer_action_context",
        new=AsyncMock(return_value=fake_context),
    ):
        action_type, stat_name, dc = await infer_action_stat(sd, "I persuade the guard")

    assert action_type == "dialogue"
    assert stat_name == "CHA"
    assert dc == 14


@pytest.mark.asyncio
async def test_infer_action_stat_defaults_when_context_incomplete() -> None:
    """Contract: missing keys in the routed context fall back to sane
    defaults rather than raising KeyError."""
    from monitor_agents.game_system._action_routing import infer_action_stat

    sd = _minimal_system_data()
    with patch(
        "monitor_agents.game_system._action_routing.infer_action_context",
        new=AsyncMock(return_value={}),
    ):
        action_type, stat_name, dc = await infer_action_stat(sd, "...")

    assert action_type == "action"
    assert stat_name == "STR"
    assert dc == 12


@pytest.mark.asyncio
async def test_infer_subsystem_hint_extracts_hint_from_context() -> None:
    from monitor_agents.game_system._action_routing import infer_subsystem_hint

    sd = _minimal_system_data()
    with patch(
        "monitor_agents.game_system._action_routing.infer_action_context",
        new=AsyncMock(return_value={"subsystem_hint": "combat"}),
    ):
        hint = await infer_subsystem_hint(sd, "I attack the guard")

    assert hint == "combat"


@pytest.mark.asyncio
async def test_infer_subsystem_hint_returns_none_when_absent() -> None:
    from monitor_agents.game_system._action_routing import infer_subsystem_hint

    sd = _minimal_system_data()
    with patch(
        "monitor_agents.game_system._action_routing.infer_action_context",
        new=AsyncMock(return_value={}),
    ):
        hint = await infer_subsystem_hint(sd, "I look around")

    assert hint is None


@pytest.mark.asyncio
async def test_game_system_runtime_delegates_to_infer_action_stat() -> None:
    """GameSystemRuntime.infer_action_stat (used by combat_loop.py and
    chat_loops.py) must delegate through the same _action_routing
    function, not reimplement its own routing."""
    from monitor_agents.game_system.runtime import GameSystemRuntime

    gsr = GameSystemRuntime(
        {
            "name": "Test System",
            "attributes": [{"name": "Strength", "abbreviation": "STR"}],
            "skills": [],
            "resources": [],
        }
    )
    with patch(
        "monitor_agents.game_system._action_routing.infer_action_context",
        new=AsyncMock(return_value={"action_type": "action", "stat_name": "STR", "difficulty_class": 12}),
    ):
        action_type, stat_name, dc = await gsr.infer_action_stat("I sneak past the guard")

    assert (action_type, stat_name, dc) == ("action", "STR", 12)
