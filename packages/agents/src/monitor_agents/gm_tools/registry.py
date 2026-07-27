"""
GM_TOOLS registry — the list dspy.ReAct consumes.

The registry holds:
* ``GM_TOOLS``: ordered list of tool functions DSPy can discover.
* A loop-bridge so sync tools can call async classifier implementations.
* ``get_tool(name)`` for lookup (used by tests + observability).
* ``set_loop_bridge(call)``: install the host event-loop bridge at startup.
* ``run_coroutine_sync(coro)``: block until the coroutine resolves.

WHY A CUSTOM BRIDGE
-------------------
DSPy ReAct is synchronous — it calls tool functions directly, with no await.
Our classifier implementations are async (they hit the embeddings provider).
Bridging the two is the whole problem.

The GMAgent runs its ReAct call inside ``asyncio.to_thread`` so the host
event loop keeps spinning. From the tool's perspective, it needs to *submit*
the coroutine to that loop and wait for the result. The standard answer is
``asyncio.run_coroutine_threadsafe`` — but that requires knowing the loop,
which is established by the GMAgent at startup.

For tests (no GMAgent) the bridge defaults to ``run_coroutine_sync`` =
``asyncio.run``-the-coroutine directly. DSPy's ReAct still runs in a thread
(via ``to_thread``), so ``asyncio.run`` from inside a thread creates a fresh
loop — works but doesn't share state with the test runner. For the agents
test suite this is fine because the hermetic env has no real embeddings to
coordinate with.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Coroutine
from typing import Any

RunSyncFn = Callable[[Coroutine[Any, Any, Any]], Any]
"""Bridge signature: schedule a coroutine on the host loop and return its result synchronously."""


# ---------------------------------------------------------------------------
# Loop bridge
# ---------------------------------------------------------------------------


_run_sync: RunSyncFn = asyncio.run  # default: hermetic / test bridge
_loop_set: bool = False


def set_loop_bridge(call: RunSyncFn) -> None:
    """Install a custom bridge (the GMAgent calls this on startup).

    The bridge must be safe to call from any thread — DSPy ReAct runs
    inside ``asyncio.to_thread`` so the tool function may execute in a
    worker thread, not the main loop's thread.
    """
    global _run_sync, _loop_set
    _run_sync = call
    _loop_set = True


def reset_loop_bridge() -> None:
    """Reset to the default ``asyncio.run`` bridge (test isolation)."""
    global _run_sync, _loop_set
    _run_sync = asyncio.run
    _loop_set = False


def run_coroutine_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Submit a coroutine through the installed bridge and return its result.

    The default bridge (``asyncio.run``) is intended for tests; the GMAgent
    overrides this with ``asyncio.run_coroutine_threadsafe`` so the host
    event loop keeps handling requests while DSPy's synchronous ReAct loop
    blocks awaiting tool results.
    """
    if not inspect.iscoroutine(coro):
        # Defensive: tools may be invoked with plain values too.
        return coro
    return _run_sync(coro)


# ---------------------------------------------------------------------------
# Build a loop bridge that talks to the GMAgent's running event loop
# ---------------------------------------------------------------------------


def build_loop_bridge_from_running_loop() -> RunSyncFn:
    """Return a bridge that schedules on the currently-running event loop.

    The GMAgent calls this once during startup; from then on every tool
    invocation crosses the loop boundary cleanly. If no loop is running
    (e.g. a sync test context) this raises — callers should test for that
    case and fall back to ``asyncio.run``.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:  # no running loop
        raise RuntimeError(
            "GMAgent tried to build a loop bridge but no event loop is running; "
            "this is a programming error — wrap ReAct in async context."
        ) from exc

    def _bridge(coro: Coroutine[Any, Any, Any]) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        # block_until_done() returns the result or raises. We block the calling
        # thread (which is the DSPy ReAct thread inside asyncio.to_thread); the
        # main event loop spins in parallel and processes the coroutine.
        return future.result()

    return _bridge


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

# Imported lazily to avoid circularity between this package and semantic/scene_state modules.
_GM_TOOLS: list[Any] | None = None


def _build_default_tools() -> list[Any]:
    """Construct the default GM_TOOLS list.

    The actual functions are defined in their respective modules (semantic,
    scene_state, etc.) so this just imports them. Tests can call this to
    get the canonical ordering.
    """
    # The embedding-based classifier tools (classify_intent /
    # classify_roll_necessity / route_action) were removed: the GMAgent LLM
    # emits intent_type / roll_necessity / action_type directly, so a
    # nearest-anchor sensor for those is redundant. Embeddings now serve
    # retrieval only (via the RetrievalService).
    from .conditions import (
        gm_tool_check_conditions,
        gm_tool_list_active_conditions,
    )
    from .dice import gm_tool_roll_dice
    from .oracle import gm_tool_resolve_oracle
    from .scene_state import (
        gm_tool_evaluate_scenery,
        gm_tool_get_scene_state,
        gm_tool_list_playable_actions,
    )

    return [
        # Scene state (perfect recall — no LLM)
        gm_tool_get_scene_state(),
        gm_tool_list_playable_actions(),
        gm_tool_evaluate_scenery(),
        # Conditions
        gm_tool_check_conditions(),
        gm_tool_list_active_conditions(),
        # Dice + oracle (mechanical ground truth)
        gm_tool_roll_dice(),
        gm_tool_resolve_oracle(),
    ]


def _ensure_built() -> list[Any]:
    global _GM_TOOLS
    if _GM_TOOLS is None:
        _GM_TOOLS = _build_default_tools()
    return _GM_TOOLS


def GM_TOOLS() -> list[Any]:
    """Return the canonical tool list. Cached at first call; tests can pin via :func:`reset_tools`."""
    return list(_ensure_built())


def get_tool(name: str) -> Any:
    """Lookup a tool by name. Used by tests for explicit invocation."""
    for t in _ensure_built():
        n = getattr(t, "name", None) or getattr(t, "__name__", None)
        if n == name:
            return t
    raise KeyError(
        f"No GM tool named {name!r}; available: {[getattr(t, 'name', getattr(t, '__name__', '?')) for t in _ensure_built()]}"
    )


def reset_tools() -> None:
    """Drop the cached tool list (test isolation when subclassing tools)."""
    global _GM_TOOLS
    _GM_TOOLS = None
