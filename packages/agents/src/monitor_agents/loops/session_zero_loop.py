"""
Session Zero Loop — Guided character development interview.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), langgraph, external libs
CALLED BY: chat_loops.py (via run_preplay_turn)

A LangGraph StateGraph that conducts a guided, story-first character
interview before mechanical character creation. The GM asks ONE evocative
question at a time (adapted to tone, system, and prior answers), collects
the player's answers, and then distills them into a character concept +
backstory.

Flow:
  ask_question → await_player → process_answer → (loop or summarize) → finish

This loop sits between the GM opening message and the CharacterCreationLoop:
    awaiting_character → session_zero → char_creation → active_play

Max questions is bounded (default 7) to respect player patience. The LLM
can signal is_final early if the character feels fleshed out.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from monitor_agents.session_zero import (
    SessionZeroQuestion,
    SessionZeroSummary,
    ask_session_zero_question,
    summarize_session_zero_answers,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_QUESTIONS = 7


# =============================================================================
# STATE SCHEMA
# =============================================================================


class SessionZeroState(BaseModel):
    """Typed state that flows through every session-zero loop node."""

    # Session context
    scene_id: Optional[UUID] = None
    story_id: Optional[UUID] = None
    universe_id: Optional[UUID] = None

    # Interview configuration
    tone: str = "dramatic"
    system_name: str = "Unknown System"
    world_lore: List[str] = Field(default_factory=list)
    system_context: str = ""
    max_questions: int = DEFAULT_MAX_QUESTIONS

    # Interview state
    question_number: int = 0
    current_question: Optional[str] = None
    current_category: str = "custom"
    answers: List[Dict[str, str]] = Field(default_factory=list)
    categories_asked: List[str] = Field(default_factory=list)

    # Player input
    player_input: Optional[str] = None

    # Summary (filled at the end)
    summary: Optional[SessionZeroSummary] = None

    # Flow control
    interview_complete: bool = False
    awaiting_input: bool = False
    gm_message: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# NODES
# =============================================================================


async def ask_question(state: SessionZeroState) -> Dict[str, Any]:
    """Generate the next interview question via LLM (or fallback)."""
    next_num = state.question_number + 1

    # Check if we've hit the limit
    if next_num > state.max_questions:
        return {
            "interview_complete": True,
            "awaiting_input": False,
        }

    question: SessionZeroQuestion = await ask_session_zero_question(
        tone=state.tone,
        system_name=state.system_name,
        world_lore=state.world_lore,
        system_context=state.system_context,
        question_number=next_num,
        max_questions=state.max_questions,
        prior_answers=state.answers,
        categories_asked=state.categories_asked,
    )

    return {
        "question_number": next_num,
        "current_question": question.question_text,
        "current_category": question.category.value,
        "gm_message": question.question_text,
        "awaiting_input": True,
        "interview_complete": question.is_final and next_num >= state.max_questions,
    }


async def process_answer(state: SessionZeroState) -> Dict[str, Any]:
    """Record the player's answer and decide whether to continue or summarize."""
    if not state.player_input:
        return {"awaiting_input": True}

    answer_text = state.player_input.strip()

    # Record the answer
    new_answer = {
        "question": state.current_question or "",
        "answer": answer_text,
        "category": state.current_category,
    }
    updated_answers = [*state.answers, new_answer]
    updated_categories = [*state.categories_asked, state.current_category]

    # Check if we should stop:
    # 1. Hit max questions
    # 2. Player says "done" / "skip" / "that's all"
    # 3. LLM signaled is_final on the last question (checked via question_number >= max)
    lower = answer_text.lower()
    stop_signals = {"done", "skip", "that's all", "that's it", "i'm done", "finish"}
    should_stop = (
        state.question_number >= state.max_questions
        or any(sig in lower for sig in stop_signals)
    )

    if should_stop:
        return {
            "answers": updated_answers,
            "categories_asked": updated_categories,
            "player_input": None,
            "interview_complete": True,
            "awaiting_input": False,
        }

    # Continue to next question
    return {
        "answers": updated_answers,
        "categories_asked": updated_categories,
        "player_input": None,
        "awaiting_input": False,
    }


async def summarize_node(state: SessionZeroState) -> Dict[str, Any]:
    """Distill the interview answers into a character concept + backstory."""
    if not state.answers:
        return {
            "interview_complete": True,
            "gm_message": "No answers to summarize — let's begin with your character as-is.",
        }

    summary: SessionZeroSummary = await summarize_session_zero_answers(
        tone=state.tone,
        system_name=state.system_name,
        world_lore=state.world_lore,
        answers=state.answers,
    )

    # Build a GM message that presents the summary
    parts = []
    if summary.character_name:
        parts.append(f"**{summary.character_name}** — {summary.concept}")
    else:
        parts.append(summary.concept)

    parts.append("")
    parts.append(summary.backstory)

    if summary.key_bonds:
        parts.append("")
        parts.append("*Bonds: " + ", ".join(summary.key_bonds) + "*")
    if summary.key_fears:
        parts.append("*Fears: " + ", ".join(summary.key_fears) + "*")
    if summary.key_motivations:
        parts.append("*Drives: " + ", ".join(summary.key_motivations) + "*")

    parts.append("")
    parts.append(
        "Does this feel right? If so, we can ground it in the system — "
        "or skip the numbers and play purely in the story."
    )

    return {
        "summary": summary,
        "gm_message": "\n".join(parts),
        "interview_complete": True,
    }


