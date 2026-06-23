"""
DSPy modules for verification and contradiction detection.

LAYER: 2 (agents)
IMPORTS FROM: dspy
CALLED BY: CanonKeeper, PlotHookAgent
"""

from __future__ import annotations

import re

import dspy


class ContradictionSignature(dspy.Signature):
    """Check if a new fact contradicts established context."""

    context = dspy.InputField(desc="Established facts and lore that are considered canon.")
    new_fact = dspy.InputField(desc="The new fact to verify against the context.")
    has_contradiction = dspy.OutputField(
        desc="Boolean: True if the new fact contradicts the context, False otherwise."
    )
    explanation = dspy.OutputField(
        desc="If has_contradiction is True, explain why. If False, explain why it's consistent."
    )


class ContradictionModule(dspy.Module):
    """
    Detect contradictions between a new fact and established context.

    Uses ChainOfThought reasoning for more reliable detection.
    """

    def __init__(self) -> None:
        super().__init__()
        self.verify = dspy.ChainOfThought(ContradictionSignature)

    def forward(self, context: str, new_fact: str) -> dict:
        from monitor_agents.dspy_runtime import dspy_context_for
        from monitor_data.schemas.llm_config import ModelRole
        with dspy_context_for("canonkeeper", ModelRole.HEAVY):
            result = self.verify(context=context, new_fact=new_fact)
        # Parse boolean from string output
        has_contradiction = str(result.has_contradiction).strip().lower() in (
            "true",
            "yes",
            "1",
        )
        return {
            "has_contradiction": has_contradiction,
            "explanation": result.explanation,
        }


class BatchContradictionSignature(dspy.Signature):
    """Identify which candidate facts contradict the established canon context.

    Only flag a DIRECT logical contradiction with the context. Do not flag a
    fact merely for adding new, unrelated information.
    """

    context = dspy.InputField(desc="Established canon facts and axioms (the existing world).")
    new_facts = dspy.InputField(
        desc="A numbered list of candidate new facts, one per line, e.g. '1. ...\\n2. ...'."
    )
    contradictions = dspy.OutputField(
        desc=(
            "For each candidate that DIRECTLY contradicts the context, output one line "
            "'INDEX: short reason' using the candidate's number. If none contradict, "
            "output exactly 'NONE'."
        )
    )


class BatchContradictionModule(dspy.Module):
    """
    Detect contradictions for MANY candidate facts against a shared context in a
    single LLM call (chunked by the caller).

    This replaces N per-proposal ContradictionModule calls with one call per
    chunk, which is dramatically cheaper during bulk knowledge-pack ingestion.
    """

    _LINE_RE = re.compile(r"^\s*\(?(\d+)\)?\s*[:.\)\-]\s*(.+?)\s*$")

    def __init__(self) -> None:
        super().__init__()
        self.verify = dspy.ChainOfThought(BatchContradictionSignature)

    def forward(self, context: str, new_facts: str) -> dict:
        """Return {index (1-based): explanation} for contradicting candidates."""
        from monitor_agents.dspy_runtime import dspy_context_for
        from monitor_data.schemas.llm_config import ModelRole

        with dspy_context_for("canonkeeper", ModelRole.HEAVY):
            result = self.verify(context=context, new_facts=new_facts)

        raw = str(getattr(result, "contradictions", "") or "").strip()
        if not raw or raw.strip().upper() == "NONE":
            return {}

        flagged: dict[int, str] = {}
        for line in raw.splitlines():
            m = self._LINE_RE.match(line)
            if not m:
                continue
            idx = int(m.group(1))
            explanation = m.group(2).strip()
            if explanation.upper() != "NONE":
                flagged[idx] = explanation
        return flagged
