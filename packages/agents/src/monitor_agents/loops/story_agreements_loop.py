"""Compact Session Zero loop for story topics, themes, lines, and veils."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from monitor_agents.story_agreements import (
    AgreementCategory,
    StoryAgreementAnswer,
    StoryAgreements,
    summarize_story_agreements,
)

AGREEMENT_SEQUENCE = (
    AgreementCategory.PREMISE,
    AgreementCategory.THEMES,
    AgreementCategory.BOUNDARIES,
)


class StoryAgreementsState(BaseModel):
    setting_intro: dict[str, Any] = Field(default_factory=dict)
    character_name: str = "the protagonist"
    default_tone: str = "dramatic"
    authored_questions: list[dict[str, Any]] = Field(default_factory=list)
    question_index: int = 0
    current_question: str = ""
    current_category: AgreementCategory = AgreementCategory.PREMISE
    answers: list[StoryAgreementAnswer] = Field(default_factory=list)
    draft: StoryAgreements | None = None
    awaiting_input: bool = False
    awaiting_confirmation: bool = False
    revision: int = 0


async def present_question(state: StoryAgreementsState) -> dict[str, Any]:
    if state.question_index >= len(AGREEMENT_SEQUENCE):
        return {"awaiting_input": False}
    category = AGREEMENT_SEQUENCE[state.question_index]
    question = _question_for(state, category)
    return {
        "current_category": category,
        "current_question": question,
        "awaiting_input": True,
    }


async def process_answer(state: StoryAgreementsState) -> dict[str, Any]:
    """The loop class injects the answer before invoking this node."""
    return {"awaiting_input": False}


async def summarize_answers(state: StoryAgreementsState) -> dict[str, Any]:
    draft = await summarize_story_agreements(
        setting_intro=str(state.setting_intro.get("intro_text") or ""),
        default_tone=state.default_tone,
        answers=state.answers,
        revision=state.revision,
    )
    return {"draft": draft, "awaiting_confirmation": True, "awaiting_input": False}


def build_story_agreements_graph() -> StateGraph[Any, Any, Any]:
    graph = StateGraph(StoryAgreementsState)
    graph.add_node("present", present_question)
    graph.add_node("process", process_answer)
    graph.add_node("summarize", summarize_answers)
    graph.set_entry_point("present")
    graph.add_edge("present", "process")
    graph.add_edge("process", "summarize")
    graph.add_edge("summarize", END)
    return graph


class StoryAgreementsLoop:
    """Stateful three-question Session Zero agreement interview."""

    def __init__(
        self,
        *,
        setting_intro: dict[str, Any],
        character_name: str,
        default_tone: str,
        authored_questions: list[dict[str, Any]] | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        self._graph = build_story_agreements_graph()
        if checkpoint:
            self._state = StoryAgreementsState.model_validate(checkpoint)
        else:
            self._state = StoryAgreementsState(
                setting_intro=setting_intro,
                character_name=character_name or "the protagonist",
                default_tone=default_tone or "dramatic",
                authored_questions=list(authored_questions or []),
            )

    async def start(self) -> dict[str, Any]:
        result = await present_question(self._state)
        self._state = self._state.model_copy(update=result)
        intro_text = str(self._state.setting_intro.get("intro_text") or "").strip()
        question = self._state.current_question
        message = f"{intro_text}\n\n---\n\n{question}" if intro_text else question
        return {
            "complete": False,
            "gm_message": message,
            "question_number": 1,
            "total_questions": len(AGREEMENT_SEQUENCE),
            "category": self._state.current_category.value,
            "session_intro": self._state.setting_intro,
        }

    async def process_player_input(self, player_input: str) -> dict[str, Any]:
        answer_text = (player_input or "").strip()
        if not answer_text:
            return {
                "complete": False,
                "gm_message": self._state.current_question,
                "question_number": self._state.question_index + 1,
                "total_questions": len(AGREEMENT_SEQUENCE),
                "category": self._state.current_category.value,
            }

        if self._state.awaiting_confirmation:
            answers = [
                *self._state.answers,
                StoryAgreementAnswer(
                    category=AgreementCategory.REVISION,
                    question="What should change in these agreements?",
                    answer=answer_text,
                ),
            ]
            self._state = self._state.model_copy(
                update={
                    "answers": answers,
                    "revision": self._state.revision + 1,
                    "awaiting_confirmation": False,
                }
            )
            summary = await summarize_answers(self._state)
            self._state = self._state.model_copy(update=summary)
            return self._summary_result()

        answer = StoryAgreementAnswer(
            category=self._state.current_category,
            question=self._state.current_question,
            answer=answer_text,
        )
        next_index = self._state.question_index + 1
        self._state = self._state.model_copy(
            update={
                "answers": [*self._state.answers, answer],
                "question_index": next_index,
                "awaiting_input": False,
            }
        )

        if next_index >= len(AGREEMENT_SEQUENCE):
            summary = await summarize_answers(self._state)
            self._state = self._state.model_copy(update=summary)
            return self._summary_result()

        question = await present_question(self._state)
        self._state = self._state.model_copy(update=question)
        return {
            "complete": False,
            "gm_message": self._state.current_question,
            "question_number": next_index + 1,
            "total_questions": len(AGREEMENT_SEQUENCE),
            "category": self._state.current_category.value,
        }

    def _summary_result(self) -> dict[str, Any]:
        draft = self._state.draft or StoryAgreements(tone=self._state.default_tone)
        return {
            "complete": True,
            "awaiting_confirmation": True,
            "gm_message": _format_summary(draft),
            "agreements": draft,
            "question_number": len(AGREEMENT_SEQUENCE),
            "total_questions": len(AGREEMENT_SEQUENCE),
            "category": AgreementCategory.BOUNDARIES.value,
        }

    @property
    def state(self) -> StoryAgreementsState:
        return self._state

    def checkpoint(self) -> dict[str, Any]:
        return self._state.model_dump(mode="json")


def _question_for(state: StoryAgreementsState, category: AgreementCategory) -> str:
    authored_index = AGREEMENT_SEQUENCE.index(category)
    if authored_index < len(state.authored_questions):
        authored = str(state.authored_questions[authored_index].get("question_text") or "").strip()
        if authored:
            return authored

    universe_name = str(state.setting_intro.get("universe_name") or "this setting").strip()
    if category == AgreementCategory.PREMISE:
        return (
            f"In {universe_name}, what kind of story do you want to explore, "
            f"and what role should {state.character_name} have in it?"
        )
    if category == AgreementCategory.THEMES:
        return (
            "Which themes do you actively want the story to explore, and should "
            f"the tone or pacing differ from **{state.default_tone}**?"
        )
    return (
        "Before we begin, what are your **lines** (subjects that must never appear) "
        "and your **veils** (subjects that may exist but should fade to black)? "
        "It is fine to say that you have none."
    )


def _format_summary(agreements: StoryAgreements) -> str:
    parts = ["## Session Zero agreements"]
    if agreements.story_premise:
        parts.append(f"**Story:** {agreements.story_premise}")
    if agreements.pc_role:
        parts.append(f"**Character role:** {agreements.pc_role}")
    if agreements.themes:
        parts.append("**Themes:** " + ", ".join(agreements.themes))
    tone_line = agreements.tone
    if agreements.pacing:
        tone_line += f"; {agreements.pacing} pacing"
    parts.append(f"**Tone:** {tone_line}")
    parts.append("**Lines:** " + (", ".join(agreements.lines) if agreements.lines else "None stated"))
    parts.append("**Veils:** " + (", ".join(agreements.veils) if agreements.veils else "None stated"))
    if agreements.boundary_notes:
        parts.append("**Boundary notes:** " + " ".join(agreements.boundary_notes))
    if agreements.needs_review:
        parts.append("*Boundary details were preserved verbatim and should be reviewed before play.*")
    parts.append("Review these agreements, revise them in chat if needed, then choose **Begin Story**.")
    return "\n\n".join(parts)
