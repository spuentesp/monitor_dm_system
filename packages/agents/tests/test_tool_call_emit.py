"""Phase 2B: verify BaseAgent.call_tool emits tool_call / tool_result events
through the stream_callback_var ContextVar.

We don't need a real agent — BaseAgent.call_tool is what every concrete agent
inherits. We instantiate it directly via a minimal subclass that overrides
`run()` (the abstract method), then call `call_tool` and assert the events
fire on the registered callback.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from monitor_agents.base import BaseAgent
from monitor_agents.dspy_runtime import stream_callback_var


class _StubAgent(BaseAgent):
    """Minimal concrete subclass — only needs `run()`."""

    async def run(self) -> None:
        return None


@pytest.fixture
def stub_agent(monkeypatch: pytest.MonkeyPatch) -> _StubAgent:
    """Build a _StubAgent with a no-op Anthropic client (we never call it)."""
    from unittest.mock import MagicMock

    monkeypatch.setattr(BaseAgent, "__init_subclass__", lambda cls: None, raising=False)

    agent = _StubAgent.__new__(_StubAgent)
    # Bypass BaseAgent.__init__ — we don't need an LLM client for this test.
    agent.agent_type = "stub"
    agent.agent_id = "stub-1"
    agent._client = MagicMock()
    return agent


@pytest.mark.asyncio
async def test_call_tool_emits_tool_call_and_tool_result(stub_agent, monkeypatch):
    """Happy path: server returns content, both frames fire on the callback."""
    events: list[tuple[str, dict]] = []

    async def cb(kind: str, data: Any) -> None:
        events.append((kind, data))

    # Stub the server_call_tool imported lazily inside call_tool.
    class _R:
        def __init__(self, t):
            self.text = t

    fake_result = [_R('[{"id": 1, "name": "Geralt"}]')]

    async def fake_server_call_tool(tool_name: str, args: dict) -> list:
        return fake_result

    import monitor_data.server as srv

    monkeypatch.setattr(srv, "call_tool", fake_server_call_tool, raising=False)

    token = stream_callback_var.set(cb)
    try:
        result = await stub_agent.call_tool("neo4j_search", {"q": "Geralt"})
        # Hook emits via loop.create_task(cb(...)) — give them a tick to run.
        await asyncio.sleep(0)
    finally:
        stream_callback_var.reset(token)

    # Result is parsed JSON.
    assert result == [{"id": 1, "name": "Geralt"}]

    # Two events fired on the callback.
    kinds = [k for k, _ in events]
    assert kinds == ["tool_call", "tool_result"]

    # tool_call carries id + name + args.
    call_kind, call_data = events[0]
    assert "id" in call_data
    assert call_data["name"] == "neo4j_search"
    assert call_data["args"] == {"q": "Geralt"}

    # tool_result carries the same id + a truncated preview.
    result_kind, result_data = events[1]
    assert result_kind == "tool_result"
    assert result_data["name"] == "neo4j_search"
    assert result_data["tool_call_id"] == call_data["id"]
    assert "Geralt" in result_data["result_preview"]


@pytest.mark.asyncio
async def test_call_tool_emits_error_on_exception(stub_agent, monkeypatch):
    """Error path: server raises, the error still surfaces as tool_result."""
    events: list[tuple[str, dict]] = []

    async def cb(kind: str, data: Any) -> None:
        events.append((kind, data))

    async def fake_server_call_tool_raises(tool_name: str, args: dict) -> list:
        raise ConnectionError("neo4j unreachable")

    import monitor_data.server as srv

    monkeypatch.setattr(srv, "call_tool", fake_server_call_tool_raises, raising=False)

    token = stream_callback_var.set(cb)
    try:
        with pytest.raises(ConnectionError):
            await stub_agent.call_tool("neo4j_search", {"q": "x"})
        await asyncio.sleep(0)
    finally:
        stream_callback_var.reset(token)

    # Both events fired (tool_call + tool_result with error).
    assert [k for k, _ in events] == ["tool_call", "tool_result"]
    err = events[1][1]
    assert "neo4j unreachable" in err["error"]
    assert "result_preview" not in err
