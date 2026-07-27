"""
DSPy Signature and Module for the CanonKeeper agent (reasoning chain only).

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_data schemas

CanonKeeper uses instructor for the final CanonKeeperVerdict (strict schema),
but uses a DSPy ChainOfThought module to reason about *whether* to accept a
proposed change before passing that reasoning to instructor.

This two-step pattern is recommended by LIBRARY_PLAN §1.2:
  candidate_reasoning = CanonKeeperReasoningModule()(proposal)
  verdict = call_llm_structured(CanonKeeperVerdict, reasoning_messages)

The reasoning module lives here; the instructor call lives in canonkeeper.py.
"""

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for

# =============================================================================
# SIGNATURES
# =============================================================================


class CanonKeeperReasoningSignature(dspy.Signature):  # type: ignore[misc]
    """
    Reason about whether a proposed world-state change is consistent with
    established canon before making a final accept/reject decision.

    The CanonKeeper is the sole arbiter of narrative truth.  Check each
    proposal against known entities, confirmed facts, and active story arcs.
    """

    # Inputs
    proposal_summary: str = dspy.InputField(desc="Human-readable description of the proposed world-state change")
    proposal_content: str = dspy.InputField(
        desc="JSON details of the proposed change (entity type, properties, relationships)"
    )
    existing_canon: str = dspy.InputField(desc="JSON excerpt of relevant Neo4j entities and facts already in canon")
    story_arcs: str = dspy.InputField(desc="Active story arcs and their current states that may be affected")

    # Output: chain-of-thought reasoning (used as context for the instructor call)
    reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step analysis of: "
            "(1) Does this contradict any existing canon? "
            "(2) Does it advance or derail active story arcs? "
            "(3) Is it internally consistent with the world's rules? "
            "Conclude with ACCEPT or REJECT and a one-sentence justification."
        )
    )


class PolicyCheckSignature(dspy.Signature):  # type: ignore[misc]
    """
    Check whether a proposed change violates any hard system policies
    (e.g. killing a protected entity, breaking world-rules).
    """

    proposal_content: str = dspy.InputField(desc="JSON details of the proposed change")
    protected_entities: str = dspy.InputField(
        desc="JSON list of entity IDs that are protected from deletion/modification"
    )
    world_rules: str = dspy.InputField(desc="Bullet list of configured world rules (tone, content flags, etc.)")

    violation_found: str = dspy.OutputField(desc="'YES' or 'NO' — whether a policy violation was found")
    violation_detail: str = dspy.OutputField(desc="Brief description of the violation, or 'none' if no violation")


# =============================================================================
# MODULES
# =============================================================================


class CanonKeeperReasoningModule(dspy.Module):  # type: ignore[misc]
    """
    Step 1 of CanonKeeper decision pipeline — reason about canon consistency.

    The output `reasoning` field is inserted into the message history for the
    subsequent instructor call that produces the final CanonKeeperVerdict.
    """

    def __init__(self) -> None:
        super().__init__()
        self.reason = dspy.ChainOfThought(CanonKeeperReasoningSignature)

    def forward(
        self,
        proposal_summary: str,
        proposal_content: str,
        existing_canon: str,
        story_arcs: str,
    ) -> dspy.Prediction:
        with dspy_context_for("canonkeeper", ModelRole.HEAVY):
            return self.reason(
                proposal_summary=proposal_summary,
                proposal_content=proposal_content,
                existing_canon=existing_canon,
                story_arcs=story_arcs,
            )


class PolicyCheckModule(dspy.Module):  # type: ignore[misc]
    """
    Fast policy gate — runs before full reasoning to short-circuit hard blocks.
    Uses simple Predict (no chain-of-thought) for speed.
    """

    def __init__(self) -> None:
        super().__init__()
        self.check = dspy.Predict(PolicyCheckSignature)

    def forward(
        self,
        proposal_content: str,
        protected_entities: str,
        world_rules: str,
    ) -> dspy.Prediction:
        with dspy_context_for("canonkeeper", ModelRole.LIGHT):
            return self.check(
                proposal_content=proposal_content,
                protected_entities=protected_entities,
                world_rules=world_rules,
            )
