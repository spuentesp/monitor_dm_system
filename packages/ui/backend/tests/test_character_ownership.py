"""Two-user ownership tests for standalone characters (Phase 4 slice).

Characters are rootless Mongo docs: ownership is the ``owner_id`` field,
checked in the Mongo query itself. Hermetic: FakePostgres registry + a fake
``characters`` collection shared by the storage helpers and the owner check.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.ownership as ownership_mod


import monitor_ui.routers.character_storage as cs_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


class FakeCursor:
    def __init__(self, docs):  # type: ignore[no-untyped-def]
        self._docs = docs

    def sort(self, *a, **k):  # type: ignore[no-untyped-def]
        return self

    def skip(self, n: int):  # type: ignore[no-untyped-def]
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int):  # type: ignore[no-untyped-def]
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeDeleteResult:
    def __init__(self, count: int) -> None:
        self.deleted_count = count


class FakeCharactersCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def _match(self, doc: dict, query: dict) -> bool:  # type: ignore[no-untyped-def]
        return all(doc.get(k) == v for k, v in query.items())

    def find_one(self, query: dict, *a, **k):  # type: ignore[no-untyped-def]
        for d in self.docs:
            if self._match(d, query):
                return d
        return None

    def find(self, query: dict, *a, **k):  # type: ignore[no-untyped-def]
        return FakeCursor([d for d in self.docs if self._match(d, query)])

    def count_documents(self, query: dict) -> int:
        return sum(1 for d in self.docs if self._match(d, query))

    def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)

    def find_one_and_update(self, query: dict, update: dict, return_document: bool = True):  # type: ignore[no-untyped-def]
        for d in self.docs:
            if self._match(d, query):
                d.update(update.get("$set", {}))
                return d
        return None

    def delete_one(self, query: dict) -> FakeDeleteResult:
        for i, d in enumerate(self.docs):
            if self._match(d, query):
                del self.docs[i]
                return FakeDeleteResult(1)
        return FakeDeleteResult(0)


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def chars() -> FakeCharactersCollection:
    return FakeCharactersCollection()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres, chars: FakeCharactersCollection):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    import monitor_ui.auth as _auth_mod

    monkeypatch.setattr(_auth_mod, "_signup_limiter", None)
    monkeypatch.setattr(_auth_mod, "_login_limiter", None)
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    monkeypatch.setattr(ownership_mod, "_characters_collection", lambda: chars)
    monkeypatch.setattr(cs_mod, "_coll", lambda: chars)
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict:
    if not c.cookies.get("monitor_csrf"):
        c.get("/api/auth/config")  # safe GET issues the CSRF cookie
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
        headers={"X-CSRF-Token": c.cookies.get("monitor_csrf", "")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


def _create(c: TestClient, name: str) -> dict:
    r = c.post(
        "/api/entities/characters",
        json={"name": name, "description": "d", "personality": "p", "first_message": "hi"},
        headers=_csrf(c),
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestCharacterOwnership:
    def test_unauthenticated_denied(self, client):
        assert client.get("/api/entities/characters").status_code == 401
        assert client.post("/api/entities/characters", json={"name": "x"}).status_code == 401
        assert client.get(f"/api/entities/characters/{uuid4()}").status_code == 401

    def test_create_stamps_owner_and_lists_are_scoped(self, client, chars):
        user_a = _signup(client, "a@example.com", "alice")
        a1 = _create(client, "Alice's Hero")
        assert a1["id"]
        doc = chars.find_one({"id": a1["id"]})
        assert doc is not None and doc["owner_id"] == user_a["id"]

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        _create(client_b, "Bob's Rogue")

        ids_a = {c["id"] for c in client.get("/api/entities/characters").json()}
        ids_b = {c["id"] for c in client_b.get("/api/entities/characters").json()}
        assert ids_a == {a1["id"]}
        assert ids_b != ids_a and len(ids_b) == 1

    def test_foreign_and_missing_404_identical(self, client):
        _signup(client, "a@example.com", "alice")
        mine = _create(client, "Mine")
        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")

        for method, path, kwargs in [
            ("GET", f"/api/entities/characters/{mine['id']}", {}),
            ("PUT", f"/api/entities/characters/{mine['id']}", {"json": {"name": "hijack"}}),
            ("DELETE", f"/api/entities/characters/{mine['id']}", {}),
            ("GET", f"/api/entities/characters/{mine['id']}/export-card", {}),
            ("GET", f"/api/entities/characters/{mine['id']}/memories", {}),
            ("GET", f"/api/entities/characters/{mine['id']}/conversations", {}),
        ]:
            r = client_b.request(method, path, headers=_csrf(client_b), **kwargs)
            assert r.status_code == 404, (method, path, r.status_code)
            assert r.json() == {"detail": "Not found"}
        missing = client_b.get(f"/api/entities/characters/{uuid4()}")
        assert missing.json() == {"detail": "Not found"}

    def test_owner_can_read_and_update(self, client, monkeypatch):
        _signup(client, "a@example.com", "alice")
        mine = _create(client, "Mine")
        assert client.get(f"/api/entities/characters/{mine['id']}").status_code == 200
        r = client.put(
            f"/api/entities/characters/{mine['id']}",
            json={"name": "Renamed"},
            headers=_csrf(client),
        )
        assert r.status_code == 200 and r.json()["name"] == "Renamed"
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.lorebook_tools.mongodb_get_lorebook_entries",
            lambda *a, **k: [],
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.lorebook_tools.mongodb_get_scan_config",
            lambda *a, **k: None,
        )
        assert client.get(f"/api/entities/characters/{mine['id']}/export-card").status_code == 200

    def test_delete_is_owner_predicated(self, client, chars):
        _signup(client, "a@example.com", "alice")
        mine = _create(client, "Mine")
        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        # B cannot delete A's card
        r = client_b.request("DELETE", f"/api/entities/characters/{mine['id']}", headers=_csrf(client_b))
        assert r.status_code == 404
        assert chars.find_one({"id": mine["id"]}) is not None
        # A can
        r = client.request("DELETE", f"/api/entities/characters/{mine['id']}", headers=_csrf(client))
        assert r.status_code == 204
        assert chars.find_one({"id": mine["id"]}) is None

    def test_import_from_foreign_universe_rejected(self, client, fake_db, monkeypatch):
        _signup(client, "a@example.com", "alice")
        # universe owned by someone else
        foreign_world = str(uuid4())
        fake_db.worlds[foreign_world] = {
            "id": foreign_world,
            "owner_id": uuid4(),
            "multiverse_id": str(uuid4()),
            "label": "w",
            "active": True,
        }
        mine = _create(client, "Mine")

        class FakeNeo4j:
            def execute_read(self, query, params):
                if "IN_UNIVERSE" in query:
                    return [{"uid": foreign_world}]
                return [{"e": {"name": "NPC", "description": "", "properties": {}}}]

        monkeypatch.setattr("monitor_data.db.neo4j.get_neo4j_client", lambda: FakeNeo4j())
        r = client.post(
            f"/api/entities/characters/{mine['id']}/import-from-universe",
            json={"source_entity_id": str(uuid4())},
            headers=_csrf(client),
        )
        assert r.status_code == 404


@pytest.fixture(autouse=True)
def _no_world_entities(monkeypatch):
    monkeypatch.setattr(ownership_mod, "_universes_of_entities", lambda ids: {})
