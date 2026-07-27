"""
GM tools — typed tool surface the GM agent can call.

LAYER: 2 (agents)
IMPORTS FROM: data-layer (embeddings), stdlib, semantic classifiers
CALLED BY: GMAgent (dspy.ReAct host)

This package is the architectural surface that turns the existing semantic
classifiers from "authorities the resolver composes from" into "sensors the
GM consults when uncertain." The classifiers themselves don't change — same
embeddings, same anchors, same fail-loud contract — they just get wrapped
as DSPy-compatible tools the ReAct loop can invoke.

Each module adds one concern:
* ``semantic``    — text-based semantic classifiers (intent / roll necessity /
                    action routing) wrapped as tools.
* ``scene_state`` — the perfect-recall-of-playable-actions tool (structured
                    retrieval, no LLM).
* ``conditions``  — active conditions / condition-trigger evaluation.
* ``dice``        — promote monitor_data.utils.dice.roll_dice to a tool.
* ``oracle``      — promote monitor_agents.oracle.Oracle().resolve_question.
* ``contracts``   — typed schemas shared across tools (GMVerdict, etc.).
* ``registry``    — GM_TOOLS = [...], the list dspy.ReAct consumes.

LOOP BRIDGING
-------------
DSPy ReAct runs synchronously inside ``asyncio.to_thread`` (the GMAgent's
predictor is blocking — it calls litellm). The tool functions here are
sync wrappers that run their async implementation by delegating back to the
host event loop via a callable the GMAgent injects at startup
(``set_loop_bridge(call_soon_threadsafe)``). Tests can swap this bridge for a
no-op (``run_coroutine_sync``).
"""

from .contracts import GMVerdict, ToolFailurePolicy
from .registry import GM_TOOLS, get_tool, run_coroutine_sync, set_loop_bridge

__all__ = [
    "GM_TOOLS",
    "GMVerdict",
    "ToolFailurePolicy",
    "get_tool",
    "run_coroutine_sync",
    "set_loop_bridge",
]
