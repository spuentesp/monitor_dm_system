"""Tests for Google OAuth sign-in, banning, and the admin console (Phase 2+/operator).

Hermetic: Postgres is the shared FakePostgres; Google's token/userinfo HTTP
calls are patched at the httpx level via monitor_ui.oauth functions.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.oauth as oauth_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres, env):
    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_postgres, None)


def _signup(c: TestClient, email: str, username: str, password: str = "correct horse battery") -> dict:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


def _make_admin(fake_db: FakePostgres, c: TestClient, email="root@example.com", username="root") -> dict:
    user = _signup(c, email, username)
    # promote directly in the fake registry (bootstrap admin)
    fake_db.users[UUID(user["id"])]["is_admin"] = True
    return user


def _mock_google(profile_email="guser@example.com", sub="google-sub-1", verified=True):
    """Patch the two network touchpoints of the OAuth flow."""
    profile = oauth_mod.GoogleProfile(
        provider_account_id=sub, email=profile_email, email_verified=verified, name="G User"
    )
    import monitor_ui.routers.auth as auth_router

    return (
        patch.object(auth_router, "exchange_code", AsyncMock(return_value="tok")),
        patch.object(auth_router, "fetch_google_profile", AsyncMock(return_value=profile)),
    )


class TestGoogleOAuth:
    def test_google_login_redirects_with_state_cookie(self, client):
        r = client.get("/api/auth/oauth/google", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"].startswith(oauth_mod.GOOGLE_AUTH_URL)
        assert "client_id=test-client-id" in r.headers["location"]
        assert client.cookies.get("monitor_oauth_state")

    def test_google_not_configured_503(self, monkeypatch, fake_db):
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        get_settings.cache_clear()
        try:

            async def _fake() -> FakePostgres:
                return fake_db

            app.dependency_overrides[get_postgres] = _fake
            c = TestClient(app)
            r = c.get("/api/auth/oauth/google", follow_redirects=False)
            assert r.status_code == 503
        finally:
            app.dependency_overrides.pop(get_postgres, None)
            get_settings.cache_clear()

    def test_callback_creates_user_and_session(self, client, fake_db):
        client.get("/api/auth/oauth/google", follow_redirects=False)
        state = client.cookies.get("monitor_oauth_state")
        p_ex, p_prof = _mock_google()
        with p_ex, p_prof:
            cb = client.get(
                "/api/auth/oauth/google/callback",
                params={"code": "abc", "state": state},
                follow_redirects=False,
            )
        assert cb.status_code in (302, 307)
        assert cb.headers["location"].startswith("http://localhost:3000/")
        # session cookie set and user created with verified email, not admin
        assert client.cookies.get("monitor_session")
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["email"] == "guser@example.com"
        assert me.json()["user"]["is_admin"] is False
        rows = list(fake_db.users.values())
        assert len(rows) == 1
        assert rows[0]["email_verified"] is True
        assert ("google", "google-sub-1") in fake_db.oauth_accounts

    def test_callback_rejects_bad_state(self, client):
        client.get("/api/auth/oauth/google", follow_redirects=False)
        p_ex, p_prof = _mock_google()
        with p_ex, p_prof:
            cb = client.get(
                "/api/auth/oauth/google/callback",
                params={"code": "abc", "state": "forged"},
                follow_redirects=False,
            )
        assert cb.status_code in (302, 307)
        assert "error=invalid_state" in cb.headers["location"]
        assert not client.cookies.get("monitor_session")

    def test_callback_links_existing_account_by_email(self, client, fake_db):
        existing = _signup(client, "guser@example.com", "existing")
        client.cookies.clear()
        client.get("/api/auth/oauth/google", follow_redirects=False)
        state = client.cookies.get("monitor_oauth_state")
        p_ex, p_prof = _mock_google(profile_email="GUSER@example.com", sub="sub-2")
        with p_ex, p_prof:
            cb = client.get(
                "/api/auth/oauth/google/callback",
                params={"code": "abc", "state": state},
                follow_redirects=False,
            )
        assert cb.status_code in (302, 307) and "error" not in cb.headers["location"]
        assert len(fake_db.users) == 1  # no duplicate account
        assert fake_db.users[UUID(existing["id"])]["email_verified"] is True
        me = client.get("/api/auth/me")
        assert me.json()["user"]["id"] == existing["id"]

    def test_callback_repeat_login_reuses_account(self, client, fake_db):
        for _ in range(2):
            client.cookies.clear()
            client.get("/api/auth/oauth/google", follow_redirects=False)
            state = client.cookies.get("monitor_oauth_state")
            p_ex, p_prof = _mock_google()
            with p_ex, p_prof:
                client.get(
                    "/api/auth/oauth/google/callback",
                    params={"code": "abc", "state": state},
                    follow_redirects=False,
                )
        assert len(fake_db.users) == 1

    def test_banned_user_cannot_use_oauth(self, client, fake_db):
        client.get("/api/auth/oauth/google", follow_redirects=False)
        state = client.cookies.get("monitor_oauth_state")
        p_ex, p_prof = _mock_google()
        with p_ex, p_prof:
            client.get(
                "/api/auth/oauth/google/callback",
                params={"code": "abc", "state": state},
                follow_redirects=False,
            )
        user = next(iter(fake_db.users.values()))
        asyncio.run(fake_db.user_set_banned(user["id"], True, "abuse"))
        client.cookies.clear()
        client.get("/api/auth/oauth/google", follow_redirects=False)
        state = client.cookies.get("monitor_oauth_state")
        with p_ex, p_prof:
            cb = client.get(
                "/api/auth/oauth/google/callback",
                params={"code": "abc", "state": state},
                follow_redirects=False,
            )
        assert "error=suspended" in cb.headers["location"]


class TestBanning:
    def test_banned_session_gets_403(self, client, fake_db):
        user = _signup(client, "a@example.com", "alice")
        assert client.get("/api/auth/me").status_code == 200
        asyncio.run(fake_db.user_set_banned(user["id"], True, "spam"))
        r = client.get("/api/auth/me")
        assert r.status_code == 403
        assert r.json()["detail"] == "Account suspended."

    def test_banned_user_cannot_login_with_password(self, client, fake_db):
        user = _signup(client, "a@example.com", "alice")
        asyncio.run(fake_db.user_set_banned(user["id"], True, "spam"))
        client.cookies.clear()
        r = client.post("/api/auth/login", json={"login": "alice", "password": "correct horse battery"})
        assert r.status_code == 403


class TestAdminConsole:
    def test_non_admin_gets_403(self, client):
        _signup(client, "a@example.com", "alice")
        assert client.get("/api/admin/users").status_code == 403
        assert (
            client.post(f"/api/admin/users/{uuid4()}/ban", json={"reason": "x"}, headers=_csrf(client)).status_code
            == 403
        )

    def test_unauthenticated_gets_401(self, client):
        assert client.get("/api/admin/users").status_code == 401

    def test_admin_lists_and_searches_users(self, client, fake_db):
        _make_admin(fake_db, client)
        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        client2 = TestClient(app)
        _signup(client2, "c@example.com", "carol")
        r = client.get("/api/admin/users")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert {u["email"] for u in body["users"]} == {
            "root@example.com",
            "b@example.com",
            "c@example.com",
        }
        # secrets never exposed
        for u in body["users"]:
            assert "password_hash" not in u
            assert set(u) >= {"id", "is_admin", "is_banned", "email_verified"}
        r = client.get("/api/admin/users", params={"q": "carol"})
        assert r.json()["total"] == 1
        assert r.json()["users"][0]["username"] == "carol"

    def test_admin_can_ban_and_unban(self, client, fake_db):
        _make_admin(fake_db, client)
        victim_client = TestClient(app)
        victim = _signup(victim_client, "v@example.com", "victim")
        r = client.post(
            f"/api/admin/users/{victim['id']}/ban",
            json={"reason": "terms violation"},
            headers=_csrf(client),
        )
        assert r.status_code == 200
        assert r.json()["is_banned"] is True
        assert r.json()["banned_reason"] == "terms violation"
        assert fake_db.users[UUID(victim["id"])]["is_banned"] is True
        r = client.post(f"/api/admin/users/{victim['id']}/unban", headers=_csrf(client))
        assert r.status_code == 200
        assert r.json()["is_banned"] is False

    def test_admin_role_grant_and_self_guard(self, client, fake_db):
        admin = _make_admin(fake_db, client)
        other_client = TestClient(app)
        other = _signup(other_client, "o@example.com", "oliver")
        r = client.post(
            f"/api/admin/users/{other['id']}/role",
            json={"is_admin": True},
            headers=_csrf(client),
        )
        assert r.status_code == 200 and r.json()["is_admin"] is True
        # cannot demote self
        r = client.post(
            f"/api/admin/users/{admin['id']}/role",
            json={"is_admin": False},
            headers=_csrf(client),
        )
        assert r.status_code == 400
        # cannot ban self
        r = client.post(
            f"/api/admin/users/{admin['id']}/ban",
            json={"reason": "x"},
            headers=_csrf(client),
        )
        assert r.status_code == 400

    def test_admin_actions_on_missing_user_404(self, client, fake_db):
        _make_admin(fake_db, client)
        missing = uuid4()
        assert client.get(f"/api/admin/users/{missing}").status_code == 404
        assert (
            client.post(f"/api/admin/users/{missing}/ban", json={"reason": "x"}, headers=_csrf(client)).status_code
            == 404
        )
