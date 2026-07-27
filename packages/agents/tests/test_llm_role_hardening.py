"""Regression tests: role values must survive as plain strings.

A str role ("heavy") reaching LLMExecutionContext / describe_dspy_target used
to raise AttributeError("'str' object has no attribute 'value'") — from the
*except* branch of describe_dspy_target too — killing an ingestion run right
after section classification, with no attempt record and no traceback.
"""

from __future__ import annotations

import pytest
from monitor_data.schemas.llm_config import ModelRole

import monitor_agents.dspy_runtime as dspy_runtime
from monitor_agents.dspy_runtime import describe_dspy_target
from monitor_agents.llm_execution import LLMExecutionContext, LLMTaskRunner
from monitor_agents.llm_registry import LLMRegistry


class _FakeLedger:
    def __init__(self):
        self.records = []

    async def llm_task_attempt_record(self, attempt):
        self.records.append(attempt)
        return attempt


class TestDescribeDspyTargetStringRole:
    def test_string_role_survives_the_fallback_branch(self, monkeypatch):
        async def _unreachable(*_args, **_kwargs):
            raise RuntimeError("registry unavailable in unit tests")

        monkeypatch.setattr(dspy_runtime, "_resolve_client", _unreachable)
        meta = describe_dspy_target("analyzer", "heavy")
        assert meta["role"] == "heavy"
        assert meta["provider"] is None

    def test_unknown_role_falls_back_to_node_default(self, monkeypatch):
        async def _unreachable(*_args, **_kwargs):
            raise RuntimeError("registry unavailable in unit tests")

        monkeypatch.setattr(dspy_runtime, "_resolve_client", _unreachable)
        meta = describe_dspy_target("analyzer", "warp-core")
        assert meta["role"] in {r.value for r in ModelRole}


@pytest.mark.asyncio
async def test_run_blocking_accepts_string_role(monkeypatch):
    ledger = _FakeLedger()
    monkeypatch.setattr("monitor_agents.llm_execution.get_postgres_client", lambda: ledger)
    monkeypatch.setattr(
        "monitor_agents.llm_execution.describe_dspy_target",
        lambda *_args, **_kwargs: {"provider": "test-provider", "model": "test-model"},
    )

    runner = LLMTaskRunner(agent_name="Analyzer", max_attempts=1, timeout_s=5)
    result = await runner.run_blocking(
        lambda: "ok",
        kwargs={},
        context=LLMExecutionContext(stage="unit", node_name="analyzer", role="heavy"),  # type: ignore[arg-type]
    )

    assert result.value == "ok"
    assert result.attempts[0].role == "heavy"


@pytest.mark.asyncio
async def test_for_role_rejects_uncoercible_role():
    registry = LLMRegistry(postgres=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Invalid model role"):
        await registry.for_role("warp-core")
