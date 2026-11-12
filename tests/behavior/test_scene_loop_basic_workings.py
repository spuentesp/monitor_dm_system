"""
Basic workings — the core autonomous play loop.

The GM surfaces are the visible half of MONITOR; this is the engine under
them. A turn goes: the player's action is *resolved* into a mechanical
outcome, the outcome is *persisted* as a queryable record, and the scene
*ends* by advancing the story's own clock and stamping what the scene
learned with the time it happened.

The model boundary is stubbed (the resolver is injected through the
documented agent-factory seam); everything else — the state machine, the
persistence, the time stamping — is the shipped code over a mongomock
store.

Use Cases: P-2, P-3, P-6 (scene lifecycle), DL-24 (resolution records)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from monitor_agents.agent_factory import AgentFactory, set_agent_factory
from monitor_agents.loops.scene_loop import (
    SceneState,
    complete_current_scene,
    persist_turn_artifacts,
    resolve_action,
)
from monitor_agents.loops.story_loop import StoryState
from tests.behavior._hermetic_stack import HermeticStack


class _StubResolver:
    """A resolver that returns a scripted outcome (no model in the loop)."""

    def __init__(self, resolution: dict[str, Any]) -> None:
        self.resolution = resolution
        self.calls: list[dict[str, Any]] = []

    async def resolve_turn(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        self.calls.append(kwargs)
        return dict(self.resolution), {}


class _StubFactory(AgentFactory):
    """An agent factory whose resolver is the scripted one."""

    def __init__(self, resolver: _StubResolver) -> None:
        self.resolver = resolver

    def create_resolver(self, agent_id: str = "resolver-1") -> Any:
        return self.resolver

    def create_canonkeeper(self, agent_id: str = "canonkeeper-1") -> Any:
        class _Noop:
            async def end_scene(self, **kwargs: Any) -> None:
                return None

        return _Noop()

    def create_extractor(self, agent_id: str = "extractor-1") -> Any:
        class _Noop:
            async def extract_scene_memories(self, **kwargs: Any) -> dict[str, Any]:
                return {"memories_to_persist": []}

        return _Noop()


@pytest.fixture
def resolver() -> _StubResolver:
    return _StubResolver(
        {
            "resolution_type": "dice",
            "action_type": "attack",
            "success_level": "success",
            "roll_total": 14,
            "difficulty_class": 12,
            "narrative_text": "Mira swings the brass key like a blade.",
            "proposals": [
                {
                    "change_type": "fact",
                    "content": {"statement": "Mira attacked the goblin with the brass key."},
                }
            ],
        }
    )


@pytest.fixture
def factory(resolver: _StubResolver) -> Any:
    """Install the stub factory through the documented seam."""
    stub = _StubFactory(resolver)
    set_agent_factory(stub)
    try:
        yield stub
    finally:
        set_agent_factory(None)


def _state(**over: Any) -> SceneState:
    base: dict[str, Any] = {
        "scene_id": uuid4(),
        "story_id": uuid4(),
        "universe_id": uuid4(),
        "actor_id": uuid4(),
        "user_input": "I attack the goblin with the brass key.",
        "max_turns": 50,
    }
    base.update(over)
    return SceneState(**base)


class TestResolveAction:
    async def test_the_action_becomes_a_resolution(
        self, hermetic: HermeticStack, factory: Any, resolver: _StubResolver
    ) -> None:
        state = _state()

        updates = await resolve_action(state)

        assert updates["resolution"]["resolution_type"] == "dice"
        assert updates["resolution"]["roll_total"] == 14
        # The resolver was given the player's action and the scene it belongs to.
        assert resolver.calls[0]["user_input"] == state.user_input
        assert resolver.calls[0]["scene_id"] == str(state.scene_id)

    async def test_the_resolution_carries_its_proposals(
        self, hermetic: HermeticStack, factory: Any
    ) -> None:
        state = _state()

        updates = await resolve_action(state)

        assert len(updates["pending_proposals"]) == 1
        assert (
            updates["pending_proposals"][0]["content"]["statement"]
            == "Mira attacked the goblin with the brass key."
        )

    async def test_proposals_are_scoped_to_the_universe(
        self, hermetic: HermeticStack, factory: Any
    ) -> None:
        state = _state()

        updates = await resolve_action(state)

        assert updates["pending_proposals"][0]["universe_id"] == str(state.universe_id)

    async def test_a_proposed_roll_becomes_the_pending_roll(
        self, hermetic: HermeticStack, factory: Any, resolver: _StubResolver
    ) -> None:
        resolver.resolution = {
            "resolution_type": "propose_roll",
            "stat": "wits",
            "difficulty_class": 13,
            "modifier": 2,
        }
        state = _state()

        updates = await resolve_action(state)

        assert updates["pending_roll"]["stat"] == "wits"
        assert updates["pending_roll"]["action"] == state.user_input

    async def test_an_empty_action_resolves_to_nothing(
        self, hermetic: HermeticStack, factory: Any
    ) -> None:
        state = _state(user_input="")

        updates = await resolve_action(state)

        assert updates == {"resolution": None}

    async def test_a_second_turn_reuses_the_settled_resolution(
        self, hermetic: HermeticStack, factory: Any, resolver: _StubResolver
    ) -> None:
        """A submitted roll settles the offer — the resolver is not asked twice."""
        state = _state(
            resolution={
                "resolution_type": "dice",
                "roll_total": 14,
                "proposals": [{"change_type": "fact", "content": {"statement": "x"}}],
            }
        )

        updates = await resolve_action(state)

        assert resolver.calls == []
        assert len(updates["pending_proposals"]) == 1
        assert updates["pending_roll"] is None


class TestPersistTurnArtifacts:
    async def test_the_resolution_is_persisted_as_a_record(self, hermetic: HermeticStack) -> None:
        turn_id = uuid4()
        state = _state(
            turn_id=turn_id,
            resolution={
                "resolution_type": "dice",
                "action_type": "attack",
                "success_level": "success",
                "roll_total": 14,
                "difficulty_class": 12,
                "roll_detail": {"rolls": [9, 5]},
                "narrative_text": "Mira swings the brass key like a blade.",
            },
            narrative_text="Mira swings the brass key like a blade.",
        )
        hermetic.seed(
            "scenes",
            [
                {
                    "scene_id": str(state.scene_id),
                    "story_id": str(state.story_id),
                    "universe_id": str(state.universe_id),
                    "title": "The goblin",
                    "purpose": "Fight the goblin.",
                    "status": "active",
                    "turns": [
                        {
                            "turn_id": str(turn_id),
                            "speaker": "player",
                            "text": "I attack the goblin.",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ],
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
        )

        await persist_turn_artifacts(state)

        stored = list(hermetic.collection("resolutions").find({}))
        assert len(stored) == 1
        assert stored[0]["mechanics"]["roll"]["total"] == 14
        assert stored[0]["success_level"] == "success"
        assert stored[0]["action"] == state.user_input
        assert stored[0]["turn_id"] == str(turn_id)

    async def test_a_proposed_roll_is_not_persisted_as_a_record(
        self, hermetic: HermeticStack
    ) -> None:
        """The roll has not happened yet — there is nothing to record."""
        state = _state(
            turn_id=uuid4(),
            resolution={"resolution_type": "propose_roll", "stat": "wits"},
        )

        await persist_turn_artifacts(state)

        assert hermetic.collection("resolutions").count_documents({}) == 0


class TestCompleteCurrentScene:
    async def test_the_story_clock_advances_with_the_scene(
        self, hermetic: HermeticStack, factory: Any
    ) -> None:
        start = datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        story_state = StoryState(
            story_id=uuid4(),
            universe_id=uuid4(),
            in_game_time=start,
            scenes_completed=2,
        )
        state = _state(story_state=story_state, total_minutes_passed=90)

        updates = await complete_current_scene(state)

        assert updates["scene_complete"] is True
        assert updates["story_state"]["scenes_completed"] == 3
        assert updates["story_state"]["in_game_time"] == start + __import__("datetime").timedelta(
            minutes=90
        )

    async def test_the_scene_does_not_write_to_canon_itself(
        self, hermetic: HermeticStack, factory: Any
    ) -> None:
        """Scene end hands proposals to CanonKeeper — it does not commit them."""
        state = _state(
            story_state=StoryState(story_id=uuid4(), universe_id=uuid4()),
            pending_proposals=[
                {"change_type": "fact", "content": {"statement": "The door opened."}}
            ],
        )

        await complete_current_scene(state)

        assert hermetic.collection("proposed_changes").count_documents({}) == 0

    async def test_what_the_scene_learned_is_stamped_with_the_scene_time(
        self, hermetic: HermeticStack, factory: Any
    ) -> None:
        scene_time = datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        state = _state(
            time_ref=scene_time,
            pending_proposals=[
                {"change_type": "fact", "content": {"statement": "The door opened."}}
            ],
        )

        updates = await complete_current_scene(state)

        stamped = updates["pending_proposals"][0]["time_ref"]
        assert str(stamped).startswith("1012-03-01T09:00:00")
