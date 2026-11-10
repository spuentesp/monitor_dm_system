"""
Tests for the story arc contract: a story spans several scenes and ends
when its arc resolves.

The arc runs rising action → climax → falling action → resolution, and the
story's scene budget decides how long it lasts. These tests pin that the
arc always reaches its resolution, that finishing a scene advances the story
instead of ending it, and that the story's progress survives a restart.

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_story_arc_contract.py -v
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver

from monitor_agents.loops import scene_loop, story_loop


@contextmanager
def _saver_context(saver):
    yield saver


@pytest.fixture
def arc_planner(monkeypatch):
    """Stub the DSPy scene planner so the arc heuristic runs on its own."""
    from monitor_agents.story.agent import StoryAgent

    monkeypatch.setattr(
        StoryAgent,
        "_plan_next_scene",
        AsyncMock(return_value={"next_scene_type": "exploration", "plot_hook": "a hook"}),
    )


async def _arc_labels(budget: int = 5) -> list[tuple[str, bool]]:
    """Run the real arc evaluation over a whole story and collect its labels.

    Each round stands for one finished scene: the story counts the scene
    before the arc looks at it, exactly as ``complete_current_scene`` does.
    """
    from monitor_agents.story.agent import StoryAgent

    agent = StoryAgent(agent_id="arc-contract")
    state = story_loop.StoryState(story_id=uuid4(), universe_id=uuid4(), scene_budget=budget)
    labels: list[tuple[str, bool]] = []
    for _ in range(budget):
        state = state.model_copy(update={"scenes_completed": state.scenes_completed + 1})
        update = await agent.evaluate_arc(state)
        state = state.model_copy(update=update)
        labels.append((update["arc_label"], update["story_complete"]))
    return labels


class TestArcContract:
    @pytest.mark.asyncio
    async def test_arc_reaches_resolution_and_ends_the_story(self, arc_planner):
        labels = await _arc_labels()

        assert [label for label, _ in labels] == [
            "rising_action",
            "rising_action",
            "climax",
            "falling_action",
            "resolution",
        ]
        assert [complete for _, complete in labels] == [False, False, False, False, True]

    @pytest.mark.asyncio
    async def test_arc_length_follows_the_scene_budget(self, arc_planner):
        labels = await _arc_labels(budget=7)

        assert [label for label, _ in labels][:6] == [
            "rising_action",
            "rising_action",
            "rising_action",
            "rising_action",
            "climax",
            "falling_action",
        ]
        assert labels[6] == ("resolution", True)

    @pytest.mark.asyncio
    async def test_the_shortest_budget_still_resolves(self, arc_planner):
        labels = await _arc_labels(budget=3)

        assert [label for label, _ in labels] == ["climax", "falling_action", "resolution"]
        assert labels[-1][1] is True

    @pytest.mark.asyncio
    async def test_an_even_budget_puts_each_phase_where_it_belongs(self, arc_planner):
        labels = await _arc_labels(budget=6)

        assert [label for label, _ in labels] == [
            "rising_action",
            "rising_action",
            "rising_action",
            "climax",
            "falling_action",
            "resolution",
        ]
        assert labels[-1][1] is True

    @pytest.mark.asyncio
    async def test_the_arc_curve_pins_tension_and_phase_boundaries(self, arc_planner):
        """The whole curve: phase, tension and threads for every scene."""
        from monitor_agents.story.agent import StoryAgent

        agent = StoryAgent(agent_id="arc-curve")
        state = story_loop.StoryState(story_id=uuid4(), universe_id=uuid4(), scene_budget=5, tension_score=0.3)

        seen = []
        for _ in range(5):
            state = state.model_copy(update={"scenes_completed": state.scenes_completed + 1})
            update = await agent.evaluate_arc(state)
            state = state.model_copy(update=update)
            seen.append(
                (
                    update["arc_label"],
                    update["tension_score"],
                    list(update["active_threads"]),
                    list(update["completed_threads"]),
                )
            )

        assert [(label, threads, done) for label, _, threads, done in seen] == [
            ("rising_action", ["central_conflict", "character_motivation"], []),
            ("rising_action", ["central_conflict", "character_motivation"], []),
            ("climax", [], ["central_conflict", "character_motivation"]),
            ("falling_action", [], ["central_conflict", "character_motivation"]),
            ("resolution", [], ["central_conflict", "character_motivation"]),
        ]
        assert [tension for _, tension, _, _ in seen] == pytest.approx([0.45, 0.75, 0.85, 0.6, 0.4])

    @pytest.mark.asyncio
    async def test_tension_never_falls_below_the_floor(self, arc_planner):
        """A quiet story still keeps its tension inside the arc's range."""
        from monitor_agents.story.agent import StoryAgent

        agent = StoryAgent(agent_id="arc-floor")
        state = story_loop.StoryState(
            story_id=uuid4(),
            universe_id=uuid4(),
            scene_budget=3,
            tension_score=0.1,
        )

        tensions = []
        for _ in range(3):
            state = state.model_copy(update={"scenes_completed": state.scenes_completed + 1})
            update = await agent.evaluate_arc(state)
            state = state.model_copy(update=update)
            tensions.append(update["tension_score"])

        assert tensions == pytest.approx([0.2, 0.3, 0.1])

    @pytest.mark.asyncio
    async def test_the_story_opens_its_threads_on_its_first_scene(self, arc_planner):
        """The threads open with the story, not only when no scene has run."""
        from monitor_agents.story.agent import StoryAgent

        agent = StoryAgent(agent_id="arc-first-scene")
        state = story_loop.StoryState(story_id=uuid4(), universe_id=uuid4(), scenes_completed=1)

        update = await agent.evaluate_arc(state)

        assert update["active_threads"] == ["central_conflict", "character_motivation"]
        assert update["completed_threads"] == []

    @pytest.mark.asyncio
    async def test_climax_pays_off_the_plot_threads(self, arc_planner):
        from monitor_agents.story.agent import StoryAgent

        agent = StoryAgent(agent_id="arc-threads")
        state = story_loop.StoryState(story_id=uuid4(), universe_id=uuid4())

        first = await agent.evaluate_arc(state)
        assert first["active_threads"] == ["central_conflict", "character_motivation"]

        state = state.model_copy(update=first)
        for _ in range(2):
            state = state.model_copy(update={"scenes_completed": state.scenes_completed + 1})
            state = state.model_copy(update=await agent.evaluate_arc(state))

        state = state.model_copy(update={"scenes_completed": state.scenes_completed + 1})
        climax = await agent.evaluate_arc(state)
        assert climax["arc_label"] == "climax"
        assert climax["active_threads"] == []
        assert climax["completed_threads"] == ["central_conflict", "character_motivation"]


