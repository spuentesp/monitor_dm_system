"""
Combat agent — at-the-table encounter support for the human GM (CF-9).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.game_system, dspy
CALLED BY: UI backend routers/gm_tools.py (GM Assistant /gm page)

State transitions (start, HP math, initiative order, rounds, end) are plain
code: they delegate to the session-combat MongoDB tools over MCP — never an
LLM call, never a Neo4j write. The optional LLM bits (initiative narration,
condition explanation fallback, end-of-encounter summary) live in the
co-located DSPy module.
"""

from monitor_agents.combat.agent import (
    ConditionExplanation,
    CombatAgent,
    _raise_on_tool_error,
)
from monitor_agents.combat.module import CombatModule

__all__ = [
    "CombatAgent",
    "CombatModule",
    "ConditionExplanation",
    "_raise_on_tool_error",
]
