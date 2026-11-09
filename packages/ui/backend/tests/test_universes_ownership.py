"""Two-user ownership tests for the universes/multiverses router (Phase 3).

Neo4j tools are patched with an in-memory fake and the Postgres registry is
the shared FakePostgres, so these run hermetically. Verifies deny-by-default,
owner-scoped lists, identical 404s for foreign vs. nonexistent IDs, and
creation-time ownership registration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.routers.universes as universes_mod
from monitor_ui.auth import LOCAL_USER_ID, get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


# ---------------------------------------------------------------------------
# In-memory Neo4j fake
# ---------------------------------------------------------------------------


class FakeNeo4j:
    def __init__(self) -> None:
        self.multiverses: dict[str, SimpleNamespace] = {}
        self.universes: dict[str, SimpleNamespace] = {}

    def ensure_omniverse(self):
        return {"omniverse_id": str(uuid4())}

    def create_multiverse(self, params):
        mv = SimpleNamespace(
            id=uuid4(),
            name=params.name,
            system_name=params.system_name,
            description=params.description,
            is_template=False,
            knowledge_tree_type=None,
            parent_multiverse_id=None,
            created_at=datetime.now(UTC),
        )
        self.multiverses[str(mv.id)] = mv
        return mv

    def get_multiverse(self, mv_id):
        return self.multiverses.get(str(mv_id))

    def list_multiverses(self, omniverse_id=None, ids=None):
        rows = list(self.multiverses.values())
        if ids is not None:
            wanted = {str(i) for i in ids}
            rows = [m for m in rows if str(m.id) in wanted]
        return rows

    def update_multiverse(self, mv_id, params):
        mv = self.multiverses.get(str(mv_id))
        if mv is None:
            raise ValueError("not found")
        if params.name is not None:
            mv.name = params.name
        return mv

    def delete_multiverse(self, mv_id, force=False):
        self.multiverses.pop(str(mv_id), None)
        return {"deleted": True}

    def create_universe(self, params):
        u = SimpleNamespace(
            id=uuid4(),
            name=params.name,
            multiverse_id=params.multiverse_id,
            genre=params.genre,
            tone=None,
            description=params.description,
            is_template=False,
            default_game_system_id=None,
            canon_level=None,
            created_at=datetime.now(UTC),
        )
        self.universes[str(u.id)] = u
        return u

    def get_universe(self, universe_id):
        return self.universes.get(str(universe_id))

    def list_universes(self, filters=None):
        rows = list(self.universes.values())
        if filters is not None:
            if filters.multiverse_id is not None:
                rows = [u for u in rows if str(u.multiverse_id) == str(filters.multiverse_id)]
            if getattr(filters, "ids", None):
                wanted = {str(i) for i in filters.ids}
                rows = [u for u in rows if str(u.id) in wanted]
        return rows

    def update_universe(self, universe_id, params):
        u = self.universes.get(str(universe_id))
        if u is None:
            raise ValueError("not found")
        if params.name is not None:
            u.name = params.name
        return u

    def delete_universe(self, universe_id, force=False):
        self.universes.pop(str(universe_id), None)
        return {"deleted": True}

    def get_universe_state(self, universe_id):
        return {"universe_id": str(universe_id), "entities": [], "facts": []}

    def fork_universe(self, source_universe_id, name, description):
        src = self.universes[str(source_universe_id)]
        u = SimpleNamespace(
            id=uuid4(),
            name=name,
            multiverse_id=src.multiverse_id,
            genre=src.genre,
            tone=None,
            description=description,
            is_template=False,
            default_game_system_id=None,
            canon_level=None,
            created_at=datetime.now(UTC),
        )
        self.universes[str(u.id)] = u
        return {"new_universe_id": str(u.id), "entities_cloned": 3, "relationships_cloned": 1}


def _zero_counts(ids):
    return {i: {"entity_count": 0, "session_count": 0, "story_count": 0} for i in ids}


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def neo() -> FakeNeo4j:
    return FakeNeo4j()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres, neo: FakeNeo4j):
    """TestClient with fake Postgres registry and fake Neo4j tools."""
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    patches = [
        patch.object(universes_mod, "neo4j_ensure_omniverse", neo.ensure_omniverse),
        patch.object(universes_mod, "neo4j_create_multiverse", neo.create_multiverse),
        patch.object(universes_mod, "neo4j_get_multiverse", neo.get_multiverse),
        patch.object(universes_mod, "neo4j_list_multiverses", neo.list_multiverses),
        patch.object(universes_mod, "neo4j_update_multiverse", neo.update_multiverse),
        patch.object(universes_mod, "neo4j_delete_multiverse", neo.delete_multiverse),
        patch.object(universes_mod, "neo4j_create_universe", neo.create_universe),
        patch.object(universes_mod, "neo4j_get_universe", neo.get_universe),
        patch.object(universes_mod, "neo4j_list_universes", neo.list_universes),
        patch.object(universes_mod, "neo4j_update_universe", neo.update_universe),
        patch.object(universes_mod, "neo4j_delete_universe", neo.delete_universe),
        patch.object(universes_mod, "neo4j_get_universe_state", neo.get_universe_state),
        patch.object(universes_mod, "_universe_counts", _zero_counts),
        patch("monitor_data.tools.neo4j_tools.neo4j_fork_universe", neo.fork_universe),
    ]
    for p in patches:
        p.start()
    c = TestClient(app)
    yield c
    for p in patches:
        p.stop()
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


def _make_world(c: TestClient, name: str = "World A") -> tuple[str, str]:
    """Create a multiverse + universe as the client's user; returns (mv_id, universe_id)."""
    r = c.post(
        "/api/universes/multiverses",
        json={"name": f"MV {name}", "description": f"Multiverse for {name}"},
        headers=_csrf(c),
    )
    assert r.status_code == 201, r.text
    mv_id = r.json()["id"]
    r = c.post(
        "/api/universes/universes",
        json={"name": name, "multiverse_id": mv_id, "description": f"Universe {name}"},
        headers=_csrf(c),
    )
    assert r.status_code == 201, r.text
    return mv_id, r.json()["id"]


