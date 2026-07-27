"""Behavior tests for StoryLoop choreography (Phase 2-3).

Exercises pure logic only — no LLM, no DB.

Covers:
- _arc_label_to_purpose
- route_after_scene
- run_scene (passthrough)
- StoryState defaults & history tracking
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_state(**overrides) -> Any:
    from monitor_agents.loops.story_loop import StoryState

    base = {"story_id": uuid4(), "universe_id": uuid4()}
    base.update(overrides)
    return StoryState(**base)


# =============================================================================
# _arc_label_to_purpose
# =============================================================================


class TestArcLabelToPurpose:
    def test_rising_action(self):
        from monitor_agents.story.agent import StoryAgent

        assert StoryAgent()._arc_label_to_purpose("rising_action") == "Tension Building"

    def test_climax(self):
        from monitor_agents.story.agent import StoryAgent

        assert StoryAgent()._arc_label_to_purpose("climax") == "Climactic Confrontation"

    def test_falling_action(self):
        from monitor_agents.story.agent import StoryAgent

        assert StoryAgent()._arc_label_to_purpose("falling_action") == "Aftermath"

    def test_resolution(self):
        from monitor_agents.story.agent import StoryAgent

        assert StoryAgent()._arc_label_to_purpose("resolution") == "Resolution"

    def test_new_thread(self):
        from monitor_agents.story.agent import StoryAgent

        assert StoryAgent()._arc_label_to_purpose("new_thread") == "New Development"

    def test_unknown_label_falls_back(self):
        from monitor_agents.story.agent import StoryAgent

        assert StoryAgent()._arc_label_to_purpose("totally_made_up") == "Story Continues"

    def test_empty_string_falls_back(self):
        from monitor_agents.story.agent import StoryAgent

        assert StoryAgent()._arc_label_to_purpose("") == "Story Continues"


# =============================================================================
# route_after_scene
# =============================================================================


class TestRouteAfterScene:
    def test_complete_routes_to_finalize(self):
        from monitor_agents.loops.story_loop import route_after_scene

        state = _make_state(story_complete=True)
        assert route_after_scene(state) == "finalize"

    def test_incomplete_routes_to_transition(self):
        from monitor_agents.loops.story_loop import route_after_scene

        state = _make_state(story_complete=False)
        assert route_after_scene(state) == "transition"

    def test_default_state_incomplete(self):
        from monitor_agents.loops.story_loop import route_after_scene

        state = _make_state()
        # Default: story_complete=False
        assert route_after_scene(state) == "transition"


# =============================================================================
# run_scene (passthrough)
# =============================================================================


class TestRunScene:
    def test_returns_completed_count(self):
        from monitor_agents.loops.story_loop import run_scene

        state = _make_state(scenes_completed=3, scenes_history=[{"scene_index": 2}])
        result = asyncio.run(run_scene(state))
        assert result["scenes_completed"] == 3
        assert result["scenes_history"] == [{"scene_index": 2}]

    def test_default_zero(self):
        from monitor_agents.loops.story_loop import run_scene

        state = _make_state()
        result = asyncio.run(run_scene(state))
        assert result["scenes_completed"] == 0
        assert result["scenes_history"] == []


# =============================================================================
# StoryState defaults
# =============================================================================


class TestStoryStateDefaults:
    def test_minimal_construct(self):
        from monitor_agents.loops.story_loop import StoryState

        sid = uuid4()
        uid = uuid4()
        state = StoryState(story_id=sid, universe_id=uid)

        assert state.story_id == sid
        assert state.universe_id == uid
        assert state.world_ticks == 0
        assert state.last_scene_duration_minutes == 0
        assert state.world_tone == "dramatic"
        assert state.story_outline is None
        assert state.scenes == []
        assert state.current_scene_id is None
        assert state.scenes_completed == 0
        assert state.story_complete is False
        assert state.arc_label == "rising_action"
        assert state.tension_score == 0.3
        assert state.active_threads == []
        assert state.completed_threads == []
        assert state.next_scene_type is None
        assert state.scene_hook is None
        assert state.scenes_history == []

    def test_in_game_time_default(self):
        from monitor_agents.loops.story_loop import StoryState

        state = StoryState(story_id=uuid4(), universe_id=uuid4())
        # Default factory: datetime(1000, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert state.in_game_time.year == 1000
        assert state.in_game_time.month == 1
        assert state.in_game_time.day == 1
        assert state.in_game_time.hour == 12

    def test_tension_score_bounds(self):
        from monitor_agents.loops.story_loop import StoryState
        from pydantic import ValidationError

        sid = uuid4()
        uid = uuid4()
        # Below 0
        with pytest.raises(ValidationError):
            StoryState(story_id=sid, universe_id=uid, tension_score=-0.1)
        # Above 1
        with pytest.raises(ValidationError):
            StoryState(story_id=sid, universe_id=uid, tension_score=1.1)
        # At bounds OK
        s1 = StoryState(story_id=sid, universe_id=uid, tension_score=0.0)
        s2 = StoryState(story_id=sid, universe_id=uid, tension_score=1.0)
        assert s1.tension_score == 0.0
        assert s2.tension_score == 1.0


# =============================================================================
# _create_scene (pure-side; mocks DB readers)
# =============================================================================


class TestCreateScene:
    def test_builds_scene_params(self, monkeypatch):
        from monitor_agents.loops import story_loop

        captured = {}

        async def fake_run_sync_read(fn, *args, **kwargs):
            captured["called"] = True
            captured["fn"] = fn
            captured["args"] = args
            return {"scene_id": uuid4()}

        monkeypatch.setattr(story_loop, "run_sync_read", fake_run_sync_read)
        monkeypatch.setattr(story_loop, "mongodb_create_scene", lambda *a, **k: None)

        scene_id = asyncio.run(
            story_loop._create_scene(
                story_id=uuid4(), universe_id=uuid4(), order=2, purpose="Test purpose"
            )
        )
        assert isinstance(scene_id, type(uuid4()))  # UUID instance
        assert captured["called"] is True

    def test_string_temporal_mode(self, monkeypatch):
        from monitor_agents.loops import story_loop

        captured_params = {}

        async def fake_run_sync_read(fn, *args, **kwargs):
            # Capture the SceneCreate params
            captured_params["params"] = args[0] if args else None
            return {"scene_id": uuid4()}

        monkeypatch.setattr(story_loop, "run_sync_read", fake_run_sync_read)

        scene_id = asyncio.run(
            story_loop._create_scene(
                story_id=uuid4(),
                universe_id=uuid4(),
                order=0,
                temporal_mode="present",
                purpose="Test",
                time_description="Now",
            )
        )
        assert scene_id is not None


# =============================================================================
# _load_story_outline (delegates to run_sync_read)
# =============================================================================


class TestLoadStoryOutline:
    def test_returns_none_when_missing(self, monkeypatch):
        from monitor_agents.loops import story_loop

        async def fake_run_sync_read(fn, *args, **kwargs):
            return None

        monkeypatch.setattr(story_loop, "run_sync_read", fake_run_sync_read)
        monkeypatch.setattr(
            story_loop, "mongodb_get_story_outline", lambda *a, **k: None
        )

        result = asyncio.run(story_loop._load_story_outline(uuid4()))
        assert result is None

    def test_returns_dict_when_present(self, monkeypatch):
        from monitor_agents.loops import story_loop

        expected = {"story_id": str(uuid4()), "theme": "epic"}

        async def fake_run_sync_read(fn, *args, **kwargs):
            return expected

        monkeypatch.setattr(story_loop, "run_sync_read", fake_run_sync_read)
        monkeypatch.setattr(
            story_loop, "mongodb_get_story_outline", lambda *a, **k: None
        )

        result = asyncio.run(story_loop._load_story_outline(uuid4()))
        assert result == expected
