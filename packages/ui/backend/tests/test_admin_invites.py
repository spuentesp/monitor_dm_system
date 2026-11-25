"""Admin invite / password-reset operator surface (UX-3) + admin_action logs.

Hermetic: Postgres is the FakePostgres registry; no SMTP is involved (the
admin path returns a one-time link instead of emailing).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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
def env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MONITOR_SIGNUP_MODE", "open")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.delenv("MONITOR_SMTP_HOST", raising=False)
    monkeypatch.setattr(auth_module, "_login_limiter", None)
    monkeypatch.setattr(auth_module, "_signup_limiter", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres, env):
    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    c = TestClient(app)
    c.get("/api/auth/config")  # safe GET issues the CSRF cookie
    yield c
    app.dependency_overrides.pop(get_postgres, None)


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


def _signup(c: TestClient, email: str, username: str, password: str = "correct horse battery") -> dict:
    response = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": password},
        headers=_csrf(c),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _make_admin(fake_db: FakePostgres, c: TestClient) -> dict:
    user = _signup(c, "root@example.com", "root")
    fake_db.users[UUID(user["id"])]["is_admin"] = True
    return user


def _fresh_client() -> TestClient:
    """A second browser sharing the app (and its dependency overrides)."""
    c = TestClient(app)
    c.get("/api/auth/config")
    return c


class TestAdminInviteRoutes:
    def test_non_admin_is_rejected_on_every_route(self, client, fake_db):
        user = _signup(client, "alice@example.com", "alice")
        invite_id = str(uuid4())
        user_id = user["id"]
        for method, path, kwargs in [
            ("GET", "/api/admin/invites", {}),
            ("POST", "/api/admin/invites", {"json": {}}),
            ("DELETE", f"/api/admin/invites/{invite_id}", {}),
            ("POST", f"/api/admin/users/{user_id}/password-reset", {"json": {}}),
            ("POST", f"/api/admin/users/{user_id}/revoke-sessions", {"json": {}}),
        ]:
            response = client.request(method, path, headers=_csrf(client), **kwargs)
            assert response.status_code == 403, (method, path, response.status_code, response.text)
        assert fake_db.invites == {}
        assert fake_db.password_resets == {}

    def test_anonymous_is_rejected(self, client, fake_db):
        client.cookies.clear()
        for method, path, kwargs in [
            ("GET", "/api/admin/invites", {}),
            ("POST", "/api/admin/invites", {"json": {}}),
            ("DELETE", f"/api/admin/invites/{uuid4()}", {}),
            ("POST", f"/api/admin/users/{uuid4()}/password-reset", {"json": {}}),
            ("POST", f"/api/admin/users/{uuid4()}/revoke-sessions", {"json": {}}),
        ]:
            response = client.request(method, path, **kwargs)
            assert response.status_code == 401, (method, path, response.status_code, response.text)

    def test_create_invite_returns_the_token_once(self, client, fake_db):
        admin = _make_admin(fake_db, client)
        response = client.post(
            "/api/admin/invites",
            json={"email": "guest@example.com"},
            headers=_csrf(client),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"id", "token", "url_path", "expires_at"}
        assert body["url_path"] == f"/login?invite={body['token']}"
        # Default lifetime is 7 days.
        expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        assert datetime.now(UTC) + timedelta(hours=167) < expires <= datetime.now(UTC) + timedelta(hours=168)
        # Only the hash is stored, and the creator is recorded.
        row = fake_db.invites[UUID(body["id"])]
        assert row["token_hash"] == hash_token(body["token"])
        assert body["token"] not in row.values()
        assert row["created_by"] == UUID(admin["id"])
        assert row["email"] == "guest@example.com"

    def test_create_invite_custom_expiry_and_no_body(self, client, fake_db):
        _make_admin(fake_db, client)
        custom = client.post(
            "/api/admin/invites",
            json={"expires_in_hours": 2},
            headers=_csrf(client),
        )
        assert custom.status_code == 200
        expires = datetime.fromisoformat(custom.json()["expires_at"].replace("Z", "+00:00"))
        assert datetime.now(UTC) + timedelta(hours=1) < expires <= datetime.now(UTC) + timedelta(hours=2)
        # Body is optional: all fields default.
        bare = client.post("/api/admin/invites", headers=_csrf(client))
        assert bare.status_code == 200
        assert bare.json()["token"]
        assert len(fake_db.invites) == 2

    def test_list_invites_shape_has_no_tokens(self, client, fake_db):
        _make_admin(fake_db, client)
        created = client.post(
            "/api/admin/invites",
            json={"email": "guest@example.com"},
            headers=_csrf(client),
        ).json()
        listed = client.get("/api/admin/invites")
        assert listed.status_code == 200
        invites = listed.json()["invites"]
        assert len(invites) == 1
        entry = invites[0]
        assert set(entry) == {"id", "email", "created_at", "expires_at", "used_at", "revoked_at", "created_by"}
        assert entry["id"] == created["id"]
        assert entry["email"] == "guest@example.com"
        assert entry["used_at"] is None
        assert entry["revoked_at"] is None

    def test_revoke_makes_the_invite_unusable(self, client, fake_db, monkeypatch):
        _make_admin(fake_db, client)
        created = client.post("/api/admin/invites", headers=_csrf(client)).json()
        invite_id = created["id"]

        revoked = client.delete(f"/api/admin/invites/{invite_id}", headers=_csrf(client))
        assert revoked.status_code == 204
        # Idempotent second revoke; unknown id is a 404.
        assert client.delete(f"/api/admin/invites/{invite_id}", headers=_csrf(client)).status_code == 204
        assert client.delete(f"/api/admin/invites/{uuid4()}", headers=_csrf(client)).status_code == 404

        # The raw token no longer signs anyone up (invite mode enforced).
        monkeypatch.setenv("MONITOR_SIGNUP_MODE", "invite")
        get_settings.cache_clear()
        guest = _fresh_client()
        signup = guest.post(
            "/api/auth/signup",
            json={
                "email": "guest@example.com",
                "username": "guest",
                "password": "correct horse battery",
                "invite_token": created["token"],
            },
            headers=_csrf(guest),
        )
        assert signup.status_code == 403
        assert len(fake_db.users) == 1  # only the admin — no guest account

    def test_signup_consumes_the_invite_visible_to_admins(self, client, fake_db, monkeypatch):
        _make_admin(fake_db, client)
        monkeypatch.setenv("MONITOR_SIGNUP_MODE", "invite")
        get_settings.cache_clear()
        created = client.post("/api/admin/invites", headers=_csrf(client)).json()
        guest = _fresh_client()
        signup = guest.post(
            "/api/auth/signup",
            json={
                "email": "guest@example.com",
                "username": "guest",
                "password": "correct horse battery",
                "invite_token": created["token"],
            },
            headers=_csrf(guest),
        )
        assert signup.status_code == 201, signup.text
        entry = next(i for i in client.get("/api/admin/invites").json()["invites"] if i["id"] == created["id"])
        assert entry["used_at"] is not None


class TestAdminUserResetRoutes:
    def test_issue_password_reset_link_works_end_to_end(self, client, fake_db):
        _make_admin(fake_db, client)
        guest = _fresh_client()
        created = _signup(guest, "guest@example.com", "guest")
        response = client.post(
            f"/api/admin/users/{created['id']}/password-reset",
            headers=_csrf(client),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"token", "url_path", "expires_at"}
        assert body["url_path"] == f"/reset-password?token={body['token']}"
        row = next(r for r in fake_db.password_resets.values() if r["token_hash"] == hash_token(body["token"]))
        assert row["used_at"] is None
        assert row["expires_at"] <= datetime.now(UTC) + timedelta(hours=1) + timedelta(seconds=5)

        # The issued token redeems through the public reset endpoint.
        redeemed = guest.post(
            "/api/auth/password/reset",
            json={"token": body["token"], "new_password": "a completely new password"},
            headers=_csrf(guest),
        )
        assert redeemed.status_code == 200, redeemed.text
        guest.cookies.clear()
        guest.get("/api/auth/config")
        assert (
            guest.post(
                "/api/auth/login",
                json={"login": "guest", "password": "a completely new password"},
                headers=_csrf(guest),
            ).status_code
            == 200
        )

    def test_issue_reset_unknown_user_is_404(self, client, fake_db):
        _make_admin(fake_db, client)
        response = client.post(f"/api/admin/users/{uuid4()}/password-reset", headers=_csrf(client))
        assert response.status_code == 404
        assert fake_db.password_resets == {}

    def test_revoke_sessions_kills_existing_sessions(self, client, fake_db):
        admin = _make_admin(fake_db, client)
        guest = _fresh_client()
        created = _signup(guest, "guest@example.com", "guest")
        assert guest.get("/api/auth/me").status_code == 200

        response = client.post(
            f"/api/admin/users/{created['id']}/revoke-sessions",
            headers=_csrf(client),
        )
        assert response.status_code == 204
        assert guest.get("/api/auth/me").status_code == 401
        # Only the guest's sessions are gone; the admin session survives.
        assert all(s["user_id"] != UUID(created["id"]) for s in fake_db.sessions.values())
        assert any(s["user_id"] == UUID(admin["id"]) for s in fake_db.sessions.values())

    def test_revoke_sessions_unknown_user_is_404(self, client, fake_db):
        _make_admin(fake_db, client)
        response = client.post(f"/api/admin/users/{uuid4()}/revoke-sessions", headers=_csrf(client))
        assert response.status_code == 404


class TestAdminActionLogging:
    def test_every_mutation_emits_admin_action(self, client, fake_db):
        admin = _make_admin(fake_db, client)
        guest = _fresh_client()
        target = _signup(guest, "guest@example.com", "guest")
        target_id = target["id"]

        with capture_logs() as logs:
            client.post(f"/api/admin/users/{target_id}/ban", json={"reason": "test"}, headers=_csrf(client))
            client.post(f"/api/admin/users/{target_id}/unban", headers=_csrf(client))
            client.post(f"/api/admin/users/{target_id}/role", json={"is_admin": False}, headers=_csrf(client))
            client.put(
                f"/api/admin/usage/{target_id}/limits",
                json={"daily_token_cap": 100, "daily_call_cap": 10, "exempt": False},
                headers=_csrf(client),
            )
            invite = client.post("/api/admin/invites", headers=_csrf(client)).json()
            client.delete(f"/api/admin/invites/{invite['id']}", headers=_csrf(client))
            client.post(f"/api/admin/users/{target_id}/password-reset", headers=_csrf(client))
            client.post(f"/api/admin/users/{target_id}/revoke-sessions", headers=_csrf(client))

        actions = {e.get("action") for e in logs if e.get("event") == "admin_action"}
        assert actions == {
            "ban",
            "unban",
            "role_change",
            "usage_limits",
            "invite_create",
            "invite_revoke",
            "password_reset_issue",
            "revoke_sessions",
        }
        for entry in logs:
            if entry.get("event") == "admin_action":
                assert entry["actor_id"] == admin["id"]
                assert entry["target_id"] in {target_id, invite["id"]}
