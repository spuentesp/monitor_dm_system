"""Regression tests: SceneLoop must actually receive a story_state so the
Narrator's arc_label/tension_score/story_premise injection (previously dead
code for real play -- see CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md Q3)
reaches live gameplay, not just unit tests of the Narrator itself.

The arc itself is not cached in the web process: it lives in the story's
MongoDB checkpoint and is read on every turn by ``scene_loop.load_context``.
What the session owns -- the identifiers and the player's stated premise --
is what this module builds.
"""

from __future__ import annotations

# Lazy import: test_chat_loops.py::test_import_errors calls
# importlib.reload on chat_loops, which replaces the module-level dict
# objects. Reading them through the module keeps the current instance.
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


def test_the_story_identifiers_are_carried():
    """The scene loop needs to know which story and universe it serves."""
    session = {"universe_id": "u-1", "story_premise": "A slow-burn mystery."}
    result = _build_story_state_dict(session, story_id="story-cache-test")

    assert result["story_id"] == "story-cache-test"
    assert result["universe_id"] == "u-1"
    assert result["story_premise"] == "A slow-burn mystery."


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
