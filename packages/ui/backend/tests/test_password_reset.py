"""Forgot / reset password flows (UX-2): enumeration safety, single-use
tokens, session revocation, ban persistence, and swallowed SMTP failures.

Hermetic: Postgres is the FakePostgres registry and the SMTP send is patched
at the router boundary — no socket ever opens (pytest-socket would block it).
"""

from __future__ import annotations

import asyncio
import secrets
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

import monitor_ui.auth as auth_module
from monitor_data.security import hash_token
from fake_postgres import FakePostgres
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):
    monkeypatch.setenv("MONITOR_SIGNUP_MODE", "open")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.delenv("MONITOR_SMTP_HOST", raising=False)
    monkeypatch.setattr(auth_module, "_login_limiter", None)
    monkeypatch.setattr(auth_module, "_signup_limiter", None)
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    c = TestClient(app)
    c.get("/api/auth/config")  # safe GET issues the CSRF cookie
    yield c
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch):
    """Configure SMTP (host only) without ever letting a thread dial out."""
    monkeypatch.setenv("MONITOR_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("MONITOR_SMTP_FROM", "noreply@test")
    get_settings.cache_clear()
    sent: list[tuple[str, str]] = []

    def _record(_settings, to_addr: str, link: str) -> None:
        sent.append((to_addr, link))

    monkeypatch.setattr("monitor_ui.routers.auth.schedule_password_reset_email", _record)
    return sent


@pytest.fixture
def alice(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/signup",
        json={"email": "alice@example.com", "username": "alice", "password": "correct horse battery"},
        headers={"X-CSRF-Token": client.cookies.get("monitor_csrf", "")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


def _forgot(c: TestClient, login: str):
    return c.post("/api/auth/password/forgot", json={"login": login}, headers=_csrf(c))


def _issue_reset(fake_db: FakePostgres, user_id, *, hours_left: float = 1.0) -> str:
    """Seed a reset token directly; returns the RAW token."""
    raw = secrets.token_urlsafe(32)
    asyncio.run(
        fake_db.password_reset_create(
            {
                "token_hash": hash_token(raw),
                "user_id": UUID(str(user_id)),
                "expires_at": datetime.now(UTC) + timedelta(hours=hours_left),
            }
        )
    )
    return raw


def _reset_rows(fake_db: FakePostgres) -> list[dict]:
    return list(fake_db.password_resets.values())


def _wait_until(predicate, timeout: float = 2.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class TestForgotPassword:
    def test_known_and_unknown_logins_answer_identically(self, client, alice, fake_db, smtp):
        known = _forgot(client, "alice@example.com")
        unknown = _forgot(client, "nobody@example.com")
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json() == {"ok": True}
        # Email scheduled for the known account only, exactly once.
        assert len(smtp) == 1
        assert smtp[0][0] == "alice@example.com"
        assert len(_reset_rows(fake_db)) == 1

    def test_reset_link_matches_the_stored_token_hash(self, client, alice, fake_db, smtp):
        response = _forgot(client, "alice@example.com")
        assert response.status_code == 202
        link = smtp[0][1]
        assert "/reset-password?token=" in link
        raw = link.partition("token=")[2]
        row = next(iter(_reset_rows(fake_db)))
        assert row["token_hash"] == hash_token(raw)
        # Single-use + <=1h: the stored expiry never outlives one hour.
        assert row["used_at"] is None
        assert row["expires_at"] <= datetime.now(UTC) + timedelta(hours=1) + timedelta(seconds=5)

    def test_without_smtp_still_answers_202_and_sends_nothing(self, client, alice, fake_db, monkeypatch):
        scheduled: list = []
        monkeypatch.setattr(
            "monitor_ui.routers.auth.schedule_password_reset_email",
            lambda *args: scheduled.append(args),
        )
        response = _forgot(client, "alice@example.com")
        assert response.status_code == 202
        assert response.json() == {"ok": True}
        assert scheduled == []
        assert _reset_rows(fake_db) == []

    def test_rate_limited_per_account(self, client, alice, smtp, monkeypatch):
        # Vary the client IP so only the per-account key can trip.
        counter = {"n": 0}

        def _varying_ip(request, settings):  # type: ignore[no-untyped-def]
            counter["n"] += 1
            return f"ip-{counter['n']}"

        monkeypatch.setattr("monitor_ui.routers.auth.client_ip", _varying_ip)
        for _ in range(5):
            assert _forgot(client, "alice@example.com").status_code == 202
        assert _forgot(client, "alice@example.com").status_code == 429

    def test_rate_limited_per_ip(self, client, alice, smtp):
        # Same IP, distinct (unknown) logins: only the per-IP key can trip.
        for i in range(5):
            assert _forgot(client, f"ghost{i}@example.com").status_code == 202
        assert _forgot(client, "ghost5@example.com").status_code == 429


class TestResetPassword:
    def test_reset_sets_password_and_revokes_every_session(self, client, alice, fake_db):
        # A second browser signed in to the same account.
        other = TestClient(app)
        other.get("/api/auth/config")
        login = other.post(
            "/api/auth/login",
            json={"login": "alice", "password": "correct horse battery"},
            headers=_csrf(other),
        )
        assert login.status_code == 200, login.text
        assert other.get("/api/auth/me").status_code == 200

        token = _issue_reset(fake_db, alice["id"])
        response = client.post(
            "/api/auth/password/reset",
            json={"token": token, "new_password": "a completely new password"},
            headers=_csrf(client),
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True}
        # This browser's cookies are dropped by the response...
        assert not client.cookies.get("monitor_session")
        # ...and the OTHER session is dead server-side, not just locally.
        assert other.get("/api/auth/me").status_code == 401

        # New password logs in; the old one does not.
        client.cookies.clear()
        client.get("/api/auth/config")
        assert (
            client.post(
                "/api/auth/login",
                json={"login": "alice", "password": "a completely new password"},
                headers=_csrf(client),
            ).status_code
            == 200
        )
        client.cookies.clear()
        client.get("/api/auth/config")
        assert (
            client.post(
                "/api/auth/login",
                json={"login": "alice", "password": "correct horse battery"},
                headers=_csrf(client),
            ).status_code
            == 401
        )

    def test_token_is_single_use(self, client, alice, fake_db):
        token = _issue_reset(fake_db, alice["id"])
        body = {"token": token, "new_password": "a completely new password"}
        first = client.post("/api/auth/password/reset", json=body, headers=_csrf(client))
        assert first.status_code == 200
        client.cookies.clear()
        client.get("/api/auth/config")
        second = client.post("/api/auth/password/reset", json=body, headers=_csrf(client))
        assert second.status_code == 400

    def test_expired_token_is_refused_and_password_unchanged(self, client, alice, fake_db):
        token = _issue_reset(fake_db, alice["id"], hours_left=-0.001)
        response = client.post(
            "/api/auth/password/reset",
            json={"token": token, "new_password": "a completely new password"},
            headers=_csrf(client),
        )
        assert response.status_code == 400
        client.cookies.clear()
        client.get("/api/auth/config")
        # Old password still works: the expired token changed nothing.
        assert (
            client.post(
                "/api/auth/login",
                json={"login": "alice", "password": "correct horse battery"},
                headers=_csrf(client),
            ).status_code
            == 200
        )

    def test_unknown_token_is_refused(self, client, alice):
        response = client.post(
            "/api/auth/password/reset",
            json={"token": secrets.token_urlsafe(32), "new_password": "a completely new password"},
            headers=_csrf(client),
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid or expired reset token."

    def test_reset_never_unbans(self, client, alice, fake_db):
        uid = UUID(str(alice["id"]))
        asyncio.run(fake_db.user_set_banned(uid, True, "abuse"))
        token = _issue_reset(fake_db, uid)
        response = client.post(
            "/api/auth/password/reset",
            json={"token": token, "new_password": "a completely new password"},
            headers=_csrf(client),
        )
        assert response.status_code == 200
        assert fake_db.users[uid]["is_banned"] is True
        client.cookies.clear()
        client.get("/api/auth/config")
        assert (
            client.post(
                "/api/auth/login",
                json={"login": "alice", "password": "a completely new password"},
                headers=_csrf(client),
            ).status_code
            == 403
        )

    def test_short_new_password_is_rejected(self, client, alice, fake_db):
        token = _issue_reset(fake_db, alice["id"])
        response = client.post(
            "/api/auth/password/reset",
            json={"token": token, "new_password": "short"},
            headers=_csrf(client),
        )
        assert response.status_code == 422
        # The validation failure must not burn the token.
        row = next(iter(_reset_rows(fake_db)))
        assert row["used_at"] is None


class TestSmtpFailures:
    def test_send_failure_is_logged_and_never_reaches_the_caller(self, client, alice, monkeypatch):
        monkeypatch.setenv("MONITOR_SMTP_HOST", "smtp.test")
        get_settings.cache_clear()

        def _boom(_settings, _to, _link):  # type: ignore[no-untyped-def]
            raise OSError("connection refused")

        monkeypatch.setattr("monitor_ui.email.send_password_reset_email", _boom)
        with capture_logs() as logs:
            response = _forgot(client, "alice@example.com")
            assert response.status_code == 202
            assert response.json() == {"ok": True}
            assert _wait_until(lambda: any(e["event"] == "password_reset_email_failed" for e in logs)), logs
        assert any(e["event"] == "password_reset_email_failed" for e in logs)

    def test_unconfigured_smtp_sender_is_a_no_op(self):
        """send_password_reset_email must not dial out when SMTP is unset."""
        from monitor_ui.config import UISettings
        from monitor_ui.email import send_password_reset_email

        settings = UISettings(_env_file=None, MONITOR_SMTP_HOST="")
        # Would raise (no host) if it tried to connect; a no-op returns cleanly.
        send_password_reset_email(settings, "to@example.com", "http://x/reset-password?token=y")
