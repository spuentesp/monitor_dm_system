"""Baseline session-0 intake questions + appearance in the summary model."""

from __future__ import annotations

import pytest

from monitor_agents.loops import preplay_support
from monitor_agents.loops.preplay_support import (
    BASELINE_SESSION_ZERO_QUESTIONS,
    resolve_authored_session_zero_questions,
)
from monitor_agents.session_zero import SessionZeroSummary


def test_baseline_questions_present_without_authored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preplay_support, "resolve_authored_questions", lambda *a, **k: [])
    questions = resolve_authored_session_zero_questions({}, None)
    categories = [q["category"] for q in questions]
    assert categories[:3] == ["name", "origin", "appearance"]
    for q in questions:
        assert q["question_text"].strip()
        assert set(q) == {"question_text", "category", "is_final", "answer_options"}


def test_authored_question_suppresses_matching_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    authored = [
        {"question_text": "How are you called?", "category": "name", "is_final": False, "answer_options": []},
        {"question_text": "What drives you?", "category": "motivation", "is_final": True, "answer_options": []},
    ]
    monkeypatch.setattr(preplay_support, "resolve_authored_questions", lambda *a, **k: authored)
    questions = resolve_authored_session_zero_questions({}, None)
    categories = [q["category"] for q in questions]
    assert categories.count("name") == 1  # authored wins, baseline name suppressed
    assert "origin" in categories and "appearance" in categories
    assert categories[-2:] == ["name", "motivation"]  # authored kept, after baseline


def test_baseline_constant_is_defensive_copy_safe() -> None:
    assert len(BASELINE_SESSION_ZERO_QUESTIONS) == 3


def test_summary_model_has_appearance() -> None:
    summary = SessionZeroSummary(concept="c", backstory="b", appearance="scarred, tall")
    assert summary.model_dump()["appearance"] == "scarred, tall"
    default = SessionZeroSummary(concept="c", backstory="b")
    assert default.appearance is None
