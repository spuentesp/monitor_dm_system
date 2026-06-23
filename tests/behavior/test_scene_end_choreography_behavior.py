"""Behavior tests for scene-end choreography (Phase 0.4).

Exercises the pure-logic routing and state-transition behavior of the
SceneLoop's "complete scene" path without requiring a database or
LangGraph checkpoint.

Covers:
- `route_after_narration`:
    * scene_complete=True -> "complete_current_scene"
    * turns_count >= max_turns -> "complete_current_scene" (safety)
    * otherwise -> END
- `route_after_resolve`:
    * no resolution -> "narrate"
    * resolution_type="forced_narrative_pushback" -> END
    * otherwise -> "narrate"
- `SceneState` defaults are well-formed
- `complete_current_scene` advances story_state when provided
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_state(**overrides):
    """Build a minimal SceneState for routing tests."""
    from monitor_agents.loops.scene_loop import SceneState

    base = {
        "scene_id": uuid4(),
        "story_id": uuid4(),
        "user_input": "I look around",
    }
    base.update(overrides)
    return SceneState(**base)


def _make_story_state(**overrides):
    """Build a minimal StoryState for complete_current_scene tests."""
    from monitor_agents.loops.story_loop import StoryState

    base = {
        "story_id": uuid4(),
        "universe_id": uuid4(),
    }
    base.update(overrides)
    return StoryState(**base)


# =============================================================================
# route_after_narration
# =============================================================================


class TestRouteAfterNarration:
    def test_scene_complete_routes_to_completion(self):
        from monitor_agents.loops.scene_loop import route_after_narration

        state = _make_state(scene_complete=True, turns_count=1, max_turns=10)
        assert route_after_narration(state) == "complete_current_scene"

    def test_max_turns_safety_routes_to_completion(self):
        from monitor_agents.loops.scene_loop import route_after_narration

        state = _make_state(scene_complete=False, turns_count=10, max_turns=10)
        assert route_after_narration(state) == "complete_current_scene"

    def test_max_turns_overrun_routes_to_completion(self):
        from monitor_agents.loops.scene_loop import route_after_narration

        state = _make_state(scene_complete=False, turns_count=12, max_turns=10)
        assert route_after_narration(state) == "complete_current_scene"

    def test_normal_turn_routes_to_end(self):
        from monitor_agents.loops.scene_loop import route_after_narration
        import langgraph.graph

        state = _make_state(scene_complete=False, turns_count=3, max_turns=10)
        assert route_after_narration(state) == str(langgraph.graph.END)


# =============================================================================
# route_after_resolve
# =============================================================================


class TestRouteAfterResolve:
    def test_no_resolution_routes_to_narrate(self):
        from monitor_agents.loops.scene_loop import route_after_resolve

        state = _make_state(resolution=None)
        assert route_after_resolve(state) == "narrate"

    def test_forced_narrative_pushback_routes_to_end(self):
        from monitor_agents.loops.scene_loop import route_after_resolve
        import langgraph.graph

        state = _make_state(resolution={"resolution_type": "forced_narrative_pushback"})
        assert route_after_resolve(state) == str(langgraph.graph.END)

    def test_normal_resolution_routes_to_narrate(self):
        from monitor_agents.loops.scene_loop import route_after_resolve

        state = _make_state(resolution={"resolution_type": "dice"})
        assert route_after_resolve(state) == "narrate"

    def test_narrative_resolution_routes_to_narrate(self):
        from monitor_agents.loops.scene_loop import route_after_resolve

        state = _make_state(resolution={"resolution_type": "narrative"})
        assert route_after_resolve(state) == "narrate"


# =============================================================================
# SceneState defaults
# =============================================================================


class TestSceneStateDefaults:
    def test_minimal_construction(self):
        from monitor_agents.loops.scene_loop import SceneState

        scene_id = uuid4()
        story_id = uuid4()
        s = SceneState(scene_id=scene_id, story_id=story_id, user_input="hi")
        assert s.scene_id == scene_id
        assert s.story_id == story_id
        assert s.user_input == "hi"
        assert s.scene_complete is False
        assert s.turns_count == 0
        assert s.max_turns == 50
        assert s.temporal_mode == "present"
        assert s.time_ref is None
        assert s.pending_proposals == []
        assert s.memories_to_persist == []
        assert s.working_state == {}
        assert s.scene_checkpoint == {}
        assert s.total_minutes_passed == 0
        assert s.resolution is None
        assert s.narrative_text is None

    def test_optional_fields_default_to_none(self):
        from monitor_agents.loops.scene_loop import SceneState

        s = SceneState(scene_id=uuid4(), story_id=uuid4(), user_input="x")
        assert s.universe_id is None
        assert s.actor_id is None
        assert s.actor_context is None
        assert s.gm_profile is None
        assert s.gm_profile_id is None
        assert s.system_id is None
        assert s.pack_id is None
        assert s.system_source_type is None
        assert s.system_source_id is None
        assert s.story_state is None

    def test_explicit_overrides(self):
        from monitor_agents.loops.scene_loop import SceneState

        s = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            user_input="x",
            scene_complete=True,
            turns_count=5,
            max_turns=20,
            temporal_mode="flashback",
        )
        assert s.scene_complete is True
        assert s.turns_count == 5
        assert s.max_turns == 20
        assert s.temporal_mode == "flashback"


# =============================================================================
# complete_current_scene behavior
# =============================================================================


class TestCompleteCurrentScene:
    @pytest.mark.asyncio
    async def test_no_story_state_returns_empty(self):
        from monitor_agents.loops.scene_loop import complete_current_scene

        state = _make_state(story_state=None, total_minutes_passed=10)
        result = await complete_current_scene(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_advances_in_game_time(self):
        from monitor_agents.loops.scene_loop import complete_current_scene

        original = _make_story_state(
            in_game_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        state = _make_state(
            story_state=original,
            total_minutes_passed=45,
        )
        result = await complete_current_scene(state)
        assert "story_state" in result
        updated = result["story_state"]
        # scenes_completed bumped to 1 (was 0 by default)
        assert updated["scenes_completed"] == 1
        # 45 minutes added to 12:00 -> 12:45
        expected = datetime(2026, 1, 1, 12, 45, 0, tzinfo=timezone.utc)
        actual = updated["in_game_time"]
        # Compare within a second for any microsecond drift
        diff = abs((actual - expected).total_seconds())
        assert diff < 1.0, f"in_game_time drift too large: {actual} vs {expected}"

    @pytest.mark.asyncio
    async def test_increments_scenes_completed(self):
        from monitor_agents.loops.scene_loop import complete_current_scene

        original = _make_story_state(
            in_game_time=datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc),
            scenes_completed=3,
        )
        state = _make_state(story_state=original, total_minutes_passed=0)
        result = await complete_current_scene(state)
        assert result["story_state"]["scenes_completed"] == 4

    @pytest.mark.asyncio
    async def test_no_memories_to_persist_is_safe(self):
        from monitor_agents.loops.scene_loop import complete_current_scene

        state = _make_state(
            story_state=_make_story_state(
                in_game_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            memories_to_persist=[],
            actor_id=None,
            total_minutes_passed=0,
        )
        # Should not raise even with no memories and no actor_id
        result = await complete_current_scene(state)
        assert "story_state" in result
