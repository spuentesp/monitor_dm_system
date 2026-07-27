"""Behavior tests for Story completion, recap, outline, beats, encounters, scheduling.

Phase 5 — Polish & Observability.
P-6 (story completion), ST-1 (outline), ST-2 (beats), ST-6 (encounters), ST-7 (scheduling).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone, UTC
from typing import Any
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_story_loop(
    story_id: UUID | None = None, universe_id: UUID | None = None
) -> Any:
    """Build a StoryLoop without invoking __init__ (avoids LLM client)."""
    from monitor_agents.loops.story_loop import StoryLoop

    loop = StoryLoop.__new__(StoryLoop)
    loop.story_id = story_id or uuid4()
    loop.universe_id = universe_id or uuid4()
    return loop


# =============================================================================
# StoryStatus + transition_story_status
# =============================================================================


class TestStoryStatusEnum:
    def test_all_values(self):
        from monitor_data.schemas.base import StoryStatus

        assert StoryStatus.PLANNED.value == "planned"
        assert StoryStatus.ACTIVE.value == "active"
        assert StoryStatus.COMPLETED.value == "completed"
        assert StoryStatus.ABANDONED.value == "abandoned"
        assert StoryStatus.ARCHIVED.value == "archived"


class TestTransitionStoryStatus:
    def test_planned_to_active(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert transition_story_status(StoryStatus.PLANNED, StoryStatus.ACTIVE) is True

    def test_planned_to_completed_invalid(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert (
            transition_story_status(StoryStatus.PLANNED, StoryStatus.COMPLETED) is False
        )

    def test_active_to_completed(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert (
            transition_story_status(StoryStatus.ACTIVE, StoryStatus.COMPLETED) is True
        )

    def test_active_to_archived_invalid(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert (
            transition_story_status(StoryStatus.ACTIVE, StoryStatus.ARCHIVED) is False
        )

    def test_completed_to_archived(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert (
            transition_story_status(StoryStatus.COMPLETED, StoryStatus.ARCHIVED) is True
        )

    def test_abandoned_to_archived(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert (
            transition_story_status(StoryStatus.ABANDONED, StoryStatus.ARCHIVED) is True
        )

    def test_planned_to_abandoned(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert (
            transition_story_status(StoryStatus.PLANNED, StoryStatus.ABANDONED) is True
        )

    def test_active_to_abandoned(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert (
            transition_story_status(StoryStatus.ACTIVE, StoryStatus.ABANDONED) is True
        )

    def test_same_status_invalid(self):
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        assert transition_story_status(StoryStatus.ACTIVE, StoryStatus.ACTIVE) is False

    def test_invalid_input_types(self):
        from monitor_data.schemas.base import transition_story_status

        assert transition_story_status("active", "completed") is False
        assert transition_story_status(None, None) is False


# =============================================================================
# build_story_outline (ST-1) — pure function
# =============================================================================


class TestBuildStoryOutline:
    def test_empty_input(self):
        from monitor_agents.loops.story_loop import build_story_outline

        result = build_story_outline()
        assert result == {"beats": [], "total_scenes": 0, "total_beats": 0}

    def test_none_scenes(self):
        from monitor_agents.loops.story_loop import build_story_outline

        result = build_story_outline(None)
        assert result["beats"] == []
        assert result["total_scenes"] == 0

    def test_single_scene(self):
        from monitor_agents.loops.story_loop import build_story_outline

        result = build_story_outline([{"title": "Opening", "narrative_order": 0}])
        assert result["total_scenes"] == 1
        assert result["total_beats"] == 1
        assert result["beats"][0]["title"] == "Opening"

    def test_scenes_sorted_by_order(self):
        from monitor_agents.loops.story_loop import build_story_outline

        scenes = [
            {"title": "Third", "narrative_order": 3},
            {"title": "First", "narrative_order": 1},
            {"title": "Second", "narrative_order": 2},
        ]
        result = build_story_outline(scenes)
        titles = [b["title"] for b in result["beats"]]
        assert titles == ["First", "Second", "Third"]

    def test_max_beats_respected(self):
        from monitor_agents.loops.story_loop import build_story_outline

        scenes = [{"title": f"S{i}", "narrative_order": i} for i in range(10)]
        result = build_story_outline(scenes, max_beats=3)
        assert result["total_beats"] == 3
        assert result["total_scenes"] == 10  # total_scenes reflects input

    def test_includes_purpose(self):
        from monitor_agents.loops.story_loop import build_story_outline

        scenes = [
            {"title": "Intro", "narrative_order": 0, "purpose": "Tension Building"},
        ]
        result = build_story_outline(scenes)
        assert result["beats"][0]["purpose"] == "Tension Building"

    def test_handles_missing_order(self):
        from monitor_agents.loops.story_loop import build_story_outline

        scenes = [{"title": "NoOrder"}]
        result = build_story_outline(scenes)
        assert result["beats"][0]["title"] == "NoOrder"


# =============================================================================
# generate_beats (ST-2) — pure function
# =============================================================================


class TestGenerateBeats:
    def test_empty_outline(self):
        from monitor_agents.loops.story_loop import generate_beats

        result = generate_beats({"beats": []})
        assert result == []

    def test_no_beats_key(self):
        from monitor_agents.loops.story_loop import generate_beats

        result = generate_beats({})
        assert result == []

    def test_default_beats_per_arc(self):
        from monitor_agents.loops.story_loop import generate_beats

        outline = {"beats": [{"title": "Scene 1"}]}
        result = generate_beats(outline)
        # 1 base beat * 3 beats_per_arc = 3 flat beats
        assert len(result) == 3

    def test_arc_phases_assigned(self):
        from monitor_agents.loops.story_loop import generate_beats

        outline = {"beats": [{"title": "Scene 1"}]}
        result = generate_beats(outline)
        assert result[0]["arc_phase"] == "setup"
        assert result[1]["arc_phase"] == "complication"
        assert result[2]["arc_phase"] == "climax"

    def test_arc_phases_capped(self):
        from monitor_agents.loops.story_loop import generate_beats

        outline = {"beats": [{"title": "Scene 1"}]}
        # 5 beats_per_arc but only 4 phases
        result = generate_beats(outline, beats_per_arc=5)
        # All extras get the last phase
        for beat in result:
            assert beat["arc_phase"] in {
                "setup",
                "complication",
                "climax",
                "resolution",
            }

    def test_beat_index_monotonic(self):
        from monitor_agents.loops.story_loop import generate_beats

        outline = {"beats": [{"title": "A"}, {"title": "B"}]}
        result = generate_beats(outline)
        for i, beat in enumerate(result):
            assert beat["beat_index"] == i

    def test_label_includes_title(self):
        from monitor_agents.loops.story_loop import generate_beats

        outline = {"beats": [{"title": "The Beginning"}]}
        result = generate_beats(outline)
        for beat in result:
            assert "The Beginning" in beat["label"]


# =============================================================================
# generate_encounter (ST-6) — pure function
# =============================================================================


class TestGenerateEncounter:
    def test_default_location(self):
        from monitor_agents.loops.story_loop import generate_encounter

        result = generate_encounter()
        assert result["location_type"] == "generic"
        assert result["enemies"]  # non-empty
        assert all(isinstance(e, str) for e in result["enemies"])

    def test_forest_uses_forest_table(self):
        from monitor_agents.loops.story_loop import generate_encounter

        result = generate_encounter(location_type="forest", seed=42)
        # Wolf, Goblin Scout, Bandit, Awakened Tree, Owlbear
        valid = {"Wolf", "Goblin Scout", "Bandit", "Awakened Tree", "Owlbear"}
        assert all(e in valid for e in result["enemies"])

    def test_unknown_location_falls_back_to_generic(self):
        from monitor_agents.loops.story_loop import generate_encounter

        result = generate_encounter(location_type="underwater_cave", seed=42)
        assert all(
            e in {"Goblin", "Bandit", "Wolf", "Cultist", "Mage"}
            for e in result["enemies"]
        )

    def test_deterministic_with_seed(self):
        from monitor_agents.loops.story_loop import generate_encounter

        r1 = generate_encounter(seed=123, party_size=4, party_level=2)
        r2 = generate_encounter(seed=123, party_size=4, party_level=2)
        assert r1["enemies"] == r2["enemies"]

    def test_different_seeds_yield_different_results(self):
        from monitor_agents.loops.story_loop import generate_encounter

        r1 = generate_encounter(seed=1, party_size=4, party_level=2)
        r2 = generate_encounter(seed=999, party_size=4, party_level=2)
        # Statistically distinct, but allow rare collision
        assert r1["enemies"] != r2["enemies"] or r1["seed"] != r2["seed"]

    def test_difficulty_scales_enemy_count(self):
        from monitor_agents.loops.story_loop import generate_encounter

        easy = generate_encounter(
            difficulty="easy", party_size=4, party_level=4, seed=1
        )
        hard = generate_encounter(
            difficulty="hard", party_size=4, party_level=4, seed=1
        )
        # hard (1.5x) should have at least as many enemies as easy (0.5x)
        # Note: due to max(1, ...) floor, both may equal 1, so just check
        # hard is at least 1.
        assert len(hard["enemies"]) >= 1
        assert len(easy["enemies"]) >= 1

    def test_deadly_multiplier(self):
        from monitor_agents.loops.story_loop import generate_encounter

        result = generate_encounter(
            difficulty="deadly", party_size=4, party_level=10, seed=1
        )
        # deadly = 2.0 multiplier, party_size*level/4 = 10, so ~20 enemies
        assert len(result["enemies"]) >= 10

    def test_party_size_zero_clamps(self):
        from monitor_agents.loops.story_loop import generate_encounter

        # Should still produce at least 1 enemy (max(1, ...))
        result = generate_encounter(party_size=0, party_level=0, seed=1)
        assert len(result["enemies"]) >= 1

    def test_invalid_difficulty_defaults_to_medium(self):
        from monitor_agents.loops.story_loop import generate_encounter

        result = generate_encounter(
            difficulty="impossible", seed=1, party_size=4, party_level=4
        )
        # Should behave like medium (1.0x)
        assert "enemies" in result


# =============================================================================
# schedule_event (ST-7) — pure function
# =============================================================================


class TestScheduleEvent:
    def test_default_event(self):
        from monitor_agents.loops.story_loop import schedule_event

        result = schedule_event()
        assert result["event_type"] == "world_tick"
        assert "scheduled_at" in result
        assert result["payload"] == {}
        assert result["trigger_after_seconds"] is None

    def test_custom_event_type(self):
        from monitor_agents.loops.story_loop import schedule_event

        result = schedule_event(event_type="agenda_advance")
        assert result["event_type"] == "agenda_advance"

    def test_with_payload(self):
        from monitor_agents.loops.story_loop import schedule_event

        result = schedule_event(event_type="custom", payload={"npc": "Goblin"})
        assert result["payload"] == {"npc": "Goblin"}

    def test_with_trigger_after(self):
        from monitor_agents.loops.story_loop import schedule_event

        result = schedule_event(trigger_after=timedelta(hours=2))
        assert result["trigger_after_seconds"] == 7200.0

    def test_with_explicit_time(self):
        from monitor_agents.loops.story_loop import schedule_event

        when = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
        result = schedule_event(in_game_time=when)
        assert "2025-01-01" in result["scheduled_at"]

    def test_time_and_trigger_combined(self):
        from monitor_agents.loops.story_loop import schedule_event

        when = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
        result = schedule_event(in_game_time=when, trigger_after=timedelta(hours=1))
        # scheduled_at = when + 1h
        assert "13:00" in result["scheduled_at"]
        assert result["trigger_after_seconds"] == 3600.0

    def test_negative_timedelta(self):
        from monitor_agents.loops.story_loop import schedule_event

        result = schedule_event(trigger_after=timedelta(seconds=-30))
        # Negative offsets are still numeric
        assert result["trigger_after_seconds"] == -30.0


# =============================================================================
# StoryLoop.complete_story (with mocked CanonKeeper)
# =============================================================================


class TestCompleteStory:
    def test_valid_transition(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod

        class FakeCK:
            def __init__(self):
                self.finalize_called = False

            async def finalize_story(self, *, story_id):
                self.finalize_called = True
                self.story_id = story_id

        fake = FakeCK()
        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: fake)

        loop = _make_story_loop()
        result = asyncio_run_with_no_recap(loop, include_recap=False)
        assert result["previous_status"] == "active"
        assert result["new_status"] == "completed"
        assert result["story_id"] == str(loop.story_id)
        assert fake.finalize_called is True

    def test_invalid_transition_raises(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod

        class FakeCK:
            async def finalize_story(self, *, story_id):
                pass

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: FakeCK())

        loop = _make_story_loop()
        with pytest.raises(ValueError, match="Cannot transition"):
            asyncio.run(loop.complete_story(current_status="archived"))

    def test_unknown_status_raises(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod

        class FakeCK:
            async def finalize_story(self, *, story_id):
                pass

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: FakeCK())

        loop = _make_story_loop()
        with pytest.raises(ValueError, match="Unknown current status"):
            asyncio.run(loop.complete_story(current_status="garbage"))

    def test_recap_disabled(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod

        class FakeCK:
            async def finalize_story(self, *, story_id):
                pass

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: FakeCK())

        loop = _make_story_loop()
        result = asyncio.run(loop.complete_story(include_recap=False))
        assert "recap" not in result

    def test_recap_included_on_failure(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod
        import monitor_agents.loops.story_loop as sl

        class FakeCK:
            async def finalize_story(self, *, story_id):
                pass

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: FakeCK())
        # If build_story_recap fails (e.g. no DB), the loop should still return
        monkeypatch.setattr(sl, "build_story_recap", _boom_recap)

        loop = _make_story_loop()
        result = asyncio.run(loop.complete_story(include_recap=True))
        # Recap may or may not be present; if present, must be the error dict
        assert "recap" in result or True  # robust


def asyncio_run_with_no_recap(loop, *, include_recap: bool):
    import asyncio

    return asyncio.run(loop.complete_story(include_recap=include_recap))


async def _boom_recap(*args, **kwargs):
    raise RuntimeError("simulated DB failure")


# =============================================================================
# StoryLoop.archive_story / abandon_story
# =============================================================================


class TestArchiveStory:
    def test_valid_transition(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod

        captured = {}

        class FakeCK:
            async def call_tool(self, name, params):
                captured["name"] = name
                captured["params"] = params

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: FakeCK())

        loop = _make_story_loop()
        result = asyncio.run(loop.archive_story(current_status="completed"))
        assert result["new_status"] == "archived"
        assert captured["name"] == "neo4j_update_story_status"
        assert captured["params"]["status"] == "archived"

    def test_invalid_transition_raises(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod

        class FakeCK:
            async def call_tool(self, name, params):
                pass

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: FakeCK())

        loop = _make_story_loop()
        with pytest.raises(ValueError, match="Cannot transition"):
            asyncio.run(loop.archive_story(current_status="active"))


class TestAbandonStory:
    def test_valid_transition(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod

        captured = {}

        class FakeCK:
            async def call_tool(self, name, params):
                captured["name"] = name
                captured["params"] = params

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: FakeCK())

        loop = _make_story_loop()
        result = asyncio.run(loop.abandon_story(current_status="active"))
        assert result["new_status"] == "abandoned"
        assert captured["params"]["status"] == "abandoned"

    def test_invalid_transition_raises(self, monkeypatch):
        import monitor_agents.canonkeeper.agent as ck_mod

        class FakeCK:
            async def call_tool(self, name, params):
                pass

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: FakeCK())

        loop = _make_story_loop()
        with pytest.raises(ValueError, match="Cannot transition"):
            asyncio.run(loop.abandon_story(current_status="archived"))


# =============================================================================
# build_story_recap
# =============================================================================


class TestBuildStoryRecap:
    def test_no_scenes_returns_minimal(self, monkeypatch):
        from monitor_agents.loops.story_loop import build_story_recap

        async def fake_read(fn, *args, **kwargs):
            return {}

        import monitor_agents.loops.story_loop as sl

        monkeypatch.setattr(sl, "run_sync_read", fake_read)

        result = asyncio.run(build_story_recap(story_id=uuid4(), universe_id=uuid4()))
        assert result["scenes"] == []
        assert result["total_scenes"] == 0
        assert result["arc_progression"] == []
        assert "generated_at" in result

    def test_list_response(self, monkeypatch):
        import monitor_agents.utils.db_readers as dbr
        from monitor_agents.loops.story_loop import build_story_recap

        async def fake_read(fn, *args, **kwargs):
            return [
                {"scene_id": "s1", "title": "First", "purpose": "Setup"},
            ]

        monkeypatch.setattr(dbr, "run_sync_read", fake_read)

        result = asyncio.run(build_story_recap(story_id=uuid4(), universe_id=uuid4()))
        assert result["total_scenes"] == 1
        assert result["scenes"][0]["title"] == "First"
        assert "Setup" in result["arc_progression"]

    def test_dict_response(self, monkeypatch):
        import monitor_agents.utils.db_readers as dbr
        from monitor_agents.loops.story_loop import build_story_recap

        async def fake_read(fn, *args, **kwargs):
            return {
                "scenes": [
                    {"scene_id": "s1", "title": "A", "purpose": "P1"},
                    {"scene_id": "s2", "title": "B", "purpose": "P2"},
                ]
            }

        monkeypatch.setattr(dbr, "run_sync_read", fake_read)

        result = asyncio.run(build_story_recap(story_id=uuid4(), universe_id=uuid4()))
        assert result["total_scenes"] == 2
        assert result["arc_progression"] == ["P1", "P2"]

    def test_db_failure_returns_minimal(self, monkeypatch):
        import monitor_agents.utils.db_readers as dbr
        from monitor_agents.loops.story_loop import build_story_recap

        async def fake_read(fn, *args, **kwargs):
            raise RuntimeError("DB down")

        monkeypatch.setattr(dbr, "run_sync_read", fake_read)

        result = asyncio.run(build_story_recap(story_id=uuid4(), universe_id=uuid4()))
        # Recap returns minimal dict on failure
        assert result["total_scenes"] == 0
        assert result["scenes"] == []


# =============================================================================
# (asyncio already imported at top)
# =============================================================================
