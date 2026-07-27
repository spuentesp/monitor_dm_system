"""Tests for authored (configurable) questions in SessionZeroLoop.

Verifies that a curated prompt collection drives the interview verbatim, that
the LLM continues once the authored queue is exhausted (hybrid), and that
authored questions compose with seed_answers.
"""

import pytest

from monitor_agents.loops import session_zero_loop as szl
from monitor_agents.loops.session_zero_loop import SessionZeroLoop
from monitor_agents.session_zero import QuestionCategory, SessionZeroQuestion, SessionZeroSummary

AUTHORED = [
    {"question_text": "What name do the covens whisper?", "category": "name", "is_final": False},
    {"question_text": "Whose blood do you regret spilling?", "category": "loss", "is_final": True},
]


@pytest.fixture
def patched_llm(monkeypatch):
    """Patch the LLM question + summary calls; record question-LLM invocations."""
    calls = {"ask": 0}

    async def fake_ask(**kwargs):
        calls["ask"] += 1
        return SessionZeroQuestion(
            question_text=f"LLM-generated question {calls['ask']}",
            category=QuestionCategory.CUSTOM,
            is_final=False,
        )

    async def fake_summary(**kwargs):
        return SessionZeroSummary(
            character_name="Konstantin",
            concept="A fallen Ventrue seeking their sire.",
            backstory="Backstory prose.",
        )

    monkeypatch.setattr(szl, "ask_session_zero_question", fake_ask)
    monkeypatch.setattr(szl, "summarize_session_zero_answers", fake_summary)
    return calls


@pytest.mark.asyncio
async def test_authored_questions_used_verbatim_without_llm(patched_llm):
    loop = SessionZeroLoop(
        tone="gothic",
        system_name="Vampire: The Masquerade",
        authored_questions=AUTHORED,
        # The caller (Phase 2 resolver) pins the budget to the authored count
        # when it wants exactly the curated set with no LLM padding.
        max_questions=len(AUTHORED),
    )

    first = await loop.start()
    assert first["complete"] is False
    assert first["gm_message"] == AUTHORED[0]["question_text"]
    assert first["category"] == "name"
    assert first["total_questions"] == 2  # driven by the authored set

    second = await loop.process_player_input("They whisper 'Konstantin'.")
    assert second["complete"] is False
    assert second["gm_message"] == AUTHORED[1]["question_text"]
    assert second["category"] == "loss"

    done = await loop.process_player_input("My mortal brother.")
    assert done["complete"] is True
    assert done["summary"].character_name == "Konstantin"

    # The authored queue fully covered the interview — LLM never asked.
    assert patched_llm["ask"] == 0


@pytest.mark.asyncio
async def test_hybrid_authored_then_llm(patched_llm):
    # One authored question, default budget of 4 → LLM fills the remaining 3.
    loop = SessionZeroLoop(
        tone="gothic",
        system_name="Vampire: The Masquerade",
        authored_questions=[AUTHORED[0]],
        max_questions=4,
    )

    first = await loop.start()
    assert first["gm_message"] == AUTHORED[0]["question_text"]
    assert first["total_questions"] == 4
    assert patched_llm["ask"] == 0

    second = await loop.process_player_input("Konstantin.")
    assert second["complete"] is False
    assert second["gm_message"].startswith("LLM-generated question")
    assert patched_llm["ask"] == 1


@pytest.mark.asyncio
async def test_authored_floor_overrides_seed_shrink(patched_llm):
    # seed_answers would shrink the budget to 2, but 3 authored questions floor
    # it at 3 so none of the authored set is truncated.
    seed = [
        {"question": "Your name?", "answer": "Konstantin", "category": "name"},
        {"question": "Your origin?", "answer": "Vienna", "category": "origin"},
    ]
    authored = [
        {"question_text": "Q1?", "category": "bond"},
        {"question_text": "Q2?", "category": "fear"},
        {"question_text": "Q3?", "category": "motivation", "is_final": True},
    ]
    loop = SessionZeroLoop(
        system_name="Vampire: The Masquerade",
        seed_answers=seed,
        authored_questions=authored,
        max_questions=4,
    )

    first = await loop.start()
    assert first["gm_message"] == "Q1?"
    assert first["total_questions"] == 3
    assert patched_llm["ask"] == 0
