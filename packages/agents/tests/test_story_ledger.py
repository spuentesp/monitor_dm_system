"""
Tests for the story ledger, the event-driven arc and the in-game clock.

The ledger is the campaign's memory: one entry per finished scene, written
when the scene ends and read back on every turn. The arc is judged from that
ledger and from the story's plot threads, not from a counter of scenes.

These tests pin the wiring across the component boundaries: the ledger
model call, the data-layer tool that stores the entry, the arc model call
and the clock the story runs on.

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_story_ledger.py -v
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from mcp.types import TextContent

from monitor_agents.loops import story_loop
from monitor_agents.story.agent import StoryAgent


@contextmanager
def _saver_context(saver):
    yield saver


class FakeToolServer:
    """Stand-in for the data-layer server that records every tool call."""

    def __init__(self, responses: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.responses = responses or {}

    async def __call__(self, name: str, arguments: dict) -> list[TextContent]:
        self.calls.append((name, arguments))
        payload = self.responses.get(name, {})
        return [TextContent(type="text", text=json.dumps(payload, default=str))]

    def calls_to(self, name: str) -> list[dict]:
        return [arguments for called, arguments in self.calls if called == name]


@pytest.fixture
def tool_server(monkeypatch):
    """Route every data-layer tool call to a recorder."""
    from monitor_data import server as data_server

    server = FakeToolServer()
    monkeypatch.setattr(data_server, "call_tool", server)
    return server


@pytest.fixture
def ledger_model(monkeypatch):
    """Stub the ledger model so no provider is called."""
    from monitor_agents.story.story import StoryLedgerModule

    captured: dict = {}

    def forward(self, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            summary="The party crossed the drowned road and found the vault door sealed.",
            state_changes=json.dumps([{"who": "Ilse", "what": "opened the vault map", "where": "the drowned road"}]),
            open_questions=json.dumps(["Who sealed the vault?"]),
        )

    monkeypatch.setattr(StoryLedgerModule, "forward", forward)
    return captured


def _state(**overrides):
    return story_loop.StoryState(story_id=uuid4(), universe_id=uuid4(), **overrides)


class TestLedgerWrite:
    @pytest.mark.asyncio
    async def test_the_entry_reaches_the_data_layer_with_its_parts(self, tool_server, ledger_model):
        """The stored entry carries what the scene did, when and what moved."""
        agent = StoryAgent(agent_id="ledger-write")
        state = _state()
        scene_id = uuid4()
        start = datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        end = datetime(1012, 3, 1, 11, 0, tzinfo=UTC)

        entry = await agent.write_ledger_entry(
            state,
            scene_id=scene_id,
            scene_turns=[{"speaker": "GM", "text": "The vault door is sealed."}],
            agenda_moves=["The miller moved his grain"],
            start_time=start,
            end_time=end,
        )

        calls = tool_server.calls_to("mongodb_append_story_ledger_entry")
        assert len(calls) == 1
        params = calls[0]["params"]
        assert params["story_id"] == str(state.story_id)
        assert params["scene_id"] == str(scene_id)
        assert params["summary"].startswith("The party crossed the drowned road")
        assert params["state_changes"] == [{"who": "Ilse", "what": "opened the vault map", "where": "the drowned road"}]
        assert params["open_questions"] == ["Who sealed the vault?"]
        assert params["start_time"].startswith("1012-03-01T09:00")
        assert params["end_time"].startswith("1012-03-01T11:00")
        assert params["world_moves"] == ["The miller moved his grain"]

        assert entry["summary"].startswith("The party crossed the drowned road")
        assert entry["state_changes"][0]["who"] == "Ilse"

    @pytest.mark.asyncio
    async def test_the_model_call_carries_the_scene_and_the_earlier_ledger(self, tool_server, ledger_model):
        """The model is asked about this scene and what came before it."""
        agent = StoryAgent(agent_id="ledger-context")
        state = _state(ledger_entries=[{"scene_index": 1, "summary": "They took the ferry across the black water."}])

        await agent.write_ledger_entry(
            state,
            scene_id=uuid4(),
            scene_turns=[{"speaker": "GM", "text": "The vault door is sealed."}],
            agenda_moves=["The miller moved his grain"],
            start_time=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
            end_time=datetime(1012, 3, 1, 11, 0, tzinfo=UTC),
        )

        assert "The vault door is sealed." in ledger_model["scene_turns"]
        assert "They took the ferry across the black water." in ledger_model["previous_ledger"]
        assert "The miller moved his grain" in ledger_model["agenda_moves"]

    @pytest.mark.asyncio
    async def test_a_failing_model_is_recorded_and_the_scene_still_gets_an_entry(self, tool_server, monkeypatch):
        """A ledger that cannot be written by the model is still a record."""
        from monitor_agents.story.story import StoryLedgerModule

        recorded: list[dict] = []

        class _Recorder:
            @staticmethod
            async def record(**kwargs):
                recorded.append(kwargs)

        def boom(self, **kwargs):
            raise RuntimeError("the model is down")

        monkeypatch.setattr(StoryLedgerModule, "forward", boom)
        monkeypatch.setattr(
            "monitor_agents.services.roleplay_error_recorder.RoleplayErrorRecorder",
            _Recorder,
        )

        agent = StoryAgent(agent_id="ledger-failure")
        entry = await agent.write_ledger_entry(
            _state(),
            scene_id=uuid4(),
            scene_turns=[{"speaker": "GM", "text": "The vault door is sealed."}],
            agenda_moves=[],
            start_time=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
            end_time=datetime(1012, 3, 1, 11, 0, tzinfo=UTC),
        )

        assert len(recorded) == 1
        assert "the model is down" in str(recorded[0]["message"])
        assert "vault door" in entry["summary"]
        # The entry still reached the data layer.
        assert len(tool_server.calls_to("mongodb_append_story_ledger_entry")) == 1


class TestLedgerAtSceneEnd:
    @pytest.mark.asyncio
    async def test_a_finished_scene_leaves_a_ledger_entry(self, monkeypatch, tool_server, ledger_model):
        """Both scene-end paths go through the story loop, so both write."""
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
        monkeypatch.setattr(story_loop, "_tick_npc_agendas", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            story_loop,
            "_read_scene_turns",
            AsyncMock(return_value=[{"speaker": "GM", "text": "The vault door is sealed."}]),
        )

        loop = story_loop.StoryLoop(story_id=uuid4(), universe_id=uuid4())

        result = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 120})

        assert len(result["ledger_entries"]) == 1
        assert result["ledger_entries"][0]["summary"].startswith("The party crossed")
        assert len(tool_server.calls_to("mongodb_append_story_ledger_entry")) == 1

    @pytest.mark.asyncio
    async def test_the_ledger_grows_and_the_clock_moves_forward(self, monkeypatch, tool_server, ledger_model):
        """Each scene adds an entry, and the in-game times increase."""
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        monkeypatch.setattr(
            story_loop,
            "simulate_world_advance",
            AsyncMock(
                side_effect=lambda state: {
                    "in_game_time": state.in_game_time
                    + __import__("datetime").timedelta(minutes=state.last_scene_duration_minutes)
                }
            ),
        )
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
        monkeypatch.setattr(story_loop, "_tick_npc_agendas", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            story_loop,
            "_read_scene_turns",
            AsyncMock(return_value=[{"speaker": "GM", "text": "The vault door is sealed."}]),
        )
        monkeypatch.setattr(
            story_loop.StoryLoop,
            "_seed_in_game_time",
            AsyncMock(
                side_effect=lambda state: (
                    state
                    if state.in_game_time_source
                    else state.model_copy(
                        update={
                            "in_game_time": datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
                            "in_game_time_source": "story",
                        }
                    )
                )
            ),
        )
        monkeypatch.setattr(story_loop, "_tick_npc_agendas", AsyncMock(return_value=[]))

        loop = story_loop.StoryLoop(story_id=uuid4(), universe_id=uuid4())

        first = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 60})
        second = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 60})

        assert len(first["ledger_entries"]) == 1
        assert len(second["ledger_entries"]) == 2
        assert first["ledger_entries"][0]["start_time"] < second["ledger_entries"][0]["end_time"]
        assert second["in_game_time"] > first["in_game_time"]


class TestArcFromEvents:
    @pytest.fixture
    def arc_model(self, monkeypatch):
        from monitor_agents.story.story import StoryArcModule

        captured: dict = {}

        def forward(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                arc_phase="climax",
                tension=0.8,
                advanced_threads=json.dumps(["The drowned road"]),
                closed_threads=json.dumps([]),
                story_complete=False,
                reasoning="The party stood at the sealed vault.",
            )

        monkeypatch.setattr(StoryArcModule, "forward", forward)
        monkeypatch.setattr(
            StoryAgent,
            "_plan_next_scene",
            AsyncMock(return_value={"next_scene_type": "combat", "plot_hook": "The door opens."}),
        )
        return captured

    @pytest.mark.asyncio
    async def test_the_judge_reads_the_ledger_and_the_plot_threads(self, monkeypatch, tool_server, arc_model):
        """The arc is judged from what happened, not from a scene counter."""
        server = FakeToolServer(
            {"neo4j_list_plot_threads": {"threads": [{"id": "t1", "title": "The drowned road", "status": "active"}]}}
        )
        monkeypatch.setattr("monitor_data.server.call_tool", server)

        agent = StoryAgent(agent_id="arc-judge")
        state = _state(
            scenes_completed=2,
            ledger_entries=[{"scene_index": 1, "summary": "They took the ferry across the black water."}],
        )

        update = await agent.evaluate_arc(state)

        assert "They took the ferry across the black water." in arc_model["ledger"]
        assert "The drowned road" in arc_model["plot_threads"]
        assert update["arc_label"] == "climax"
        assert update["tension_score"] == pytest.approx(0.8)
        assert update["active_threads"] == ["The drowned road"]

    @pytest.mark.asyncio
    async def test_the_plot_threads_are_read_for_the_story(self, monkeypatch, tool_server, arc_model):
        """The threads come from the story's own record in Neo4j."""
        server = FakeToolServer(
            {"neo4j_list_plot_threads": {"threads": [{"id": "t1", "title": "The drowned road", "status": "active"}]}}
        )
        monkeypatch.setattr("monitor_data.server.call_tool", server)

        agent = StoryAgent(agent_id="arc-threads-call")
        state = _state(scenes_completed=1)

        await agent.evaluate_arc(state)

        calls = server.calls_to("neo4j_list_plot_threads")
        assert len(calls) == 1
        assert calls[0]["params"]["story_id"] == str(state.story_id)

    @pytest.mark.asyncio
    async def test_the_phase_is_the_models_answer_not_the_scene_count(self, monkeypatch, tool_server):
        """Two runs with different stories get different phases."""
        from monitor_agents.story.story import StoryArcModule

        phases = iter(["climax", "falling_action"])

        def forward(self, **kwargs):
            return SimpleNamespace(
                arc_phase=next(phases),
                tension=0.5,
                advanced_threads=json.dumps([]),
                closed_threads=json.dumps([]),
                story_complete=False,
                reasoning="because",
            )

        monkeypatch.setattr(StoryArcModule, "forward", forward)
        monkeypatch.setattr(
            StoryAgent,
            "_plan_next_scene",
            AsyncMock(return_value={"next_scene_type": "exploration", "plot_hook": "a hook"}),
        )

        agent = StoryAgent(agent_id="arc-phases")
        first = await agent.evaluate_arc(_state(scenes_completed=2))
        second = await agent.evaluate_arc(_state(scenes_completed=2))

        assert first["arc_label"] == "climax"
        assert second["arc_label"] == "falling_action"

    @pytest.mark.asyncio
    async def test_the_budget_is_an_upper_bound_not_the_driver(self, monkeypatch, tool_server, arc_model):
        """A story that used its budget resolves, even mid-rising-action."""
        agent = StoryAgent(agent_id="arc-budget")
        state = _state(scenes_completed=5, scene_budget=5)

        update = await agent.evaluate_arc(state)

        assert update["arc_label"] == "resolution"
        assert update["story_complete"] is True

    @pytest.mark.asyncio
    async def test_a_story_below_the_budget_is_not_finished(self, monkeypatch, tool_server):
        """The counter alone never ends a story."""
        from monitor_agents.story.story import StoryArcModule

        def forward(self, **kwargs):
            return SimpleNamespace(
                arc_phase="rising_action",
                tension=0.4,
                advanced_threads=json.dumps([]),
                closed_threads=json.dumps([]),
                story_complete=False,
                reasoning="because",
            )

        monkeypatch.setattr(StoryArcModule, "forward", forward)
        monkeypatch.setattr(
            StoryAgent,
            "_plan_next_scene",
            AsyncMock(return_value={"next_scene_type": "exploration", "plot_hook": "a hook"}),
        )

        agent = StoryAgent(agent_id="arc-open")
        update = await agent.evaluate_arc(_state(scenes_completed=1, scene_budget=5))

        assert update["story_complete"] is False
        assert update["arc_label"] == "rising_action"

    @pytest.mark.asyncio
    async def test_no_thread_is_invented_for_the_story(self, monkeypatch, tool_server, arc_model):
        """The story's threads are the ones recorded in Neo4j."""
        agent = StoryAgent(agent_id="arc-threads")
        update = await agent.evaluate_arc(_state(scenes_completed=1))

        assert "central_conflict" not in update["active_threads"]
        assert "character_motivation" not in update["active_threads"]

    @pytest.mark.asyncio
    async def test_a_closed_thread_leaves_the_open_list(self, monkeypatch, tool_server):
        """When the judge closes a thread, it is closed for the story."""
        from monitor_agents.story.story import StoryArcModule

        monkeypatch.setattr(
            "monitor_data.server.call_tool",
            FakeToolServer(
                {
                    "neo4j_list_plot_threads": {
                        "threads": [
                            {"id": "t1", "title": "The drowned road", "status": "active"},
                            {"id": "t2", "title": "The sealed vault", "status": "active"},
                        ]
                    }
                }
            ),
        )

        def forward(self, **kwargs):
            return SimpleNamespace(
                arc_phase="falling_action",
                tension=0.5,
                advanced_threads=json.dumps([]),
                closed_threads=json.dumps(["The sealed vault"]),
                story_complete=False,
                reasoning="because",
            )

        monkeypatch.setattr(StoryArcModule, "forward", forward)
        monkeypatch.setattr(
            StoryAgent,
            "_plan_next_scene",
            AsyncMock(return_value={"next_scene_type": "dialogue", "plot_hook": "a hook"}),
        )

        agent = StoryAgent(agent_id="arc-closed")
        update = await agent.evaluate_arc(_state(scenes_completed=3))

        assert update["active_threads"] == ["The drowned road"]
        assert "The sealed vault" in update["completed_threads"]


