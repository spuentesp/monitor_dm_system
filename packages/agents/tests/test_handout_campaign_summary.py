"""CF-6 + CF-12: the "campaign_summary" handout type is anchored on the
story's persisted arc recap.

Pins that generate_handout(handout_type="campaign_summary") fetches the
persisted arc recap via the mongodb_get_arc_recap tool and feeds it to the
LLM prompt, that a missing story_id falls back to the universe's latest
story, and that other handout types never touch the arc recap.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_agents.plot_hooks import Handout, HandoutListResponse, PlotHookAgent


def _tool_dispatch(calls: list, arc_recap: dict | None, stories: list | None = None):  # type: ignore[no-untyped-def]
    async def _call(tool_name: str, arguments: dict):  # type: ignore[no-untyped-def]
        calls.append((tool_name, arguments))
        if tool_name == "mongodb_get_arc_recap":
            return arc_recap
        if tool_name == "neo4j_list_stories":
            return {"stories": stories or [], "total": len(stories or [])}
        if tool_name == "neo4j_list_entities":
            return {"entities": []}
        if tool_name == "neo4j_list_facts":
            return {"facts": []}
        if tool_name == "neo4j_list_plot_threads":
            return {"threads": []}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    return _call


def _llm_capture(calls: list, handout_type: str = "campaign_summary"):  # type: ignore[no-untyped-def]
    async def _structured(_schema, messages, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(messages)
        return HandoutListResponse(
            handouts=[
                Handout(
                    title="The Story So Far",
                    content="## Major Arcs\n- The vault opened.",
                    handout_type=handout_type,
                )
            ]
        )

    return _structured


@pytest.mark.asyncio
async def test_campaign_summary_handout_uses_persisted_arc_recap():
    agent = PlotHookAgent()
    universe_id, story_id = uuid4(), uuid4()
    arc_recap = {"story_id": str(story_id), "recap_markdown": "## Major Arcs\n- The vault opened.\n"}
    tool_calls: list = []
    llm_calls: list = []

    with (
        patch.object(agent, "call_tool", new=AsyncMock(side_effect=_tool_dispatch(tool_calls, arc_recap))),
        patch.object(agent, "call_llm_structured", new=AsyncMock(side_effect=_llm_capture(llm_calls))),
    ):
        handout = await agent.generate_handout(
            universe_id=universe_id,
            handout_type="campaign_summary",
            story_id=story_id,
        )

    assert handout.handout_type == "campaign_summary"
    # the arc recap tool was called for exactly this story
    recap_calls = [c for c in tool_calls if c[0] == "mongodb_get_arc_recap"]
    assert len(recap_calls) == 1
    assert recap_calls[0][1]["story_id"] == str(story_id)
    # and the persisted recap reached the LLM prompt
    prompt = llm_calls[0][1]["content"]
    assert "The vault opened." in prompt
    assert "campaign_summary" in prompt


@pytest.mark.asyncio
async def test_campaign_summary_without_story_id_uses_latest_story():
    agent = PlotHookAgent()
    universe_id = uuid4()
    latest_story = uuid4()
    arc_recap = {"story_id": str(latest_story), "recap_markdown": "## Party Journey\n- They came from the coast."}
    tool_calls: list = []
    llm_calls: list = []

    with (
        patch.object(
            agent,
            "call_tool",
            new=AsyncMock(side_effect=_tool_dispatch(tool_calls, arc_recap, stories=[{"id": str(latest_story)}])),
        ),
        patch.object(agent, "call_llm_structured", new=AsyncMock(side_effect=_llm_capture(llm_calls))),
    ):
        handout = await agent.generate_handout(universe_id=universe_id, handout_type="campaign_summary")

    assert handout.handout_type == "campaign_summary"
    story_calls = [c for c in tool_calls if c[0] == "neo4j_list_stories"]
    assert len(story_calls) == 1
    recap_calls = [c for c in tool_calls if c[0] == "mongodb_get_arc_recap"]
    assert recap_calls[0][1]["story_id"] == str(latest_story)
    assert "They came from the coast." in llm_calls[0][1]["content"]


@pytest.mark.asyncio
async def test_campaign_summary_without_persisted_recap_still_generates():
    agent = PlotHookAgent()
    universe_id, story_id = uuid4(), uuid4()
    tool_calls: list = []
    llm_calls: list = []

    with (
        patch.object(agent, "call_tool", new=AsyncMock(side_effect=_tool_dispatch(tool_calls, None))),
        patch.object(agent, "call_llm_structured", new=AsyncMock(side_effect=_llm_capture(llm_calls))),
    ):
        handout = await agent.generate_handout(
            universe_id=universe_id,
            handout_type="campaign_summary",
            story_id=story_id,
        )

    assert handout.handout_type == "campaign_summary"
    assert "None persisted yet" in llm_calls[0][1]["content"]


@pytest.mark.asyncio
async def test_other_handout_types_never_read_the_arc_recap():
    agent = PlotHookAgent()
    tool_calls: list = []
    llm_calls: list = []

    with (
        patch.object(agent, "call_tool", new=AsyncMock(side_effect=_tool_dispatch(tool_calls, {"recap_markdown": "x"}))),
        patch.object(
            agent, "call_llm_structured", new=AsyncMock(side_effect=_llm_capture(llm_calls, handout_type="letter"))
        ),
    ):
        handout = await agent.generate_handout(universe_id=uuid4(), handout_type="letter")

    assert handout.handout_type == "letter"
    assert all(c[0] != "mongodb_get_arc_recap" for c in tool_calls)
    assert "arc recap" not in llm_calls[0][1]["content"].lower()
