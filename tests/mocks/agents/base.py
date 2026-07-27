"""
Fake BaseAgent and StubAgent for testing agent subclasses.

Usage::

    from tests.mocks.agents.base import FakeBaseAgent

    class MyAgent(FakeBaseAgent):
        async def run(self):
            return None
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from monitor_agents.base import BaseAgent


class StubAgent(BaseAgent):
    """Minimal BaseAgent subclass for testing.

    Implements the abstract run() method as a no-op.
    call_tool is replaced with an AsyncMock for easy assertion.
    """

    def __init__(
        self,
        agent_type: str = "Test",
        agent_id: str = "test-1",
        model: str | None = None,
    ) -> None:
        super().__init__(agent_type=agent_type, agent_id=agent_id, model=model)
        self.call_tool = AsyncMock()  # type: ignore[assignment]
        self.call_llm_structured = AsyncMock()  # type: ignore[assignment]

    async def run(self) -> None:
        return None


class FakeBaseAgent(BaseAgent):
    """BaseAgent with configurable call_tool responses.

    Usage::

        agent = FakeBaseAgent(agent_type="Narrator", agent_id="n-1")
        agent.set_tool_response("neo4j_get_entity", {"id": "e1", "name": "Goblin"})
        result = await agent.call_tool("neo4j_get_entity", {"id": "e1"})
    """

    def __init__(
        self,
        agent_type: str = "Test",
        agent_id: str = "test-1",
        model: str | None = None,
    ) -> None:
        super().__init__(agent_type=agent_type, agent_id=agent_id, model=model)
        self._tool_responses: dict[str, Any] = {}
        self._tool_errors: dict[str, Exception] = {}

    def set_tool_response(self, tool_name: str, result: Any) -> None:
        """Configure a response for a tool call."""
        self._tool_responses[tool_name] = result

    def set_tool_error(self, tool_name: str, exc: Exception) -> None:
        """Configure an error for a tool call."""
        self._tool_errors[tool_name] = exc

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:  # type: ignore[override]
        if tool_name in self._tool_errors:
            raise self._tool_errors[tool_name]
        if tool_name in self._tool_responses:
            return self._tool_responses[tool_name]
        raise NotImplementedError(f"No fake response configured for {tool_name}")

    async def run(self) -> None:
        return None
