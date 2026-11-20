"""Invite-only / open / closed signup and the OAuth first-login rule (UX-2).

Hermetic: Postgres is the FakePostgres registry, Google's HTTP calls are
patched at the router boundary, and ``MONITOR_SIGNUP_MODE`` is set explicitly
per test (the hermetic default is open).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.auth as auth_module
import monitor_ui.oauth as oauth_mod
from monitor_data.security import hash_token
from fake_postgres import FakePostgres
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def make_client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):
    """Factory for a TestClient running in the given MONITOR_SIGNUP_MODE."""
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(auth_module, "_signup_limiter", None)
    monkeypatch.setattr(auth_module, "_login_limiter", None)

    def _make(signup_mode: str = "invite") -> TestClient:
        monkeypatch.setenv("MONITOR_SIGNUP_MODE", signup_mode)
        get_settings.cache_clear()

        async def _fake_get_postgres() -> FakePostgres:
            return fake_db

        app.dependency_overrides[get_postgres] = _fake_get_postgres
        client = TestClient(app)
        client.get("/api/auth/config")  # safe GET issues the CSRF cookie
        return client

    yield _make
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("monitor_csrf", "")}


def _signup(
    client: TestClient,
    *,
    email: str = "alice@example.com",
    username: str = "alice",
    invite_token: str | None = None,
) -> dict:
    body: dict = {
        "email": email,
        "username": username,
        "password": "correct horse battery",
    }
    if invite_token is not None:
        body["invite_token"] = invite_token
    response = client.post("/api/auth/signup", json=body, headers=_csrf(client))
    return {"status": response.status_code, "body": response.json() if response.content else {}}


def _make_invite(
    fake_db: FakePostgres,
    *,
    hours_left: float = 168.0,
    revoked: bool = False,
    used: bool = False,
    email: str | None = None,
) -> str:
    """Seed an invite directly in the fake registry; returns the RAW token."""
    raw = secrets.token_urlsafe(32)
    row = _run(
        fake_db.invite_create(
            {
                "token_hash": hash_token(raw),
                "email": email,
                "created_by": uuid4(),
                "expires_at": datetime.now(UTC) + timedelta(hours=hours_left),
            }
        )
    )
    if revoked:
        row["revoked_at"] = datetime.now(UTC)
    if used:
        row["used_by"] = uuid4()
        row["used_at"] = datetime.now(UTC)
    return raw


def _run(coro):  # type: ignore[no-untyped-def]
    import asyncio

    return asyncio.run(coro)


def _mock_google(profile_email: str = "guser@example.com", sub: str = "google-sub-1"):
    """Patch the two network touchpoints of the OAuth flow (router namespace)."""
    profile = oauth_mod.GoogleProfile(provider_account_id=sub, email=profile_email, email_verified=True, name="G User")
    import monitor_ui.routers.auth as auth_router

    return (
        patch.object(auth_router, "exchange_code", AsyncMock(return_value="tok")),
        patch.object(auth_router, "fetch_google_profile", AsyncMock(return_value=profile)),
    )


def _oauth_roundtrip(client: TestClient, invite: str | None = None):  # type: ignore[no-untyped-def]
    """Start Google sign-in (optionally carrying an invite) and run the callback."""
    params = {"invite": invite} if invite else None
    client.get("/api/auth/oauth/google", params=params, follow_redirects=False)
    state = client.cookies.get("monitor_oauth_state")
    p_ex, p_prof = _mock_google()
    with p_ex, p_prof:
        return client.get(
            "/api/auth/oauth/google/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )


class TestSignupModes:
    def test_invite_mode_requires_a_token(self, make_client, fake_db):
        client = make_client("invite")
        result = _signup(client)
        assert result["status"] == 403
        assert "invite" in result["body"]["detail"].lower()
        assert fake_db.users == {}

    def test_invite_mode_signup_consumes_the_invite(self, make_client, fake_db):
        client = make_client("invite")
        token = _make_invite(fake_db, email="alice@example.com")
        result = _signup(client, invite_token=token)
        assert result["status"] == 201, result
        assert client.cookies.get("monitor_session")
        used = [r for r in fake_db.invites.values() if r["used_at"] is not None]
        assert len(used) == 1
        assert used[0]["token_hash"] == hash_token(token)

    def test_invite_is_single_use(self, make_client, fake_db):
        client = make_client("invite")
        token = _make_invite(fake_db)
        assert _signup(client, invite_token=token)["status"] == 201
        client.cookies.clear()
        client.get("/api/auth/config")
        second = _signup(client, email="bob@example.com", username="bob", invite_token=token)
        assert second["status"] == 403
        assert len(fake_db.users) == 1

    def test_expired_invite_is_refused(self, make_client, fake_db):
        client = make_client("invite")
        token = _make_invite(fake_db, hours_left=-1)
        result = _signup(client, invite_token=token)
        assert result["status"] == 403
        assert fake_db.users == {}

    def test_revoked_invite_is_refused(self, make_client, fake_db):
        client = make_client("invite")
        token = _make_invite(fake_db, revoked=True)
        assert _signup(client, invite_token=token)["status"] == 403
        assert fake_db.users == {}

    def test_already_used_invite_is_refused(self, make_client, fake_db):
        client = make_client("invite")
        token = _make_invite(fake_db, used=True)
        assert _signup(client, invite_token=token)["status"] == 403
        assert fake_db.users == {}

    def test_unknown_invite_token_is_refused(self, make_client, fake_db):
        client = make_client("invite")
        assert _signup(client, invite_token=secrets.token_urlsafe(32))["status"] == 403
        assert fake_db.users == {}

    def test_failed_creation_leaves_the_invite_unused(self, make_client, fake_db):
        """A duplicate-account 409 must not burn the invite (atomic consume)."""
        client = make_client("invite")
        assert _signup(client, invite_token=_make_invite(fake_db))["status"] == 201
        second_invite = _make_invite(fake_db, email="other@example.com")
        client.cookies.clear()
        client.get("/api/auth/config")
        clash = _signup(client, invite_token=second_invite)  # same email/username
        assert clash["status"] == 409
        unused = next(r for r in fake_db.invites.values() if r["token_hash"] == hash_token(second_invite))
        assert unused["used_at"] is None

    def test_open_mode_creates_without_invite(self, make_client, fake_db):
        client = make_client("open")
        result = _signup(client)
        assert result["status"] == 201
        assert fake_db.users != {}

    def test_closed_mode_refuses_always(self, make_client, fake_db):
        client = make_client("closed")
        without = _signup(client)
        assert without["status"] == 403
        assert without["body"]["detail"] == "Signup is closed."
        token = _make_invite(fake_db)
        with_invite = _signup(client, email="bob@example.com", username="bob", invite_token=token)
        assert with_invite["status"] == 403
        assert fake_db.users == {}
        # The invite was never consumed either.
        assert all(r["used_at"] is None for r in fake_db.invites.values())


class TestAuthConfigFlags:
    @pytest.mark.parametrize(
        ("mode", "signup_open", "signup_invite_only"),
        [("invite", False, True), ("open", True, False), ("closed", False, False)],
    )
    def test_signup_flags_follow_the_mode(self, make_client, mode, signup_open, signup_invite_only):
        client = make_client(mode)
        body = client.get("/api/auth/config").json()
        assert body["signup_open"] is signup_open
        assert body["signup_invite_only"] is signup_invite_only

    def test_email_reset_is_false_without_smtp(self, make_client, monkeypatch):
        monkeypatch.delenv("MONITOR_SMTP_HOST", raising=False)
        client = make_client("invite")
        assert client.get("/api/auth/config").json()["email_reset"] is False

    def test_email_reset_is_true_with_smtp(self, make_client, monkeypatch):
        monkeypatch.setenv("MONITOR_SMTP_HOST", "smtp.example.com")
        get_settings.cache_clear()
        client = make_client("invite")
        assert client.get("/api/auth/config").json()["email_reset"] is True


class TestOAuthFirstLoginFollowsSignupMode:
    def test_oauth_new_account_requires_invite(self, make_client, fake_db):
        client = make_client("invite")
        cb = _oauth_roundtrip(client)
        assert cb.status_code in (302, 307)
        assert "error=invite_required" in cb.headers["location"]
        assert fake_db.users == {}
        assert not client.cookies.get("monitor_session")

    def test_oauth_new_account_with_valid_invite(self, make_client, fake_db):
        client = make_client("invite")
        token = _make_invite(fake_db, email="guser@example.com")
        cb = _oauth_roundtrip(client, invite=token)
        assert cb.status_code in (302, 307)
        assert "error" not in cb.headers["location"]
        assert len(fake_db.users) == 1
        assert fake_db.users[next(iter(fake_db.users))]["email_verified"] is True
        used = [r for r in fake_db.invites.values() if r["used_at"] is not None]
        assert len(used) == 1

    def test_oauth_invalid_invite_is_refused(self, make_client, fake_db):
        client = make_client("invite")
        cb = _oauth_roundtrip(client, invite=secrets.token_urlsafe(32))
        assert "error=invite_invalid" in cb.headers["location"]
        assert fake_db.users == {}

    def test_oauth_existing_account_needs_no_invite(self, make_client, fake_db):
        """Linking to an existing email is a login, not a signup."""
        _run(
            fake_db.user_create(
                {
                    "email": "guser@example.com",
                    "email_normalized": "guser@example.com",
                    "username": "existing",
                    "username_normalized": "existing",
                    "password_hash": "x",
                }
            )
        )
        client = make_client("invite")
        cb = _oauth_roundtrip(client)
        assert "error" not in cb.headers["location"]
        assert len(fake_db.users) == 1
        assert client.cookies.get("monitor_session")

    def test_oauth_closed_mode_refuses_new_account(self, make_client, fake_db):
        client = make_client("closed")
        cb = _oauth_roundtrip(client)
        assert "error=signup_closed" in cb.headers["location"]
        assert fake_db.users == {}

    def test_oauth_open_mode_creates_without_invite(self, make_client, fake_db):
        client = make_client("open")
        cb = _oauth_roundtrip(client)
        assert "error" not in cb.headers["location"]
        assert len(fake_db.users) == 1

    def test_invite_cookie_is_dropped_after_the_callback(self, make_client, fake_db):
        client = make_client("invite")
        token = _make_invite(fake_db)
        cb = _oauth_roundtrip(client, invite=token)
        assert "error" not in cb.headers["location"]
        # One-shot: the invite cookie must not linger for a later sign-in.
        assert not client.cookies.get("monitor_oauth_invite")

    def test_failed_callback_drops_the_invite_cookie(self, make_client, fake_db):
        client = make_client("invite")
        client.get(
            "/api/auth/oauth/google",
            params={"invite": _make_invite(fake_db)},
            follow_redirects=False,
        )
        cb = client.get(
            "/api/auth/oauth/google/callback",
            params={"code": "abc", "state": "forged"},
            follow_redirects=False,
        )
        assert "error=invalid_state" in cb.headers["location"]
        assert not client.cookies.get("monitor_oauth_invite")
