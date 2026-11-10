"""Guided-start questions — plan order, start question, choice resolution.

Phase 2 tasks 2 and 3: the fixed CAMPAIGN_INTENT_QUESTION is replaced by a
model-written question presenting the seed's start options by name; the
question series is ordered how to start, who you are, what you want, one
adaptive follow-up, capped at 4.
"""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

import monitor_agents.session_zero as sz
from monitor_agents.loops.session_zero_loop import SessionZeroLoop, SessionZeroState
from monitor_agents.session_zero import (
    GUIDED_DESIRE_QUESTION,
    GUIDED_IDENTITY_QUESTION,
    QuestionCategory,
    StartChoice,
    ask_start_options_question,
    build_question_plan,
    fallback_start_question,
    resolve_start_choice,
    start_option_titles,
)

pytestmark = pytest.mark.unit

OPTIONS = [
    {"option_id": "dockside-heist-1", "title": "Dockside Heist", "location": "The Docks"},
    {"option_id": "last-watch-2", "title": "The Last Watch", "location": "The Wall"},
]


# ─── question plan (task 3) ──────────────────────────────────────────────────


def test_plan_order_is_start_identity_desire_plus_adaptive():
    fixed, total = build_question_plan(start_options=OPTIONS, start_question_text="How begin?")
    categories = [q["category"] for q in fixed]
    assert categories[0] == "start_choice"
    assert categories[1] == GUIDED_IDENTITY_QUESTION["category"]
    assert categories[2] == GUIDED_DESIRE_QUESTION["category"]
    # One adaptive follow-up fills the last slot.
    assert total == 4
    assert len(fixed) == 3


def test_plan_cap_is_four():
    fixed, total = build_question_plan(
        start_options=OPTIONS,
        start_question_text="How begin?",
        authored_questions=[{"question_text": f"authored {i}", "category": "custom"} for i in range(5)],
    )
    assert len(fixed) <= 4
    assert total <= 4


def test_persona_shortens_the_series():
    fixed, total = build_question_plan(start_options=OPTIONS, start_question_text="How begin?", has_persona=True)
    categories = [q["category"] for q in fixed]
    assert "name" not in categories  # who you are is already known
    assert total < 4


def test_rich_first_message_shortens_the_series():
    fixed, total = build_question_plan(start_options=OPTIONS, start_question_text="How begin?", has_premise=True)
    categories = [q["category"] for q in fixed]
    assert "motivation" not in categories
    assert total < 4


def test_plan_start_question_carries_option_chips():
    fixed, _ = build_question_plan(start_options=OPTIONS, start_question_text="How begin?")
    answers = fixed[0]["answer_options"]
    assert "Dockside Heist" in answers
    assert "The Last Watch" in answers
    assert "Surprise me" in answers
    assert fixed[0]["question_text"] == "How begin?"


def test_plan_without_start_options_keeps_legacy_shape():
    fixed, total = build_question_plan(start_options=[])
    assert fixed  # identity + desire still form the series
    assert all(q["category"] != "start_choice" for q in fixed)
    assert total >= len(fixed)


# ─── the start question (task 2) ─────────────────────────────────────────────


def test_fallback_start_question_presents_options_and_surprise():
    text = fallback_start_question(OPTIONS)
    assert "Dockside Heist" in text
    assert "The Last Watch" in text
    assert "surprise me" in text


def test_start_option_titles_prefer_title_over_location():
    assert start_option_titles([{"location": "Only Location"}]) == ["Only Location"]


@pytest.mark.asyncio
async def test_ask_start_options_question_fallback_without_dspy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sz, "_DSPY_AVAILABLE", False)
    question = await ask_start_options_question(
        system_name="Mistlands Core",
        tone="grim",
        start_options=OPTIONS,
    )
    assert question.category == QuestionCategory.START_CHOICE
    assert "Dockside Heist" in question.question_text
    assert "Surprise me" in question.suggested_answers


