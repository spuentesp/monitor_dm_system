"""
Tool contracts — typed input/output schemas shared across gm_tools.

These are the *returned-shape* contracts, not the full Pydantic models the
GM uses internally. We keep them small and tool-shaped so the registry can
advertise them cleanly to dspy.ReAct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from monitor_agents.gm_awareness import ActionType, CausalityAction, IntentType, RollNecessity


class ToolFailurePolicy(StrEnum):
    """How the GM agent should react when a tool raises.

    * ``RAISE`` — propagate to caller; the GM loop catches at its boundary
      and falls through to the structured GMAwareness seed.
    * ``RETURN_EMPTY`` — return a benign empty result; the GM uses the seed.
    * ``LOG`` — record the failure on the verdict's tool_calls_made but
      continue running other tools.
    """

    RAISE = "raise"
    RETURN_EMPTY = "return_empty"
    LOG = "log"


@dataclass
class GMVerdict:
    """The GM's decision after the ReAct loop converges.

    Extends today's GMAwareness with action router signals (subsystem_hint,
    stat_recommendation, dc_recommendation), the narrative draft the ReAct
    loop produced, and observability fields so we can see what the agent did.
    """

    # ── Core (from GMAwareness) ──
    intent_type: IntentType
    action_type: ActionType
    roll_necessity: RollNecessity
    causality_action: CausalityAction = CausalityAction.ACCEPT
    suggested_stat: str | None = None
    suggested_dc: int | None = None
    declares_outcome: bool = False
    violates_causality: bool = False
    pushback_prompt: str | None = None

    # ── Causality detail (from GMAwareness) ──
    severity: str = "none"  # "none" | "minor" | "major" | "deus_ex_machina"
    reasons: list[str] = field(default_factory=list)

    # ── Routed (from SemanticActionRouter) ──
    subsystem_hint: str | None = None
    action_route: dict[str, Any] | None = None  # raw action_context dict

    # ── GM's first draft (narrator refines) ──
    narrative_draft: str = ""
    tool_calls_made: list[str] = field(default_factory=list)
    tool_failures: list[str] = field(default_factory=list)
    tool_call_count: int = 0
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for transport over the resolver boundary."""
        return {
            "intent_type": self.intent_type.value,
            "action_type": self.action_type.value,
            "roll_necessity": self.roll_necessity.value,
            "causality_action": self.causality_action.value,
            "suggested_stat": self.suggested_stat,
            "suggested_dc": self.suggested_dc,
            "declares_outcome": self.declares_outcome,
            "violates_causality": self.violates_causality,
            "pushback_prompt": self.pushback_prompt,
            "severity": self.severity,
            "reasons": list(self.reasons),
            "subsystem_hint": self.subsystem_hint,
            "action_route": self.action_route,
            "narrative_draft": self.narrative_draft,
            "tool_calls_made": list(self.tool_calls_made),
            "tool_failures": list(self.tool_failures),
            "tool_call_count": self.tool_call_count,
            "reasoning": self.reasoning,
        }