class TestInGameTime:
    @pytest.mark.asyncio
    async def test_the_story_date_wins_when_the_story_has_one(self, tool_server):
        """An authored date is the world's date."""
        tool_server.responses["neo4j_get_story"] = {
            "id": "s1",
            "start_time_ref": "1345-06-01T08:00:00+00:00",
        }
        agent = StoryAgent(agent_id="time-story")

        when, source = await agent.seed_in_game_time(uuid4(), uuid4())

        assert source == "story"
        assert when == datetime(1345, 6, 1, 8, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_the_model_estimate_is_used_when_the_world_has_no_date(self, tool_server):
        """With no authored date, the world itself is asked."""
        tool_server.responses["neo4j_get_story"] = {"id": "s1", "start_time_ref": None}
        tool_server.responses["neo4j_get_universe"] = {
            "id": "u1",
            "name": "Ashen Reach",
            "description": "A kingdom of ash and iron, three centuries after the burning.",
            "genre": "fantasy",
            "tech_level": "medieval",
        }

        from monitor_agents.story.story import StoryTimeSeedModule

        captured: dict = {}

        def forward(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                start_time="1327-04-01T08:00:00+00:00",
                reasoning="the burning was three centuries ago",
            )

        with pytest.MonkeyPatch.context() as patcher:
            patcher.setattr(StoryTimeSeedModule, "forward", forward)
            agent = StoryAgent(agent_id="time-model")
            when, source = await agent.seed_in_game_time(uuid4(), uuid4())

        assert source == "model"
        assert when == datetime(1327, 4, 1, 8, 0, tzinfo=UTC)
        assert "Ashen Reach" in captured["universe_name"]
        assert "three centuries" in captured["universe_description"]

    @pytest.mark.asyncio
    async def test_the_fallback_is_used_when_nothing_can_be_read(self, tool_server):
        """A world that cannot be read still gets a clock."""
        tool_server.responses["neo4j_get_story"] = {}
        tool_server.responses["neo4j_get_universe"] = {}

        agent = StoryAgent(agent_id="time-fallback")
        when, source = await agent.seed_in_game_time(uuid4(), uuid4())

        assert source == "fallback"
        assert when.year == 1000

    @pytest.mark.asyncio
    async def test_the_clock_is_read_from_the_worlds_own_records(self, tool_server):
        """The story and the universe are the records the clock comes from."""
        tool_server.responses["neo4j_get_story"] = {}
        tool_server.responses["neo4j_get_universe"] = {
            "id": "u1",
            "name": "Ashen Reach",
            "description": "A kingdom of ash.",
            "genre": "fantasy",
            "tech_level": "medieval",
        }

        agent = StoryAgent(agent_id="time-reads")
        story_id = uuid4()
        universe_id = uuid4()

        await agent.seed_in_game_time(universe_id, story_id)

        assert tool_server.calls_to("neo4j_get_story")[0]["story_id"] == str(story_id)
        assert tool_server.calls_to("neo4j_get_universe")[0]["universe_id"] == str(universe_id)


class TestProgressionXp:
    def test_the_xp_comes_from_the_scene_that_was_played(self):
        from monitor_agents.loops.story_loop import _derive_scene_xp

        quiet = _derive_scene_xp({"total_minutes_passed": 5, "turns_count": 1}, arc_label="rising_action")
        busy = _derive_scene_xp(
            {"total_minutes_passed": 300, "turns_count": 12},
            arc_label="climax",
            state_changes=4,
        )

        assert quiet >= 1
        assert busy > quiet

    def test_the_xp_is_never_below_one(self):
        from monitor_agents.loops.story_loop import _derive_scene_xp

        assert _derive_scene_xp({}, arc_label=None) == 1
