"""Typed Session Zero story agreements and LLM-backed summarization."""

from __future__ import annotations

import asyncio
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

log = structlog.get_logger()


class AgreementCategory(StrEnum):
    PREMISE = "premise"
    THEMES = "themes"
    BOUNDARIES = "boundaries"
    REVISION = "revision"


class StoryAgreementAnswer(BaseModel):
    category: AgreementCategory
    question: str
    answer: str


class StoryAgreements(BaseModel):
    """Session-scoped story contract confirmed before narration begins."""

    story_premise: str = ""
    themes: list[str] = Field(default_factory=list)
    tone: str = "dramatic"
    pacing: str = ""
    pc_role: str = ""
    lines: list[str] = Field(default_factory=list)
    veils: list[str] = Field(default_factory=list)
    boundary_notes: list[str] = Field(default_factory=list)
    raw_answers: list[StoryAgreementAnswer] = Field(default_factory=list)
    source: str = "interview"
    revision: int = 0
    confirmed: bool = False
    confirmed_at: datetime | None = None
    needs_review: bool = False
    schema_version: int = 1


try:
    import dspy

    _DSPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DSPY_AVAILABLE = False


if _DSPY_AVAILABLE:

    class StoryAgreementsSignature(dspy.Signature):  # type: ignore[misc]
        """
        Distill a three-question tabletop Session Zero conversation into a
        precise story agreement. Use only the player's answers and supplied
        setting frame. Do not invent preferences or boundaries.

        `lines` are subjects that must never be depicted or introduced.
        `veils` are subjects that may exist but must fade to black without
        descriptive detail. If the player did not state a line or veil, leave
        the corresponding list empty. Keep each item short and unambiguous.
        """

        setting_intro: str = dspy.InputField(desc="Grounded explanatory setting introduction.")
        default_tone: str = dspy.InputField(desc="Tone selected during setup.")
        interview_transcript: str = dspy.InputField(desc="Three categorized questions and answers.")

        story_premise: str = dspy.OutputField(desc="The desired story or central situation.")
        themes: list[str] = dspy.OutputField(desc="Themes the player actively wants explored.")
        tone: str = dspy.OutputField(desc="Agreed tone; default_tone when unchanged.")
        pacing: str = dspy.OutputField(desc="Agreed pacing, or empty when unstated.")
        pc_role: str = dspy.OutputField(desc="The player character's role in this story.")
        lines: list[str] = dspy.OutputField(desc="Hard content exclusions explicitly stated by the player.")
        veils: list[str] = dspy.OutputField(desc="Fade-to-black subjects explicitly stated by the player.")


    class StoryAgreementsModule(dspy.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self._predict = dspy.Predict(StoryAgreementsSignature)

        def forward(self, **kwargs: Any) -> Any:
            return self._predict(**kwargs)


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


async def summarize_story_agreements(
    *,
    setting_intro: str,
    default_tone: str,
    answers: list[StoryAgreementAnswer],
    revision: int = 0,
) -> StoryAgreements:
    """Summarize agreement answers without heuristic text parsing."""

    if not _DSPY_AVAILABLE:
        return _fallback_agreements(default_tone, answers, revision=revision)

    transcript = "\n\n".join(
        f"[{answer.category.value}]\nQ: {answer.question}\nA: {answer.answer}"
        for answer in answers
    )
    try:
        prediction = await _run_summary(
            setting_intro=setting_intro,
            default_tone=default_tone,
            interview_transcript=transcript,
        )
        return StoryAgreements(
            story_premise=str(getattr(prediction, "story_premise", "") or "").strip(),
            themes=_as_string_list(getattr(prediction, "themes", [])),
            tone=str(getattr(prediction, "tone", "") or default_tone).strip() or default_tone,
            pacing=str(getattr(prediction, "pacing", "") or "").strip(),
            pc_role=str(getattr(prediction, "pc_role", "") or "").strip(),
            lines=_as_string_list(getattr(prediction, "lines", [])),
            veils=_as_string_list(getattr(prediction, "veils", [])),
            raw_answers=answers,
            revision=revision,
        )
    except Exception as exc:
        log.warning("story_agreements.summary_failed", error=str(exc))
        return _fallback_agreements(default_tone, answers, revision=revision)


async def _run_summary(
    *,
    setting_intro: str,
    default_tone: str,
    interview_transcript: str,
) -> Any:
    from monitor_data.schemas.llm_config import ModelRole

    from monitor_agents.dspy_runtime import dspy_context_for

    module = StoryAgreementsModule()

    def _predict() -> Any:
        with dspy_context_for("story_agreements", ModelRole.LIGHT):
            return module.forward(
                setting_intro=setting_intro or "(setting details unavailable)",
                default_tone=default_tone or "dramatic",
                interview_transcript=interview_transcript,
            )

    return await asyncio.to_thread(_predict)


def _fallback_agreements(
    default_tone: str,
    answers: list[StoryAgreementAnswer],
    *,
    revision: int,
) -> StoryAgreements:
    """Preserve answers without guessing semantic fields when the LLM is unavailable."""

    by_category = {answer.category: answer.answer.strip() for answer in answers}
    premise = by_category.get(AgreementCategory.PREMISE, "")
    themes = by_category.get(AgreementCategory.THEMES, "")
    boundaries = by_category.get(AgreementCategory.BOUNDARIES, "")
    return StoryAgreements(
        story_premise=premise,
        themes=[themes] if themes else [],
        tone=default_tone or "dramatic",
        boundary_notes=[boundaries] if boundaries else [],
        raw_answers=answers,
        revision=revision,
        needs_review=bool(boundaries),
    )
