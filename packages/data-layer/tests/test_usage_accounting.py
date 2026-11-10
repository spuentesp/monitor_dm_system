"""Per-owner daily usage accounting and quota enforcement (multi-tenancy B).

Covers the shared enforcement used by both the HTTP ``usage_quota_guard``
and the per-model-call checks: caps from env and per-user overrides, admin
and exempt bypasses, the typed ``QuotaExceededError``, the never-raising
usage write (a failure is logged and recorded), and the no-owner no-op
contract (local mode, scripts, workers, tests see no accounting).
"""

from __future__ import annotations

from typing import Any
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.usage import (
    QUOTA_CALL_CAP_ENV,
    QUOTA_TOKEN_CAP_ENV,
    QuotaExceededError,
    effective_caps,
    enforce_owner_quota,
    enforce_usage_quota,
    estimate_text_tokens,
    record_completion_usage,
    record_model_usage,
    record_usage,
    tokens_from_response,
)
from monitor_data.tenancy import set_owner_id


class FakeUsageDB:
    """In-memory stand-in for the PostgresClient usage surface."""

    def __init__(self) -> None:
        self.users: dict[Any, dict[str, Any]] = {}
        self.limits: dict[Any, dict[str, Any]] = {}
        self.usage: dict[Any, dict[str, int]] = {}
        self.record_calls: list[tuple[Any, int, int]] = []

    async def user_get_by_id(self, user_id: Any) -> dict[str, Any] | None:
        return self.users.get(user_id)

    async def usage_limit_get(self, user_id: Any) -> dict[str, Any] | None:
        return self.limits.get(user_id)

    async def usage_get(self, user_id: Any, day: Any = None) -> dict[str, Any]:
        u = self.usage.get(user_id, {"tokens": 0, "calls": 0})
        return {"tokens": u["tokens"], "calls": u["calls"]}

    async def usage_record(self, user_id: Any, *, tokens: int = 0, calls: int = 0, day: Any = None) -> dict[str, Any]:
        self.record_calls.append((user_id, int(tokens), int(calls)))
        u = self.usage.setdefault(user_id, {"tokens": 0, "calls": 0})
        u["tokens"] += int(tokens)
        u["calls"] += int(calls)
        return dict(u)

    def seed(self, user_id: Any, *, tokens: int = 0, calls: int = 0) -> None:
        self.usage[user_id] = {"tokens": tokens, "calls": calls}


class TestEnforceUsageQuota:
    async def test_no_caps_configured_never_refuses(self) -> None:
        db = FakeUsageDB()
        await enforce_usage_quota(db, uuid4())

    async def test_call_cap_refuses_at_the_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QUOTA_CALL_CAP_ENV, "2")
        db = FakeUsageDB()
        uid = uuid4()
        db.seed(uid, calls=1)
        await enforce_usage_quota(db, uid)  # 1 < 2 — allowed
        db.seed(uid, calls=2)
        with pytest.raises(QuotaExceededError) as exc:
            await enforce_usage_quota(db, uid)
        assert exc.value.kind == "call"
        assert "00:00 UTC" in exc.value.user_message

    async def test_token_cap_refuses_at_the_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QUOTA_TOKEN_CAP_ENV, "100")
        db = FakeUsageDB()
        uid = uuid4()
        db.seed(uid, tokens=99)
        await enforce_usage_quota(db, uid)
        db.seed(uid, tokens=100)
        with pytest.raises(QuotaExceededError) as exc:
            await enforce_usage_quota(db, uid)
        assert exc.value.kind == "token"

    async def test_two_users_one_capped_one_unaffected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QUOTA_CALL_CAP_ENV, "1")
        db = FakeUsageDB()
        capped, fresh = uuid4(), uuid4()
        db.seed(capped, calls=1)
        with pytest.raises(QuotaExceededError):
            await enforce_usage_quota(db, capped)
        await enforce_usage_quota(db, fresh)  # the other user is unaffected

    async def test_admin_is_never_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QUOTA_CALL_CAP_ENV, "0")
        db = FakeUsageDB()
        uid = uuid4()
        db.users[uid] = {"id": uid, "is_admin": True}
        db.seed(uid, calls=99)
        await enforce_usage_quota(db, uid)

    async def test_per_user_exempt_bypasses_caps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QUOTA_CALL_CAP_ENV, "0")
        db = FakeUsageDB()
        uid = uuid4()
        db.limits[uid] = {"exempt": True, "daily_token_cap": None, "daily_call_cap": None}
        await enforce_usage_quota(db, uid)

    async def test_per_user_override_beats_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QUOTA_CALL_CAP_ENV, "1")
        db = FakeUsageDB()
        uid = uuid4()
        db.limits[uid] = {"exempt": False, "daily_token_cap": None, "daily_call_cap": 5}
        db.seed(uid, calls=3)
        await enforce_usage_quota(db, uid)  # override 5 > env 1
        db.seed(uid, calls=5)
        with pytest.raises(QuotaExceededError):
            await enforce_usage_quota(db, uid)

    async def test_effective_caps_reads_override_then_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(QUOTA_TOKEN_CAP_ENV, "10")
        db = FakeUsageDB()
        assert await effective_caps(db, uuid4()) == (10, None)
        uid = uuid4()
        db.limits[uid] = {"daily_token_cap": 4, "daily_call_cap": 7}
        assert await effective_caps(db, uid) == (4, 7)


