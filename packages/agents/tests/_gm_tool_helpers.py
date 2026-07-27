"""
Shared helpers for the gm_tools test suite.

Provides the hermetic loop bridge so DSPy-style sync tool calls can resolve
async implementations without a real event loop coordinator.

(The former ``force_intent_for_tool`` / ``force_roll_for_tool`` helpers were
removed with the roll + intent classifiers — the GMAgent LLM emits those
verdicts directly now, so there are no classifier tools to stub.)
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any

from monitor_agents.gm_tools.registry import (
    reset_loop_bridge,
    set_loop_bridge,
)


def _run_sync_via_asyncio(coro: Any) -> Any:
    """Test-time loop bridge: run the coroutine via ``asyncio.run``.

    DSPy ReAct wants sync tool calls; our tool implementations submit
    coroutines to "the loop". In tests there is no GMAgent-supplied loop,
    so ``asyncio.run`` is the simplest valid bridge.
    """
    return asyncio.run(coro)


@contextmanager
def gm_tools_bridge():
    """Install the test-time loop bridge for the duration of the with-block."""
    set_loop_bridge(_run_sync_via_asyncio)
    try:
        yield
    finally:
        reset_loop_bridge()
