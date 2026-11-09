"""Ownership tests for the semantic-search router (multi-tenancy Phase 3/4).

Verifies the global search can never run unscoped: it is either pinned to an
owned universe or restricted to the caller's owned-universe allowlist via a
server-added Qdrant predicate. Hermetic: qdrant_search and embedding are
patched.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.routers.search as search_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):
    """TestClient + captured qdrant_search calls; returns (client, calls, fake_db)."""
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres

    calls: list = []

    def fake_qdrant_search(params):
        calls.append(params)
        return SimpleNamespace(results=[])

    monkeypatch.setattr(search_mod, "qdrant_search", fake_qdrant_search)
    monkeypatch.setattr(search_mod, "_embed_query_text", lambda q: [0.1, 0.2])

    c = TestClient(app)
    yield c, calls, fake_db
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _own_world(fake_db: FakePostgres, owner_id: str, universe_id: str | None = None) -> str:
    uid = universe_id or str(uuid4())
    fake_db.worlds[uid] = {
        "id": uid,
        "owner_id": UUID(owner_id),
        "multiverse_id": str(uuid4()),
        "label": "w",
        "active": True,
    }
    return uid


class TestSearchAuthz:
    def test_unauthenticated_denied(self, captured):
        c, calls, _ = captured
        assert c.get("/api/search/search", params={"q": "dragon"}).status_code == 401
        assert c.get(f"/api/search/universes/{uuid4()}/search", params={"q": "dragon"}).status_code == 401
        assert calls == []

    def test_global_search_without_universe_is_scoped_to_owned(self, captured):
        c, calls, fake_db = captured
        user = _signup(c, "a@example.com", "alice")
        w1 = _own_world(fake_db, user["id"])
        w2 = _own_world(fake_db, user["id"])

        r = c.get("/api/search/search", params={"q": "dragon"})
        assert r.status_code == 200, r.text
        assert r.json()["total_results"] == 0
        # Qdrant received a server-added MatchAny allowlist of owned worlds
        assert calls, "expected qdrant_search to be called"
        filters = [call.filter for call in calls if call.filter is not None]
        assert filters
        for f in filters:
            assert f.universe_ids is not None
            assert {str(u) for u in f.universe_ids} == {w1, w2}

    def test_global_search_with_zero_owned_returns_empty_without_query(self, captured):
        c, calls, _ = captured
        _signup(c, "b@example.com", "bob")
        r = c.get("/api/search/search", params={"q": "dragon"})
        assert r.status_code == 200
        assert r.json()["total_results"] == 0
        assert calls == []  # never queried unscoped

    def test_global_search_with_foreign_universe_404(self, captured):
        c, _, fake_db = captured
        user = _signup(c, "a@example.com", "alice")
        foreign = _own_world(fake_db, str(uuid4()))  # owned by someone else

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        r_missing = client_b.get("/api/search/search", params={"q": "x", "universe_id": str(uuid4())})
        r_foreign = client_b.get("/api/search/search", params={"q": "x", "universe_id": foreign})
        assert r_foreign.status_code == r_missing.status_code == 404
        assert r_foreign.json() == r_missing.json() == {"detail": "Not found"}
        assert user["id"]  # noqa: B018

    def test_universe_search_requires_ownership(self, captured):
        c, calls, fake_db = captured
        user = _signup(c, "a@example.com", "alice")
        mine = _own_world(fake_db, user["id"])
        foreign = _own_world(fake_db, str(uuid4()))

        r = c.get(f"/api/search/universes/{mine}/search", params={"q": "dragon"})
        assert r.status_code == 200
        assert calls and all(str(call.filter.universe_id) == mine for call in calls if call.filter)

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        assert client_b.get(f"/api/search/universes/{mine}/search", params={"q": "dragon"}).status_code == 404
        assert client_b.get(f"/api/search/universes/{foreign}/search", params={"q": "dragon"}).status_code == 404
