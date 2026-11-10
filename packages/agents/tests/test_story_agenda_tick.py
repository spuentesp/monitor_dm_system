"""
Tests for the NPC agenda tick the story loop runs when a scene ends.

The tick used to call ``self.call_tool("neo4j_tick_agendas", ...)`` on a
class that has no such method: the call raised ``AttributeError`` and a
blanket ``except`` swallowed it, so the off-screen NPCs never moved. These
tests pin that the tick really reaches the data-layer tool, with the
arguments the tool expects, and that a failing tick is recorded instead of
disappearing.

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_story_agenda_tick.py -v
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from mcp.types import TextContent

from monitor_agents.loops import story_loop
from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource


@contextmanager
def _saver_context(saver):
    yield saver


@pytest.fixture
def story_deps(monkeypatch):
    """Stub everything around the agenda tick so the tick is what runs."""
    saver = MemorySaver()
    monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
    monkeypatch.setattr(story_loop, "simulate_world_advance", AsyncMock(return_value={}))
    monkeypatch.setattr(
        story_loop,
        "evaluate_arc",
        AsyncMock(return_value={"arc_label": "rising_action", "story_complete": False}),
    )
    monkeypatch.setattr(
        story_loop,
        "transition_scene",
        AsyncMock(return_value={"current_scene_id": uuid4()}),
    )
    monkeypatch.setattr(story_loop, "finalize_story", AsyncMock())


class _RecordingErrorRecorder:
    """Stand-in for the recorder that keeps the failures in a list."""

    def __init__(self) -> None:
        self.recorded: list[dict] = []

    async def record(self, **kwargs: object) -> None:
        self.recorded.append(kwargs)


@pytest.fixture
def recorder(monkeypatch):
    """Capture the roleplay errors the story loop records."""
    fake = _RecordingErrorRecorder()
    monkeypatch.setattr(story_loop, "RoleplayErrorRecorder", fake)
    return fake


class TestAgendaTick:
    @pytest.mark.asyncio
    async def test_the_tick_calls_the_agenda_tool_with_the_universe(self, monkeypatch, story_deps):
        """The tick reaches the tool, with the universe it belongs to."""
        from monitor_data import server as data_server

        calls: list[tuple[str, dict]] = []

        async def fake_call_tool(name: str, arguments: dict) -> list[TextContent]:
            calls.append((name, arguments))
            return [TextContent(type="text", text=json.dumps(["Count Dracula advanced: Blood Tithe"]))]

        monkeypatch.setattr(data_server, "call_tool", fake_call_tool)

        universe_id = uuid4()
        loop = story_loop.StoryLoop(story_id=uuid4(), universe_id=universe_id)

        result = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 10})

        assert calls == [
            (
                "neo4j_tick_agendas",
                {"universe_id": str(universe_id), "agent_type": "StoryLoop"},
            )
        ]
        assert result["agenda_moves"] == ["Count Dracula advanced: Blood Tithe"]

    @pytest.mark.asyncio
    async def test_the_tick_reaches_the_neo4j_tool_through_the_server(self, monkeypatch, story_deps):
        """The call goes through the data-layer server, authority check included."""
        from monitor_data import server as data_server

        seen: list[str] = []

        def fake_tick(universe_id: str) -> list[str]:
            seen.append(universe_id)
            return ["The miller moved his grain"]

        monkeypatch.setitem(data_server.TOOL_REGISTRY, "neo4j_tick_agendas", fake_tick)

        universe_id = uuid4()
        loop = story_loop.StoryLoop(story_id=uuid4(), universe_id=universe_id)

        result = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 10})

        assert seen == [str(universe_id)]
        assert result["agenda_moves"] == ["The miller moved his grain"]

    @pytest.mark.asyncio
    async def test_a_failing_tick_is_recorded_and_the_scene_still_advances(self, monkeypatch, story_deps, recorder):
        """A broken tick is visible afterwards and costs no scene transition."""
        from monitor_data import server as data_server

        async def failing_call_tool(name: str, arguments: dict) -> list[TextContent]:
            return [TextContent(type="text", text="Error executing tool: neo4j is down")]

        monkeypatch.setattr(data_server, "call_tool", failing_call_tool)

        universe_id = uuid4()
        story_id = uuid4()
        loop = story_loop.StoryLoop(story_id=story_id, universe_id=universe_id)

        result = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 10})

        assert len(recorder.recorded) == 1
        assert recorder.recorded[0]["source"] == RoleplayErrorSource.STORY_LOOP
        assert recorder.recorded[0]["category"] == RoleplayErrorCategory.NPC_AGENDA_TICK_FAILED
        assert recorder.recorded[0]["universe_id"] == universe_id
        assert recorder.recorded[0]["story_id"] == story_id
        assert "neo4j is down" in str(recorder.recorded[0]["message"])

        # The story still moves on: the tick is a side effect, not a gate.
        assert result["agenda_moves"] == []
        assert result["current_scene_id"] is not None
        assert result["story_complete"] is False

    @pytest.mark.asyncio
    async def test_the_tick_is_not_swallowed_by_a_bare_except(self, monkeypatch, story_deps, recorder):
        """An authorization error surfaces as a recorded failure, not silence."""
        from monitor_data import server as data_server

        async def unauthorized_call_tool(name: str, arguments: dict) -> list[TextContent]:
            return [
                TextContent(
                    type="text",
                    text="Authorization error: Agent 'Nobody' is not authorized to call 'neo4j_tick_agendas'.",
                )
            ]

        monkeypatch.setattr(data_server, "call_tool", unauthorized_call_tool)

        loop = story_loop.StoryLoop(story_id=uuid4(), universe_id=uuid4())

        result = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 10})

        assert len(recorder.recorded) == 1
        assert recorder.recorded[0]["category"] == RoleplayErrorCategory.NPC_AGENDA_TICK_FAILED
        assert "Authorization error" in str(recorder.recorded[0]["message"])
        assert result["agenda_moves"] == []

    @pytest.mark.asyncio
    async def test_an_unreadable_answer_is_recorded_as_a_failure(self, monkeypatch, story_deps, recorder):
        """A tool that answers with something else is a failure, not a crash."""
        from monitor_data import server as data_server

        async def noisy_call_tool(name: str, arguments: dict) -> list[TextContent]:
            return [TextContent(type="text", text="the agenda tool is thinking about it")]

        monkeypatch.setattr(data_server, "call_tool", noisy_call_tool)

        loop = story_loop.StoryLoop(story_id=uuid4(), universe_id=uuid4())

        result = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 10})

        assert len(recorder.recorded) == 1
        assert recorder.recorded[0]["category"] == RoleplayErrorCategory.NPC_AGENDA_TICK_FAILED
        assert "no JSON" in str(recorder.recorded[0]["message"])
        assert result["agenda_moves"] == []
        assert result["current_scene_id"] is not None
