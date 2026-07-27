"""
SessionZero — Guided, story-first character development interview.

LAYER: 2 (agents)
IMPORTS FROM: pydantic, dspy (via dspy_runtime)

WHY THIS EXISTS
---------------
Before this module, the pre-play flow jumped from "player describes character"
directly to mechanical character creation (stat rolls, class selection). There
was no guided interview phase — no 20-questions-style development of the
character's story, bonds, fears, and motivations.

This module implements a **Session Zero** interview: the GM asks ONE evocative
question at a time, adapted to the setting's tone and the player's prior
answers. After a bounded number of questions (default 7), the answers are
distilled into a character concept and backstory that feed into the
CharacterCreationLoop (mechanics) or narrative-only play.

Inspired by:
  - Legend of the Five Rings' 20 Questions
  - Dungeon World bonds / PbtA playbook prompts
  - Vampire: The Masquerade 20th Anniversary Prelude
  - Death in Space origin + background rolls

WHY DSPY (NOT INSTRUCTOR)
-------------------------
Same rationale as GMAwareness: the prompt IS the test surface. Golden
input/output datasets let us regression-test the question quality. The
signature is a typed Python object that tests can inspect.

ARCHITECTURE
------------

    Player's initial character description
        ↓
    ask_session_zero_question(tone, system, lore, prior_answers)
        ↓
    SessionZeroQuestion  ← ONE LLM call (DSPy Predict)
        ↓
    SessionZeroLoop asks the question, collects the answer, loops
        ↓ (after max_questions)
    summarize_session_zero_answers() → character concept + backstory
        ↓
    Hand off to CharacterCreationLoop (mechanics) or active_play

FAILURE MODES
-------------
- LLM unavailable / timeout → fallback to canned tone-based questions.
- LLM returns invalid category → parsed leniently to "custom".
- LLM marks is_final early → loop respects the signal and summarizes.

TESTING THE PROMPT (DSPY METRICS)
----------------------------------
The gold-set lives in `monitor_agents.tests.test_session_zero_prompts`:
each example pins one input → one expected question category. The `metric()`
function scores question quality (category match, evocativeness).
"""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ===========================================================================
# Enums (validated strings — no drift)
# ===========================================================================


class QuestionCategory(StrEnum):
    """What aspect of the character is this question exploring?"""

    NAME = "name"  # What are you called?
    ORIGIN = "origin"  # Where do you come from?
    BOND = "bond"  # Who matters to you?
    FEAR = "fear"  # What are you afraid of?
    MOTIVATION = "motivation"  # What drives you forward?
    CONFLICT = "conflict"  # What internal struggle do you face?
    SECRET = "secret"  # What are you hiding?
    LOSS = "loss"  # What did you lose?
    APPEARANCE = "appearance"  # What do you look like?
    SKILL = "skill"  # What are you known for?
    FAITH = "faith"  # What do you believe in?
    RELATIONSHIP = "relationship"  # Who shaped you?
    CUSTOM = "custom"  # Adaptive question not in the standard set
    CAMPAIGN_INTENT = "campaign_intent"  # What kind of story does the player want? (asked
    # once, up front, by SessionZeroLoop directly --
    # see ask_campaign_intent -- not chosen by this
    # module's own question-selection LLM call)


# ===========================================================================
# The question — single source of truth for the interview loop
# ===========================================================================


class SessionZeroQuestion(BaseModel):
    """
    Structured output from the Session Zero LLM call.

    One question at a time, adapted to the setting's tone and the player's
    prior answers. The GM asks this, the player answers, and the loop
    continues until max_questions or is_final.
    """

    question_text: str = Field(
        ...,
        description=(
            "The evocative, in-fiction question the GM asks the player. "
            "Must be a single question (not a list). Should be concrete and "
            "specific to the setting's tone and the player's prior answers. "
            "Never ask about mechanics (stats, dice, classes) — only story."
        ),
    )

    category: QuestionCategory = Field(
        default=QuestionCategory.CUSTOM,
        description=(
            "What aspect of the character this question explores. Used to ensure variety across the interview."
        ),
    )

    is_final: bool = Field(
        default=False,
        description=(
            "True if this is the last question before summarizing. "
            "Set to True when the character feels fleshed out (usually "
            "after 5-7 questions) and the next step should be the summary."
        ),
    )

    reasoning: str = Field(
        default="",
        description=(
            "Free-form reasoning: why this question, given the tone and prior answers. For debugging and audit."
        ),
    )


