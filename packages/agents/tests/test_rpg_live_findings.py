"""Regressions found in a live RPG run on MiniMax."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_agents.extraction.agent import ExtractionAgent


@pytest.mark.parametrize(
    ("narration", "expected"),
    [
        ("The door is open now.", "State change: door is now open"),
        ("The guards are dead.", "State change: guards is now dead"),
        ("The hatch opens with a groan.", "Barrier breached"),
        ("You grab the keycard.", "Item acquired: keycard"),
    ],
)
def test_fact_extraction_handles_every_template(narration: str, expected: str) -> None:
    agent = ExtractionAgent(agent_id="test-extractor")
    result = asyncio.run(agent.extract_facts(narration, [], uuid4()))
    assert expected in result.get("established_facts", [])


def test_story_planner_runs_with_a_bound_model() -> None:
    from monitor_agents.story.agent import StoryAgent
    from monitor_agents.loops.story_loop import StoryState

    bound: list[str] = []
    inside = {"active": False}

    @contextlib.contextmanager
    def fake_context(node: str, role: Any = None, **_kw: Any):
        bound.append(node)
        inside["active"] = True
        try:
            yield
        finally:
            inside["active"] = False

    def forward(self: Any, **_kw: Any) -> dict[str, str]:
        assert inside["active"], "planner ran with no model context"
        return {"next_scene_type": "social", "plot_hook": "A stranger arrives."}

    state = StoryState(story_id=uuid4(), universe_id=uuid4())
    agent = StoryAgent.__new__(StoryAgent)
    with (
        patch("monitor_agents.dspy_runtime.dspy_context_for", fake_context),
        patch("monitor_agents.story.story.StoryPlannerModule.forward", forward),
        patch("monitor_agents.story.story.StoryPlannerModule.__init__", lambda self: None),
    ):
        result = asyncio.run(agent._plan_next_scene(state))

    assert result["plot_hook"] == "A stranger arrives."
    assert bound == ["story_planner"]
