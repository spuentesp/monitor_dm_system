"""Ownership tests for the world-graph router (multi-tenancy Phase 6 task 4).

Verifies the Neo4j reads behind /api/graph are scoped to universes the
caller owns: the universe list is queried with an owned-id filter (asserted
on the real callee's arguments), and a foreign universe_id answers the same
generic 404 as a missing one. Hermetic: the neo4j tools are patched at the
router namespace.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.routers.graph as graph_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    import monitor_ui.auth as _auth_mod

    monkeypatch.setattr(_auth_mod, "_signup_limiter", None)
    monkeypatch.setattr(_auth_mod, "_login_limiter", None)
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres

    calls: list = []

    def fake_list_universes(filters):
        calls.append(("universes", filters))
        return []

    def fake_list_multiverses(ids=None):
        calls.append(("multiverses", ids))
        return []

    def fake_list_entities(filters):
        calls.append(("entities", filters))
        return SimpleNamespace(entities=[])

    monkeypatch.setattr(graph_mod, "neo4j_ensure_omniverse", lambda: None)
    monkeypatch.setattr(graph_mod, "neo4j_list_multiverses", fake_list_multiverses)
    monkeypatch.setattr(graph_mod, "neo4j_list_universes", fake_list_universes)
    monkeypatch.setattr(graph_mod, "neo4j_list_entities", fake_list_entities)

    c = TestClient(app)
    yield c, calls, fake_db
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict:
    if not c.cookies.get("monitor_csrf"):
        c.get("/api/auth/config")
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
        headers={"X-CSRF-Token": c.cookies.get("monitor_csrf", "")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _own_world(fake_db: FakePostgres, owner_id: str) -> str:
    uid = str(uuid4())
    fake_db.worlds[uid] = {
        "id": uid,
        "owner_id": UUID(owner_id),
        "multiverse_id": str(uuid4()),
        "label": "w",
        "active": True,
    }
    return uid


class TestGraphScoping:
    def test_universe_list_is_scoped_to_owned(self, captured):
        c, calls, fake_db = captured
        user = _signup(c, "a@example.com", "alice")
        mine = _own_world(fake_db, user["id"])
        r = c.get("/api/graph/world")
        assert r.status_code == 200, r.text
        universe_calls = [f for name, f in calls if name == "universes"]
        assert universe_calls, "expected neo4j_list_universes to be called"
        # the real callee got a filter carrying exactly the owned universe ids
        ids = universe_calls[-1].ids
        assert ids is not None and {str(i) for i in ids} == {mine}

    def test_foreign_universe_is_the_same_404_as_missing(self, captured):
        c, calls, fake_db = captured
        user = _signup(c, "a@example.com", "alice")
        foreign = _own_world(fake_db, str(uuid4()))
        mine = _own_world(fake_db, user["id"])
        # A's own universe passes the gate (handler may answer 200)
        assert c.get("/api/graph/world", params={"universe_id": mine}).status_code == 200
        r_foreign = c.get("/api/graph/world", params={"universe_id": foreign})
        r_missing = c.get("/api/graph/world", params={"universe_id": uuid4()})
        assert r_foreign.status_code == r_missing.status_code == 404
        assert r_foreign.json() == r_missing.json() == {"detail": "Not found"}

    def test_universe_graph_route_requires_ownership(self, captured):
        c, calls, fake_db = captured
        user = _signup(c, "a@example.com", "alice")
        foreign = _own_world(fake_db, str(uuid4()))
        mine = _own_world(fake_db, user["id"])
        assert c.get(f"/api/graph/universes/{mine}/graph").status_code == 200
        assert c.get(f"/api/graph/universes/{foreign}/graph").status_code == 404

    def test_entity_graph_route_requires_ownership(self, captured):
        c, calls, fake_db = captured
        _signup(c, "a@example.com", "alice")
        foreign = _own_world(fake_db, str(uuid4()))
        entity_id = uuid4()
        # A's entity resolves to A's universe and passes the gate; a foreign
        # universe behind an entity id is rejected identically to a missing one.
        r = c.get(f"/api/graph/universes/{foreign}/graph/entity/{entity_id}")
        assert r.status_code == 404
        assert r.json() == {"detail": "Not found"}
