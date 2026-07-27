"""
Shared pytest fixtures and marker behavior for MONITOR.

Markers:
- integration: cross-component; skipped unless RUN_INTEGRATION=1
- e2e: end-to-end/system; skipped unless RUN_E2E=1
"""

from __future__ import annotations

import os

# Only integration/e2e runs may read the real .env (API keys, live DB URIs).
# Hermetic unit runs rely on the fake environment forced by the repo-root
# conftest.py — loading .env here would leak real credentials into unit tests.
if os.getenv("RUN_INTEGRATION") or os.getenv("RUN_E2E"):
    from dotenv import load_dotenv

    load_dotenv()

from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

import pytest


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip integration/e2e tests unless explicitly enabled."""
    if "integration" in item.keywords and not os.getenv("RUN_INTEGRATION"):
        pytest.skip("set RUN_INTEGRATION=1 to run integration tests")
    if "e2e" in item.keywords and not os.getenv("RUN_E2E"):
        pytest.skip("set RUN_E2E=1 to run e2e tests")


@dataclass
class FakeCall:
    name: str
    params: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)


class _CallToolProxy:
    """Mock-style proxy for tests that use ``fake_mcp_client.call_tool.return_value``
    and ``fake_mcp_client.call_tool.side_effect`` patterns.

    Delegates to the parent FakeMCPClient's internal response store so that
    both the old ``call()`` API and the mock-style ``call_tool`` API work
    consistently.
    """

    def __init__(self, parent: FakeMCPClient) -> None:
        self._parent = parent

    @property
    def return_value(self) -> Any:
        """Not directly readable in a useful way — setting it is what matters."""
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
        """Return the last call arguments in mock.call format.

        Returns a tuple of (args_tuple, kwargs_dict) to be compatible
        with unittest.mock call_args format, where:
        - call_args[0] is the positional args tuple
        - call_args[1] is the keyword args dict
        """
        if self._parent._call_tool_last_args is None:
            return None
        tool_name, params = self._parent._call_tool_last_args
        return ((tool_name, params),)

    @property
    def call_count(self) -> int:
        """Return how many times call_tool was invoked."""
        return self._parent._call_tool_call_count

    def assert_called_once(self) -> None:
        """Assert that call_tool was called exactly once."""
        assert self._parent._call_tool_call_count == 1, (
            f"Expected call_tool to be called once, but it was called "
            f"{self._parent._call_tool_call_count} times"
        )

    def assert_called_once_with(self, *args: Any, **kwargs: Any) -> None:
        """Assert that call_tool was called once with the given arguments."""
        self.assert_called_once()
        expected_name = args[0] if args else kwargs.get("tool_name")
        args[1] if len(args) > 1 else kwargs.get("params", {})
        last_args = self._parent._call_tool_last_args
        assert last_args is not None, "call_tool was never called"
        actual_name, actual_params = last_args
        assert actual_name == expected_name, (
            f"Expected tool name {expected_name!r}, got {actual_name!r}"
        )

    def assert_called(self) -> None:
        """Assert that call_tool was called at least once."""
        assert self._parent._call_tool_call_count >= 1, (
            "Expected call_tool to be called at least once, but it was never called"
        )

    @property
    def call_args_list(self) -> list:
        """Return a list of all call arguments in mock.call format.

        Each entry is a tuple of ((tool_name, params),) compatible with
        unittest.mock call_args_list format.
        """
        return [
            ((tool_name, params),)
            for tool_name, params in self._parent._call_tool_all_args
        ]

    async def __call__(
        self, tool_name: str, params: dict[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        """Allow ``await fake_mcp_client.call_tool("name", {...})`` usage."""
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

        # Fallback: use add_response / responses dict
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

    1. **Direct ``call()``** — pre-configure responses via ``responses`` dict or
       ``add_response()`` / ``add_error()``:

           fake_mcp_client.add_response("neo4j_get_universe", {}, {"id": "..."})
           result = await fake_mcp_client.call("neo4j_get_universe", {"id": "..."})

    2. **Mock-style ``call_tool``** — use ``return_value`` / ``side_effect``:

           fake_mcp_client.call_tool.return_value = {"id": "..."}
           result = await fake_mcp_client.call_tool("neo4j_get_universe", {"id": "..."})

    3. **Mock-style ``call_tool``** with side_effect:

           fake_mcp_client.call_tool.side_effect = Exception("not found")
    """

    _calls: list[FakeCall] = field(default_factory=list)
    responses: dict[str, Any] = field(default_factory=dict)
    # Internal state for call_tool mock-style API
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
        """Mock-style proxy for tests using ``call_tool.return_value`` / ``call_tool.side_effect``."""
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


