"""
CausalityCheck — LLM-driven causality violation detection.

LAYER: 2 (agents)
IMPORTS FROM: pydantic, instructor (via BaseAgent.call_llm_structured)

This module replaces the old regex-based forced-narrative detection with a
proper consciousness check. When the player declares an outcome (e.g. "I
shoot him dead" or "I convince the bartender" or "I find the key in my
pocket"), the resolver hands the input to a small LLM that reasons:

    1. Is the player declaring an outcome or attempting an action?
    2. If declaring an outcome, does the outcome violate causality given
       established facts?
    3. If causality is violated, what should the resolver do?
       - accept in narrative/god mode
       - push back and ask for a roll
       - request clarification (e.g. "where did the key come from?")

This is the GM's conscious mind doing the work — no regex, no keyword lists,
no heuristics. The LLM reads the player's text and uses judgment.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CausalityAction(StrEnum):
    """What the resolver should do based on the causality verdict."""

    ACCEPT = "accept"  # Outcome is consistent with causality — proceed
    PUSH_BACK = "push_back"  # Outcome violates causality — ask the player to roll
    REQUEST_CLARIFICATION = "request_clarification"  # Need more info to decide
    NARRATIVE_OVERRIDE = "narrative_override"  # We're in narrative/god mode — accept anyway


class CausalityVerdict(BaseModel):
    """Structured output from the causality check LLM call."""

    # Is the player declaring a completed outcome vs attempting an action?
    declares_outcome: bool = Field(
        ...,
        description=(
            "True if the player is asserting that something already happened "
            "(past tense, present perfect, or 'I do X' where X is the result, "
            "not the attempt). False if the player is attempting an action "
            "whose outcome is unknown ('I try to...', 'I attempt to...', "
            "'I aim at...', 'I search for...')."
        ),
    )

    # Does the declared outcome violate causality?
    violates_causality: bool = Field(
        ...,
        description=(
            "True if accepting this declaration would violate causality: "
            "introduce things that don't exist (deus ex machina), break "
            "established facts, or skip the world's logic. "
            "Examples of violations: 'I shoot him dead' (no roll), "
            "'I find the key in my pocket' (key never established), "
            "'I remember the code' (memory never established), "
            "'I convince the guard' (no roll attempted)."
        ),
    )

    # Severity — how bad is the violation if there is one?
    severity: str = Field(
        default="none",
        description=(
            "'none' if no violation. 'minor' for small leaps (convincing someone "
            "without a roll — usually recoverable). 'major' for clear violations "
            "(killing without a roll — requires dice). 'deus_ex_machina' for "
            "introducing entire objects/characters/NPCs/knowledge that don't "
            "exist in the scene (a key appears from nowhere, an NPC walks in, "
            "the character knows something they couldn't know)."
        ),
    )

    # What was wrong?
    reasons: list[str] = Field(
        default_factory=list,
        description=(
            "Specific reasons the outcome violates causality. Each reason "
            "should reference what was introduced that doesn't exist or what "
            "established fact was skipped."
        ),
    )

    # What should the resolver do?
    action: CausalityAction = Field(
        ...,
        description=(
            "ACCEPT: outcome is fine, proceed. "
            "PUSH_BACK: outcome violates causality, ask player to roll. "
            "REQUEST_CLARIFICATION: need more info ('Where did the key come from?'). "
            "NARRATIVE_OVERRIDE: we're in god mode, accept anyway."
        ),
    )

    # Suggested roll (if pushing back)
    suggested_stat: str | None = Field(
        None,
        description=(
            "If pushing back with a roll, what stat should resolve it? "
            "E.g. 'Strength' for forcing a door, 'Charisma' for persuading."
        ),
    )
    suggested_dc: int | None = Field(
        None,
        description=(
            "If pushing back with a roll, what DC? Lower for easy actions, "
            "higher for hard ones. Default 12 for standard difficulty."
        ),
    )

    # Reasoning — the GM's thought process
    reasoning: str = Field(
        default="",
        description=(
            "Free-form reasoning the GM used to reach this verdict. "
            'For example: \'The player says "I convince the guard" but no '
            "roll was attempted. This is a clear social outcome declaration "
            "that requires a Charisma check to resolve.'"
        ),
    )

    # Pushback prompt for the player
    pushback_prompt: str | None = Field(
        None,
        description=(
            "If pushing back, the message shown to the player. Should be "
            "concrete: 'You still need to roll Charisma (DC 12) to convince "
            "the guard' or 'Where did the key come from? You haven't established "
            "having one.'"
        ),
    )


_CAUSALITY_CHECK_SYSTEM_PROMPT = """You are the GM's causality check — the part of the GM's mind that evaluates whether the player's declared action makes sense in the world.

