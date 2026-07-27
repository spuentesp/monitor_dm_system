"""
Oracle tool — wrap ``monitor_agents.oracle.Oracle.resolve_question`` for dspy.
"""

from __future__ import annotations

import json
from typing import Any

import dspy


def _resolve_oracle_sync(
    question: str,
    likelihood: str = "fifty_fifty",
    tension_score: float = 0.5,
) -> dict[str, Any]:
    """Synchronous oracle resolver — runs once per question."""
    # Avoid a circular import at module-load time by importing lazily.
    from monitor_agents.oracle import Likelihood, Oracle

    try:
        like = Likelihood(likelihood)
    except Exception:
        like = Likelihood.FIFTY_FIFTY

    try:
        result = Oracle().resolve_question(question, likelihood=like, tension_score=tension_score)
        # Strip any non-JSON-serializable detail — Oracle already returns a dict.
        return {
            k: (str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v)
            for k, v in result.items()
        }
    except Exception as exc:
        return {"question": question, "error": str(exc), "method": "fail"}


def gm_tool_resolve_oracle() -> Any:
    """Return a ``dspy.Tool`` that resolves a world-truth question.

    Use this when the player asks an in-fiction yes/no question whose answer
    the world doesn't have a hardcoded fact for (P-18 "is the trap armed?").
    """

    def resolve_oracle(question: str, likelihood: str = "fifty_fifty", tension_score: float = 0.5) -> str:
        """Resolve a yes/no world-truth question via the Oracle mechanic.

        ``likelihood`` is one of: nearly_certain, very_likely, likely, fifty_fifty,
        unlikely, very_unlikely, nearly_impossible. ``tension_score`` is 0.0-1.0
        and skews the result: higher makes 'Yes' harder.
        """
        return json.dumps(_resolve_oracle_sync(question, likelihood, tension_score))

    return dspy.Tool(
        resolve_oracle,
        name="resolve_oracle",
        desc=(
            "Resolve a yes/no world-truth question via the Oracle mechanic. Use "
            "when the player asks something the world doesn't have a hardcoded "
            "fact for (e.g. 'is the trap armed?', 'does the guard notice me?'). "
            "The result includes is_yes, outcome label, and whether the result "
            "is exceptional. DO NOT fabricate answers to world-truth questions — "
            "call this tool."
        ),
        args={
            "question": {"type": "string", "description": "The yes/no question to resolve."},
            "likelihood": {
                "type": "string",
                "description": "Prior likelihood (see docstring). Defaults to fifty_fifty.",
                "default": "fifty_fifty",
            },
            "tension_score": {
                "type": "number",
                "description": "Tension 0.0-1.0; higher skews against Yes.",
                "default": 0.5,
            },
        },
    )