class TestRecordUsage:
    async def test_records_tokens_and_calls_with_expected_arguments(self) -> None:
        db = FakeUsageDB()
        uid = uuid4()
        await record_usage(db, uid, tokens=42, calls=1)
        assert db.record_calls == [(uid, 42, 1)]

    async def test_failed_write_is_recorded_and_never_raised(self) -> None:
        db = MagicMock()
        db.usage_record = AsyncMock(side_effect=RuntimeError("db down"))
        uid = uuid4()
        with patch("monitor_data.tools.mongodb_tools.mongodb_record_roleplay_error") as record_error:
            await record_usage(db, uid, tokens=1, calls=1)  # must not raise
            record_error.assert_called_once()
            params = record_error.call_args.args[0]
            assert "usage_record_failed" in params.message

    async def test_failed_write_survives_a_failing_error_recorder(self) -> None:
        db = MagicMock()
        db.usage_record = AsyncMock(side_effect=RuntimeError("db down"))
        with patch(
            "monitor_data.tools.mongodb_tools.mongodb_record_roleplay_error",
            side_effect=RuntimeError("mongo down"),
        ):
            await record_usage(db, uuid4(), tokens=1, calls=1)  # must not raise

    async def test_record_completion_usage_prefers_real_response_usage(self) -> None:
        db = FakeUsageDB()
        uid = uuid4()
        response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3))
        with patch("monitor_data.db.postgres.get_postgres_client", lambda: db):
            set_owner_id(uid)
            try:
                await record_completion_usage(messages=[{"role": "user", "content": "hi"}], response=response)
            finally:
                set_owner_id(None)
        assert db.record_calls == [(uid, 10, 1)]

    async def test_record_completion_usage_estimates_without_response_usage(self) -> None:
        db = FakeUsageDB()
        uid = uuid4()
        with patch("monitor_data.db.postgres.get_postgres_client", lambda: db):
            set_owner_id(uid)
            try:
                await record_completion_usage(
                    messages=[{"role": "user", "content": "hello brave adventurer"}],
                    output_text="well met",
                )
            finally:
                set_owner_id(None)
        assert len(db.record_calls) == 1
        assert db.record_calls[0][0] == uid
        assert db.record_calls[0][2] == 1  # one call counted
        assert db.record_calls[0][1] > 0  # estimated tokens


class TestContextWiring:
    def test_no_owner_means_no_db_traffic(self) -> None:
        db = MagicMock()
        with patch("monitor_data.db.postgres.get_postgres_client", lambda: db):
            set_owner_id(None)
            try:
                enforce_owner_quota()
                record_model_usage(tokens=5, calls=1)
            finally:
                set_owner_id(None)
        assert db.mock_calls == []

    def test_sync_wrappers_hit_the_real_callee_with_expected_arguments(self) -> None:
        db = FakeUsageDB()
        uid = uuid4()
        with patch("monitor_data.db.postgres.get_postgres_client", lambda: db):
            set_owner_id(uid)
            try:
                record_model_usage(tokens=11, calls=1)
                enforce_owner_quota()  # no caps configured — no refusal
            finally:
                set_owner_id(None)
        assert db.record_calls == [(uid, 11, 1)]

    def test_sync_wrappers_honor_explicit_owner_over_context(self) -> None:
        db = FakeUsageDB()
        with patch("monitor_data.db.postgres.get_postgres_client", lambda: db):
            set_owner_id(uuid4())
            try:
                explicit = uuid4()
                record_model_usage(tokens=3, calls=1, expected_owner_id=explicit)
            finally:
                set_owner_id(None)
        assert db.record_calls == [(explicit, 3, 1)]


class TestHelpers:
    def test_tokens_from_response_openai_shape(self) -> None:
        response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=6))
        assert tokens_from_response(response) == (5, 6)

    def test_tokens_from_response_anthropic_shape(self) -> None:
        assert tokens_from_response({"usage": {"input_tokens": 2, "output_tokens": 3}}) == (2, 3)

    def test_tokens_from_response_without_usage_is_none(self) -> None:
        assert tokens_from_response(object()) is None

    def test_estimate_text_tokens_is_positive(self) -> None:
        assert estimate_text_tokens("hello brave adventurer") > 0

    def test_bad_owner_id_never_raises_from_recording(self) -> None:
        with patch("monitor_data.db.postgres.get_postgres_client", MagicMock()):
            record_model_usage(tokens=1, calls=1, expected_owner_id="not-a-uuid")  # must not raise