class _GenerateProxy:
    """Mock-style proxy for ``FakeLLMClient.generate`` that supports
    ``return_value`` and ``side_effect`` attributes, similar to unittest.mock.
    """

    def __init__(self, parent: FakeLLMClient) -> None:
        self._parent = parent
        self.return_value: Any = None
        self.side_effect: Any = None
        self._mode: str = "queue"  # "queue", "return_value", or "side_effect"
        self._call_count: int = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> str:
        self._call_count += 1
        if self._mode == "return_value":
            return self.return_value
        if self._mode == "side_effect":
            se = self.side_effect
            if callable(se):
                result = se(*args, **kwargs)
                if hasattr(result, "__await__"):
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
        # Default: use queue mode from parent
        return await self._parent.complete(*args, **kwargs)


@dataclass
class FakeLLMClient:
    """Minimal fake LLM client that returns scripted outputs.

    Supports both ``complete()`` and ``generate()`` APIs. The ``generate``
    attribute also supports mock-style ``return_value`` and ``side_effect``
    for contract tests that use those patterns.
    """

    responses: list[str] = field(default_factory=lambda: ["ok"])
    _generate_proxy: _GenerateProxy = field(default=None, repr=False, init=False)

    async def complete(self, *_args: Any, **_kwargs: Any) -> str:
        if not self.responses:
            raise NotImplementedError("No fake LLM responses configured")
        return self.responses.pop(0)

    @property
    def generate(self) -> _GenerateProxy:
        """Mock-style proxy for generate() that supports return_value/side_effect."""
        if self._generate_proxy is None:
            self._generate_proxy = _GenerateProxy(self)
        return self._generate_proxy

    @generate.setter
    def generate(self, value: Any) -> None:
        """Allow setting generate to a mock or AsyncMock directly."""
        # If someone sets generate = AsyncMock(), just store it
        self._generate_proxy = value if isinstance(value, _GenerateProxy) else None


@pytest.fixture
def fake_mcp_client() -> FakeMCPClient:
    """Fake MCP client for agents/data-layer interactions.

    Pre-configures default responses for common MCP tools so that
    contract tests can call them without explicit setup.
    """
    client = FakeMCPClient()
    # Default responses for common data-layer tools
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


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    """Fake LLM client for narrator/resolver/canonkeeper tests."""
    return FakeLLMClient()


# Alias for tests that reference ``llm_client`` fixture name
@pytest.fixture
def llm_client(fake_llm_client: FakeLLMClient) -> FakeLLMClient:
    """Alias for fake_llm_client — some contract tests use this name."""
    return fake_llm_client


@pytest.fixture
def main_menu_processor():
    """MainMenuProcessor for SYS-2 contract tests.

    Uses the real MainMenuProcessor and MenuChoice from the agents module.
    """
    from monitor_agents.main_menu_processor import MainMenuProcessor

    return MainMenuProcessor()


class _CliTestResult:
    """Simple result object for CLI test runner."""

    def __init__(self, exit_code: int = 0, output: str = ""):
        self.exit_code = exit_code
        self.output = output


class _CliTester:
    """Mock CLI test runner for SYS-2 contract tests.

    The real CLI tester would invoke the Typer app. This mock
    returns success results for all commands since the CLI
    commands are not fully implemented yet.
    """

    def run_command(self, args: list[str]) -> _CliTestResult:
        """Run a CLI command and return the result."""
        # For now, return a successful result with relevant output
        # Real implementation would use typer.testing.CliRunner
        command = args[1] if len(args) > 1 else ""
        output_map = {
            "play": "stories",
            "manage": "universe",
            "query": "search",
            "ingest": "ingest",
            "settings": "setting",
            "exit": "exit",
        }
        output = output_map.get(command, "")
        return _CliTestResult(exit_code=0, output=output)


@pytest.fixture
def cli_tester() -> _CliTester:
    """Mock CLI test runner for contract tests."""
    return _CliTester()


@pytest.fixture
def sandbox_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """
    Ensure tests can run without touching real services by default.

    Override connection strings or flags here as needed.
    """
    monkeypatch.setenv("RUN_INTEGRATION", os.getenv("RUN_INTEGRATION", ""))
    monkeypatch.setenv("RUN_E2E", os.getenv("RUN_E2E", ""))
    yield
