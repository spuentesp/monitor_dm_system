"""Regression test: get_dspy_lm must configure litellm's actual timeout
keyword, not a name litellm silently ignores.

Live bug (2026-07-22): a real ingestion job hung for 50+ minutes (near-zero
CPU, zero new LLM attempts recorded) in the agenda-extraction stage. Root
cause: get_dspy_lm() set kwargs["request_timeout"], but litellm.completion()
has no such per-call parameter -- it only reads a per-call `timeout` kwarg
(request_timeout is a module-level global litellm reads as a fallback
default, never a kwarg). dspy.LM stores **kwargs verbatim and splats them
into litellm.completion(**self.kwargs), so the misnamed key was silently
absorbed and the intended timeout never reached the actual HTTP client. The
outer asyncio.wait_for(asyncio.to_thread(...)) wrapper elsewhere in the
pipeline cannot kill an already-blocked OS thread -- only litellm's own
client-side timeout can actually abort a hung request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from monitor_data.schemas.llm_config import LLMProviderType

from monitor_agents import dspy_runtime


@dataclass
class _FakeClient:
    model: str = "MiniMax-M3"
    provider: LLMProviderType = LLMProviderType.MINIMAX
    params: dict[str, Any] = None
    api_key: str = "fake-key"
    base_url: str | None = "https://api.minimax.io/anthropic"
    prompt_version: str | None = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


def test_get_dspy_lm_sets_timeout_not_request_timeout(monkeypatch):
    fake_client = _FakeClient()

    async def _fake_resolve_client(node_name, role=None):
        return fake_client

    monkeypatch.setattr(dspy_runtime, "_resolve_client", _fake_resolve_client)
    monkeypatch.setenv("MONITOR_LLM_TIMEOUT", "77")

    lm = dspy_runtime.get_dspy_lm("analyzer")

    assert lm.kwargs.get("timeout") == 77
    assert "request_timeout" not in lm.kwargs