class TestStoryProgression:
    @pytest.mark.asyncio
    async def test_finishing_a_scene_advances_the_story_without_ending_it(self, monkeypatch, arc_planner):
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        monkeypatch.setattr(story_loop, "simulate_world_advance", AsyncMock(return_value={}))
        next_scene = uuid4()
        monkeypatch.setattr(story_loop, "transition_scene", AsyncMock(return_value={"current_scene_id": next_scene}))
        finalize = AsyncMock()
        monkeypatch.setattr(story_loop, "finalize_story", finalize)

        loop = story_loop.StoryLoop(uuid4(), uuid4())

        result = await loop.complete_current_scene(uuid4(), {"scene_complete": True})

        assert result["story_complete"] is False
        assert result["current_scene_id"] == next_scene
        finalize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_story_ends_when_its_arc_resolves(self, monkeypatch, arc_planner):
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        monkeypatch.setattr(story_loop, "simulate_world_advance", AsyncMock(return_value={}))
        monkeypatch.setattr(story_loop, "transition_scene", AsyncMock(return_value={"current_scene_id": uuid4()}))
        finalize = AsyncMock()
        monkeypatch.setattr(story_loop, "finalize_story", finalize)

        loop = story_loop.StoryLoop(uuid4(), uuid4())

        results = []
        for _ in range(5):
            results.append(await loop.complete_current_scene(uuid4(), {"scene_complete": True}))

        assert results[-1]["story_complete"] is True
        assert finalize.await_count == 1
        # One scene counted per finished scene — not two.
        assert results[-1]["scenes_completed"] == 5

    @pytest.mark.asyncio
    async def test_story_progress_survives_a_restart(self, monkeypatch, arc_planner):
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        monkeypatch.setattr(story_loop, "simulate_world_advance", AsyncMock(return_value={}))
        monkeypatch.setattr(story_loop, "transition_scene", AsyncMock(return_value={"current_scene_id": uuid4()}))

        loop = story_loop.StoryLoop(uuid4(), uuid4())

        first = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 10})
        second = await loop.complete_current_scene(first["current_scene_id"], {"total_minutes_passed": 20})

        resumed = await loop.start_or_resume()

        assert second["scenes_completed"] == 2
        assert resumed["scenes_completed"] == 2
        assert resumed["current_scene_id"] == second["current_scene_id"]
        assert resumed["arc_label"] == second["arc_label"]

    @pytest.mark.asyncio
    async def test_a_story_asked_to_end_ends_at_once(self, monkeypatch, arc_planner):
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        finalize = AsyncMock()
        monkeypatch.setattr(story_loop, "finalize_story", finalize)

        loop = story_loop.StoryLoop(uuid4(), uuid4())

        result = await loop.complete_current_scene(uuid4(), {"story_complete": True})

        assert result["story_complete"] is True
        finalize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_resolved_story_does_not_open_another_scene(self, monkeypatch, arc_planner):
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        monkeypatch.setattr(story_loop, "simulate_world_advance", AsyncMock(return_value={}))
        transition = AsyncMock(return_value={"current_scene_id": uuid4()})
        monkeypatch.setattr(story_loop, "transition_scene", transition)
        monkeypatch.setattr(story_loop, "finalize_story", AsyncMock())

        loop = story_loop.StoryLoop(uuid4(), uuid4())

        for _ in range(5):
            await loop.complete_current_scene(uuid4(), {"scene_complete": True})

        transition.reset_mock()
        result = await loop.complete_current_scene(uuid4(), {"scene_complete": True})

        assert result["story_complete"] is True
        transition.assert_not_awaited()


