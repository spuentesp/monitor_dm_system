"""
Hermetic stack for behavior tests — the real tool path, fake databases.

The "basic workings" tests must exercise the *shipped* code path, not a
pile of hand-written doubles: an agent calls a tool, the tool validates its
arguments, the tool talks to a store, and the agent reads the result back.
This module provides exactly that, minus the databases and the network:

- **Mongo** — a real ``mongomock`` client installed as the module-level
  singleton, so every ``mongodb_*`` tool in the data layer runs for real
  (validation, defaults, upserts, status transitions).
- **MCP** — ``monitor_data.server.call_tool`` is replaced by a dispatcher
  that keeps the server's authority check and argument validation, calls the
  real registered tool function, and formats the reply exactly like the
  server does. Individual tools can be overridden per test (mostly for the
  Neo4j-backed ones, whose Cypher is not worth re-implementing here).
- **Neo4j / Postgres** — untouched; the tests that need them either stub
  the specific tool or do not touch them at all.

Everything is per-test: the fixtures restore the previous singletons.
"""

from __future__ import annotations

import json
from typing import Any

import mongomock
from monitor_data.db import mongodb as mongodb_module
from monitor_data.db.mongodb import MongoDBClient

# The collections the shipped tools write to. mongomock creates them lazily,
# but pre-creating them keeps ``list_collection_names`` stable for tools that
# check for a collection's presence.
_COLLECTIONS = (
    "scenes",
    "turns",
    "stories",
    "proposed_changes",
    "memories",
    "player_shares",
    "shared_artifacts",
    "combat_sessions",
    "world_clocks",
    "session_entries",
    "story_ledger",
    "arc_recaps",
    "characters",
    "parties",
    "documents",
)


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


def _format_result(result: Any) -> str:
    """Format a tool result the way the MCP server does."""
    if hasattr(result, "model_dump_json"):
        return result.model_dump_json(indent=2)
    if hasattr(result, "json") and not isinstance(result, (list, dict, str)):
        return result.json(indent=2)
    return json.dumps(_jsonable(result), indent=2, default=str)


class _NullNeo4j:
    """A graph client that answers every read with "nothing there".

    The Cypher MONITOR writes is not worth re-implementing here: the tests
    that need graph content override the specific ``neo4j_*`` tool, and the
    rest only need the graph to be *quiet*.
    """

    def execute_read(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        # A story-existence probe answers "yes" — the graph is the quiet
        # part of the fixture, not a second source of truth.
        if "Story" in query and parameters and "story_id" in parameters:
            return [{"story_id": parameters["story_id"]}]
        return []

    def execute_write(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return []

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return []

    async def run_read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return []

    async def run_write(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return []

    async def verify_connectivity(self) -> bool:
        return False

    async def close(self) -> None:
        return None


class HermeticStack:
    """Real MCP tool path over fake databases.

    Attributes:
        mongo: the mongomock client standing in for MongoDB.
        overrides: tool name → replacement value or callable. A callable is
            awaited when it is a coroutine function and called with the
            tool arguments otherwise.
        calls: ``(tool_name, arguments)`` for every dispatch, in order.
    """

    def __init__(self) -> None:
        self.mongo = mongomock.MongoClient()
        db = self.mongo["monitor"]
        for name in _COLLECTIONS:
            db.create_collection(name)
        self.overrides: dict[str, Any] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._previous_mongo: MongoDBClient | None = None

    # -- store helpers ---------------------------------------------------

    def collection(self, name: str) -> Any:
        """The mongomock collection for ``name``."""
        return self.mongo["monitor"][name]

    def seed(self, name: str, docs: list[dict[str, Any]]) -> None:
        """Insert documents into a collection."""
        if docs:
            self.collection(name).insert_many(docs)

    def override(self, tool_name: str, value: Any) -> None:
        """Replace one tool's result for the duration of the test."""
        self.overrides[tool_name] = value

    def calls_to(self, tool_name: str) -> list[dict[str, Any]]:
        """Every argument dict passed to ``tool_name``."""
        return [args for name, args in self.calls if name == tool_name]

    def called(self, tool_name: str) -> bool:
        """Whether ``tool_name`` was dispatched at least once."""
        return any(name == tool_name for name, _ in self.calls)

    # -- installation ----------------------------------------------------

    def install(self, monkeypatch: Any) -> "HermeticStack":
        """Point the data layer at the fake databases and the dispatcher."""
        import sys

        from monitor_data import server as server_module

        client = MongoDBClient()
        client._client = self.mongo  # type: ignore[assignment]
        client._db = self.mongo["monitor"]  # type: ignore[assignment]
        client._indexes_created = True

        self._previous_mongo = mongodb_module._mongodb_client_instance
        mongodb_module._mongodb_client_instance = client

        # The tool modules bind ``get_mongodb_client`` at import time, so the
        # singleton alone is not enough — re-point every binding at our
        # mongomock-backed client. The graph client gets the same treatment:
        # a quiet one, so no test ever dials a real socket.
        null_graph = _NullNeo4j()
        for module in list(sys.modules.values()):
            name = getattr(module, "__name__", "")
            if not name.startswith(("monitor_data", "monitor_agents", "monitor_ui")):
                continue
            if module is None:
                continue
            if hasattr(module, "get_mongodb_client"):
                monkeypatch.setattr(module, "get_mongodb_client", lambda: client)
            if hasattr(module, "get_neo4j_client"):
                monkeypatch.setattr(module, "get_neo4j_client", lambda: null_graph)

        monkeypatch.setattr(server_module, "call_tool", self._dispatch)
        return self

    def uninstall(self) -> None:
        """Restore the previous Mongo singleton."""
        mongodb_module._mongodb_client_instance = self._previous_mongo
        self._previous_mongo = None

    # -- the dispatcher --------------------------------------------------

    async def _dispatch(self, name: str, arguments: dict[str, Any]) -> list[Any]:
        """Stand-in for ``monitor_data.server.call_tool``."""
        from mcp.types import TextContent

        from monitor_data.middleware.auth import check_authority
        from monitor_data.middleware.validation import validate_tool_input
        from monitor_data.server import TOOL_REGISTRY

        args = dict(arguments)
        agent_type = args.pop("agent_type", "Unknown")
        args.pop("agent_id", None)
        self.calls.append((name, args))

        if name in self.overrides:
            override = self.overrides[name]
            if callable(override):
                result = override(**args)
                if hasattr(result, "__await__"):
                    result = await result
            else:
                result = override
            return [TextContent(type="text", text=_format_result(result))]

        tool_func = TOOL_REGISTRY.get(name)
        if tool_func is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        if not check_authority(name, agent_type):
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Authorization error: Agent '{agent_type}' is not authorized to call "
                        f"'{name}'."
                    ),
                )
            ]

        try:
            validated = validate_tool_input(name, tool_func, args)
        except Exception as exc:  # noqa: BLE001  # reason: mirrors the server's error text
            return [TextContent(type="text", text=f"Validation error: {exc}")]

        try:
            if hasattr(tool_func, "__call__") and _is_async(tool_func):
                result = await tool_func(**validated)
            else:
                result = tool_func(**validated)
        except Exception as exc:  # noqa: BLE001  # reason: mirrors the server's error text
            return [TextContent(type="text", text=f"Error executing tool: {exc!s}")]

        return [TextContent(type="text", text=_format_result(result))]


def _is_async(fn: Any) -> bool:
    import inspect

    return inspect.iscoroutinefunction(fn)
