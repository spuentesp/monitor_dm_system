"""
Basic workings — the in-fiction world clock (CF-11 / G04).

The world clock is the feature that makes "three days pass" mean something.
Its basics are deterministic and worth pinning: set the clock, hang a
deadline on it, advance time, and watch the deadline flip from *upcoming* to
*due* — with the move reported as "crossed" so the GM sees what the jump
triggered.

The clock never moves backwards and never moves twice for the same target.
Those two rules are what make the audit log trustworthy, so they are tested
here too.

Use Cases: CF-11 (G04)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from monitor_agents.gm_table import GmTableAgent, OffScreenSummary
from monitor_data.schemas.world_clock import WorldClockAdvance, WorldClockDeadlineUpsert
from monitor_data.tools.mongodb_tools.world_clock import (
    mongodb_advance_world_clock,
    mongodb_get_world_clock,
    mongodb_upsert_world_deadline,
)
from tests.behavior._hermetic_stack import HermeticStack

START = datetime(1012, 3, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def story() -> tuple[UUID, UUID]:
    return uuid4(), uuid4()


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> GmTableAgent:
    """A GmTableAgent whose off-screen tick is scripted (no model in the loop)."""

    async def _fake_llm(
        self: GmTableAgent, response_model: type, messages: list[dict[str, Any]], **kwargs: Any
    ) -> Any:
        return OffScreenSummary(
            summary="While time passed, the harbour council met without Mira.",
            npc_activities=["The harbour council met"],
        )

    monkeypatch.setattr(GmTableAgent, "call_llm_structured", _fake_llm)
    return GmTableAgent()


class TestClockBasics:
    def test_an_unset_story_has_no_clock(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        from monitor_data.schemas.world_clock import WorldClockQuery

        assert (
            mongodb_get_world_clock(WorldClockQuery(universe_id=universe_id, story_id=story_id))
            is None
        )

    def test_an_absolute_time_creates_the_clock(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        result = mongodb_advance_world_clock(
            WorldClockAdvance(
                universe_id=universe_id,
                story_id=story_id,
                target_time=START,
                display="1st of Bloomtide",
            )
        )

        assert result.initialized is True
        assert result.changed is True
        assert result.clock.current_at == START
        assert result.clock.display == "1st of Bloomtide"

    def test_a_relative_delta_before_the_first_set_is_refused(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        with pytest.raises(ValueError, match="No world clock yet"):
            mongodb_advance_world_clock(
                WorldClockAdvance(universe_id=universe_id, story_id=story_id, delta="+3 days")
            )

    def test_the_same_target_twice_is_a_no_op(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )
        again = mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )

        assert again.changed is False
        assert len(again.clock.advances) == 1

    def test_time_never_moves_backwards(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )
        with pytest.raises(ValueError, match="cannot move backwards"):
            mongodb_advance_world_clock(
                WorldClockAdvance(
                    universe_id=universe_id,
                    story_id=story_id,
                    target_time=START - timedelta(days=1),
                )
            )

    def test_every_real_advance_is_audited(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, delta="+2 days")
        )

        from monitor_data.schemas.world_clock import WorldClockQuery

        clock = mongodb_get_world_clock(WorldClockQuery(universe_id=universe_id, story_id=story_id))
        assert clock is not None
        assert len(clock.advances) == 2
        assert clock.advances[0].delta == "+2 days"
        assert clock.current_at == START + timedelta(days=2)


class TestDeadlineFlip:
    def test_a_deadline_starts_upcoming(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )
        clock = mongodb_upsert_world_deadline(
            WorldClockDeadlineUpsert(
                universe_id=universe_id,
                story_id=story_id,
                title="The tide turns",
                due_at=START + timedelta(days=5),
            )
        )

        assert len(clock.deadlines) == 1
        assert clock.deadlines[0].status == "upcoming"

    def test_advancing_past_a_deadline_flips_it_to_due(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )
        mongodb_upsert_world_deadline(
            WorldClockDeadlineUpsert(
                universe_id=universe_id,
                story_id=story_id,
                title="The tide turns",
                due_at=START + timedelta(days=5),
            )
        )

        result = mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, delta="+7 days")
        )

        assert [d.title for d in result.crossed] == ["The tide turns"]
        assert result.crossed[0].status in ("due", "overdue")
        assert [d.title for d in result.clock.deadlines if d.status in ("due", "overdue")] == [
            "The tide turns"
        ]

    def test_a_deadline_cannot_be_added_before_the_clock_exists(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        with pytest.raises(ValueError, match="No world clock yet"):
            mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="The tide turns",
                    due_at=START + timedelta(days=5),
                )
            )


class TestAdvanceAndSummarize:
    """The agent-level flow the CF-11 route drives."""

    async def test_an_advance_reports_the_deadlines_it_crossed(
        self, hermetic: HermeticStack, agent: GmTableAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )
        mongodb_upsert_world_deadline(
            WorldClockDeadlineUpsert(
                universe_id=universe_id,
                story_id=story_id,
                title="The tide turns",
                due_at=START + timedelta(days=5),
            )
        )

        outcome = await agent.advance_and_summarize(
            universe_id=universe_id, story_id=story_id, delta="+7 days"
        )

        assert outcome.changed is True
        assert [d.title for d in outcome.crossed] == ["The tide turns"]
        assert [d.title for d in outcome.due] == ["The tide turns"]
        assert outcome.clock.current_at == START + timedelta(days=7)

    async def test_the_off_screen_tick_is_generated_when_time_passed(
        self, hermetic: HermeticStack, agent: GmTableAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )
        # With canon to ground on, the tick is generated instead of falling
        # back to the deterministic one-liner.
        hermetic.override("neo4j_list_entities", {"entities": [{"id": "e1", "name": "Mira"}]})
        hermetic.override("neo4j_list_facts", {"facts": []})

        outcome = await agent.advance_and_summarize(
            universe_id=universe_id, story_id=story_id, delta="+2 days"
        )

        assert outcome.offscreen is not None
        assert "harbour council" in outcome.offscreen.summary

    async def test_the_first_advance_only_initializes(
        self, hermetic: HermeticStack, agent: GmTableAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        outcome = await agent.advance_and_summarize(
            universe_id=universe_id, story_id=story_id, target_time=START
        )

        assert outcome.initialized is True
        assert outcome.offscreen is None

    async def test_an_idempotent_advance_changes_nothing(
        self, hermetic: HermeticStack, agent: GmTableAgent, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        mongodb_advance_world_clock(
            WorldClockAdvance(universe_id=universe_id, story_id=story_id, target_time=START)
        )

        outcome = await agent.advance_and_summarize(
            universe_id=universe_id, story_id=story_id, target_time=START
        )

        assert outcome.changed is False
        assert outcome.offscreen is None
