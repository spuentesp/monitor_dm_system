"""Daily usage quota tests (multi-tenancy Phase 6).

Covers the env-configurable daily caps (MONITOR_DAILY_CALL_CAP /
MONITOR_DAILY_TOKEN_CAP), the 429 at the cap, per-user admin overrides,
admin/local exemption, and the admin usage routes.

Hermetic: FakePostgres + real auth (two signed-up users), no LLM calls —
the quota dependency runs before any handler, so the at-cap cases never
reach the model.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import monitor_ui.auth as auth_mod
from monitor_ui.auth import Principal, get_postgres, usage_quota_guard
from monitor_ui.config import get_settings
from fake_postgres import FakePostgres


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):
    from monitor_ui.main import app

    monkeypatch.setenv("MONITOR_AUTH_DISABLED", "false")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.delenv(auth_mod.QUOTA_TOKEN_CAP_ENV, raising=False)
    monkeypatch.delenv(auth_mod.QUOTA_CALL_CAP_ENV, raising=False)
    monkeypatch.setattr(auth_mod, "_signup_limiter", None)
    monkeypatch.setattr(auth_mod, "_login_limiter", None)
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


def _signup(c: TestClient, email: str, username: str) -> dict:
    if not c.cookies.get("monitor_csrf"):
        c.get("/api/auth/config")
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
        headers=_csrf(c),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _principal(user_id, is_admin: bool = False, via: str = "session") -> Principal:
    return Principal(user_id=user_id, is_admin=is_admin, via=via)


async def _run_guard(db, principal) -> None:
    await usage_quota_guard(principal=principal, db=db)


# ---------------------------------------------------------------------------
# Cross-component: the guard charges the real usage recorder
# ---------------------------------------------------------------------------


class TestGuardRecordsUsage:
    @pytest.mark.asyncio
    async def test_guard_records_one_call_with_expected_arguments(self, fake_db: FakePostgres) -> None:
        uid = uuid4()
        spy = AsyncMock(side_effect=fake_db.usage_record)
        fake_db.usage_record = spy  # type: ignore[method-assign]
        await _run_guard(fake_db, _principal(uid))
        spy.assert_awaited_once()
        args, kwargs = spy.await_args
        assert args == (uid,)
        assert kwargs == {"calls": 1}
        usage = await fake_db.usage_get(uid)
        assert usage["calls"] == 1

    @pytest.mark.asyncio
    async def test_no_caps_configured_never_rejects(self, fake_db: FakePostgres) -> None:
        await _run_guard(fake_db, _principal(uuid4()))


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------


class TestCaps:
    @pytest.mark.asyncio
    async def test_call_cap_blocks_after_n_calls(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_CALL_CAP_ENV, "2")
        uid = uuid4()
        for _ in range(2):
            await _run_guard(fake_db, _principal(uid))
        with pytest.raises(HTTPException) as exc:
            await _run_guard(fake_db, _principal(uid))
        assert exc.value.status_code == 429
        assert "Daily model-call limit" in exc.value.detail
        assert "00:00 UTC" in exc.value.detail

    @pytest.mark.asyncio
    async def test_other_users_are_unaffected(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_CALL_CAP_ENV, "1")
        a, b = uuid4(), uuid4()
        await _run_guard(fake_db, _principal(a))
        with pytest.raises(HTTPException):
            await _run_guard(fake_db, _principal(a))
        # B is under their own cap and is not affected by A's exhaustion.
        await _run_guard(fake_db, _principal(b))

    @pytest.mark.asyncio
    async def test_token_cap_blocks(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_TOKEN_CAP_ENV, "100")
        uid = uuid4()
        await fake_db.usage_record(uid, tokens=90, calls=0)
        await _run_guard(fake_db, _principal(uid))  # 90 < 100 — allowed
        await fake_db.usage_record(uid, tokens=10, calls=0)
        with pytest.raises(HTTPException) as exc:
            await _run_guard(fake_db, _principal(uid))
        assert exc.value.status_code == 429
        assert "Daily token limit" in exc.value.detail

    @pytest.mark.asyncio
    async def test_admin_is_never_capped(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_CALL_CAP_ENV, "0")
        for _ in range(5):
            await _run_guard(fake_db, _principal(uuid4(), is_admin=True))

    @pytest.mark.asyncio
    async def test_local_mode_is_never_capped(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_CALL_CAP_ENV, "0")
        for _ in range(5):
            await _run_guard(fake_db, _principal(uuid4(), via="local"))

    @pytest.mark.asyncio
    async def test_per_user_override_beats_env(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_CALL_CAP_ENV, "1")
        uid = uuid4()
        await fake_db.usage_limit_set(uid, daily_token_cap=None, daily_call_cap=3, exempt=False)
        for _ in range(3):
            await _run_guard(fake_db, _principal(uid))
        with pytest.raises(HTTPException):
            await _run_guard(fake_db, _principal(uid))

    @pytest.mark.asyncio
    async def test_per_user_exempt_bypasses_caps(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_CALL_CAP_ENV, "0")
        uid = uuid4()
        await fake_db.usage_limit_set(uid, daily_token_cap=None, daily_call_cap=None, exempt=True)
        for _ in range(5):
            await _run_guard(fake_db, _principal(uid))

    @pytest.mark.asyncio
    async def test_invalid_env_value_means_no_cap(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_CALL_CAP_ENV, "not-a-number")
        await _run_guard(fake_db, _principal(uuid4()))
        assert auth_mod._env_cap(auth_mod.QUOTA_CALL_CAP_ENV) is None


# ---------------------------------------------------------------------------
# End-to-end over HTTP: 429 with a readable message before any model runs
# ---------------------------------------------------------------------------


class TestQuotaOverHttp:
    def test_at_call_cap_gets_429_and_other_user_is_unaffected(
        self, monkeypatch: pytest.MonkeyPatch, client: TestClient
    ) -> None:
        monkeypatch.setenv(auth_mod.QUOTA_CALL_CAP_ENV, "1")
        # Keep the handler model-free: the guard runs before it, and the
        # under-cap request must not depend on an LLM being available.
        monkeypatch.setattr(
            "monitor_ui.routers.character_conversation.draft_card",
            AsyncMock(return_value={"name": "Detective"}),
        )
        _signup(client, "a@example.com", "alice")
        client_b = TestClient(client.app)
        _signup(client_b, "b@example.com", "bob")

        path = "/api/entities/characters/draft"
        payload = {"concept": "a grizzled detective"}

        first = client.post(path, json=payload, headers=_csrf(client))
        assert first.status_code == 200, first.text

        second = client.post(path, json=payload, headers=_csrf(client))
        assert second.status_code == 429, second.text
        assert "Daily model-call limit" in second.json()["detail"]

        # B has their own budget: not 429.
        other = client_b.post(path, json=payload, headers=_csrf(client_b))
        assert other.status_code == 200, other.text

    def test_admin_route_lists_usage(self, client: TestClient, fake_db: FakePostgres) -> None:
        me = _signup(client, "admin@example.com", "admin1")
        fake_db.users[UUID(me["id"])]["is_admin"] = True
        r = client.get("/api/admin/usage", headers=_csrf(client))
        assert r.status_code == 200, r.text
        body = r.json()
        assert "users" in body and "day" in body

    def test_admin_can_view_and_change_limits(self, client: TestClient, fake_db: FakePostgres) -> None:
        me = _signup(client, "admin@example.com", "admin1")
        fake_db.users[UUID(me["id"])]["is_admin"] = True
        uid = me["id"]
        r = client.put(
            f"/api/admin/usage/{uid}/limits",
            json={"daily_token_cap": 5000, "daily_call_cap": 25, "exempt": False},
            headers=_csrf(client),
        )
        assert r.status_code == 200, r.text
        assert r.json()["daily_call_cap"] == 25

        r = client.get(f"/api/admin/usage/{uid}", headers=_csrf(client))
        assert r.status_code == 200
        assert r.json()["daily_token_cap"] == 5000

    def test_usage_routes_require_admin(self, client: TestClient) -> None:
        _signup(client, "a@example.com", "alice")
        for method, path, kwargs in [
            ("GET", "/api/admin/usage", {}),
            ("GET", f"/api/admin/usage/{uuid4()}", {}),
            ("PUT", f"/api/admin/usage/{uuid4()}/limits", {"json": {"exempt": True}}),
        ]:
            r = client.request(method, path, headers=_csrf(client), **kwargs)
            assert r.status_code == 403, (method, path, r.status_code)