class TestDenyByDefault:
    def test_unauthenticated_requests_get_401(self, client):
        assert client.get("/api/universes/universes").status_code == 401
        assert client.get("/api/universes/multiverses").status_code == 401
        r = client.post("/api/universes/multiverses", json={"name": "x"})
        assert r.status_code == 401
        assert client.get("/api/universes/universes/%s" % uuid4()).status_code == 401


class TestOwnershipScoping:
    def test_creation_registers_owner_and_lists_are_scoped(
        self, client: TestClient, fake_db: FakePostgres, neo: FakeNeo4j
    ):
        user_a = _signup(client, "a@example.com", "alice")
        mv_id, uni_id = _make_world(client, "World A")
        assert fake_db.multiverses[mv_id]["owner_id"] == UUID(user_a["id"])
        assert fake_db.worlds[uni_id]["owner_id"] == UUID(user_a["id"])
        assert fake_db.worlds[uni_id]["multiverse_id"] == mv_id

        # A sees exactly one multiverse and one universe
        mvs = client.get("/api/universes/multiverses").json()
        assert [m["id"] for m in mvs] == [mv_id]
        unis = client.get("/api/universes/universes").json()
        assert [u["id"] for u in unis] == [uni_id]

        # B (separate session) sees nothing of A's
        client_b = TestClient(app)
        user_b = _signup(client_b, "b@example.com", "bob")
        assert user_b["id"] != user_a["id"]
        assert client_b.get("/api/universes/multiverses").json() == []
        assert client_b.get("/api/universes/universes").json() == []

    def test_foreign_and_missing_ids_return_identical_404(self, client: TestClient, neo: FakeNeo4j):
        _signup(client, "a@example.com", "alice")
        mv_id, uni_id = _make_world(client, "World A")

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")

        foreign = client_b.get(f"/api/universes/universes/{uni_id}")
        missing = client_b.get(f"/api/universes/universes/{uuid4()}")
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json() == {"detail": "Not found"}

        assert (
            client_b.put(
                f"/api/universes/universes/{uni_id}", json={"name": "hijack"}, headers=_csrf(client_b)
            ).status_code
            == 404
        )
        assert (
            client_b.request("DELETE", f"/api/universes/universes/{uni_id}", headers=_csrf(client_b)).status_code == 404
        )
        assert client_b.get(f"/api/universes/universes/{uni_id}/state").status_code == 404
        assert (
            client_b.request("DELETE", f"/api/universes/multiverses/{mv_id}", headers=_csrf(client_b)).status_code
            == 404
        )
        # B cannot create a universe under A's multiverse
        r = client_b.post(
            "/api/universes/universes",
            json={"name": "sneaky", "multiverse_id": mv_id},
            headers=_csrf(client_b),
        )
        assert r.status_code == 404
        assert neo.universes.keys() == {uni_id}

    def test_fork_registers_new_world_under_caller(self, client: TestClient, fake_db: FakePostgres, monkeypatch):
        # The pre-existing fork path also clones Mongo/Qdrant data; stub those.
        monkeypatch.setattr(universes_mod, "mongodb_fork_universe_data", lambda *a, **k: {"copied": 0})
        monkeypatch.setattr(universes_mod, "qdrant_clone_collection", lambda *a, **k: {"points_copied": 0})

        class _FakeMinio:
            async def copy_prefix(self, *a, **k):  # type: ignore[no-untyped-def]
                return {"copied": 0}

        monkeypatch.setattr(universes_mod, "get_minio_client", lambda: _FakeMinio())
        user_a = _signup(client, "a@example.com", "alice")
        _, uni_id = _make_world(client, "World A")

        r = client.post(
            f"/api/universes/universes/{uni_id}/fork",
            json={"name": "Fork"},
            headers=_csrf(client),
        )
        assert r.status_code == 200, r.text
        fork_id = r.json()["new_universe_id"]
        assert fake_db.worlds[fork_id]["owner_id"] == UUID(user_a["id"])

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        assert client_b.get(f"/api/universes/universes/{fork_id}").status_code == 404
        assert [u["id"] for u in client.get("/api/universes/universes").json()] == [uni_id, fork_id] or {
            u["id"] for u in client.get("/api/universes/universes").json()
        } == {uni_id, fork_id}

    def test_delete_detaches_registry_row(self, client: TestClient, fake_db: FakePostgres):
        _signup(client, "a@example.com", "alice")
        _, uni_id = _make_world(client, "World A")
        r = client.request("DELETE", f"/api/universes/universes/{uni_id}", headers=_csrf(client))
        assert r.status_code == 204
        assert uni_id not in fake_db.worlds
        # Now even the owner gets the generic 404 (unregistered fails closed)
        assert client.get(f"/api/universes/universes/{uni_id}").status_code == 404

    def test_owner_can_still_use_own_world(self, client: TestClient):
        _signup(client, "a@example.com", "alice")
        mv_id, uni_id = _make_world(client, "World A")
        assert client.get(f"/api/universes/universes/{uni_id}").status_code == 200
        r = client.put(f"/api/universes/universes/{uni_id}", json={"name": "Renamed"}, headers=_csrf(client))
        assert r.status_code == 200 and r.json()["name"] == "Renamed"
        assert client.get(f"/api/universes/universes/{uni_id}/state").status_code == 200
        assert client.get("/api/universes/universes", params={"multiverse_id": mv_id}).status_code == 200


class TestLocalMode:
    def test_auth_disabled_lists_everything(
        self, monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres, neo: FakeNeo4j
    ):
        monkeypatch.setenv("MONITOR_AUTH_DISABLED", "true")
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
        get_settings.cache_clear()
        try:

            async def _fake_get_postgres() -> FakePostgres:
                return fake_db

            app.dependency_overrides[get_postgres] = _fake_get_postgres
            # Seed a "legacy" world with no registry row
            legacy = neo.create_universe(
                SimpleNamespace(multiverse_id=uuid4(), name="Legacy", description="", genre=None)
            )
            with (
                patch.object(universes_mod, "neo4j_list_universes", neo.list_universes),
                patch.object(universes_mod, "neo4j_list_multiverses", neo.list_multiverses),
                patch.object(universes_mod, "_universe_counts", _zero_counts),
            ):
                c = TestClient(app)
                r = c.get("/api/universes/universes")
                assert r.status_code == 200
                assert [u["id"] for u in r.json()] == [str(legacy.id)]
                me = c.get("/api/auth/me").json()
                assert me["user"]["id"] == str(LOCAL_USER_ID)
        finally:
            app.dependency_overrides.pop(get_postgres, None)
            get_settings.cache_clear()
