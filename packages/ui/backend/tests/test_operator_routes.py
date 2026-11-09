"""Operator-only route tests: databases, llm, performance, jobs-health require admin.

Plan §5.3 policy: DB connection settings, LLM provider secrets/config, and
global performance/process controls are operator-only (403 for ordinary
users, 401 unauthenticated, allowed for admins and in local mode).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres

OPERATOR_PATHS = [
    "/api/databases",
    "/api/databases/neo4j",
    "/api/llm/providers",
    "/api/llm/assignments",
    "/api/performance",
    "/api/performance/report",
    "/api/jobs/health",
]


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
    # avoid real DB probes for the admin-200 case
    monkeypatch.setattr(
        "monitor_ui.routers.databases._check_db",
        lambda key: _async_status(key),
    )
    # handlers may hit real DBs in the admin/local cases; we only assert
    # the authz gate (not 401/403), so don't re-raise server exceptions
    c = TestClient(app, raise_server_exceptions=False)
    yield c
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


async def _async_status(key: str):  # type: ignore[no-untyped-def]
    from monitor_ui.routers.databases import DatabaseStatus

    return DatabaseStatus(name=key, db_type=key, url="x://", status="online")


def _signup(c: TestClient, email: str, username: str) -> dict:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestOperatorRoutes:
    def test_unauthenticated_gets_401(self, client):
        for path in OPERATOR_PATHS:
            assert client.get(path).status_code == 401, path

    def test_non_admin_gets_403(self, client):
        _signup(client, "a@example.com", "alice")
        for path in OPERATOR_PATHS:
            r = client.get(path)
            assert r.status_code == 403, (path, r.status_code)
        # mutations too
        assert client.post("/api/llm/providers", json={}).status_code in (403, 422)
        assert client.post("/api/performance/reset").status_code == 403

    def test_admin_allowed(self, client, fake_db):
        user = _signup(client, "root@example.com", "root")
        fake_db.users[UUID(user["id"])]["is_admin"] = True
        r = client.get("/api/databases")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        # other operator routes pass the authz gate (handler may 503 without DBs,
        # but must not be 401/403)
        for path in OPERATOR_PATHS[2:]:
            assert client.get(path).status_code not in (401, 403), path

    def test_local_mode_allowed_without_login(self, monkeypatch, fake_db):
        monkeypatch.setenv("MONITOR_AUTH_DISABLED", "true")
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
        get_settings.cache_clear()
        try:

            async def _fake() -> FakePostgres:
                return fake_db

            app.dependency_overrides[get_postgres] = _fake
            import monitor_ui.auth as auth_mod

            monkeypatch.setattr(auth_mod, "get_postgres_client", lambda: fake_db)
            monkeypatch.setattr("monitor_ui.routers.databases._check_db", lambda key: _async_status(key))
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/api/databases")
            assert r.status_code == 200
            assert c.get("/api/jobs/health").status_code not in (401, 403)
        finally:
            app.dependency_overrides.pop(get_postgres, None)
            get_settings.cache_clear()
