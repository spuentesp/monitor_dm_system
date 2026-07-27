"""Regression tests: SceneLoop must actually receive a story_state so the
Narrator's arc_label/tension_score/story_premise injection (previously dead
code for real play -- see CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md Q3)
reaches live gameplay, not just unit tests of the Narrator itself.
"""

from __future__ import annotations

from monitor_ui.routers.chat_loops import _STORY_STATES, _build_story_state_dict


def test_returns_none_without_universe_id():
    assert _build_story_state_dict({}, story_id="story-1") is None


def test_returns_none_without_story_id():
    assert _build_story_state_dict({"universe_id": "u-1"}, story_id="") is None


def test_includes_story_premise_from_session():
    session = {"universe_id": "u-1", "story_premise": "A heist against a rival Prince."}
    result = _build_story_state_dict(session, story_id="story-1")

    assert result["story_id"] == "story-1"
    assert result["universe_id"] == "u-1"
    assert result["story_premise"] == "A heist against a rival Prince."


def test_omits_story_premise_when_unset():
    session = {"universe_id": "u-1"}
    result = _build_story_state_dict(session, story_id="story-1")

    assert "story_premise" not in result


def test_merges_cached_story_loop_arc_data():
    """_STORY_STATES is populated after each scene completes (existing
    Gap-4 caching) -- confirm it's picked up alongside story_premise."""
    _STORY_STATES["story-cache-test"] = {
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
        _STORY_STATES.pop("story-cache-test", None)


def test_result_round_trips_through_real_story_state_model():
    """The dict must validate as a real StoryState (SceneState's own field
    type) -- not just look right as a plain dict."""
    from monitor_agents.loops.story_loop import StoryState

    session = {
        "universe_id": "6f3b9b1a-8b1a-4b1a-8b1a-4b1a8b1a4b1a",
        "story_premise": "A heist.",
    }
    result = _build_story_state_dict(session, story_id="7f3b9b1a-8b1a-4b1a-8b1a-4b1a8b1a4b1b")

    state = StoryState(**result)
    assert state.story_premise == "A heist."
