"""
Behavior tests for pure routing functions in scene_loop.py.

Covers:
- route_after_narration: decides whether to continue or end scene
- route_after_resolve: routes to narrate vs wait for user
- _is_combat_action: detects combat keywords in user input

These are pure functions with no external dependencies, so they run
as fast unit tests.

Use Cases: P-2, P-3, P-6, P-14 (scene lifecycle / choreography)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from monitor_agents.loops.scene_loop import (
    SceneState,
    route_after_narration,
    route_after_resolve,
    _is_combat_action,
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
        state = _make_state(resolution={
            "resolution_type": "narrative",
            "success_level": "success",
        })
        result = route_after_resolve(state)
        assert result == "narrate"

    def test_dice_resolution_routes_to_narrate(self):
        """Dice resolution → narrate."""
        state = _make_state(resolution={
            "resolution_type": "dice",
            "success_level": "success",
            "roll_total": 18,
        })
        result = route_after_resolve(state)
        assert result == "narrate"

    def test_forced_narrative_pushback_routes_to_end(self):
        """Forced narrative pushback means we wait for user choice → END."""
        state = _make_state(resolution={
            "resolution_type": "forced_narrative_pushback",
            "forced_narrative": True,
        })
        result = route_after_resolve(state)
        assert result in ("END", "__end__")

    def test_empty_resolution_dict_routes_to_narrate(self):
        """Empty resolution dict (no resolution_type key) → narrate."""
        state = _make_state(resolution={})
        result = route_after_resolve(state)
        assert result == "narrate"


# =============================================================================
# _is_combat_action
# =============================================================================


class TestIsCombatAction:
    """Detect combat keywords in user input."""

    @pytest.mark.parametrize(
        "text",
        [
            "I attack the orc with my sword",
            "I strike at the bandit",
            "I shoot an arrow at the goblin",
            "I stab him in the back",
            "I slash through the vines",
            "I fight the dragon",
            "I rush toward the enemy",
            "I charge the line",
            "I punch him in the face",
            "I kick open the door",
            "I swing my axe",
            "I fire my crossbow",
            "I blast them with magic",
            "We enter combat with the guards",
        ],
    )
    def test_combat_keywords_detected(self, text):
        """All combat keywords should be detected."""
        assert _is_combat_action(text) is True, f"'{text}' should be detected as combat"

    @pytest.mark.parametrize(
        "text",
        [
            "I look around the room",
            "I talk to the merchant",
            "I open the chest carefully",
            "I sneak past the guards",
            "I cast a spell to light the area",
            "I examine the ancient runes",
            "I climb the wall",
            "I sit down to rest",
            "Hello there!",
            "What's in the box?",
        ],
    )
    def test_non_combat_input_not_detected(self, text):
        """Non-combat input should not trigger combat detection."""
        assert _is_combat_action(text) is False, f"'{text}' should NOT be detected as combat"

    def test_empty_string(self):
        """Empty string is not combat."""
        assert _is_combat_action("") is False

    def test_case_insensitive(self):
        """Combat detection should be case-insensitive (verify with all-caps)."""
        assert _is_combat_action("I ATTACK THE ORC") is True

    def test_keyword_anywhere_in_text(self):
        """Keyword anywhere in the text triggers detection."""
        assert _is_combat_action("While walking, I decide to attack the guard") is True


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

        now = datetime.now(timezone.utc)
        state2 = SceneState(scene_id=uuid4(), story_id=uuid4(), time_ref=now)
        assert state2.time_ref == now
