"""Tests for the /api/auth routes and principal resolution (multi-tenancy Phase 2).

Uses FastAPI's dependency override to swap the Postgres ownership registry for
an in-memory fake, so these run hermetically without a real database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import monitor_ui.auth as auth_module
from monitor_data.security import hash_token
from fake_postgres import FakePostgres
from monitor_ui.auth import LOCAL_USER_ID, get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres) -> TestClient:
    """TestClient with the Postgres dependency overridden by the fake registry.

    AUTH_COOKIE_SECURE=false because the test transport is plain HTTP —
    httpx refuses to send Secure cookies over http://testserver.
    """
    monkeypatch.setattr(auth_module, "_login_limiter", None)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    # No `with` block: entering the context would run the app lifespan, which
    # touches Mongo/Neo4j. Existing backend tests use the bare client too.
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(
    c: TestClient, email: str = "alice@example.com", username: str = "alice", password: str = "correct horse battery"
) -> dict:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _csrf_headers(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


class TestSignup:
    def test_signup_success_sets_secure_cookies_and_hides_password(self, client):
        r = client.post(
            "/api/auth/signup",
            json={
                "email": "alice@example.com",
                "username": "alice",
                "password": "correct horse battery",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == "alice@example.com"
        assert body["username"] == "alice"
        assert body["is_admin"] is False
        assert "password_hash" not in body
        assert "password" not in body
        assert client.cookies.get("monitor_session")
        assert client.cookies.get("monitor_csrf")
        # Session cookie must be HttpOnly; the CSRF cookie stays JS-readable
        # (double-submit pattern) but carries the same expiry.
        set_cookies = r.headers.get_list("set-cookie")
        session_header = next(h for h in set_cookies if h.startswith("monitor_session="))
        csrf_header = next(h for h in set_cookies if h.startswith("monitor_csrf="))
        assert "httponly" in session_header.lower()
        assert "httponly" not in csrf_header.lower()
        assert "samesite=lax" in session_header.lower()

    def test_signup_duplicate_conflict(self, client):
        _signup(client)
        r = client.post(
            "/api/auth/signup",
            json={"email": "alice@example.com", "username": "alice2", "password": "another password 1"},
        )
        assert r.status_code == 409
        r2 = client.post(
            "/api/auth/signup",
            json={"email": "other@example.com", "username": "alice", "password": "another password 1"},
        )
        assert r2.status_code == 409

    def test_signup_short_password_rejected(self, client):
        r = client.post(
            "/api/auth/signup",
            json={"email": "bob@example.com", "username": "bob", "password": "short"},
        )
        assert r.status_code == 422

    def test_signup_bad_email_rejected(self, client):
        r = client.post(
            "/api/auth/signup",
            json={"email": "not-an-email", "username": "carol", "password": "another password 1"},
        )
        assert r.status_code == 422


class TestLoginAndMe:
    def test_me_requires_auth(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code == 401

    def test_signup_then_me(self, client):
        _signup(client)
        r = client.get("/api/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["auth_disabled"] is False
        assert body["user"]["username"] == "alice"

    def test_login_generic_failure_for_unknown_user_and_wrong_password(self, client):
        _signup(client)
        client.cookies.clear()
        r_unknown = client.post("/api/auth/login", json={"login": "nobody@example.com", "password": "whatever123"})
        r_wrong = client.post("/api/auth/login", json={"login": "alice@example.com", "password": "wrong password!!"})
        assert r_unknown.status_code == 401
        assert r_wrong.status_code == 401
        assert r_unknown.json()["detail"] == r_wrong.json()["detail"] == "Invalid login or password."

    def test_login_by_username_and_session_rotation(self, client, fake_db):
        _signup(client)
        old_session = client.cookies.get("monitor_session")
        r = client.post("/api/auth/login", json={"login": "ALICE", "password": "correct horse battery"})
        assert r.status_code == 200
        assert r.json()["username"] == "alice"
        new_session = client.cookies.get("monitor_session")
        assert new_session and new_session != old_session
        # old session token is not valid: only one live session row per login here
        # (rotation creates a new row; the old one remains until expiry — the new
        # cookie is what the client uses)
        assert hash_token(new_session) in fake_db.sessions
        r = client.get("/api/auth/me")
        assert r.status_code == 200

    def test_login_rate_limited(self, client):
        for _ in range(5):
            r = client.post(
                "/api/auth/login",
                json={"login": "ratelimit@example.com", "password": "bad password 000"},
            )
            assert r.status_code == 401
        r = client.post(
            "/api/auth/login",
            json={"login": "ratelimit@example.com", "password": "bad password 000"},
        )
        assert r.status_code == 429


class TestLogoutAndCsrf:
    def test_logout_requires_csrf_token(self, client):
        _signup(client)
        r = client.post("/api/auth/logout")
        assert r.status_code == 403

    def test_logout_with_csrf_invalidates_session(self, client, fake_db):
        _signup(client)
        session_cookie = client.cookies.get("monitor_session")
        r = client.post("/api/auth/logout", headers=_csrf_headers(client))
        assert r.status_code == 200
        assert hash_token(session_cookie) not in fake_db.sessions
        assert client.get("/api/auth/me").status_code == 401

    def test_cross_origin_unsafe_request_rejected(self, client):
        _signup(client)
        r = client.post(
            "/api/auth/logout",
            headers={**_csrf_headers(client), "Origin": "https://evil.example"},
        )
        assert r.status_code == 403

    def test_bearer_requests_exempt_from_csrf(self, client, fake_db):
        _signup(client)
        r = client.post(
            "/api/auth/tokens",
            json={"name": "sillytavern"},
            headers=_csrf_headers(client),
        )
        assert r.status_code == 201
        raw = r.json()["token"]
        bearer = TestClient(app)
        # Bearer-authenticated unsafe request needs no CSRF header
        r2 = bearer.post("/api/auth/logout", headers={"Authorization": f"Bearer {raw}"})
        assert r2.status_code == 200


class TestApiTokens:
    def _make_token(self, client) -> str:
        r = client.post("/api/auth/tokens", json={"name": "cli"}, headers=_csrf_headers(client))
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["token"].startswith("mntk_")
        assert body["token_prefix"]
        return body["token"]

    def test_create_returns_raw_token_once_and_list_hides_it(self, client):
        _signup(client)
        raw = self._make_token(client)
        r = client.get("/api/auth/tokens")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["name"] == "cli"
        assert "token" not in items[0]
        assert items[0]["token_prefix"] == raw[:12]

    def test_bearer_token_authenticates(self, client):
        _signup(client)
        raw = self._make_token(client)
        bearer = TestClient(app)
        r = bearer.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 200
        assert r.json()["user"]["username"] == "alice"

    def test_revoked_token_stops_working(self, client):
        _signup(client)
        raw = self._make_token(client)
        r = client.get("/api/auth/tokens")
        token_id = r.json()[0]["id"]
        r = client.request("DELETE", f"/api/auth/tokens/{token_id}", headers=_csrf_headers(client))
        assert r.status_code == 204
        bearer = TestClient(app)
        r = bearer.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401

    def test_cannot_revoke_another_users_token(self, client, fake_db):
        _signup(client)
        raw_a = self._make_token(client)
        # second user + token
        _signup(client, email="b@example.com", username="bob")
        raw_b = self._make_token(client)
        id_b = client.get("/api/auth/tokens").json()[0]["id"]
        # user A (fresh client) tries to revoke B's token → 404
        client_a = TestClient(app)
        _signup(client_a, email="a2@example.com", username="alice2")
        self._make_token(client_a)
        r = client_a.request("DELETE", f"/api/auth/tokens/{id_b}", headers=_csrf_headers(client_a))
        assert r.status_code == 404
        # B's token still works
        bearer_b = TestClient(app)
        assert bearer_b.get("/api/auth/me", headers={"Authorization": f"Bearer {raw_b}"}).status_code == 200
        assert raw_a  # noqa: B018 - silence unused warnings

    def test_expired_session_rejected_and_deleted(self, client, fake_db):
        _signup(client)
        session_cookie = client.cookies.get("monitor_session")
        th = hash_token(session_cookie)
        fake_db.sessions[th]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
        assert client.get("/api/auth/me").status_code == 401
        assert th not in fake_db.sessions


class TestAuthDisabledMode:
    def test_local_user_resolution(self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):
        monkeypatch.setenv("MONITOR_AUTH_DISABLED", "true")
        get_settings.cache_clear()
        try:

            async def _fake_get_postgres() -> FakePostgres:
                return fake_db

            app.dependency_overrides[get_postgres] = _fake_get_postgres
            c = TestClient(app)
            r = c.get("/api/auth/me")
            assert r.status_code == 200
            body = r.json()
            assert body["auth_disabled"] is True
            assert body["user"]["id"] == str(LOCAL_USER_ID)
            assert body["user"]["email"] == "local@monitor.invalid"
            assert body["user"]["is_admin"] is True
            # local account persisted with an unusable (random) password hash
            row = fake_db.users[LOCAL_USER_ID]
            assert row["password_hash"].startswith("$argon2id$")
        finally:
            app.dependency_overrides.pop(get_postgres, None)
            get_settings.cache_clear()


def test_is_expired_accepts_iso_string():
    """Regression: rows crossing asyncpg as ISO strings must not crash."""
    from monitor_ui.auth import _is_expired

    assert _is_expired("2000-01-01T00:00:00+00:00") is True
    assert _is_expired("2999-01-01T00:00:00+00:00") is False
    assert _is_expired(None) is False
