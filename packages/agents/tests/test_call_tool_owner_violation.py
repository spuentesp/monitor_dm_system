"""``BaseAgent.call_tool`` surfaces ``OwnerViolationError`` typed.

The data-layer server re-raises an ownership refusal instead of returning
an ``"Error executing tool: ..."`` string, and ``BaseAgent.call_tool``
passes the typed exception on to the calling agent — while every other
tool failure keeps the pre-existing error-string contract, so no other
caller sees a behavior change.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from monitor_agents.base import BaseAgent
from monitor_data.tenancy import OwnerViolationError


class _StubAgent(BaseAgent):
    """Minimal concrete subclass — only needs ``run()``."""

    async def run(self) -> None:
        return None


@pytest.fixture
def stub_agent() -> _StubAgent:
    # Bypass BaseAgent.__init__ — no LLM client is needed here.
    agent = _StubAgent.__new__(_StubAgent)
    agent.agent_type = "stub"
    agent.agent_id = "stub-1"
    return agent


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Any:
    tests_dir = Path(__file__).resolve().parents[2] / "data-layer" / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from _tenancy_fakes import install_fakes

    return install_fakes(monkeypatch)


async def test_owner_violation_reaches_agent_as_typed_exception(
    stub_agent: _StubAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import monitor_data.server as srv

    async def _refuse(tool_name: str, args: dict[str, Any]) -> Any:
        raise OwnerViolationError("refusing x write: target is not owned")

    monkeypatch.setattr(srv, "call_tool", _refuse, raising=False)
    with pytest.raises(OwnerViolationError):
        await stub_agent.call_tool("mongodb_create_scene", {})


async def test_owner_violation_through_the_real_server_boundary(
    stub_agent: _StubAgent,
    fakes: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: real server.call_tool + a real guarded write tool."""
    from uuid import uuid4

    import monitor_data.server as srv
    from monitor_data.tenancy import set_owner_id
    from monitor_data.tools.mongodb_tools.gm_notes import mongodb_upsert_gm_note

    mongo, _neo4j, _pg = fakes
    monkeypatch.setitem(srv.TOOL_REGISTRY, "mongodb_upsert_gm_note", mongodb_upsert_gm_note)
    set_owner_id(str(uuid4()))  # an owner that owns nothing
    try:
        with pytest.raises(OwnerViolationError):
            await stub_agent.call_tool(
                "mongodb_upsert_gm_note",
                {"universe_id": str(uuid4()), "params": {"content": "x"}},
            )
    finally:
        set_owner_id(None)
    assert mongo.total_write_calls == 0


async def test_other_tool_errors_still_arrive_as_error_strings(
    stub_agent: _StubAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-tenancy tool failures keep the pre-existing string contract."""
    import monitor_data.server as srv

    async def _fail(tool_name: str, args: dict[str, Any]) -> Any:
        class _R:
            def __init__(self, t: str) -> None:
                self.text = t

        return [_R("Error executing tool: boom")]

    monkeypatch.setattr(srv, "call_tool", _fail, raising=False)
    result = await stub_agent.call_tool("mongodb_create_scene", {})
    assert result == "Error executing tool: boom"