# ===========================================================================
# The summary — distills answers into a character concept + backstory
# ===========================================================================


class SessionZeroSummary(BaseModel):
    """
    Distilled character concept and backstory from the interview answers.
    """

    character_name: str | None = Field(None, description="The character's name, if mentioned in the answers.")

    concept: str = Field(
        ...,
        description=(
            "A one-sentence character concept distilled from the answers. "
            "Example: 'A disgraced surgeon seeking redemption in the slums.'"
        ),
    )

    backstory: str = Field(
        ...,
        description=(
            "A 2-4 paragraph backstory woven from the player's answers. "
            "Should read as narrative prose, not a bullet list. "
            "Incorporates origin, bonds, fears, motivations, and losses."
        ),
    )

    key_bonds: list[str] = Field(
        default_factory=list, description="Key relationships or bonds mentioned in the answers."
    )

    key_fears: list[str] = Field(default_factory=list, description="Fears or vulnerabilities mentioned in the answers.")

    key_motivations: list[str] = Field(default_factory=list, description="What drives the character forward.")


# ===========================================================================
# DSPy signature — the prompt IS the test surface
# ===========================================================================

try:
    import dspy

    _DSPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DSPY_AVAILABLE = False


if _DSPY_AVAILABLE:

    class SessionZeroSignature(dspy.Signature):  # type: ignore[misc]
        """
        You are the GM conducting a Session Zero interview.

        Your job: ask ONE evocative question at a time that develops the
        player's character as a person — their story, bonds, fears, and
        motivations. NOT their mechanics (stats, dice, classes).

        Rules:
        - Ask exactly ONE question. Never a list.
        - The question must be in-fiction and concrete, not abstract.
        - Adapt to the setting's tone: grim settings ask about loss and
          survival; heroic settings ask about quests and ideals; horror
          asks about fear and what you've seen; mystery asks about secrets.
        - Reference the player's prior answers when relevant — show you
          listened.
        - Never ask about numbers, stats, dice, or game mechanics.
        - After 2-4 substantive answers, set is_final=True to signal the
          interview is winding down.
        - Vary the category — don't ask two origin questions in a row.
        - Anchor each question to the setting's distinguishing features
          (use the system_name and any world_lore provided). Avoid
          generic RPG standbys — tavern barkeeps, road encounters, hand
          scars, "where do you come from" cliches — that could apply to
          any world. The question should feel like it could only be
          asked in THIS setting.
        """

        # ── STATIC PREFIX (session-level, cacheable) ──

        tone: str = dspy.InputField(
            desc="The session's narrative tone: grim, horror, dramatic, heroic, mystery, adventure.",
        )
        system_name: str = dspy.InputField(
            desc="The game system / setting name (e.g., 'Death in Space', 'Vampire: The Masquerade').",
        )
        world_lore: str = dspy.InputField(
            desc="Key world facts and axioms that ground the questions (newline-separated). Empty if no lore available.",
        )
        system_context: str = dspy.InputField(
            desc="Context from the game system, such as background options, creation steps, and thematic prompts.",
        )

        # ── DYNAMIC (turn-specific) ──

        question_number: int = dspy.InputField(
            desc="Which question this is in the interview (1-based). Question 1 is the opening.",
        )
        max_questions: int = dspy.InputField(
            desc="Maximum questions before summarizing. Typically 4.",
        )
        prior_answers: str = dspy.InputField(
            desc="Newline-separated list of prior Q&A pairs (format 'Q: ... A: ...'). Empty for the first question.",
        )
        categories_asked: str = dspy.InputField(
            desc="Comma-separated list of question categories already asked (e.g., 'origin,bond'). Empty for the first question.",
        )

        # ── OUTPUTS ──

        question_text: str = dspy.OutputField(
            desc="The single evocative, in-fiction question the GM asks. Must be one question, not a list. Concrete and specific to the tone and prior answers.",
        )
        category: str = dspy.OutputField(
            desc="What aspect this question explores: name / origin / bond / fear / motivation / conflict / secret / loss / appearance / skill / faith / relationship / custom. Vary from prior categories.",
        )
        is_final: bool = dspy.OutputField(
            desc="True if this is the last question before summarizing (usually after 2-4 substantive answers). False otherwise.",
        )
        reasoning: str = dspy.OutputField(
            desc="Why this question, given the tone and prior answers.",
        )

    class SessionZeroModule(dspy.Module):  # type: ignore[misc]
        """
        DSPy module that wraps the SessionZero signature with Predict.
        """

        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(SessionZeroSignature)

        def forward(
            self,
            *,
            tone: str,
            system_name: str,
            world_lore: str,
            system_context: str,
            question_number: int,
            max_questions: int,
            prior_answers: str,
            categories_asked: str,
        ) -> dspy.Prediction:
            return self.predict(
                tone=tone,
                system_name=system_name,
                world_lore=world_lore,
                system_context=system_context,
                question_number=question_number,
                max_questions=max_questions,
                prior_answers=prior_answers,
                categories_asked=categories_asked,
            )

    class SessionZeroSummarySignature(dspy.Signature):  # type: ignore[misc]
        """
        You are the GM summarizing a Session Zero interview into a character
        concept and backstory.

        Take the player's answers and weave them into:
        1. A one-sentence character concept
        2. A 2-4 paragraph backstory (narrative prose, not bullet points)
        3. Key bonds, fears, and motivations (as lists)

        The backstory should read as if written in the character's voice or
        a close third-person narrator. It should incorporate the setting's
        tone and world lore where relevant.

        Anchor every name, place, and reference in the setting's
        distinguishing features (use the system_name and any world_lore
        provided). Avoid generic RPG standbys — tavern barkeeps, road
        encounters, hand scars, "wandering swordsman" cliches — that
        could apply to any world. The backstory should feel like it
        could only belong to THIS setting.
        """

        tone: str = dspy.InputField(
            desc="The session's narrative tone.",
        )
        system_name: str = dspy.InputField(
            desc="The game system / setting name.",
        )
        world_lore: str = dspy.InputField(
            desc="Key world facts and axioms (newline-separated).",
        )
        interview_transcript: str = dspy.InputField(
            desc="The full Q&A transcript from the Session Zero interview.",
        )

        character_name: str = dspy.OutputField(
            desc="The character's name if mentioned in the answers, or 'Unknown' if not.",
        )
        concept: str = dspy.OutputField(
            desc="A one-sentence character concept distilled from the answers.",
        )
        backstory: str = dspy.OutputField(
            desc="A 2-4 paragraph backstory woven from the answers. Narrative prose, not bullet points.",
        )
        key_bonds: str = dspy.OutputField(
            desc="Comma-separated list of key relationships or bonds.",
        )
        key_fears: str = dspy.OutputField(
            desc="Comma-separated list of fears or vulnerabilities.",
        )
        key_motivations: str = dspy.OutputField(
            desc="Comma-separated list of what drives the character.",
        )

    class SessionZeroSummaryModule(dspy.Module):  # type: ignore[misc]
        """DSPy module for summarizing session zero answers."""

        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(SessionZeroSummarySignature)

        def forward(
            self,
            *,
            tone: str,
            system_name: str,
            world_lore: str,
            interview_transcript: str,
        ) -> dspy.Prediction:
            return self.predict(
                tone=tone,
                system_name=system_name,
                world_lore=world_lore,
                interview_transcript=interview_transcript,
            )


