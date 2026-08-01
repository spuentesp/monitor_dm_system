"""Tests for typed Begin Story intent and session-facts grounding of OOC answers."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from monitor_agents.loops.preplay_support import (
    answer_ooc_question,
    is_begin_story_command,
    is_ooc_question,
    normalize_ooc_text,
    record_director_note,
    session_facts_block,
)


class TestIsBeginStoryCommand:
    @pytest.mark.parametrize(
        "text",
        [
            "begin",
            "begin story",
            "Begin Story",
            "begin the story!",
            "start the narration",
            "confirm",
            "looks good.",
            "let's begin",
            "lets go",
            "ok",
            "  yes  ",
        ],
    )
    def test_confirmation_phrases_match(self, text: str) -> None:
        assert is_begin_story_command(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "begin the story, but first change the tone",
            "actually, make it more comedic",
            "((begin story))",  # OOC-wrapped stays an OOC question
            "beginner's luck",
            "when does the story begin?",
        ],
    )
    def test_non_commands_do_not_match(self, text: str) -> None:
        assert is_begin_story_command(text) is False


class TestSessionFactsBlock:
    def test_includes_character_and_agreements(self) -> None:
        session: dict[str, Any] = {
            "speaker_label": "John Cunningham",
            "character_summary": {
                "character_name": "John Cunningham",
                "concept": "A neurologist turned undead.",
                "backstory": "Embraced by a Malkavian, then abandoned.",
            },
            "story_agreements": {
                "story_premise": "A researcher studies visions in Valparaíso.",
                "themes": ["humor", "vampirism"],
            },
        }
        block = session_facts_block(session)
        assert "John Cunningham" in block
        assert "neurologist turned undead" in block
        assert "Embraced by a Malkavian" in block
        assert "researcher studies visions" in block
        assert "humor" in block and "vampirism" in block

    def test_empty_session_yields_empty_block(self) -> None:
        assert session_facts_block({}) == ""

    def test_falls_back_to_speaker_label(self) -> None:
        block = session_facts_block({"speaker_label": "Mara"})
        assert block == "Player character: Mara"


class _FakePrediction:
    def __init__(self, answer: str) -> None:
        self.answer = answer


class _FakePredict:
    """Captures the kwargs the OOC answerer hands to dspy.Predict."""

    last_kwargs: dict[str, Any] | None = None
    answer_text = "((You are John Cunningham, a neurologist turned undead.))"

    def __call__(self, _signature: Any) -> Any:
        def _invoke(**kwargs: Any) -> _FakePrediction:
            _FakePredict.last_kwargs = kwargs
            return _FakePrediction(_FakePredict.answer_text)

        return _invoke


def _patch_ooc_llm():
    import contextlib

    return (
        patch(
            "monitor_agents.dspy_runtime.dspy_context_for",
            lambda *a, **k: contextlib.nullcontext(),
        ),
        patch("dspy.Predict", _FakePredict()),
    )


class TestAnswerOocQuestionGrounding:
    @pytest.mark.asyncio
    async def test_ooc_answer_receives_session_facts(self) -> None:
        session: dict[str, Any] = {
            "tone": "mystery",
            "speaker_label": "John Cunningham",
            "character_summary": {
                "character_name": "John Cunningham",
                "concept": "A neurologist turned undead.",
                "backstory": "Embraced by a Malkavian, then abandoned.",
            },
            "story_agreements": {
                "story_premise": "A researcher studies visions.",
                "themes": ["vampirism"],
            },
        }
        _FakePredict.last_kwargs = None
        ctx1, ctx2 = _patch_ooc_llm()
        with ctx1, ctx2:
            answer = await answer_ooc_question(
                session,
                "((who am i?))",
                session_game_system_doc=None,
                gsr_available=False,
            )

        assert "John Cunningham" in answer
        assert _FakePredict.last_kwargs is not None
        facts = _FakePredict.last_kwargs["session_facts"]
        assert "neurologist turned undead" in facts
        assert "researcher studies visions" in facts
        # The question itself is not a fact — nothing recorded.
        assert not session.get("director_notes")

    @pytest.mark.asyncio
    async def test_ooc_answer_without_facts_still_works(self) -> None:
        _FakePredict.last_kwargs = None
        ctx1, ctx2 = _patch_ooc_llm()
        with ctx1, ctx2:
            answer = await answer_ooc_question(
                {"tone": "dramatic"},
                "((what can i play?))",
                session_game_system_doc=None,
                gsr_available=False,
            )
        assert answer
        assert _FakePredict.last_kwargs is not None
        assert _FakePredict.last_kwargs["session_facts"] == "(nothing established yet)"

    @pytest.mark.asyncio
    async def test_ooc_statement_is_recorded_as_director_note(self) -> None:
        session: dict[str, Any] = {"tone": "mystery"}
        _FakePredict.last_kwargs = None
        ctx1, ctx2 = _patch_ooc_llm()
        with ctx1, ctx2:
            await answer_ooc_question(
                session,
                "((lets be clear: this is happening in santiago de chile))",
                session_game_system_doc=None,
                gsr_available=False,
            )
        assert session["director_notes"] == ["lets be clear: this is happening in santiago de chile"]
        # The recorded note is fed back into the next answer's facts.
        assert "santiago de chile" in (_FakePredict.last_kwargs or {})["session_facts"]


class TestDirectorNotes:
    def test_statement_is_recorded(self) -> None:
        session: dict[str, Any] = {}
        assert record_director_note(session, "this happens in Santiago") is True
        assert session["director_notes"] == ["this happens in Santiago"]

    def test_mid_sentence_question_mark_still_records(self) -> None:
        session: dict[str, Any] = {}
        note = "lets be clear: this is happening in santiago de chile. okay? i want a santiago nocturno experience"
        assert record_director_note(session, note) is True
        assert session["director_notes"] == [note]

    def test_questions_are_not_recorded(self) -> None:
        session: dict[str, Any] = {}
        assert record_director_note(session, "who am i?") is False
        assert record_director_note(session, "what is this place") is False
        assert not session.get("director_notes")

    def test_duplicates_are_skipped(self) -> None:
        session: dict[str, Any] = {"director_notes": ["note one"]}
        assert record_director_note(session, "note one") is False
        assert session["director_notes"] == ["note one"]

    def test_notes_are_capped_and_mutated_in_place(self) -> None:
        notes = [f"note {i}" for i in range(20)]
        session: dict[str, Any] = {"director_notes": notes}
        record_director_note(session, "newest note")
        assert session["director_notes"] is notes  # same list object (shared with SceneLoop)
        assert len(notes) == 20
        assert notes[-1] == "newest note"
        assert "note 0" not in notes

    def test_facts_block_includes_director_notes(self) -> None:
        block = session_facts_block({"director_notes": ["setting is Santiago de Chile"]})
        assert "Player direction" in block
        assert "setting is Santiago de Chile" in block


class TestUnclosedOocWrapper:
    @pytest.mark.parametrize(
        "text",
        ["(( Oracle:", "((who am i?", "(( just a thought"],
    )
    def test_unclosed_wrapper_is_ooc(self, text: str) -> None:
        assert is_ooc_question(text) is True

    def test_unclosed_wrapper_normalizes(self) -> None:
        assert normalize_ooc_text("(( Oracle:") == "Oracle:"

    def test_closed_wrapper_still_works(self) -> None:
        assert is_ooc_question("((who am i?))") is True
        assert normalize_ooc_text("((who am i?))") == "who am i?"
