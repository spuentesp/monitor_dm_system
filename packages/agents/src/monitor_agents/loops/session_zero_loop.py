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
from typing import Any
from uuid import UUID

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from monitor_agents.session_zero import (
    SessionZeroQuestion,
    SessionZeroSummary,
    _parse_category,
    ask_session_zero_question,
    summarize_session_zero_answers,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_QUESTIONS = 4  # [G-1] lowered 7 → 4: rich-intro seeding keeps the budget tight

# Asked once, up front, when ask_campaign_intent=True -- not LLM-generated,
# since this is a fixed, deliberate question (character-template plan Q3),
# not an adaptive one the per-question LLM call should be choosing among.
CAMPAIGN_INTENT_QUESTION = (
    "Before we get into who you are — what kind of story pulls you in "
    "tonight? A heist, a slow-burn mystery, survival horror, political "
    "intrigue... whatever you're in the mood for. (Or just say 'skip' and "
    "I'll surprise you.)"
)


# =============================================================================
# STATE SCHEMA
# =============================================================================


class SessionZeroState(BaseModel):
    """Typed state that flows through every session-zero loop node."""

    # Session context
    scene_id: UUID | None = None
    story_id: UUID | None = None
    universe_id: UUID | None = None

    # Interview configuration
    tone: str = "dramatic"
    system_name: str = "Unknown System"
    world_lore: list[str] = Field(default_factory=list)
    system_context: str = ""
    max_questions: int = DEFAULT_MAX_QUESTIONS

    # Authored questions (from a curated prompt_collection). When present, the
    # question for a given position is taken from this list *before* falling
    # back to the LLM. Each dict mirrors a serialized PromptEntry:
    # {"question_text", "category", "is_final"}. The LLM continues the interview
    # once the authored queue is exhausted (hybrid authored → adaptive).
    authored_questions: list[dict[str, Any]] = Field(default_factory=list)

    # Interview state
    question_number: int = 0
    current_question: str | None = None
    current_category: str = "custom"
    answers: list[dict[str, str]] = Field(default_factory=list)
    categories_asked: list[str] = Field(default_factory=list)

    # Player input
    player_input: str | None = None

    # Campaign-intent pre-question (character-template plan Q3): asked once,
    # up front, before the character-focused interview -- not part of the
    # normal question_number/max_questions budget.
    campaign_intent_pending: bool = False
    campaign_intent_answer: str | None = None

    # Summary (filled at the end)
    summary: SessionZeroSummary | None = None

    # Flow control
    interview_complete: bool = False
    awaiting_input: bool = False
    gm_message: str | None = None
    error: str | None = None


# =============================================================================
# NODES
# =============================================================================


async def ask_question(state: SessionZeroState) -> dict[str, Any]:
    """Generate the next interview question via authored queue, then LLM fallback."""
    next_num = state.question_number + 1

    # Check if we've hit the limit
    if next_num > state.max_questions:
        return {
            "interview_complete": True,
            "awaiting_input": False,
        }

    # Authored question for this position (0-based index into the curated set).
    # Curated content is scaffolding, not keyword logic: it simply supplies the
    # question text/category; the LLM still handles anything beyond the queue.
    authored = state.authored_questions
    idx = next_num - 1
    if 0 <= idx < len(authored):
        aq = authored[idx]
        question_text = str(aq.get("question_text", "")).strip()
        if question_text:
            category = _parse_category(str(aq.get("category", "custom"))).value
            # Always PRESENT an authored question; completion is decided by
            # process_answer once the count/budget is reached. Marking it
            # complete at ask-time (as the LLM path may) would skip showing
            # the curator's final question.
            return {
                "question_number": next_num,
                "current_question": question_text,
                "current_category": category,
                "gm_message": question_text,
                "awaiting_input": True,
                "interview_complete": False,
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


async def process_answer(state: SessionZeroState) -> dict[str, Any]:
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
    should_stop = state.question_number >= state.max_questions or any(sig in lower for sig in stop_signals)

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


async def summarize_node(state: SessionZeroState) -> dict[str, Any]:
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


def build_session_zero_graph() -> StateGraph[Any, Any, Any]:
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
        world_lore: list[str] | None = None,
        system_context: str = "",
        max_questions: int = DEFAULT_MAX_QUESTIONS,
        scene_id: UUID | None = None,
        story_id: UUID | None = None,
        universe_id: UUID | None = None,
        seed_answers: list[dict[str, str]] | None = None,
        ask_campaign_intent: bool = False,
        authored_questions: list[dict[str, Any]] | None = None,
    ) -> None:
        self._tone = tone
        self._system_name = system_name
        self._world_lore = world_lore or []
        self._system_context = system_context
        self._scene_id = scene_id
        self._story_id = story_id
        self._universe_id = universe_id
        self._graph = build_session_zero_graph()

        # A returning persona already answers most of what Session Zero would
        # ask (name/origin/personality/voice) -- seed those as already-known
        # prior_answers (ask_session_zero_question reads state.answers to
        # avoid asking about things already covered) and shrink the question
        # budget so the interview becomes a short confirmation/system-fit
        # pass instead of a full 7-question interview from scratch. At least
        # 2 questions remain so there's still room to ground the persona in
        # *this* setting, not just repeat what the persona already says.
        seed = list(seed_answers or [])
        effective_max_questions = max(2, max_questions - len(seed)) if seed else max_questions

        # When a curated question set is supplied, the interview length is
        # driven by the authored set: never truncate authored questions below
        # their count. If the authored set is shorter than the budget, the LLM
        # fills the remainder (hybrid authored → adaptive).
        authored = list(authored_questions or [])
        if authored:
            effective_max_questions = max(effective_max_questions, len(authored))
        self._max_questions = effective_max_questions

        self._state = SessionZeroState(
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
            tone=tone,
            system_name=system_name,
            world_lore=world_lore or [],
            system_context=system_context,
            max_questions=effective_max_questions,
            answers=seed,
            categories_asked=[a.get("category", "custom") for a in seed],
            campaign_intent_pending=ask_campaign_intent,
            authored_questions=authored,
        )

    async def start(self) -> dict[str, Any]:
        """Initialize the loop and return the first GM question."""
        if self._state.campaign_intent_pending:
            # Fixed, deliberate question -- not LLM-chosen, doesn't consume
            # a slot from the character-question budget. question_number
            # stays 0 so the first *real* question (asked once this is
            # answered) still reports as question 1.
            self._state = self._state.model_copy(
                update={
                    "current_question": CAMPAIGN_INTENT_QUESTION,
                    "current_category": "campaign_intent",
                    "gm_message": CAMPAIGN_INTENT_QUESTION,
                    "awaiting_input": True,
                }
            )
            return {
                "complete": False,
                "gm_message": self._state.gm_message,
                "question_number": 0,
                "total_questions": self._max_questions,
                "category": "campaign_intent",
            }

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

    async def _process_campaign_intent_answer(self, player_input: str) -> dict[str, Any]:
        """Record the campaign-intent answer (or a skip) and move on to the
        normal character-focused interview. Deliberately NOT recorded into
        state.answers/categories_asked -- that list feeds character concept
        + backstory synthesis (summarize_session_zero_answers), and "what
        story do you want" is a different concern from character
        backstory. It's surfaced separately via this method's returned
        "campaign_intent" key so the caller can backfill
        session["story_premise"] if it wasn't already set."""
        answer = (player_input or "").strip()
        skip_signals = {"done", "skip", "that's all", "that's it", "i'm done", "finish", ""}
        campaign_intent_answer = None if answer.lower() in skip_signals else answer

        self._state = self._state.model_copy(
            update={
                "campaign_intent_pending": False,
                "campaign_intent_answer": campaign_intent_answer,
            }
        )

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
                "campaign_intent": campaign_intent_answer,
            }

        return {
            "complete": False,
            "gm_message": self._state.gm_message,
            "question_number": self._state.question_number,
            "total_questions": self._max_questions,
            "category": self._state.current_category,
            "campaign_intent": campaign_intent_answer,
        }

    async def process_player_input(self, player_input: str) -> dict[str, Any]:
        """Process the player's answer and return the next question or summary."""
        if self._state.campaign_intent_pending:
            return await self._process_campaign_intent_answer(player_input)

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
    def answers(self) -> list[dict[str, str]]:
        """The accumulated Q&A pairs from the interview."""
        return self._state.answers

    @property
    def summary(self) -> SessionZeroSummary | None:
        """The distilled character summary (available after completion)."""
        return self._state.summary
