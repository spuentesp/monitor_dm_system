"""Character-focused interview API.

The implementation historically lived in :mod:`monitor_agents.session_zero`,
but that name conflated character discovery with the table-agreement stage.
These aliases provide the corrected domain language while preserving existing
imports during the migration.
"""

from __future__ import annotations

from monitor_agents.session_zero import (
    QuestionCategory,
    SessionZeroQuestion,
    SessionZeroSummary,
    _parse_category,
    ask_session_zero_question,
    ground_world_lore,
    summarize_session_zero_answers,
)

CharacterInterviewQuestion = SessionZeroQuestion
CharacterInterviewSummary = SessionZeroSummary
ask_character_interview_question = ask_session_zero_question
summarize_character_interview_answers = summarize_session_zero_answers

__all__ = [
    "CharacterInterviewQuestion",
    "CharacterInterviewSummary",
    "QuestionCategory",
    "_parse_category",
    "ask_character_interview_question",
    "ground_world_lore",
    "summarize_character_interview_answers",
]
