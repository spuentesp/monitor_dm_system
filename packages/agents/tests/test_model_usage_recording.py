"""Per-model-call usage recording at the LLM runtime (multi-tenancy B.1).

Covers the dspy_runtime helper (quota check before the model call, usage
record after) and the direct LLMClient call sites in llm_registry, asserting
the real cross-component callees are invoked with the expected arguments.
Includes the two-user isolation case: a capped owner's next model call fails
with the typed error while the other user is unaffected.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_agents.dspy_runtime import _estimate_call_tokens, _track_model_usage
from monitor_data.usage import QuotaExceededError


class _FakeUsageDB:
    def __init__(self) -> None:
        self.users: dict[Any, Any] = {}
        self.limits: dict[Any, Any] = {}
        self.usage: dict[Any, dict[str, int]] = {}
        self.record_calls: list[tuple[Any, int, int]] = []

    async def user_get_by_id(self, user_id: Any) -> Any:
        return self.users.get(user_id)

    async def usage_limit_get(self, user_id: Any) -> Any:
        return self.limits.get(user_id)

    async def usage_get(self, user_id: Any, day: Any = None) -> dict[str, int]:
        return dict(self.usage.get(user_id, {"tokens": 0, "calls": 0}))

    async def usage_record(self, user_id: Any, *, tokens: int = 0, calls: int = 0, day: Any = None) -> dict[str, int]:
        self.record_calls.append((user_id, int(tokens), int(calls)))
        u = self.usage.setdefault(user_id, {"tokens": 0, "calls": 0})
        u["tokens"] += int(tokens)
        u["calls"] += int(calls)
        return dict(u)


class _FakeLM:
    model = "test-model"
    node_name = "narrator"


def _make_tracked(call_body: Any) -> Any:
    return _track_model_usage(lambda self, prompt=None, messages=None, **kw: call_body())


class TestDspyRuntimeHelper:
    def test_records_tokens_and_one_call_with_expected_arguments(self) -> None:
        db = _FakeUsageDB()
        uid = uuid4()
        calls: list[dict[str, Any]] = []

        def body() -> list[str]:
            calls.append({"ran": True})
            return ["well met, traveler"]

        tracked = _make_tracked(body)
        with patch("monitor_data.db.postgres.get_postgres_client", lambda: db):
            from monitor_data.tenancy import set_owner_id

            set_owner_id(uid)
            try:
                result = tracked(_FakeLM(), messages=[{"role": "user", "content": "hello brave adventurer"}])
            finally:
                set_owner_id(None)
        assert result == ["well met, traveler"]
        assert calls, "the model call itself did not run"
        assert len(db.record_calls) == 1
        owner, tokens, n_calls = db.record_calls[0]
        assert owner == uid
        assert n_calls == 1
        assert tokens > 0

    def test_quota_exceeded_fails_before_the_model_call(self) -> None:
        calls: list[dict[str, Any]] = []

        def body() -> list[str]:
            calls.append({"ran": True})
            return ["text"]

        tracked = _make_tracked(body)
        with patch(
            "monitor_data.usage.enforce_owner_quota",
            side_effect=QuotaExceededError("token", 100),
        ):
            with pytest.raises(QuotaExceededError) as exc:
                tracked(_FakeLM(), messages=[{"role": "user", "content": "hi"}])
        assert exc.value.user_message.startswith("Daily token limit reached")
        assert calls == [], "the model call ran despite the quota refusal"

    def test_two_users_one_capped_one_unaffected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MONITOR_DAILY_CALL_CAP", "1")
        db = _FakeUsageDB()
        capped, fresh = uuid4(), uuid4()
        db.usage[capped] = {"tokens": 0, "calls": 1}
        ran: list[str] = []

        def body() -> list[str]:
            ran.append("x")
            return ["text"]

        tracked = _make_tracked(body)
        from monitor_data.tenancy import set_owner_id

        with patch("monitor_data.db.postgres.get_postgres_client", lambda: db):
            set_owner_id(capped)
            try:
                with pytest.raises(QuotaExceededError):
                    tracked(_FakeLM(), messages=[{"role": "user", "content": "hi"}])
            finally:
                set_owner_id(None)
            set_owner_id(fresh)
            try:
                tracked(_FakeLM(), messages=[{"role": "user", "content": "hi"}])
            finally:
                set_owner_id(None)
        assert ran == ["x"], "only the uncapped user's model call ran"

    def test_failed_usage_write_never_breaks_the_call(self) -> None:
        db = MagicMock()
        db.usage_record = AsyncMock(side_effect=RuntimeError("db down"))
        db.usage_limit_get = AsyncMock(return_value=None)
        db.user_get_by_id = AsyncMock(return_value=None)
        db.usage_get = AsyncMock(return_value={"tokens": 0, "calls": 0})

        def body() -> list[str]:
            return ["text"]

        tracked = _make_tracked(body)
        with (
            patch("monitor_data.db.postgres.get_postgres_client", lambda: db),
            patch("monitor_data.tools.mongodb_tools.mongodb_record_roleplay_error"),
        ):
            from monitor_data.tenancy import set_owner_id

            set_owner_id(uuid4())
            try:
                assert tracked(_FakeLM(), messages=[{"role": "user", "content": "hi"}]) == ["text"]
            finally:
                set_owner_id(None)

    def test_no_owner_means_no_accounting(self) -> None:
        db = MagicMock()

        def body() -> list[str]:
            return ["text"]

        tracked = _make_tracked(body)
        with patch("monitor_data.db.postgres.get_postgres_client", lambda: db):
            from monitor_data.tenancy import set_owner_id

            set_owner_id(None)
            try:
                tracked(_FakeLM(), messages=[{"role": "user", "content": "hi"}])
            finally:
                set_owner_id(None)
        assert db.mock_calls == []

    def test_estimate_call_tokens_returns_positive_counts(self) -> None:
        prompt_tokens, completion_tokens = _estimate_call_tokens(
            "test-model",
            None,
            [{"role": "user", "content": "hello brave adventurer"}],
            ["well met"],
        )
        assert prompt_tokens > 0
        assert completion_tokens > 0


class _FakeAsyncOpenAI:
    """Minimal AsyncOpenAI-shaped client for LLMClient.complete_text."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.chat = MagicMock()
        self.chat.completions.create = AsyncMock(return_value=response)


