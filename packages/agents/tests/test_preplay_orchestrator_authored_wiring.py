"""Tests that the preplay orchestrator threads authored questions into the
SessionZeroLoop (Phase 2 wiring, post-refactor into preplay_orchestrator)."""

import pytest

from monitor_agents.loops import preplay_orchestrator as po


@pytest.fixture(autouse=True)
def _clear_loop_cache():
    po._SESSION_ZERO_LOOPS.clear()
    po._CHAR_CREATION_LOOPS.clear()
    yield
    po._SESSION_ZERO_LOOPS.clear()
    po._CHAR_CREATION_LOOPS.clear()


AUTHORED = [
    {"question_text": "What are you called?", "category": "name", "is_final": False},
    {"question_text": "Whose blood do you regret?", "category": "loss", "is_final": True},
]


def test_authored_questions_pin_budget_and_seed_state():
    loop = po.get_session_zero_loop(
        "sess-1",
        {"tone": "gothic", "system_label": "VtM"},
        world_lore=[],
        system_context="",
        authored_questions=AUTHORED,
    )
    assert loop is not None
    # Budget pinned to the authored count (no LLM padding).
    assert loop._max_questions == 2
    assert [q["question_text"] for q in loop._state.authored_questions] == [
        "What are you called?",
        "Whose blood do you regret?",
    ]


def test_no_authored_questions_uses_default_budget():
    loop = po.get_session_zero_loop(
        "sess-2",
        {"tone": "gothic", "system_label": "VtM"},
        world_lore=[],
        system_context="",
    )
    assert loop is not None
    assert loop._max_questions == po.DEFAULT_MAX_QUESTIONS
    assert loop._state.authored_questions == []


def test_loop_is_cached_per_session():
    first = po.get_session_zero_loop("sess-3", {"system_label": "VtM"}, [], "", authored_questions=AUTHORED)
    second = po.get_session_zero_loop("sess-3", {"system_label": "VtM"}, [], "")
    assert first is second  # cache hit ignores later args, as documented


def test_session_zero_cache_is_bounded():
    for i in range(po._SESSION_ZERO_LOOPS_MAX + 5):
        po.get_session_zero_loop(f"s-{i}", {"system_label": "VtM"}, [], "")
    assert len(po._SESSION_ZERO_LOOPS) == po._SESSION_ZERO_LOOPS_MAX
    # Oldest evicted, newest retained.
    assert "s-0" not in po._SESSION_ZERO_LOOPS
    assert f"s-{po._SESSION_ZERO_LOOPS_MAX + 4}" in po._SESSION_ZERO_LOOPS


def test_char_creation_cache_is_bounded():
    for i in range(po._CHAR_CREATION_LOOPS_MAX + 5):
        po.get_character_creation_loop(f"c-{i}", {"name": "VtM", "character_creation": {"steps": []}})
    assert len(po._CHAR_CREATION_LOOPS) <= po._CHAR_CREATION_LOOPS_MAX
