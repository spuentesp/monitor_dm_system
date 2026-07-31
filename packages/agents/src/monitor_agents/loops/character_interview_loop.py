"""Character interview loop API.

The implementation remains in ``session_zero_loop`` as a compatibility layer;
new orchestration code uses the corrected character-interview terminology.
"""

from __future__ import annotations

from monitor_agents.loops.session_zero_loop import (
    DEFAULT_MAX_QUESTIONS,
    SessionZeroLoop,
    SessionZeroState,
    ask_question,
    build_session_zero_graph,
    process_answer,
    summarize_node,
)

CharacterInterviewLoop = SessionZeroLoop
CharacterInterviewState = SessionZeroState
build_character_interview_graph = build_session_zero_graph

__all__ = [
    "CharacterInterviewLoop",
    "CharacterInterviewState",
    "DEFAULT_MAX_QUESTIONS",
    "ask_question",
    "build_character_interview_graph",
    "process_answer",
    "summarize_node",
]