def _openai_response(text: str) -> Any:
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=7, completion_tokens=3)
    return response


class TestLLMClientAccounting:
    async def test_complete_text_records_real_usage_with_expected_arguments(self) -> None:
        from monitor_agents.llm_registry import LLMClient
        from monitor_data.schemas.llm_config import LLMProviderType

        response = _openai_response("well met")
        client = LLMClient(
            model="gpt-test",
            provider=LLMProviderType.OPENAI,
            params={},
            api_key="k",
            _raw_client=_FakeAsyncOpenAI(response),
        )
        enforce = AsyncMock()
        record = AsyncMock()
        with (
            patch("monitor_agents.llm_registry.enforce_owner_quota_async", enforce),
            patch("monitor_agents.llm_registry.record_completion_usage", record),
        ):
            text = await client.complete_text([{"role": "user", "content": "hi"}])
        assert text == "well met"
        enforce.assert_awaited_once()
        record.assert_awaited_once()
        kwargs = record.await_args.kwargs
        assert kwargs["response"] is response
        assert kwargs["output_text"] == "well met"

    async def test_stream_text_records_joined_output(self) -> None:
        from monitor_agents.llm_registry import LLMClient
        from monitor_data.schemas.llm_config import LLMProviderType

        class _Chunk:
            def __init__(self, text: str) -> None:
                self.choices = [MagicMock(delta=MagicMock(content=text))]

        async def _stream(*args: Any, **kwargs: Any) -> Any:
            for part in ("well ", "met"):
                yield _Chunk(part)

        raw = MagicMock()
        raw.chat.completions.create = AsyncMock(return_value=_stream())
        client = LLMClient(
            model="gpt-test",
            provider=LLMProviderType.OPENAI,
            params={},
            api_key="k",
            _raw_client=raw,
        )
        record = AsyncMock()
        with (
            patch("monitor_agents.llm_registry.enforce_owner_quota_async", AsyncMock()),
            patch("monitor_agents.llm_registry.record_completion_usage", record),
        ):
            parts = [part async for part in await client.stream_text([{"role": "user", "content": "hi"}])]
        assert "".join(parts) == "well met"
        record.assert_awaited_once()
        assert record.await_args.kwargs["output_text"] == "well met"


class TestQuotaErrorSurfacing:
    async def test_scene_orchestrator_maps_quota_refusal_to_readable_meta(self) -> None:
        from monitor_agents.loops.scene_orchestrator import (
            SceneOrchestratorState,
            run_core_scene_loop,
        )

        class _Loop:
            async def run(self, user_input: str, resolution_override: Any = None) -> dict[str, Any]:
                raise QuotaExceededError("call", 3)

        class _Callbacks:
            def get_scene_loop(self, *args: Any, **kwargs: Any) -> _Loop:
                return _Loop()

            def now_iso(self) -> str:
                return "2026-01-01T00:00:00+00:00"

            def db_save_session(self, session: Any) -> None:
                return None

        state = SceneOrchestratorState(
            session_id=str(uuid4()),
            user_content="hello",
            session={"phase": "active_play"},
            callbacks=_Callbacks(),
            story_id=str(uuid4()),
            scene_id=str(uuid4()),
            scene_input="hello",
        )
        result = await run_core_scene_loop(state)
        assert result.metadata is not None
        assert result.metadata["type"] == "llm_provider_error"
        assert result.metadata["error_class"] == "quota_exceeded"
        assert result.response_text == QuotaExceededError("call", 3).user_message