class TestSceneFinalize:
    @pytest.mark.asyncio
    async def test_finalize_closes_the_scene_without_narrating_a_turn(self, monkeypatch):
        saver = MemorySaver()
        monkeypatch.setattr(scene_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        monkeypatch.setattr(scene_loop, "_SCENE_GRAPH_TEMPLATE", None)
        calls: list[str] = []

        async def load(state):
            return {}

        async def resolve(state):
            calls.append("resolve")
            return {"resolution": {"resolution_type": "narrative"}}

        async def narrate(state):
            calls.append("narrate")
            return {"turns_count": state.turns_count + 1}

        async def complete(state):
            calls.append("complete")
            return {"scene_complete": True}

        async def empty(state):
            return {}

        monkeypatch.setattr(scene_loop, "load_context", load)
        monkeypatch.setattr(scene_loop, "resolve_action", resolve)
        monkeypatch.setattr(scene_loop, "narrate", narrate)
        monkeypatch.setattr(scene_loop, "complete_current_scene", complete)
        for name in (
            "extract_new_entities",
            "extract_memories",
            "extract_facts",
            "persist_memories_node",
            "check_consistency",
            "check_events",
            "check_foreshadowing",
            "persist_turn_artifacts",
            "canonize_checkpoint",
        ):
            monkeypatch.setattr(scene_loop, name, empty)

        loop = scene_loop.SceneLoop(scene_id=uuid4(), story_id=uuid4())
        await loop.finalize()

        assert calls == ["complete"]


class TestGroupConversation:
    @pytest.mark.asyncio
    async def test_each_npc_hears_the_replies_already_given(self, monkeypatch):
        from monitor_agents.loops import conversation_loop
        from monitor_agents.npc_voice.agent import NPCVoice
        from monitor_data.schemas.conversations import ConversationMode

        first, second = uuid4(), uuid4()
        histories: list[list[dict]] = []

        async def respond(self, **kwargs):
            histories.append(kwargs["conversation_history"])
            return {"npc_response": str(kwargs["npc_id"]), "emotional_state_after": {}}

        monkeypatch.setattr(NPCVoice, "respond_direct", respond)

        state = conversation_loop.ConversationState(
            conversation_id=uuid4(),
            universe_id=uuid4(),
            mode=ConversationMode.DIRECT,
            npc_ids=[first, second],
            current_player_input="hello",
            turns=[{"speaker_role": "player", "text": "hello"}],
        )

        result = await conversation_loop.generate_npc_responses(state)

        assert len(result["current_npc_responses"]) == 2
        # The second NPC hears the first NPC's reply.
        assert histories[1][-1]["entity_id"] == str(first)
