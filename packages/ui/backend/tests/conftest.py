"""Shared fixtures for UI backend tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_chat_loops_globals():
    """Clear chat-loop module-level caches around every test.

    Without this, mutations made by tests in `test_chat_loops.py` (which
    already has its own autouse fixture) leak across files and break
    tests in `test_scene_loop_story_state_wiring.py` and others.
    """
    from monitor_ui.routers import chat_loops

    chat_loops._SCENE_LOOPS.clear()
    chat_loops._STORY_STATES.clear()
    chat_loops._CONVERSATION_LOOPS.clear()
    yield
    chat_loops._SCENE_LOOPS.clear()
    chat_loops._STORY_STATES.clear()
    chat_loops._CONVERSATION_LOOPS.clear()
