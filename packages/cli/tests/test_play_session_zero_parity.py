"""Tests for CLI Session Zero parity (Phase 5).

build_cli_session_zero_loop reuses the shared agents-layer resolver so the CLI
and web author from the same prompt collections. When authored questions
exist, the returned loop is pinned to the curated set; otherwise it returns
None and the CLI falls back to mechanical creation only.
"""

from unittest.mock import patch

from monitor_cli.commands import play

_RESOLVER = "monitor_cli.commands.play.resolve_authored_session_zero_questions"

AUTHORED = [
    {"question_text": "What are you called?", "category": "name", "is_final": False},
    {"question_text": "Whose blood do you regret?", "category": "loss", "is_final": True},
]

GAME_CONTEXT = {"system_id": "a227676a-edab-4a43-80d9-8f76b74ff289", "name": "Vampire: The Masquerade"}


def test_returns_none_when_no_authored_collection():
    with patch(_RESOLVER, return_value=[]):
        loop = play.build_cli_session_zero_loop(GAME_CONTEXT, universe_id=None)
    assert loop is None


def test_builds_loop_pinned_to_authored_set():
    with patch(_RESOLVER, return_value=AUTHORED) as m:
        loop = play.build_cli_session_zero_loop(GAME_CONTEXT, universe_id=None, tone="gothic")

    assert loop is not None
    assert loop._max_questions == 2
    assert loop._system_name == "Vampire: The Masquerade"
    assert [q["question_text"] for q in loop._state.authored_questions] == [
        "What are you called?",
        "Whose blood do you regret?",
    ]
    # The resolver received a CLI-built session dict + the game_context doc.
    session_arg, doc_arg = m.call_args.args
    assert session_arg["system_id"] == GAME_CONTEXT["system_id"]
    assert doc_arg is GAME_CONTEXT
