"""
Fake MCP client — re-exported from tests/conftest.py for the mocks package.

This module provides the same FakeMCPClient that was originally defined in
tests/conftest.py, but in the mocks package for better organization.

The original in tests/conftest.py is kept for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeCall:
    """Record of a single MCP tool call."""

    name: str
    params: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)


class _CallToolProxy:
    """Mock-style proxy for tests that use call_tool.return_value / side_effect."""

    def __init__(self, parent: FakeMCPClient) -> None:
        self._parent = parent

    @property
    def return_value(self) -> Any:
        return self._parent._call_tool_return_value

    @return_value.setter
    def return_value(self, value: Any) -> None:
        self._parent._call_tool_return_value = value
        self._parent._call_tool_mode = "return_value"

    @property
    def side_effect(self) -> Any:
        return self._parent._call_tool_side_effect

    @side_effect.setter
    def side_effect(self, value: Any) -> None:
        self._parent._call_tool_side_effect = value
        self._parent._call_tool_mode = "side_effect"

    @property
    def call_args(self) -> Any:
        if self._parent._call_tool_last_args is None:
            return None
        tool_name, params = self._parent._call_tool_last_args
        return ((tool_name, params),)

    @property
    def call_count(self) -> int:
        return self._parent._call_tool_call_count

    def assert_called_once(self) -> None:
        assert self._parent._call_tool_call_count == 1, (
            f"Expected call_tool to be called once, but it was called "
            f"{self._parent._call_tool_call_count} times"
        )

    def assert_called_once_with(self, *args: Any, **kwargs: Any) -> None:
        self.assert_called_once()
        expected_name = args[0] if args else kwargs.get("tool_name")
        last_args = self._parent._call_tool_last_args
        assert last_args is not None, "call_tool was never called"
        actual_name, _ = last_args
        assert actual_name == expected_name, (
            f"Expected tool name {expected_name!r}, got {actual_name!r}"
        )

    def assert_called(self) -> None:
        assert self._parent._call_tool_call_count >= 1

    @property
    def call_args_list(self) -> list:
        return [
            ((tool_name, params),)
            for tool_name, params in self._parent._call_tool_all_args
        ]

    async def __call__(
        self, tool_name: str, params: dict[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        self._parent._call_tool_call_count += 1
        self._parent._call_tool_last_args = (tool_name, params or {})
        self._parent._call_tool_all_args.append((tool_name, params or {}))

        if self._parent._call_tool_mode == "side_effect":
            se = self._parent._call_tool_side_effect
            if callable(se):
                result = se(tool_name, params or {})
                if hasattr(result, "__aiter__") or hasattr(result, "__await__"):
                    return await result
                return result
            elif isinstance(se, list):
                item = se.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item
            elif isinstance(se, Exception):
                raise se
            return se

        if self._parent._call_tool_mode == "return_value":
            return self._parent._call_tool_return_value

        effective_name = tool_name
        if effective_name in self._parent.responses:
            resp = self._parent.responses[effective_name]
            if isinstance(resp, Exception):
                raise resp
            return resp

        raise NotImplementedError(f"No fake response configured for {tool_name}")


@dataclass
class FakeMCPClient:
    """Fake MCP client that records calls and supports multiple stub patterns.

    Supports three usage patterns:

    1. **Direct call()** — pre-configure responses via responses dict or
       add_response() / add_error():

           fake_mcp_client.add_response("neo4j_get_universe", {}, {"id": "..."})
           result = await fake_mcp_client.call("neo4j_get_universe", {"id": "..."})

    2. **Mock-style call_tool** — use return_value / side_effect:

           fake_mcp_client.call_tool.return_value = {"id": "..."}
           result = await fake_mcp_client.call_tool("neo4j_get_universe", {"id": "..."})

    3. **Mock-style call_tool** with side_effect:

           fake_mcp_client.call_tool.side_effect = Exception("not found")
    """

    _calls: list[FakeCall] = field(default_factory=list)
    responses: dict[str, Any] = field(default_factory=dict)
    _call_tool_return_value: Any = field(default=None, repr=False)
    _call_tool_side_effect: Any = field(default=None, repr=False)
    _call_tool_mode: str = field(default="responses", repr=False)
    _call_tool_last_args: Any = field(default=None, repr=False)
    _call_tool_call_count: int = field(default=0, repr=False)
    _call_tool_all_args: list = field(default_factory=list, repr=False)

    def add_response(self, tool_name: str, params: dict[str, Any], result: Any) -> None:
        """Pre-configure a successful response for a specific tool call."""
        self.responses[tool_name] = result

    def add_error(
        self, tool_name: str, params: dict[str, Any], exception: Exception
    ) -> None:
        """Pre-configure an error response for a specific tool call."""
        self.responses[tool_name] = exception

    @property
    def call_tool(self) -> _CallToolProxy:
        """Mock-style proxy for tests using call_tool.return_value / call_tool.side_effect."""
        return _CallToolProxy(self)

    async def call(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any:
        ctx = context or {}
        self._calls.append(FakeCall(tool_name, params, ctx))
        if tool_name in self.responses:
            resp = self.responses[tool_name]
            if isinstance(resp, Exception):
                raise resp
            return resp
        raise NotImplementedError(f"No fake response configured for {tool_name}")


def make_mock_mcp_client() -> FakeMCPClient:
    """Return a FakeMCPClient pre-loaded with default tool responses."""
    client = FakeMCPClient()
    client.add_response(
        "neo4j_get_entity",
        {},
        {
            "id": "entity-123",
            "name": "Test Entity",
            "type": "character",
            "description": "A test entity",
            "universe_id": "universe-123",
        },
    )
    client.add_response(
        "neo4j_get_universe",
        {},
        {
            "id": "universe-123",
            "name": "Test Universe",
            "description": "A test universe",
            "multiverse_id": "multiverse-001",
        },
    )
    client.add_response(
        "neo4j_list_entities",
        {},
        [
            {
                "id": "char-001",
                "name": "Test Character",
                "type": "character",
                "description": "A test character",
            }
        ],
    )
    client.add_response(
        "neo4j_list_archetypes",
        {},
        [
            {
                "id": "archetype-001",
                "name": "Warrior",
                "entity_type": "archetype",
                "description": "A fighter archetype",
            }
        ],
    )
    client.add_response(
        "neo4j_create_entity", {}, "550e8400-e29b-41d4-a716-446655440000"
    )
    client.add_response(
        "neo4j_create_relationship", {}, "650e8400-e29b-41d4-a716-446655440001"
    )
    client.add_response("neo4j_create_story", {}, "story-123")
    client.add_response("mongodb_create_scene", {}, "scene-456")
    client.add_response("mongodb_create_character_sheet", {}, "sheet-789")
    client.add_response("mongodb_append_turn", {}, "turn-789")
    client.add_response("mongodb_create_story_outline", {}, "outline-456")
    client.add_response(
        "qdrant_search",
        {},
        [
            {
                "id": "result-001",
                "score": 0.95,
                "payload": {"content": "Test search result"},
            }
        ],
    )
    return client
