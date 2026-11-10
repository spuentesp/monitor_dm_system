"""
Tests for the story arc contract: a story spans several scenes and ends
when its arc resolves.

The arc is judged from what happened — the story's ledger and its plot
threads — not from a counter of scenes. The scene budget stays an upper
bound: it can end a story, but it never starts one.

These tests pin that the arc follows the model's reading of the ledger, that
the budget is a ceiling, and that the story's progress survives a restart.

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_story_arc_contract.py -v
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver

from monitor_agents.loops import scene_loop, story_loop


@contextmanager
def _saver_context(saver):
    yield saver


@pytest.fixture
def arc_judge(monkeypatch):
    """Stub the arc judge so the contract runs on its own.

    The judge answers with the phase the ledger says the story is in; the
    tests drive that answer to pin the contract around it.
    """
    from monitor_agents.story.agent import StoryAgent
    from monitor_agents.story.story import StoryArcModule

    answers: list[SimpleNamespace] = []

    def forward(self, **kwargs):
        return answers.pop(0) if answers else _verdict("rising_action", 0.4)

    monkeypatch.setattr(StoryArcModule, "forward", forward)
    monkeypatch.setattr(
        StoryAgent,
        "_plan_next_scene",
        AsyncMock(return_value={"next_scene_type": "exploration", "plot_hook": "a hook"}),
    )
    # The plot threads live in Neo4j; the contract here is about the arc.
    monkeypatch.setattr(StoryAgent, "_fetch_plot_threads", AsyncMock(return_value=[]))
    return answers


def _verdict(phase: str, tension: float, *, complete: bool = False, **threads) -> SimpleNamespace:
    return SimpleNamespace(
        arc_phase=phase,
        tension=tension,
        advanced_threads=json.dumps(threads.get("advanced", [])),
        closed_threads=json.dumps(threads.get("closed", [])),
        story_complete=complete,
        reasoning="because",
    )


async def _arc_labels(
    answers: list[SimpleNamespace],
    *,
    budget: int = 5,
    rounds: int | None = None,
) -> list[tuple[str, bool]]:
    """Run the real arc evaluation over a whole story and collect its labels.

    Each round stands for one finished scene: the story counts the scene
    before the arc looks at it, exactly as ``complete_current_scene`` does.
    """
    from monitor_agents.story.agent import StoryAgent

    agent = StoryAgent(agent_id="arc-contract")
    state = story_loop.StoryState(story_id=uuid4(), universe_id=uuid4(), scene_budget=budget)
    labels: list[tuple[str, bool]] = []
    for _ in range(rounds if rounds is not None else budget):
        state = state.model_copy(update={"scenes_completed": state.scenes_completed + 1})
        update = await agent.evaluate_arc(state)
        state = state.model_copy(update=update)
        labels.append((update["arc_label"], update["story_complete"]))
    return labels


class TestArcContract:
    @pytest.mark.asyncio
    async def test_the_arc_follows_the_judges_reading(self, arc_judge):
        """The phase is the one the ledger earned, not one the count implies."""
        arc_judge.extend(
            [
                _verdict("rising_action", 0.4),
                _verdict("climax", 0.9),
                _verdict("falling_action", 0.6),
                _verdict("resolution", 0.3, complete=True),
            ]
        )

        labels = await _arc_labels(arc_judge, rounds=4)

        assert [label for label, _ in labels] == [
            "rising_action",
            "climax",
            "falling_action",
            "resolution",
        ]
        assert labels[-1][1] is True

    @pytest.mark.asyncio
    async def test_a_story_that_resolves_early_ends(self, arc_judge):
        """A story whose conflict is resolved does not keep playing."""
        arc_judge.extend([_verdict("resolution", 0.2, complete=True)])

        labels = await _arc_labels(arc_judge, budget=8)

        assert labels[0] == ("resolution", True)

    @pytest.mark.asyncio
    async def test_two_stories_with_different_ledgers_differ(self, arc_judge):
        """The same scene count can lead to different arcs."""
        arc_judge.extend([_verdict("climax", 0.8), _verdict("falling_action", 0.5)])

        labels = await _arc_labels(arc_judge, rounds=2)

        assert [label for label, _ in labels] == ["climax", "falling_action"]

    @pytest.mark.asyncio
    async def test_the_budget_ends_a_story_that_would_go_on(self, arc_judge):
        """The budget is a ceiling, not the driver."""
        arc_judge.extend([_verdict("rising_action", 0.4) for _ in range(5)])

        labels = await _arc_labels(arc_judge, budget=3)

        assert labels[-1] == ("resolution", True)

    @pytest.mark.asyncio
    async def test_tension_never_leaves_the_scale(self, arc_judge):
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

        assert all(0.0 <= tension <= 1.0 for tension in tensions)

    @pytest.mark.asyncio
    async def test_the_story_invents_no_threads_of_its_own(self, arc_judge):
        """The story's threads are the ones recorded in Neo4j."""
        from monitor_agents.story.agent import StoryAgent

        agent = StoryAgent(agent_id="arc-threads")
        update = await agent.evaluate_arc(story_loop.StoryState(story_id=uuid4(), universe_id=uuid4()))

        assert update["active_threads"] == []
        assert update["completed_threads"] == []


class TestStoryProgression:
    @pytest.mark.asyncio
    async def test_finishing_a_scene_advances_the_story_without_ending_it(self, monkeypatch, arc_judge):
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        monkeypatch.setattr(story_loop, "simulate_world_advance", AsyncMock(return_value={}))
        monkeypatch.setattr(
            story_loop.StoryLoop,
            "_write_ledger_entry",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            story_loop.StoryLoop,
            "_seed_in_game_time",
            AsyncMock(side_effect=lambda state: state),
        )
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
    async def test_story_progress_survives_a_restart(self, monkeypatch, arc_judge):
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        monkeypatch.setattr(story_loop, "simulate_world_advance", AsyncMock(return_value={}))
        monkeypatch.setattr(
            story_loop.StoryLoop,
            "_write_ledger_entry",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            story_loop.StoryLoop,
            "_seed_in_game_time",
            AsyncMock(side_effect=lambda state: state),
        )
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
    async def test_a_story_asked_to_end_ends_at_once(self, monkeypatch, arc_judge):
        saver = MemorySaver()
        monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
        finalize = AsyncMock()
        monkeypatch.setattr(story_loop, "finalize_story", finalize)

        loop = story_loop.StoryLoop(uuid4(), uuid4())

        result = await loop.complete_current_scene(uuid4(), {"story_complete": True})

        assert result["story_complete"] is True
        finalize.assert_awaited_once()


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
