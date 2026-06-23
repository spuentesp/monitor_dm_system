"""
DSPy Signatures for the Simulacrum Council (World Advancement).

These signatures define the roles of the Opportunist, Realist, and Reconciler
agents who resolve off-screen faction agency and world ripples.
"""

import dspy


class OpportunistSimulacrumSignature(dspy.Signature):
    """
    You are the Opportunist Simulacrum. Your goal is to maximize narrative
    drama and conflict.

    Given a set of high-impact world events and a faction's agenda, propose
    the most aggressive, bold, or escalating move the faction could make.
    Look for ways to capitalize on chaos, power vacuums, or weakened rivals.
    """

    current_time: str = dspy.InputField(desc="The current date/time in the world.")
    high_impact_events: str = dspy.InputField(
        desc="Recent high-magnitude facts/events from the world."
    )
    faction_name: str = dspy.InputField(desc="The name of the faction acting.")
    faction_agenda: str = dspy.InputField(desc="The current objectives and clocks of the faction.")

    proposed_move: str = dspy.OutputField(desc="A bold, dramatic action or clock advancement.")
    reasoning: str = dspy.OutputField(desc="Why this move creates the best narrative tension.")


class RealistSimulacrumSignature(dspy.Signature):
    """
    You are the Realist Simulacrum. Your goal is to maintain world internal
    logic, logistical groundedness, and believable pacing.

    Given a set of high-impact world events and a faction's agenda, propose
     the most logical, incremental, or protective move the faction could make.
    Consider resource constraints, travel times, and the need for self-preservation.
    """

    current_time: str = dspy.InputField(desc="The current date/time in the world.")
    high_impact_events: str = dspy.InputField(
        desc="Recent high-magnitude facts/events from the world."
    )
    faction_name: str = dspy.InputField(desc="The name of the faction acting.")
    faction_agenda: str = dspy.InputField(desc="The current objectives and clocks of the faction.")

    proposed_move: str = dspy.OutputField(desc="A logical, grounded action or clock advancement.")
    reasoning: str = dspy.OutputField(desc="Why this move is the most believable response.")


class CouncilReconcilerSignature(dspy.Signature):
    """
    You are the Council Reconciler. You take the aggressive proposals of the
    Opportunist and the grounded proposals of the Realist to create a single,
    final world-state change.

    Your goal is to ensure the world moves forward without "exploding" into
    unearned chaos, but while still honoring the impact of player actions.
    """

    opportunist_move: str = dspy.InputField()
    realist_move: str = dspy.InputField()
    world_tone: str = dspy.InputField(desc="The current session tone (e.g., Grim, Heroic).")

    final_decision: str = dspy.OutputField(desc="The final synthesized move.")
    change_type: str = dspy.OutputField(desc="entity_update, create_fact, or clock_advance")
    clock_tick: int = dspy.OutputField(
        desc="Amount to advance/retreat the clock (-2 to +2). Usually 0 or 1."
    )
    summary: str = dspy.OutputField(desc="A concise summary of the outcome.")
