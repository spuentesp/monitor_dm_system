"""Regression tests: SceneLoop must actually receive a story_state so the
Narrator's arc_label/tension_score/story_premise injection (previously dead
code for real play -- see CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md Q3)
reaches live gameplay, not just unit tests of the Narrator itself.
"""

from __future__ import annotations

# Lazy import: test_chat_loops.py::test_import_errors calls
# importlib.reload on chat_loops, which replaces the module-level dict
# objects. Binding _STORY_STATES at import time would capture the orphaned
# OLD dict; reading it through chat_loops._STORY_STATES always returns the
# current canonical instance.
from monitor_ui.routers import chat_loops
from monitor_ui.routers.chat_loops import _build_story_state_dict


def test_returns_none_without_universe_id():
    assert _build_story_state_dict({}, story_id="story-1") is None


def test_returns_none_without_story_id():
    assert _build_story_state_dict({"universe_id": "u-1"}, story_id="") is None


def test_includes_story_premise_from_session():
    session = {"universe_id": "u-1", "story_premise": "A slow-burn mystery."}
    result = _build_story_state_dict(session, story_id="story-1")
    assert result is not None
    assert result["story_premise"] == "A slow-burn mystery."
    assert result["universe_id"] == "u-1"


def test_world_id_alias_when_universe_id_missing():
    session = {"world_id": "w-1", "story_premise": "Test."}
    result = _build_story_state_dict(session, story_id="story-1")
    assert result is not None
    assert result["universe_id"] == "w-1"


def test_merges_cached_story_loop_arc_data():
    """chat_loops._STORY_STATES is populated after each scene completes (existing
    Gap-4 caching) -- confirm it's picked up alongside story_premise."""
    chat_loops._STORY_STATES["story-cache-test"] = {
        "story_id": "story-cache-test",
        "universe_id": "u-1",
        "arc_label": "climax",
        "tension_score": 0.9,
    }
    try:
        session = {"universe_id": "u-1", "story_premise": "A slow-burn mystery."}
        result = _build_story_state_dict(session, story_id="story-cache-test")

        assert result["arc_label"] == "climax"
        assert result["tension_score"] == 0.9
        assert result["story_premise"] == "A slow-burn mystery."
    finally:
        chat_loops._STORY_STATES.pop("story-cache-test", None)


def test_result_round_trips_through_real_story_state_model():
    """The dict must validate as a real StoryState (SceneState's own field
    type) -- not just look right as a plain dict."""
    from monitor_agents.loops.story_loop import StoryState

    session = {
        "universe_id": "6f3b9b1a-8b1a-4b1a-8b1a-4b1a8b1a4b1a",
        "story_premise": "A heist.",
    }
    result = _build_story_state_dict(session, story_id="7f3b9b1a-8b1a-4b1a-8b1a-4b1a8b1a4b1b")
    assert result is not None
    validated = StoryState(**result)
    assert validated.story_premise == "A heist."
