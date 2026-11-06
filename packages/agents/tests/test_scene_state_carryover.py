"""Scene state must carry across SceneLoop.run calls.

Each turn is a separate graph run against the same checkpoint thread. These
tests use the real graph and a real in-memory checkpointer; only the agents
and storage behind the nodes are stubbed.
"""

from __future__ import annotations

import contextlib
import types
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from monitor_agents.loops import scene_loop as sl
from monitor_agents.loops import scene_orchestrator as so


class _World:
    """Stub agents that record what the graph hands them."""

    def __init__(self) -> None:
        self.turn = 0
        self.resolutions: list[dict[str, Any]] = []
        self.pending_rolls: list[Any] = []
        self.narrated: list[Any] = []
        self.canon_batches: list[list[str]] = []
        self.facts_seen: list[list[str]] = []
        self.end_scene_calls = 0

    # --- factory ---
    def create_resolver(self) -> Any:
        return types.SimpleNamespace(resolve_turn=self._resolve)

    def create_narrator(self) -> Any:
        return types.SimpleNamespace(narrate_turn=self._narrate)

    def create_extractor(self) -> Any:
        return types.SimpleNamespace(
            extract_new_entities=AsyncMock(return_value={}),
            extract_memories=AsyncMock(return_value={"memories_to_persist": []}),
            extract_facts=self._extract_facts,
        )

    def create_world_rules(self) -> Any:
        return types.SimpleNamespace(
            check_consistency=AsyncMock(return_value={}),
            check_events=AsyncMock(return_value={}),
        )

    def create_canonkeeper(self) -> Any:
        return types.SimpleNamespace(evaluate_proposals=self._evaluate, end_scene=self._end_scene)

    def create_context_assembly(self) -> Any:
        return types.SimpleNamespace(
            assemble=AsyncMock(return_value={"entities": [], "turns": []}),
            check_and_compress_if_needed=AsyncMock(side_effect=lambda ctx, player_action="": ctx),
        )

    # --- behaviours ---
    async def _resolve(self, **kwargs: Any) -> tuple[dict[str, Any], None]:
        self.pending_rolls.append(kwargs["context"]["pending_roll"])
        resolution = self.resolutions.pop(0) if self.resolutions else {"resolution_type": "narrative"}
        return {"proposals": [], **resolution}, None

    async def _narrate(self, **kwargs: Any) -> dict[str, Any]:
        self.turn += 1
        self.narrated.append(kwargs["user_input"])
        return {
            "narrative_text": f"prose {self.turn}",
            "turn_id": str(uuid4()),
            "minutes_elapsed": 10,
            "proposals": [{"change_type": "fact", "content": {"statement": f"fact {self.turn}"}}],
        }

    async def _extract_facts(self, **kwargs: Any) -> dict[str, Any]:
        facts = list(kwargs["established_facts"])
        self.facts_seen.append(facts)
        return {"established_facts": [*facts, f"extracted {self.turn}"]}

    async def _evaluate(self, scene_id: Any, proposals: list[dict[str, Any]]) -> None:
        self.canon_batches.append([p["content"]["statement"] for p in proposals])

    async def _end_scene(self, **_kwargs: Any) -> dict[str, Any]:
        self.end_scene_calls += 1
        return {}


async def _fake_read(fn: Any, *_args: Any, **_kwargs: Any) -> Any:
    name = getattr(fn, "__name__", "")
    if name == "mongodb_get_scene":
        return types.SimpleNamespace(universe_id=uuid4(), temporal_mode="present", time_ref=None)
    if name == "mongodb_create_resolution":
        return types.SimpleNamespace(id=uuid4())
    return []


@pytest.fixture
def world():
    saver = InMemorySaver()
    state = _World()

    @contextlib.contextmanager
    def conn(_uri: str):
        yield saver

    with (
        patch.object(sl.MongoDBSaver, "from_conn_string", conn),
        patch.object(sl, "get_agent_factory", lambda: state),
        patch("monitor_agents.agent_factory.get_agent_factory", lambda: state),
        patch("monitor_agents.utils.db_readers.run_sync_read", _fake_read),
        patch.object(sl.PersistenceService, "clear_scene_runtime_cache", lambda *_a, **_k: None),
        patch.object(sl.PersistenceService, "persist_working_state", AsyncMock(return_value={})),
        patch("monitor_agents.foreshadowing.agent.ForeshadowingAgent.propose", AsyncMock(return_value={})),
        patch.object(sl, "seed_npc_profiles_for_accepted_proposals", AsyncMock(return_value=0)),
    ):
        yield state


def _loop(**kwargs: Any) -> sl.SceneLoop:
    return sl.SceneLoop(scene_id=uuid4(), story_id=uuid4(), universe_id=uuid4(), **kwargs)


@pytest.mark.asyncio
async def test_counters_and_proposals_accumulate(world: _World) -> None:
    loop = _loop()
    results = [await loop.run(f"action {i}") for i in range(3)]

    assert [r["turns_count"] for r in results] == [1, 2, 3]
    assert [r["total_minutes_passed"] for r in results] == [10, 20, 30]
    assert len(results[-1]["pending_proposals"]) == 3


