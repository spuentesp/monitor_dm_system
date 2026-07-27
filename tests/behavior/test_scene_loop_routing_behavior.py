"""
Behavior tests for pure routing functions in scene_loop.py.

Covers:
- route_after_narration: decides whether to continue or end scene
- route_after_resolve: routes to narrate vs wait for user

These are pure functions with no external dependencies, so they run
as fast unit tests.

Combat detection used to live here as a keyword-matching heuristic
(``_is_combat_action``); it was removed as part of the de-heuristic
refactor (see feedback memory: "never reintroduce keyword matching").
Combat is now detected via ``subsystem_hint``/``action_type`` from the
semantic action router (SceneLoop.run(), scene_loop.py).

Use Cases: P-2, P-3, P-6, P-14 (scene lifecycle / choreography)
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

from monitor_agents.loops.scene_loop import (
    SceneState,
    route_after_narration,
    route_after_resolve,
)


def _make_state(**overrides) -> SceneState:
    """Helper: create a SceneState with sensible defaults."""
    defaults = {
        "scene_id": uuid4(),
        "story_id": uuid4(),
        "turns_count": 1,
        "max_turns": 50,
        "scene_complete": False,
    }
    defaults.update(overrides)
    return SceneState(**defaults)


# =============================================================================
# route_after_narration
# =============================================================================


class TestRouteAfterNarration:
    """Decide whether to continue the scene or end it."""

    def test_normal_turn_ends_scene(self):
        """Mid-scene, the turn loop should end (control returns to user)."""
        state = _make_state(turns_count=5, max_turns=50, scene_complete=False)
        # In our model: route returns 'complete_current_scene' OR END
        # After persist_turn_artifacts, normal case → END (user will re-inject input)
        result = route_after_narration(state)
        # The route returns either 'complete_current_scene' or END (langgraph's END marker)
        assert result in ("complete_current_scene", "END", "__end__")

    def test_scene_complete_flag_routes_to_complete(self):
        """If scene_complete=True, route to complete_current_scene."""
        state = _make_state(scene_complete=True)
        result = route_after_narration(state)
        assert result == "complete_current_scene"

    def test_max_turns_reached_routes_to_complete(self):
        """Safety: when turns >= max, end the scene to prevent infinite loops."""
        state = _make_state(turns_count=50, max_turns=50)
        result = route_after_narration(state)
        assert result == "complete_current_scene"

    def test_max_turns_exceeded_routes_to_complete(self):
        """If turns_count goes past max, still end the scene."""
        state = _make_state(turns_count=51, max_turns=50)
        result = route_after_narration(state)
        assert result == "complete_current_scene"

    def test_scene_complete_takes_precedence_over_max_turns(self):
        """If both flags set, scene_complete wins (no special handling needed)."""
        state = _make_state(scene_complete=True, turns_count=50, max_turns=50)
        result = route_after_narration(state)
        assert result == "complete_current_scene"

    def test_turn_one_of_50_continues(self):
        """Early in the scene, we should not end."""
        state = _make_state(turns_count=1, max_turns=50, scene_complete=False)
        result = route_after_narration(state)
        # Should be END (loop ends, user re-injects next action)
        assert result in ("END", "__end__")

    def test_turn_at_49_continues(self):
        """Near the end but not yet at max, continue."""
        state = _make_state(turns_count=49, max_turns=50, scene_complete=False)
        result = route_after_narration(state)
        assert result in ("END", "__end__")


# =============================================================================
# route_after_resolve
# =============================================================================


class TestRouteAfterResolve:
    """Decide whether to narrate or wait for user choice after resolve."""

    def test_no_resolution_routes_to_narrate(self):
        """If resolver produced no resolution, fall through to narrate."""
        state = _make_state(resolution=None)
        result = route_after_resolve(state)
        assert result == "narrate"

    def test_normal_resolution_routes_to_narrate(self):
        """Standard resolution → narrate."""
        state = _make_state(
            resolution={
                "resolution_type": "narrative",
                "success_level": "success",
            }
        )
        result = route_after_resolve(state)
        assert result == "narrate"

    def test_dice_resolution_routes_to_narrate(self):
        """Dice resolution → narrate."""
        state = _make_state(
            resolution={
                "resolution_type": "dice",
                "success_level": "success",
                "roll_total": 18,
            }
        )
        result = route_after_resolve(state)
        assert result == "narrate"

    def test_forced_narrative_pushback_routes_to_end(self):
        """Forced narrative pushback means we wait for user choice → END."""
        state = _make_state(
            resolution={
                "resolution_type": "forced_narrative_pushback",
                "forced_narrative": True,
            }
        )
        result = route_after_resolve(state)
        assert result in ("END", "__end__")

    def test_empty_resolution_dict_routes_to_narrate(self):
        """Empty resolution dict (no resolution_type key) → narrate."""
        state = _make_state(resolution={})
        result = route_after_resolve(state)
        assert result == "narrate"


# =============================================================================
# SceneState Schema
# =============================================================================


class TestSceneStateSchema:
    """SceneState Pydantic model has expected defaults and fields."""

    def test_minimal_state(self):
        """Only scene_id and story_id are required."""
        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert state.turns_count == 0
        assert state.max_turns == 50
        assert state.scene_complete is False
        assert state.temporal_mode == "present"
        assert state.session_tone == "dramatic"

    def test_temporal_modes(self):
        """Temporal mode can be 'present', 'past', 'flashback' (P-14)."""
        for mode in ("present", "past", "flashback"):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                temporal_mode=mode,
            )
            assert state.temporal_mode == mode

    def test_tone_profiles(self):
        """Tone profiles match the Narrator's available tones."""
        for tone in ("dramatic", "grim", "horror", "heroic", "mystery", "adventure"):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                session_tone=tone,
            )
            assert state.session_tone == tone

    def test_play_modes(self):
        """Play modes are 'narrative', 'dice_standard', or 'dice_game_system'."""
        for mode in ("narrative", "dice_standard", "dice_game_system"):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                play_mode=mode,
            )
            assert state.play_mode == mode

    def test_roll_modes(self):
        """Roll modes are 'normal', 'advantage', or 'disadvantage'."""
        for mode in ("normal", "advantage", "disadvantage"):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                roll_mode=mode,
            )
            assert state.roll_mode == mode

    def test_time_ref_default_none(self):
        """time_ref is None by default but accepts datetime."""
        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert state.time_ref is None

        now = datetime.now(UTC)
        state2 = SceneState(scene_id=uuid4(), story_id=uuid4(), time_ref=now)
        assert state2.time_ref == now
