"""
Test helpers for building GMAwareness verdicts.

The resolver test suite mocks the LLM (via `check_gm_awareness`) to control
routing. This module provides concise builders so each test reads as intent,
not boilerplate.
"""

from __future__ import annotations

from typing import Optional

from monitor_agents.gm_awareness import (
    ActionType,
    CausalityAction,
    GMAwareness,
    IntentType,
    RollNecessity,
    Severity,
)


def make_verdict(
    intent: IntentType = IntentType.ACTION,
    action: ActionType = ActionType.EXPLORATION,
    roll_necessity: RollNecessity = RollNecessity.PROPOSE_ROLL,
    declares_outcome: bool = False,
    violates_causality: bool = False,
    severity: Severity = Severity.NONE,
    reasons: Optional[list[str]] = None,
    causality_action: CausalityAction = CausalityAction.ACCEPT,
    suggested_stat: Optional[str] = None,
    suggested_dc: Optional[int] = None,
    target: Optional[str] = None,
    pushback_prompt: Optional[str] = None,
    reasoning: str = "test verdict",
) -> GMAwareness:
    """Build a GMAwareness verdict for tests."""
    return GMAwareness(
        intent_type=intent,
        action_type=action,
        roll_necessity=roll_necessity,
        declares_outcome=declares_outcome,
        violates_causality=violates_causality,
        severity=severity,
        reasons=list(reasons or []),
        action=causality_action,
        suggested_stat=suggested_stat,
        suggested_dc=suggested_dc,
        target=target,
        pushback_prompt=pushback_prompt,
        reasoning=reasoning,
    )


def trivial_attempt() -> GMAwareness:
    """A routine action that needs no roll (look around, walk, simple speech)."""
    return make_verdict(
        intent=IntentType.ACTION,
        action=ActionType.EXPLORATION,
        roll_necessity=RollNecessity.TRIVIAL,
        suggested_stat="Wisdom",
        suggested_dc=10,
        reasoning="Routine observation — no stakes.",
    )


def trivial_dialogue() -> GMAwareness:
    """Low-stakes social exchange (greeting, body language)."""
    return make_verdict(
        intent=IntentType.DIALOGUE,
        action=ActionType.DIALOGUE,
        roll_necessity=RollNecessity.TRIVIAL,
        reasoning="Low-stakes speech — no roll needed.",
    )


def propose_persuasion() -> GMAwareness:
    """Stakes-bearing dialogue that needs a roll."""
    return make_verdict(
        intent=IntentType.DIALOGUE,
        action=ActionType.DIALOGUE,
        roll_necessity=RollNecessity.PROPOSE_ROLL,
        suggested_stat="Charisma",
        suggested_dc=12,
        reasoning="Persuasion with stakes — offer the roll.",
    )


def propose_stealth() -> GMAwareness:
    """Stealth past danger."""
    return make_verdict(
        intent=IntentType.ACTION,
        action=ActionType.STEALTH,
        roll_necessity=RollNecessity.PROPOSE_ROLL,
        suggested_stat="Dexterity",
        suggested_dc=14,
        reasoning="Sneaking past danger — offer the roll.",
    )


def contested_attack() -> GMAwareness:
    """Combat action — roll now."""
    return make_verdict(
        intent=IntentType.ACTION,
        action=ActionType.COMBAT,
        roll_necessity=RollNecessity.CONTESTED,
        suggested_stat="Strength",
        suggested_dc=12,
        reasoning="Combat — roll immediately.",
    )


def contested_shoot() -> GMAwareness:
    """Ranged attack — roll now."""
    return make_verdict(
        intent=IntentType.ACTION,
        action=ActionType.COMBAT,
        roll_necessity=RollNecessity.CONTESTED,
        suggested_stat="Dexterity",
        suggested_dc=12,
        reasoning="Ranged attack — roll immediately.",
    )


def contested_spell() -> GMAwareness:
    """Casting a spell — contested."""
    return make_verdict(
        intent=IntentType.ACTION,
        action=ActionType.COMBAT,
        roll_necessity=RollNecessity.CONTESTED,
        suggested_stat="Intelligence",
        suggested_dc=13,
        reasoning="Spellcasting — contested roll.",
    )


def query_intent(question: str = "Is the door locked?") -> GMAwareness:
    """World-truth question → Oracle route."""
    return make_verdict(
        intent=IntentType.QUERY,
        action=ActionType.NONE,
        roll_necessity=RollNecessity.TRIVIAL,
        reasoning="World-truth question, route to Oracle.",
    )


def ooc_marker() -> GMAwareness:
    """Out-of-character block ((rolling STR))."""
    return make_verdict(
        intent=IntentType.OOC,
        action=ActionType.NONE,
        roll_necessity=RollNecessity.TRIVIAL,
        causality_action=CausalityAction.REQUEST_CLARIFICATION,
        reasoning="OOC block — strip and treat as protocol signal.",
    )


def forced_narrative_accept() -> GMAwareness:
    """Player declared a low-stakes outcome — accept."""
    return make_verdict(
        intent=IntentType.ACTION,
        action=ActionType.MOVEMENT,
        roll_necessity=RollNecessity.TRIVIAL,
        declares_outcome=True,
        causality_action=CausalityAction.ACCEPT,
        reasoning="Player declared low-stakes outcome — accept.",
    )


def forced_narrative_pushback(stat: str = "Strength", dc: int = 15) -> GMAwareness:
    """Player declared an outcome that violates causality — push back."""
    return make_verdict(
        intent=IntentType.ACTION,
        action=ActionType.COMBAT,
        roll_necessity=RollNecessity.PROPOSE_ROLL,
        declares_outcome=True,
        violates_causality=True,
        severity=Severity.MAJOR,
        reasons=["Killing without a roll requires a check."],
        causality_action=CausalityAction.PUSH_BACK,
        suggested_stat=stat,
        suggested_dc=dc,
        pushback_prompt=f"Roll {stat} (DC {dc}) to land the killing blow.",
        reasoning="Combat declaration without a roll — push back.",
    )


def deus_ex_machina() -> GMAwareness:
    """Player introduced an object that doesn't exist."""
    return make_verdict(
        intent=IntentType.ACTION,
        action=ActionType.NONE,
        roll_necessity=RollNecessity.TRIVIAL,
        declares_outcome=True,
        violates_causality=True,
        severity=Severity.DEUS_EX_MACHINA,
        reasons=["The key was never established as part of the character."],
        causality_action=CausalityAction.REQUEST_CLARIFICATION,
        pushback_prompt="Where did the key come from?",
        reasoning="Deus ex machina — clarify the source.",
    )
