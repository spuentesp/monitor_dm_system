"""
Basic workings — the campaign-level arc recap (CF-12 / G05).

The arc recap answers "where are we in this campaign?" — it spans every
scene of a story, not just the last session. Two properties matter for the
GM: it must be *persisted* (one document per story, so the prep panel can
show it without regenerating), and regenerating it must *replace* rather
than accumulate.

Use Cases: CF-12 (G05)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from monitor_agents.recap.agent import RecapAgent
from monitor_data.schemas.arc_recaps import ArcRecapDetail
from monitor_data.tools.mongodb_tools.stories import mongodb_get_arc_recap
from tests.behavior._hermetic_stack import HermeticStack


@pytest.fixture
def story() -> tuple[UUID, UUID]:
    return uuid4(), uuid4()


def _scene(story_id: UUID, universe_id: UUID, index: int) -> dict[str, Any]:
    return {
        "scene_id": str(uuid4()),
        "story_id": str(story_id),
        "universe_id": str(universe_id),
        "title": f"Scene {index}",
        "purpose": "Advance the harbour investigation.",
        "status": "completed",
        "summary": f"What happened in scene {index}.",
        "created_at": datetime(1012, 3, index, 9, 0, tzinfo=UTC),
        "updated_at": datetime(1012, 3, index, 9, 0, tzinfo=UTC),
    }


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> RecapAgent:
    """A RecapAgent with the two model calls scripted and Neo4j reads stubbed."""
    import monitor_agents.recap.agent as recap_module

    monkeypatch.setattr(recap_module, "neo4j_list_facts", lambda filters: [])
    monkeypatch.setattr(recap_module, "neo4j_list_plot_threads", lambda filters: {"threads": []})

    agent = RecapAgent()
    monkeypatch.setattr(
        agent.arc_module,
        "summarize_chunk",
        lambda **kwargs: type("P", (), {"arc_beats": "- The party reached the harbour."})(),
    )
    monkeypatch.setattr(
        agent.arc_module,
        "synthesize_campaign",
        lambda **kwargs: type(
            "P", (), {"recap_markdown": "# Campaign so far\n\nThe party reached the harbour."}
        )(),
    )
    return agent


class TestArcRecapGeneration:
    async def test_a_story_with_nothing_to_recap_returns_none(
        self, hermetic: HermeticStack, agent: RecapAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        recap = await agent.generate_arc_recap(story_id=story_id, universe_id=universe_id)

        assert recap is None
        assert hermetic.collection("arc_recaps").count_documents({}) == 0

    async def test_scenes_produce_a_campaign_recap(
        self, hermetic: HermeticStack, agent: RecapAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        hermetic.seed(
            "scenes", [_scene(story_id, universe_id, 1), _scene(story_id, universe_id, 2)]
        )

        recap = await agent.generate_arc_recap(story_id=story_id, universe_id=universe_id)

        assert recap is not None
        assert "The party reached the harbour." in recap.recap_markdown
        assert recap.scene_count == 2
        assert recap.detail is ArcRecapDetail.STANDARD


class TestArcRecapPersistence:
    async def test_the_recap_is_persisted_for_the_story(
        self, hermetic: HermeticStack, agent: RecapAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        hermetic.seed("scenes", [_scene(story_id, universe_id, 1)])

        recap = await agent.generate_arc_recap(story_id=story_id, universe_id=universe_id)

        assert recap is not None
        stored = mongodb_get_arc_recap(story_id)
        assert stored is not None
        assert stored.recap_markdown == recap.recap_markdown
        assert stored.recap_id == recap.recap_id

    async def test_regenerating_replaces_the_recap_instead_of_accumulating(
        self, hermetic: HermeticStack, agent: RecapAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        hermetic.seed("scenes", [_scene(story_id, universe_id, 1)])

        first = await agent.generate_arc_recap(story_id=story_id, universe_id=universe_id)
        second = await agent.generate_arc_recap(story_id=story_id, universe_id=universe_id)

        assert first is not None and second is not None
        # One document per story, same identity — the panel reads one recap.
        assert hermetic.collection("arc_recaps").count_documents({}) == 1
        assert first.recap_id == second.recap_id

    async def test_the_detail_level_is_carried_through(
        self, hermetic: HermeticStack, agent: RecapAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        hermetic.seed("scenes", [_scene(story_id, universe_id, 1)])

        recap = await agent.generate_arc_recap(
            story_id=story_id,
            universe_id=universe_id,
            detail=ArcRecapDetail.SHORT,
        )

        assert recap is not None
        assert recap.detail is ArcRecapDetail.SHORT

    async def test_an_unknown_detail_level_is_refused(
        self, hermetic: HermeticStack, agent: RecapAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        with pytest.raises(ValueError, match="detail must be one of"):
            await agent.generate_arc_recap(
                story_id=story_id,
                universe_id=universe_id,
                detail="exhaustive",  # type: ignore[arg-type]
            )

    async def test_persist_false_leaves_the_store_alone(
        self, hermetic: HermeticStack, agent: RecapAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        hermetic.seed("scenes", [_scene(story_id, universe_id, 1)])

        recap = await agent.generate_arc_recap(
            story_id=story_id, universe_id=universe_id, persist=False
        )

        assert recap is not None
        assert hermetic.collection("arc_recaps").count_documents({}) == 0
        assert mongodb_get_arc_recap(story_id) is None
