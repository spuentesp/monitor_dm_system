"""Hardening tests: security headers, operator-only deep health, login timing equalization."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    monkeypatch.setattr("monitor_ui.main.get_postgres_client", lambda: fake_db)
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestSecurityHeaders:
    def test_headers_on_public_response(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "default-src 'none'" in r.headers["content-security-policy"]
        assert "camera=()" in r.headers["permissions-policy"]

    def test_hsts_only_over_https(self, client):
        r = client.get("/api/health")  # test transport is http
        assert "strict-transport-security" not in r.headers


class TestDeepHealth:
    def test_liveness_is_public(self, client):
        assert client.get("/api/health").status_code == 200

    def test_deep_requires_auth(self, client):
        assert client.get("/api/health", params={"deep": "true"}).status_code == 401

    def test_deep_forbidden_for_non_admin(self, client):
        _signup(client, "a@example.com", "alice")
        r = client.get("/api/health", params={"deep": "true"})
        assert r.status_code == 403

    def test_deep_allowed_for_admin(self, client, fake_db):
        user = _signup(client, "root@example.com", "root")
        fake_db.users[UUID(user["id"])]["is_admin"] = True
        r = client.get("/api/health", params={"deep": "true"})
        assert r.status_code == 200
        assert "components" in r.json() or r.json()["status"] in ("ok", "degraded")

    def test_deep_allowed_in_local_mode(self, monkeypatch, fake_db):
        monkeypatch.setenv("MONITOR_AUTH_DISABLED", "true")
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
        get_settings.cache_clear()
        try:

            async def _fake() -> FakePostgres:
                return fake_db

            app.dependency_overrides[get_postgres] = _fake
            monkeypatch.setattr("monitor_ui.main.get_postgres_client", lambda: fake_db)
            c = TestClient(app)
            r = c.get("/api/health", params={"deep": "true"})
            assert r.status_code == 200
        finally:
            app.dependency_overrides.pop(get_postgres, None)
            get_settings.cache_clear()


class TestLoginTiming:
    def test_unknown_user_still_runs_argon2_verify(self, client):
        """The dummy-hash verify keeps unknown-login timing equal to wrong-password."""
        with patch("monitor_ui.routers.auth.verify_password", return_value=False) as mock_verify:
            r = client.post("/api/auth/login", json={"login": "ghost@example.com", "password": "whatever123"})
        assert r.status_code == 401
        mock_verify.assert_called_once()  # called with the dummy hash, not skipped
        assert mock_verify.call_args[0][1] != ""  # a real hash argument
