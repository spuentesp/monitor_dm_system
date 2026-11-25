"""The MCP tool boundary re-raises ``OwnerViolationError`` typed.

``monitor_data.server.call_tool`` historically converted every tool
exception into an ``"Error executing tool: ..."`` text payload, so a
tenancy refusal was indistinguishable from any other failure once it
crossed the boundary. These tests pin the split contract:

- A tool raising ``OwnerViolationError`` → the typed exception propagates
  out of ``call_tool`` (still logged as a failed call).
- Every other tool exception → the pre-existing error-string payload,
  unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

import monitor_data.server as server_mod
from monitor_data.tenancy import OwnerViolationError


def _refusing_tool() -> str:
    raise OwnerViolationError("refusing demo write: target is not owned")


def _failing_tool() -> str:
    raise ValueError("boom")


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A private TOOL_REGISTRY copy so test tools never leak into the real one."""
    fake: dict[str, Any] = dict(server_mod.TOOL_REGISTRY)
    monkeypatch.setattr(server_mod, "TOOL_REGISTRY", fake)
    return fake


async def test_owner_violation_propagates_typed(registry: dict[str, Any]) -> None:
    registry["mongodb_fake_owner_refusal"] = _refusing_tool
    with pytest.raises(OwnerViolationError):
        await server_mod.call_tool("mongodb_fake_owner_refusal", {"agent_type": "TestAgent"})


async def test_other_tool_errors_stay_error_strings(registry: dict[str, Any]) -> None:
    registry["mongodb_fake_failure"] = _failing_tool
    contents = await server_mod.call_tool("mongodb_fake_failure", {"agent_type": "TestAgent"})
    assert len(contents) == 1
    assert contents[0].text.startswith("Error executing tool:")
    assert "boom" in contents[0].text