@pytest.mark.asyncio
async def test_ask_start_options_question_uses_model_written_question(monkeypatch: pytest.MonkeyPatch):
    """Cross-component: the question text comes from the typed LLM call,
    which receives the option titles."""
    received: dict[str, Any] = {}

    class _FakePredict:
        def __init__(self, _sig: Any) -> None:
            pass

        def __call__(self, **kwargs: Any) -> Any:
            received.update(kwargs)
            return SimpleNamespace(question_text="Torn between the heist and the watch — where do we begin?")

    monkeypatch.setattr(sz.dspy, "Predict", _FakePredict)
    monkeypatch.setattr(sz, "_DSPY_AVAILABLE", True)
    monkeypatch.setattr("monitor_agents.dspy_runtime.dspy_context_for", lambda *a, **k: nullcontext())
    question = await ask_start_options_question(
        system_name="Mistlands Core",
        tone="grim",
        start_options=OPTIONS,
    )
    assert question.question_text == "Torn between the heist and the watch — where do we begin?"
    assert "Dockside Heist" in received["option_titles"]
    assert received["system_name"] == "Mistlands Core"


# ─── choice resolution (task 2) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_start_choice_matches_option_by_name_without_llm():
    choice = await resolve_start_choice(
        question_text="How begin?",
        options=OPTIONS,
        answer="Let's do the Dockside Heist.",
    )
    assert choice.option_id == "dockside-heist-1"
    assert choice.is_surprise is False


@pytest.mark.asyncio
async def test_resolve_start_choice_surprise_uses_model(monkeypatch: pytest.MonkeyPatch):
    """Free answers (including 'surprise me') are judged by a typed model
    call, never a keyword table."""
    received: dict[str, Any] = {}

    class _FakePredict:
        def __init__(self, _sig: Any) -> None:
            pass

        def __call__(self, **kwargs: Any) -> Any:
            received.update(kwargs)
            return SimpleNamespace(chosen_index=2, is_surprise=True, free_answer="")

    monkeypatch.setattr(sz.dspy, "Predict", _FakePredict)
    monkeypatch.setattr(sz, "_DSPY_AVAILABLE", True)
    monkeypatch.setattr("monitor_agents.dspy_runtime.dspy_context_for", lambda *a, **k: nullcontext())
    choice = await resolve_start_choice(question_text="How begin?", options=OPTIONS, answer="surprise me")
    assert choice.option_id == "last-watch-2"
    assert choice.is_surprise is True
    assert "surprise me" in received["player_answer"]


@pytest.mark.asyncio
async def test_resolve_start_choice_free_answer_kept_when_llm_down(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sz, "_DSPY_AVAILABLE", False)
    choice = await resolve_start_choice(
        question_text="How begin?",
        options=OPTIONS,
        answer="I want to start in the flooded underworks.",
    )
    assert choice == StartChoice(free_answer="I want to start in the flooded underworks.")


# ─── loop wiring: plan questions, chips, answered-category plumbing ──────────


def _plan_loop() -> SessionZeroLoop:
    fixed, total = build_question_plan(start_options=OPTIONS, start_question_text="How begin?")
    return SessionZeroLoop(
        tone="grim",
        system_name="Mistlands Core",
        authored_questions=fixed,
        plan_total=total,
        start_options=OPTIONS,
    )


@pytest.mark.asyncio
async def test_loop_presents_plan_first_question_with_chips():
    loop = _plan_loop()
    result = await loop.start()
    assert result["gm_message"] == "How begin?"
    assert result["category"] == "start_choice"
    assert "Dockside Heist" in result["suggested_answers"]
    assert "Surprise me" in result["suggested_answers"]
    assert result["question_number"] == 1
    assert result["total_questions"] == 4


@pytest.mark.asyncio
async def test_loop_records_answered_category_for_start_choice():
    loop = _plan_loop()
    await loop.start()
    result = await loop.process_player_input("Dockside Heist")
    assert result["answered_category"] == "start_choice"
    assert result["answered_text"] == "Dockside Heist"
    # The next question is the identity question of the series.
    assert result["category"] == "name"


@pytest.mark.asyncio
async def test_loop_checkpoint_round_trips_question_and_chips():
    """Task 8 support: the persisted state carries the plan, the current
    question, and its chips across a backend restart."""
    loop = _plan_loop()
    await loop.start()
    dumped = loop.state.model_dump(mode="json")
    restored = SessionZeroState.model_validate(dumped)
    assert restored.current_question == "How begin?"
    assert restored.question_number == 1
    assert "Dockside Heist" in restored.current_answer_options
    assert [o["option_id"] for o in restored.start_options] == ["dockside-heist-1", "last-watch-2"]
    assert [q["question_text"] for q in restored.authored_questions][0] == "How begin?"
