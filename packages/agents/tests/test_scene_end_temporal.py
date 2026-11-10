"""
Tests for the temporal side of a scene's end (P-14, ST-1).

Two things happen when a scene closes: the scene's in-game time is stamped
on the proposals it produced, so the canon is dated in the world's own clock,
and a flashback is checked against that chronology before it is canonized.

Run:
    cd /path to/monitor_dm_system && pytest packages/agents/tests/test_scene_end_temporal.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from monitor_agents.loops import scene_loop


def _state(**overrides):
    base = {
        "scene_id": uuid4(),
        "story_id": uuid4(),
        "universe_id": uuid4(),
        "user_input": "I look around",
    }
    base.update(overrides)
    return scene_loop.SceneState(**base)


@pytest.fixture
def canonkeeper(monkeypatch):
    """A CanonKeeper that records what it was asked to do."""
    calls: list[dict] = []

    class _CanonKeeper:
        async def end_scene(self, **kwargs):
            calls.append(kwargs)

    class _Factory:
        def create_canonkeeper(self):
            return _CanonKeeper()

    monkeypatch.setattr("monitor_agents.agent_factory.get_agent_factory", lambda: _Factory())
    return calls


class TestProposalTimeStamping:
    @pytest.mark.asyncio
    async def test_the_proposals_carry_the_scenes_in_game_time(self, canonkeeper):
        """Every fact canonized from the scene is dated when it happened."""
        state = _state(
            time_ref=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
            pending_proposals=[{"proposal_type": "create_lore_fact", "content": {"statement": "The door is sealed."}}],
        )

        result = await scene_loop.complete_current_scene(state)

        stamped = result["pending_proposals"][0]
        assert stamped["time_ref"].startswith("1012-03-01T09:00")
        assert stamped["content"]["time_ref"].startswith("1012-03-01T09:00")

    @pytest.mark.asyncio
    async def test_a_proposal_with_its_own_time_keeps_it(self, canonkeeper):
        """An authored time is not overwritten by the scene's clock."""
        state = _state(
            time_ref=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
            pending_proposals=[
                {
                    "proposal_type": "create_lore_fact",
                    "content": {"statement": "The door is sealed."},
                    "time_ref": "0999-01-01T00:00:00+00:00",
                }
            ],
        )

        result = await scene_loop.complete_current_scene(state)

        assert result["pending_proposals"][0]["time_ref"] == "0999-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_a_scene_without_proposals_stamps_nothing(self, canonkeeper):
        """Nothing to date means nothing to stamp."""
        state = _state(time_ref=datetime(1012, 3, 1, 9, 0, tzinfo=UTC))

        result = await scene_loop.complete_current_scene(state)

        assert "pending_proposals" not in result


class TestFlashbackValidation:
    @pytest.mark.asyncio
    async def test_a_flashback_is_checked_before_it_is_canonized(self, monkeypatch, canonkeeper):
        """The flashback's chronology is checked against the canon."""
        from monitor_agents import temporal_validation

        seen: list[dict] = {}

        async def fake_validate(**kwargs):
            seen.update(kwargs)
            return {
                "is_valid": True,
                "can_proceed": True,
                "warnings": [{"type": "temporal", "severity": "warning", "description": "The bell rang early."}],
                "violations": [],
            }

        monkeypatch.setattr(temporal_validation, "validate_scene_revision", fake_validate)

        state = _state(
            temporal_mode="flashback",
            time_ref=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
            narrative_text="The bell rang as the party crossed the road.",
        )

        result = await scene_loop.complete_current_scene(state)

        assert seen["scene_id"] == state.scene_id
        assert seen["story_id"] == state.story_id
        assert seen["universe_id"] == state.universe_id
        assert seen["scene_time_ref"] == datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        assert "The bell rang" in seen["scene_text"]
        assert result["temporal_warnings"] == [
            {
                "type": "temporal",
                "severity": "warning",
                "description": "The bell rang early.",
            }
        ]

    @pytest.mark.asyncio
    async def test_a_present_scene_is_not_checked(self, monkeypatch, canonkeeper):
        """Only flashbacks pay for the temporal check."""
        from monitor_agents import temporal_validation

        calls: list[dict] = []

        async def fake_validate(**kwargs):
            calls.append(kwargs)
            return {"is_valid": True, "can_proceed": True, "warnings": [], "violations": []}

        monkeypatch.setattr(temporal_validation, "validate_scene_revision", fake_validate)

        state = _state(temporal_mode="present", time_ref=datetime(1012, 3, 1, 9, 0, tzinfo=UTC))

        result = await scene_loop.complete_current_scene(state)

        assert calls == []
        assert "temporal_warnings" not in result

    @pytest.mark.asyncio
    async def test_a_failed_check_does_not_cost_the_player_the_scene(self, monkeypatch, canonkeeper):
        """A check that cannot run is recorded; the scene still closes."""
        from monitor_agents import temporal_validation

        async def boom(**kwargs):
            raise RuntimeError("the canon is unreachable")

        monkeypatch.setattr(temporal_validation, "validate_scene_revision", boom)

        recorded: list[dict] = []

        class _Recorder:
            @staticmethod
            async def record(**kwargs):
                recorded.append(kwargs)

        monkeypatch.setattr(
            "monitor_agents.loops.scene_loop.RoleplayErrorRecorder",
            _Recorder,
        )

        state = _state(temporal_mode="flashback", time_ref=datetime(1012, 3, 1, 9, 0, tzinfo=UTC))

        result = await scene_loop.complete_current_scene(state)

        assert result["scene_complete"] is True
        assert len(recorded) == 1
        assert "the canon is unreachable" in str(recorded[0]["message"])
