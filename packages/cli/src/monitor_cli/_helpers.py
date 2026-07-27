"""
Shared CLI helpers — eliminate duplication across command modules.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2)
NEVER IMPORTS: monitor_data (Layer 1)
"""

import asyncio
import json
from collections.abc import Coroutine
from typing import Any

from monitor_agents.resolver import Resolver


def get_resolver() -> Resolver:
    """Return a Resolver agent instance for CLI commands."""
    return Resolver()


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from synchronous CLI handlers."""
    return asyncio.run(coro)


def parse_tool_result(raw: Any) -> dict[str, Any]:
    """Parse a tool result that may be a JSON string or already-parsed dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            res = json.loads(raw)
            if isinstance(res, dict):
                return res
            return {"result": res}
        except json.JSONDecodeError:
            return {"text": raw}
    return {"text": str(raw)}