# =============================================================================
# ROUTING
# =============================================================================


def _route_after_ask(state: SessionZeroState) -> str:
    """Route after asking a question."""
    if state.interview_complete:
        return "summarize"
    if state.awaiting_input:
        return "await"
    return "ask"  # shouldn't happen, but safe


def _route_after_process(state: SessionZeroState) -> str:
    """Route after processing an answer."""
    if state.interview_complete:
        return "summarize"
    if state.error:
        return "ask"  # retry the question
    return "ask"  # continue to next question


# =============================================================================
# GRAPH BUILDER
# =============================================================================


def build_session_zero_graph() -> StateGraph:
    """Build the LangGraph StateGraph for the session zero interview."""
    graph = StateGraph(SessionZeroState)

    graph.add_node("ask", ask_question)
    graph.add_node("process", process_answer)
    graph.add_node("summarize", summarize_node)

    graph.set_entry_point("ask")

    # ask → (await: process) | (done: summarize)
    graph.add_conditional_edges(
        "ask",
        _route_after_ask,
        {
            "await": "process",
            "summarize": "summarize",
            "ask": "ask",  # self-loop safety (shouldn't trigger)
        },
    )

    # process → (continue: ask) | (done: summarize)
    graph.add_conditional_edges(
        "process",
        _route_after_process,
        {
            "ask": "ask",
            "summarize": "summarize",
        },
    )

    # summarize → END
    graph.add_edge("summarize", END)

    return graph


# =============================================================================
# LOOP CLASS
# =============================================================================


class SessionZeroLoop:
    """
    High-level interface for the session zero interview loop.

    Usage:
        loop = SessionZeroLoop(tone="grim", system_name="Death in Space", ...)
        result = await loop.start()          # get first question
        result = await loop.process_player_input("I was a soldier...")  # answer + next question
        # ... repeat until result["complete"] is True
    """

    def __init__(
        self,
        *,
        tone: str = "dramatic",
        system_name: str = "Unknown System",
        world_lore: Optional[List[str]] = None,
        system_context: str = "",
        max_questions: int = DEFAULT_MAX_QUESTIONS,
        scene_id: Optional[UUID] = None,
        story_id: Optional[UUID] = None,
        universe_id: Optional[UUID] = None,
    ) -> None:
        self._tone = tone
        self._system_name = system_name
        self._world_lore = world_lore or []
        self._system_context = system_context
        self._max_questions = max_questions
        self._scene_id = scene_id
        self._story_id = story_id
        self._universe_id = universe_id
        self._graph = build_session_zero_graph()
        self._state = SessionZeroState(
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
            tone=tone,
            system_name=system_name,
            world_lore=world_lore or [],
            system_context=system_context,
            max_questions=max_questions,
        )

    async def start(self) -> Dict[str, Any]:
        """Initialize the loop and return the first GM question."""
        result = await ask_question(self._state)
        self._state = self._state.model_copy(update=result)

        if self._state.interview_complete and not self._state.answers:
            # Edge case: max_questions was 0 or LLM immediately said final
            summary_result = await summarize_node(self._state)
            self._state = self._state.model_copy(update=summary_result)
            return {
                "complete": True,
                "gm_message": self._state.gm_message,
                "summary": self._state.summary,
            }

        return {
            "complete": False,
            "gm_message": self._state.gm_message,
            "question_number": self._state.question_number,
            "total_questions": self._max_questions,
            "category": self._state.current_category,
        }

    async def process_player_input(self, player_input: str) -> Dict[str, Any]:
        """Process the player's answer and return the next question or summary."""
        self._state = self._state.model_copy(update={"player_input": player_input})

        result = await process_answer(self._state)
        self._state = self._state.model_copy(update=result)

        if self._state.interview_complete:
            # Generate the summary
            summary_result = await summarize_node(self._state)
            self._state = self._state.model_copy(update=summary_result)
            return {
                "complete": True,
                "gm_message": self._state.gm_message,
                "summary": self._state.summary,
                "answers": self._state.answers,
            }

        # Ask the next question
        ask_result = await ask_question(self._state)
        self._state = self._state.model_copy(update=ask_result)

        if self._state.interview_complete:
            summary_result = await summarize_node(self._state)
            self._state = self._state.model_copy(update=summary_result)
            return {
                "complete": True,
                "gm_message": self._state.gm_message,
                "summary": self._state.summary,
                "answers": self._state.answers,
            }

        return {
            "complete": False,
            "gm_message": self._state.gm_message,
            "question_number": self._state.question_number,
            "total_questions": self._max_questions,
            "category": self._state.current_category,
        }

    @property
    def state(self) -> SessionZeroState:
        """Read-only access to the current loop state (for debugging/tests)."""
        return self._state

    @property
    def answers(self) -> List[Dict[str, str]]:
        """The accumulated Q&A pairs from the interview."""
        return self._state.answers

    @property
    def summary(self) -> Optional[SessionZeroSummary]:
        """The distilled character summary (available after completion)."""
        return self._state.summary