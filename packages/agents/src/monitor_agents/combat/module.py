"""
DSPy signatures and modules for the Combat agent (CF-9).

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_agents.dspy_runtime

The three optional LLM bits only — every state transition stays in plain code
(``mongodb_combat_*`` tools). Each signature is a prompt test surface: the
inputs are the JSON state, the output is typed.
"""

from __future__ import annotations

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for


class InitiativeNarrationSignature(dspy.Signature):  # type: ignore[misc]
    """Announce the initiative order for a tabletop combat encounter.

    One short paragraph a GM can read aloud: who acts first, notable ties
    broken, and which combatants are holding back (no roll). Do not invent
    mechanical effects — only report the order you were given.
    """

    combatants_json: str = dspy.InputField(
        desc="JSON list of {name, side, initiative, tiebreak} in the order they will act"
    )

    narration: str = dspy.OutputField(desc="2-4 sentences announcing the order")


class ConditionExplanationSignature(dspy.Signature):  # type: ignore[misc]
    """Explain what a tabletop condition tag means when the bound game system
    has no structured definition for it.

    Be concrete about typical table use, and say plainly that this is general
    guidance rather than the system's own rule when the system text is absent.
    """

    condition: str = dspy.InputField(desc="Condition tag to explain (e.g. 'poisoned')")
    system_context: str = dspy.InputField(
        desc="Name of the bound game system, or 'none' when no system is bound",
        default="none",
    )

    explanation: str = dspy.OutputField(desc="2-3 sentences explaining the condition")


class EncounterSummarySignature(dspy.Signature):  # type: ignore[misc]
    """Summarize a finished tabletop combat encounter for the GM's records.

    Report only what is in the state JSON: rounds lasted, who fell, who walked
    away hurt. No invented loot, XP, or faction consequences — those are the
    GM's to stage.
    """

    state_json: str = dspy.InputField(desc="JSON of the final encounter state")

    summary: str = dspy.OutputField(desc="3-5 sentences summarizing the encounter")


class CombatModule(dspy.Module):  # type: ignore[misc]
    """Combat LLM bits: initiative narration, condition fallback, end summary."""

    def __init__(self) -> None:
        super().__init__()
        self.narrate = dspy.ChainOfThought(InitiativeNarrationSignature)
        self.explain = dspy.ChainOfThought(ConditionExplanationSignature)
        self.summarize = dspy.ChainOfThought(EncounterSummarySignature)

    def narrate_initiative(self, combatants_json: str, role: ModelRole | None = None) -> str:
        with dspy_context_for("combat", role or ModelRole.LIGHT):
            prediction = self.narrate(combatants_json=combatants_json)
        return str(prediction.narration)

    def explain_condition(self, condition: str, system_context: str, role: ModelRole | None = None) -> str:
        with dspy_context_for("combat", role or ModelRole.LIGHT):
            prediction = self.explain(condition=condition, system_context=system_context)
        return str(prediction.explanation)

    def summarize_encounter(self, state_json: str, role: ModelRole | None = None) -> str:
        with dspy_context_for("combat", role or ModelRole.LIGHT):
            prediction = self.summarize(state_json=state_json)
        return str(prediction.summary)
