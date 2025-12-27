"""
Shared pytest fixtures and marker behavior for MONITOR.

Markers:
- integration: cross-component; skipped unless RUN_INTEGRATION=1
- e2e: end-to-end/system; skipped unless RUN_E2E=1
"""

from __future__ import annotations

import os
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


@dataclass
class FakeMCPClient:
    """Minimal fake MCP client that records calls."""

    calls: list[FakeCall] = field(default_factory=list)
    responses: dict[str, Any] = field(default_factory=dict)

    async def call(self, tool_name: str, params: dict[str, Any], context: dict[str, Any] | None = None) -> Any:
        ctx = context or {}
        self.calls.append(FakeCall(tool_name, params, ctx))
        if tool_name in self.responses:
            return self.responses[tool_name]
        raise NotImplementedError(f"No fake response configured for {tool_name}")


@dataclass
class FakeLLMClient:
    """Minimal fake LLM client that returns scripted outputs."""

    responses: list[str] = field(default_factory=lambda: ["ok"])

    async def complete(self, *_args: Any, **_kwargs: Any) -> str:
        if not self.responses:
            raise NotImplementedError("No fake LLM responses configured")
        return self.responses.pop(0)


@pytest.fixture
def fake_mcp_client() -> FakeMCPClient:
    """Fake MCP client for agents/data-layer interactions."""
    return FakeMCPClient()


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    """Fake LLM client for narrator/resolver/canonkeeper tests."""
    return FakeLLMClient()


@pytest.fixture
def sandbox_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """
    Ensure tests can run without touching real services by default.

    Override connection strings or flags here as needed.
    """
    monkeypatch.setenv("RUN_INTEGRATION", os.getenv("RUN_INTEGRATION", ""))
    monkeypatch.setenv("RUN_E2E", os.getenv("RUN_E2E", ""))
    yield