# ===========================================================================
# DSPy ↔ Pydantic conversion
# ===========================================================================


def _parse_category(value: str) -> QuestionCategory:
    """Map a string from the LLM to the QuestionCategory enum (lenient)."""
    if not value:
        return QuestionCategory.CUSTOM
    normalized = str(value).strip().lower()
    aliases = {
        "name": "name",
        "origin": "origin",
        "background": "origin",
        "where_from": "origin",
        "bond": "bond",
        "bonds": "bond",
        "relationship": "relationship",
        "relationships": "relationship",
        "fear": "fear",
        "fears": "fear",
        "motivation": "motivation",
        "drive": "motivation",
        "goal": "motivation",
        "conflict": "conflict",
        "internal_conflict": "conflict",
        "secret": "secret",
        "secrets": "secret",
        "loss": "loss",
        "appearance": "appearance",
        "look": "appearance",
        "skill": "skill",
        "skills": "skill",
        "faith": "faith",
        "belief": "faith",
        "custom": "custom",
        "other": "custom",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return QuestionCategory(normalized)
    except ValueError:
        return QuestionCategory.CUSTOM


def _parse_bool(value: Any) -> bool:
    """Leniently parse a boolean from LLM output."""
    if isinstance(value, bool):
        return value
    if not value:
        return False
    normalized = str(value).strip().lower()
    return normalized in ("true", "yes", "1", "final", "last")


def _parse_string_list(value: str) -> list[str]:
    """Parse a comma-separated string into a list."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def prediction_to_question(pred: Any) -> SessionZeroQuestion:
    """Convert a DSPy Prediction into a typed SessionZeroQuestion."""
    return SessionZeroQuestion(
        question_text=str(getattr(pred, "question_text", "") or "").strip(),
        category=_parse_category(getattr(pred, "category", "")),
        is_final=_parse_bool(getattr(pred, "is_final", False)),
        reasoning=str(getattr(pred, "reasoning", "") or ""),
    )


def prediction_to_summary(pred: Any) -> SessionZeroSummary:
    """Convert a DSPy Prediction into a typed SessionZeroSummary."""
    name_raw = str(getattr(pred, "character_name", "") or "").strip()
    name = None if name_raw.lower() in ("", "unknown", "none", "null") else name_raw
    return SessionZeroSummary(
        character_name=name,
        concept=str(getattr(pred, "concept", "") or "").strip(),
        backstory=str(getattr(pred, "backstory", "") or "").strip(),
        key_bonds=_parse_string_list(getattr(pred, "key_bonds", "")),
        key_fears=_parse_string_list(getattr(pred, "key_fears", "")),
        key_motivations=_parse_string_list(getattr(pred, "key_motivations", "")),
    )


# ===========================================================================
# Fallback questions — used when the LLM is unavailable
# ===========================================================================

_FALLBACK_QUESTIONS: dict[str, list[dict[str, Any]]] = {
    "grim": [
        {"category": "origin", "text": "Where did you come from, before everything fell apart?"},
        {"category": "loss", "text": "What did you lose that still keeps you awake?"},
        {"category": "bond", "text": "Who do you still have left to protect?"},
        {"category": "fear", "text": "What are you running from — and is it catching up?"},
        {"category": "motivation", "text": "What keeps you moving when there's no hope left?"},
        {"category": "secret", "text": "What are you hiding from the others?"},
        {"category": "conflict", "text": "What line won't you cross, even to survive?"},
    ],
    "horror": [
        {"category": "origin", "text": "What brought you to this place — and was it your choice?"},
        {"category": "fear", "text": "What did you see that you can't unsee?"},
        {"category": "secret", "text": "What are you not telling the others about what happened?"},
        {"category": "bond", "text": "Who here do you trust — and why is that dangerous?"},
        {"category": "loss", "text": "Who didn't make it out with you?"},
        {"category": "motivation", "text": "What do you need to find before you can leave?"},
        {"category": "conflict", "text": "What part of you is changing — and do you want it to?"},
    ],
    "dramatic": [
        {"category": "origin", "text": "Where did you come from, and what brought you here?"},
        {"category": "bond", "text": "Who matters to you — and are they here?"},
        {"category": "motivation", "text": "What do you want from this?"},
        {"category": "fear", "text": "What are you afraid will happen if you fail?"},
        {"category": "secret", "text": "What are you not telling me?"},
        {"category": "conflict", "text": "What do you want that you can't have?"},
        {"category": "loss", "text": "What did you leave behind?"},
    ],
    "heroic": [
        {
            "category": "origin",
            "text": "Where did your story begin — and what set you on this path?",
        },
        {"category": "motivation", "text": "What quest drives you forward?"},
        {"category": "bond", "text": "Who do you fight for?"},
        {"category": "fear", "text": "What would it mean if you failed?"},
        {
            "category": "skill",
            "text": "What are you known for — what can you do that others can't?",
        },
        {"category": "faith", "text": "What do you believe in, when things are darkest?"},
        {"category": "conflict", "text": "What price are you willing to pay for victory?"},
    ],
    "mystery": [
        {"category": "origin", "text": "What brought you here — and was it really your choice?"},
        {"category": "secret", "text": "What are you hiding from everyone else?"},
        {"category": "bond", "text": "Who here do you know — and how?"},
        {"category": "fear", "text": "What do you know that frightens you?"},
        {"category": "motivation", "text": "What are you really looking for?"},
        {"category": "conflict", "text": "What truth are you afraid to uncover?"},
        {"category": "loss", "text": "What disappeared — and why does it matter to you?"},
    ],
    "adventure": [
        {"category": "origin", "text": "Where are you from, and how did you end up here?"},
        {"category": "motivation", "text": "What's the plan — what are you after?"},
        {"category": "skill", "text": "What are you good at — what's your specialty?"},
        {"category": "bond", "text": "Who's your crew — who's got your back?"},
        {"category": "fear", "text": "What could go wrong — and are you ready for it?"},
        {"category": "secret", "text": "What's the one thing you're not telling the others?"},
        {"category": "conflict", "text": "What's the one rule you won't break?"},
    ],
}


def _fallback_question(
    tone: str,
    question_number: int,
    max_questions: int,
    system_context: str = "",
) -> SessionZeroQuestion:
    """Generate a fallback question when the LLM is unavailable."""
    is_final = question_number >= max_questions

    # Try to extract backgrounds from system_context
    backgrounds = []
    if system_context:
        for line in system_context.split("\n"):
            if line.startswith("Backgrounds/Origins:"):
                bgs = line.replace("Backgrounds/Origins:", "").split(",")
                backgrounds = [bg.strip() for bg in bgs if bg.strip()]
                break

    if backgrounds and question_number == 1:
        bg_list = ", ".join(backgrounds[:5])
        return SessionZeroQuestion(
            question_text=f"Which of these origins fits you best: {bg_list}, or something else?",
            category=QuestionCategory.ORIGIN,
            is_final=is_final,
            reasoning="Fallback question using system backgrounds (LLM unavailable).",
        )

    tone_key = tone.lower().strip()
    questions = _FALLBACK_QUESTIONS.get(tone_key, _FALLBACK_QUESTIONS["dramatic"])

    # Cycle through the tone's question list
    idx = (question_number - 1) % len(questions)
    q = questions[idx]

    return SessionZeroQuestion(
        question_text=q["text"],
        category=QuestionCategory(q["category"]),
        is_final=is_final,
        reasoning=f"Fallback question for tone '{tone_key}' (LLM unavailable).",
    )


def _fallback_summary(
    tone: str,
    system_name: str,
    answers: list[dict[str, str]],
) -> SessionZeroSummary:
    """Generate a fallback summary when the LLM is unavailable."""
    # Extract a name if any answer mentions one
    name = None
    for a in answers:
        text = a.get("answer", "")
        for prefix in ("my name is", "call me", "i am", "i'm"):
            lower = text.lower()
            if prefix in lower:
                idx = lower.index(prefix) + len(prefix)
                rest = text[idx:].strip().split()
                if rest:
                    candidate = rest[0].strip(".,;!?")
                    if candidate and candidate[0].isupper():
                        name = candidate
                        break
        if name:
            break

    # Build a simple backstory from the answers
    parts = []
    for a in answers:
        q = a.get("question", "")
        ans = a.get("answer", "")
        if q and ans:
            parts.append(f"{ans}")

    backstory = " ".join(parts) if parts else "A character with an untold story."
    if len(backstory) < 50:
        backstory += " Their full story has yet to be written."

    concept = "A character shaped by their past, seeking something in the present."
    if name:
        concept = f"{name} — a character shaped by their past, seeking something in the present."

    return SessionZeroSummary(
        character_name=name,
        concept=concept,
        backstory=backstory,
        key_bonds=[],
        key_fears=[],
        key_motivations=[],
    )


def ground_world_lore(
    world_lore: list[str],
    system_name: str,
    system_context: str,
) -> list[str]:
    """Append a per-universe grounding sentence to the Session Zero lore list.

    The 2026-07-23 LLM-vs-LLM play log surfaced a "barkeep / scar on your
    hand" verbatim question in Turn 2 of all three sessions (Death in
    Space, Fallout, VtM) — the same model converging on the same generic
    RPG prior across unrelated universes. Root cause: when ``world_lore``
    is empty (Neo4j returned no axioms/facts) or thin, the Session Zero
    prompt degenerates to ``tone + system_name`` and the model reaches
    for the safest RPG standby.

    This helper always appends a setting-anchored instruction, even when
    the lore list is empty, so the LLM has *something* universe-specific
    to ground the question in. The grounding sentence is appended LAST
    so it sits where the LLM attends most.

    Args:
        world_lore: Lore items from fetch_opening_hook (axioms + facts).
            May be empty.
        system_name: Universe/system label (e.g. "Death in Space"). May be
            empty if the caller hasn't resolved it yet.
        system_context: Backgrounds, creation steps, themes from the
            game system. May be empty.

    Returns:
        A new list: the input lore + exactly one grounding sentence.
        Returns a copy; the input list is not mutated.
    """
    label = (system_name or "this setting").strip() or "this setting"

    if world_lore:
        return [
            *world_lore,
            (
                f"Every question must reference specifics from {label!r} — "
                "its locations, factions, technologies, or named roles. "
                "Never reach for generic tavern-barkeep, scar-on-your-hand, "
                "or road-encounter prompts that could apply to any RPG."
            ),
        ]

    # Empty-lore fallback: use system_context (truncated) as the anchor
    # so the LLM still sees SOMETHING universe-specific, not just a tone.
    context_excerpt = (system_context or "").strip().replace("\n", " ")[:200]
    if not context_excerpt:
        context_excerpt = "the game system itself"

    return [
        (
            f"This is a {label!r} session. Its distinguishing features are "
            f"drawn from {context_excerpt}. "
            "Anchor every question in this setting's specifics — never reach "
            "for generic tavern/scar/road prompts that could apply to any RPG."
        )
    ]


# ===========================================================================
# Main entry points — LLM calls
# ===========================================================================


async def ask_session_zero_question(
    tone: str,
    system_name: str,
    world_lore: list[str],
    question_number: int,
    max_questions: int,
    prior_answers: list[dict[str, str]],
    categories_asked: list[str],
    system_context: str = "",
) -> SessionZeroQuestion:
    """
    Run the Session Zero question-generation LLM call.

    Args:
        tone: The session's narrative tone (grim, horror, dramatic, etc.).
        system_name: The game system / setting name.
        world_lore: Key world facts and axioms for grounding.
        question_number: Which question this is (1-based).
        max_questions: Maximum questions before summarizing.
        prior_answers: List of prior Q&A dicts: {"question": ..., "answer": ..., "category": ...}.
        categories_asked: List of categories already asked.
        system_context: Context from the game system, such as background options.

    Returns:
        A SessionZeroQuestion with the next question to ask.
    """
    # Fast path: if we've hit max questions, signal final
    if question_number > max_questions:
        return SessionZeroQuestion(
            question_text="That's enough for now — let's bring your character to life.",
            category=QuestionCategory.CUSTOM,
            is_final=True,
            reasoning="Max questions reached; signaling final.",
        )

    if not _DSPY_AVAILABLE:
        return _fallback_question(tone, question_number, max_questions, system_context)

    lore_text = "\n".join(f"- {f}" for f in world_lore[:6]) if world_lore else ""
    answers_text = ""
    for a in prior_answers:
        answers_text += f"Q: {a.get('question', '')}\nA: {a.get('answer', '')}\n\n"
    categories_text = ",".join(categories_asked) if categories_asked else ""

    try:
        return await _run_dspy_question(
            tone=tone,
            system_name=system_name,
            world_lore=lore_text,
            system_context=system_context,
            question_number=question_number,
            max_questions=max_questions,
            prior_answers=answers_text.strip(),
            categories_asked=categories_text,
        )
    except Exception as exc:
        logger.warning(
            "Session Zero question LLM call failed (%s); using fallback",
            exc,
        )
        return _fallback_question(tone, question_number, max_questions, system_context)


async def _run_dspy_question(
    *,
    tone: str,
    system_name: str,
    world_lore: str,
    system_context: str,
    question_number: int,
    max_questions: int,
    prior_answers: str,
    categories_asked: str,
) -> SessionZeroQuestion:
    """Run the DSPy Predict module for question generation."""
    from monitor_data.schemas.llm_config import ModelRole

    from monitor_agents.dspy_runtime import dspy_context_for

    module = SessionZeroModule()

    def _predict() -> Any:
        with dspy_context_for("session_zero", ModelRole.LIGHT):
            return module.forward(
                tone=tone or "dramatic",
                system_name=system_name or "Unknown System",
                world_lore=world_lore or "(none)",
                system_context=system_context or "(none)",
                question_number=question_number,
                max_questions=max_questions,
                prior_answers=prior_answers or "(none)",
                categories_asked=categories_asked or "(none)",
            )

    pred = await asyncio.to_thread(_predict)
    return prediction_to_question(pred)


async def summarize_session_zero_answers(
    tone: str,
    system_name: str,
    world_lore: list[str],
    answers: list[dict[str, str]],
) -> SessionZeroSummary:
    """
    Run the Session Zero summary LLM call.

    Distills the interview answers into a character concept and backstory.

    Args:
        tone: The session's narrative tone.
        system_name: The game system / setting name.
        world_lore: Key world facts and axioms.
        answers: List of Q&A dicts from the interview.

    Returns:
        A SessionZeroSummary with concept, backstory, bonds, fears, motivations.
    """
    if not _DSPY_AVAILABLE:
        return _fallback_summary(tone, system_name, answers)

    lore_text = "\n".join(f"- {f}" for f in world_lore[:6]) if world_lore else ""
    transcript = ""
    for a in answers:
        transcript += f"Q: {a.get('question', '')}\nA: {a.get('answer', '')}\n\n"

    try:
        return await _run_dspy_summary(
            tone=tone,
            system_name=system_name,
            world_lore=lore_text,
            interview_transcript=transcript.strip(),
        )
    except Exception as exc:
        logger.warning(
            "Session Zero summary LLM call failed (%s); using fallback",
            exc,
        )
        return _fallback_summary(tone, system_name, answers)


async def _run_dspy_summary(
    *,
    tone: str,
    system_name: str,
    world_lore: str,
    interview_transcript: str,
) -> SessionZeroSummary:
    """Run the DSPy Predict module for summary generation."""
    from monitor_data.schemas.llm_config import ModelRole

    from monitor_agents.dspy_runtime import dspy_context_for

    module = SessionZeroSummaryModule()

    def _predict() -> Any:
        with dspy_context_for("session_zero", ModelRole.LIGHT):
            return module.forward(
                tone=tone or "dramatic",
                system_name=system_name or "Unknown System",
                world_lore=world_lore or "(none)",
                interview_transcript=interview_transcript or "(none)",
            )

    pred = await asyncio.to_thread(_predict)
    return prediction_to_summary(pred)