Your job is to read the player's text and judge two things:

1. **Does the player declare a completed outcome, or attempt an action?**
   - Declares outcome: "I shoot him dead", "I convince the guard", "I find the key in my pocket", "I remember the code"
   - Attempts action: "I try to shoot him", "I attempt to convince the guard", "I aim at him", "I search for a key"

   The grammatical structure matters. "I shoot him" without a qualifier is a declaration. "I try to shoot him" is an attempt.

2. **If declaring an outcome, does it violate causality given the established facts?**
   - The player introduces things that don't exist (deus ex machina): a key appears from nowhere, an NPC they never met helps them, they know things they couldn't know
   - The player skips the world's logic: kills without a roll, succeeds without a check, bypasses obstacles without effort
   - The player contradicts established facts: the door was sealed, they say it's open

   If everything is consistent with the scene, no violation.

Be strict but not pedantic. A player saying "I attack the guard" is an action, not a violation — they need to roll. A player saying "I kill the guard" without rolling IS a violation.

When pushing back, give the player a useful prompt: what stat, what DC, what they need to clarify.
"""


async def check_causality(
    agent: Any,
    user_input: str,
    scene_context: dict[str, Any],
    play_mode: str,
    established_facts: list[str],
    roll_mode: str = "normal",
) -> CausalityVerdict:
    """
    Run the causality check LLM call.

    Args:
        agent: A BaseAgent instance (for call_llm_structured).
        user_input: The player's declared action.
        scene_context: The assembled scene context (entities, memories, prior turns).
        play_mode: "narrative" (god mode), "dice_standard", or "dice_game_system".
        established_facts: Accumulated facts from the session.
        roll_mode: "normal", "advantage", "disadvantage", or "auto".

    Returns:
        CausalityVerdict with structured outcome.
    """
    # In narrative/god mode, always accept
    if play_mode == "narrative":
        return CausalityVerdict(
            declares_outcome=True,
            violates_causality=False,
            severity="none",
            reasons=[],
            action=CausalityAction.NARRATIVE_OVERRIDE,
            reasoning="Session is in narrative (god) mode — all declared outcomes are accepted.",
        )

    # In auto-roll mode, the system will roll dice, so accept declarations
    # but flag that we should auto-roll.
    if roll_mode == "auto":
        return CausalityVerdict(
            declares_outcome=True,
            violates_causality=False,
            severity="none",
            reasons=[],
            action=CausalityAction.ACCEPT,
            reasoning="Auto-roll mode: the system will roll dice for the player.",
        )

    # Build the user message with full context
    facts_text = "\n".join(f"- {f}" for f in established_facts[-20:])
    entities_text = "\n".join(
        f"- {e.get('name', '?')} ({e.get('entity_type', '?')})" for e in scene_context.get("entities", [])
    )
    prior_turns_text = ""
    for turn in scene_context.get("turns", [])[-3:]:
        prior_turns_text += f"- {turn.get('speaker', '?')}: {turn.get('text', '')[:200]}\n"

    user_message = f"""Evaluate this player action for causality violations:

PLAYER ACTION:
{user_input}

ESTABLISHED FACTS (from earlier in the session):
{facts_text or "(none yet)"}

SCENE ENTITIES:
{entities_text or "(none)"}

RECENT TURNS:
{prior_turns_text or "(none)"}

PLAY MODE: {play_mode}
ROLL MODE: {roll_mode}

Decide:
1. Does the player declare a completed outcome, or attempt an action?
2. If declaring an outcome, does it violate causality given the established facts?
3. What should the resolver do?

If pushing back with a roll, suggest a stat and DC. Use defaults: STR/DEX/CON for physical, INT/WIS for mental, CHA for social. DC 12 for standard, 10 for easy, 15 for hard.
"""

    try:
        verdict: CausalityVerdict = await agent.call_llm_structured(
            response_model=CausalityVerdict,
            messages=[
                {"role": "system", "content": _CAUSALITY_CHECK_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=800,
        )
        return verdict
    except Exception as exc:
        logger.warning(
            "Causality check LLM call failed (%s); falling back to permissive",
            exc,
        )
        # On LLM failure, be permissive — let the roll resolver handle it
        return CausalityVerdict(
            declares_outcome=False,
            violates_causality=False,
            severity="none",
            reasons=[],
            action=CausalityAction.ACCEPT,
            reasoning=f"Causality check unavailable ({exc}); falling back to standard resolution.",
        )
