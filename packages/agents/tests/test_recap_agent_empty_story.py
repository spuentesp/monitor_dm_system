"""Regression test: RecapAgent must not paper over "nothing to recap" with
LLM-generated filler.

Found live: a story bootstrapped from the Play Console gets a placeholder
outline immediately (generic theme/premise/template, empty `beats`) even
before any play happens. With no COMPLETED scenes and no high-magnitude
facts either, the LLM was still fed that placeholder and produced fluent
"the story hasn't started yet" prose -- which callers could not distinguish
from a real recap by length alone, since `outline_result` itself was always
truthy. generate_recap must detect true emptiness (no populated `beats`, no
scene summaries, no facts) up front and return "" instead.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_agents.recap.agent import RecapAgent

_PLACEHOLDER_OUTLINE = {
    "story_id": "bf7a473c-961b-42e9-8a7e-d6cf71a47be5",
    "theme": "dramatic play",
    "premise": "Session started from the Play Console.",
    "constraints": [],
    "beats": [],
    "structure_type": "linear",
}


@pytest.mark.asyncio
async def test_generate_recap_returns_empty_when_nothing_to_recap():
    agent = RecapAgent()

    with patch("monitor_agents.recap.agent.run_sync_read", new=AsyncMock(side_effect=[None, {}, []])):
        agent.module.forward = AsyncMock(side_effect=AssertionError("LLM must not be called for an empty story"))
        result = await agent.generate_recap(uuid4(), uuid4())

    assert result == ""


@pytest.mark.asyncio
async def test_generate_recap_returns_empty_for_bootstrap_placeholder_outline():
    """The real live case: a non-None outline dict that's pure bootstrap
    boilerplate (empty beats) must still count as "nothing to recap"."""
    agent = RecapAgent()

    with patch(
        "monitor_agents.recap.agent.run_sync_read",
        new=AsyncMock(side_effect=[_PLACEHOLDER_OUTLINE, {}, []]),
    ):
        agent.module.forward = AsyncMock(
            side_effect=AssertionError("LLM must not be called for a placeholder-only outline")
        )
        result = await agent.generate_recap(uuid4(), uuid4())

    assert result == ""


@pytest.mark.asyncio
async def test_generate_recap_calls_llm_when_facts_exist_even_without_scenes():
    agent = RecapAgent()

    class _Prediction:
        recap_markdown = "The war began quietly, with a single betrayal."

    with patch(
        "monitor_agents.recap.agent.run_sync_read",
        new=AsyncMock(side_effect=[None, {}, [[{"statement": "The king was betrayed."}]]]),
    ):
        agent.module.forward = lambda **_kwargs: _Prediction()
        result = await agent.generate_recap(uuid4(), uuid4())

    assert result == "The war began quietly, with a single betrayal."


@pytest.mark.asyncio
async def test_generate_recap_calls_llm_when_outline_has_real_beats():
    agent = RecapAgent()

    outline_with_beats = {
        **_PLACEHOLDER_OUTLINE,
        "beats": ["The heist goes wrong", "Rook is captured"],
    }

    class _Prediction:
        recap_markdown = "The heist went sideways, and Rook was taken."

    with patch(
        "monitor_agents.recap.agent.run_sync_read",
        new=AsyncMock(side_effect=[outline_with_beats, {}, []]),
    ):
        agent.module.forward = lambda **_kwargs: _Prediction()
        result = await agent.generate_recap(uuid4(), uuid4())

    assert result == "The heist went sideways, and Rook was taken."