@pytest.mark.asyncio
async def test_per_turn_output_does_not_leak_into_the_next_turn(world: _World) -> None:
    loop = _loop()
    world.resolutions = [
        {"resolution_type": "dice", "stat": "STR"},
        {"resolution_type": "forced_narrative_pushback"},
    ]
    await loop.run("first")
    second = await loop.run("second")

    # The pushback run stops before narrate, so nothing from turn one may remain.
    assert second["narrative_text"] is None
    assert second["turn_id"] is None
    assert second["resolution"]["resolution_type"] == "forced_narrative_pushback"


@pytest.mark.asyncio
async def test_extracted_facts_reach_later_turns_with_director_notes(world: _World) -> None:
    notes: list[str] = ["set in Santiago"]
    loop = _loop(director_notes=notes)
    await loop.run("first")
    notes.append("it is raining")  # recorded out of character between turns
    await loop.run("second")

    assert world.facts_seen[0] == ["set in Santiago"]
    assert world.facts_seen[1] == ["set in Santiago", "it is raining", "extracted 1"]


@pytest.mark.asyncio
async def test_max_turns_completes_the_scene_with_every_proposal(world: _World) -> None:
    loop = _loop(max_turns=2)
    first = await loop.run("first")
    second = await loop.run("second")

    assert first["scene_complete"] is False
    assert second["scene_complete"] is True
    assert world.canon_batches == [["fact 1", "fact 2"]]
    assert second["pending_proposals"] == []
    assert world.end_scene_calls == 1


@pytest.mark.asyncio
async def test_finalize_canonizes_the_whole_scene_without_narrating(world: _World) -> None:
    loop = _loop()
    await loop.run("first")
    await loop.run("second")
    await loop.finalize()

    assert world.narrated == ["first", "second"]
    assert world.canon_batches == [["fact 1", "fact 2"]]
    assert world.end_scene_calls == 1


@pytest.mark.asyncio
async def test_proposed_roll_reaches_the_next_turn_with_its_attribute(world: _World) -> None:
    loop = _loop()
    world.resolutions = [
        {
            "resolution_type": "propose_roll",
            "stat": "STR",
            "difficulty_class": 12,
            "modifier": 1,
            "attribute_value": 5,
        }
    ]
    await loop.run("I climb")
    await loop.run("I keep climbing")

    assert world.pending_rolls[0] is None
    assert world.pending_rolls[1]["stat"] == "STR"
    assert world.pending_rolls[1]["attribute_value"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kept_by", "still_pending"),
    [
        ("oracle", True),
        ("rag_lookup", True),
        ("forced_narrative_clarification", True),
        ("dice", False),
        ("forced_narrative", False),
        ("narrative", False),
        ("trivial", False),
    ],
)
async def test_pending_roll_only_survives_turns_that_do_not_settle_it(
    world: _World, kept_by: str, still_pending: bool
) -> None:
    loop = _loop()
    world.resolutions = [
        {"resolution_type": "propose_roll", "stat": "STR", "difficulty_class": 12},
        {"resolution_type": kept_by},
    ]
    await loop.run("I climb")
    result = await loop.run("next")

    assert bool(result["pending_roll"]) is still_pending


@pytest.mark.asyncio
async def test_tapped_roll_clears_the_pending_roll(world: _World) -> None:
    loop = _loop()
    world.resolutions = [{"resolution_type": "propose_roll", "stat": "STR", "difficulty_class": 12}]
    await loop.run("I climb")
    result = await loop.run("I climb", resolution_override={"resolution_type": "dice", "proposals": []})

    assert result["pending_roll"] is None
    assert result["resolution"]["resolution_type"] == "dice"


@pytest.mark.asyncio
async def test_reaching_max_turns_advances_the_story_without_ending_it() -> None:
    """A full scene moves on to the next one; it must not finalize the story."""
    next_scene = uuid4()
    outcomes: list[dict[str, Any]] = []

    class _Story:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def complete_current_scene(self, *, scene_id: Any, outcome: dict[str, Any]) -> dict[str, Any]:
            outcomes.append(outcome)
            return {"current_scene_id": next_scene}

    session: dict[str, Any] = {"id": "s", "universe_id": str(uuid4())}
    loop = types.SimpleNamespace(
        run=AsyncMock(
            return_value={"resolution": {}, "narrative_text": "End.", "scene_complete": True, "total_minutes_passed": 90}
        )
    )
    callbacks = types.SimpleNamespace(
        now_iso=lambda: "now",
        db_save_session=lambda _s: None,
        get_scene_loop=lambda *_a, **_k: loop,
        messages={},
        get_story_state=None,
    )
    state = so.SceneOrchestratorState(
        session_id="s",
        user_content="last move",
        session=session,
        callbacks=callbacks,
        story_id=str(uuid4()),
        scene_id=str(uuid4()),
    )

    with patch.object(so, "StoryLoop", _Story):
        result = await so.run_core_scene_loop(state)

    assert session["scene_id"] == str(next_scene)
    assert result.metadata["scene_transition"] is True
    assert outcomes[0]["scene_complete"] is False
    assert outcomes[0]["total_minutes_passed"] == 90
