"""Two-user ownership tests for the pack library (Phase 4).

knowledge_packs are rootless Mongo docs carrying owner_id; the router-level
guard checks pack ownership (and universe ownership for apply) on every route.
Hermetic: FakePostgres + patched pack tools at the router namespace.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.routers.pack_library as pl_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


def _pack(pack_id: UUID, owner_id: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=pack_id,
        pack_id=pack_id,
        owner_id=owner_id,
        name="Pack",
        description="",
        status="ready",
    )


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
    c = TestClient(app, raise_server_exceptions=False)
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


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


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


class TestPackOwnership:
    def test_unauthenticated_denied(self, client):
        assert client.get("/api/ingest/packs").status_code == 401
        assert client.get(f"/api/ingest/packs/{uuid4()}").status_code == 401
        assert client.post("/api/ingest/packs", json={}).status_code == 401

    def test_list_scoped_and_get_404_for_foreign(self, client, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        mine = _pack(uuid4(), user["id"])
        foreign = _pack(uuid4(), str(uuid4()))
        packs = {str(mine.pack_id): mine, str(foreign.pack_id): foreign}
        captured = {}

        def fake_list(params):
            captured["owner_id"] = params.owner_id
            return SimpleNamespace(packs=[], total=0, limit=params.limit, offset=params.offset)

        def fake_get(pid):
            return packs.get(str(pid))

        monkeypatch.setattr(pl_mod, "mongodb_list_knowledge_packs", fake_list)
        monkeypatch.setattr(pl_mod, "mongodb_get_knowledge_pack", fake_get)
        monkeypatch.setattr("monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack", fake_get)
        monkeypatch.setattr(pl_mod, "_pack_to_dict", lambda p: {"id": str(p.pack_id)})

        r = client.get("/api/ingest/packs")
        assert r.status_code == 200
        assert captured["owner_id"] == user["id"]

        assert client.get(f"/api/ingest/packs/{mine.pack_id}").status_code == 200
        r = client.get(f"/api/ingest/packs/{foreign.pack_id}")
        assert r.status_code == 404 and r.json() == {"detail": "Not found"}
        assert client.get(f"/api/ingest/packs/{uuid4()}").json() == {"detail": "Not found"}

    def test_delete_foreign_pack_404(self, client, monkeypatch):
        _signup(client, "a@example.com", "alice")
        foreign = _pack(uuid4(), str(uuid4()))
        monkeypatch.setattr(
            pl_mod, "mongodb_get_knowledge_pack", lambda pid: foreign if str(pid) == str(foreign.pack_id) else None
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
            lambda pid: foreign if str(pid) == str(foreign.pack_id) else None,
        )
        client_b = TestClient(app, raise_server_exceptions=False)
        _signup(client_b, "b@example.com", "bob")
        r = client_b.request("DELETE", f"/api/ingest/packs/{foreign.pack_id}", headers=_csrf(client_b))
        assert r.status_code == 404

    def test_apply_requires_pack_and_universe_ownership(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        my_pack = _pack(uuid4(), user["id"])
        foreign_pack = _pack(uuid4(), str(uuid4()))
        my_world = _own_world(fake_db, user["id"])
        foreign_world = _own_world(fake_db, str(uuid4()))
        packs = {str(my_pack.pack_id): my_pack, str(foreign_pack.pack_id): foreign_pack}
        monkeypatch.setattr(pl_mod, "mongodb_get_knowledge_pack", lambda pid: packs.get(str(pid)))
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack", lambda pid: packs.get(str(pid))
        )
        # if the guard passes, the handler would proceed; stub the service to record
        called = []

        async def fake_apply(**kwargs):  # type: ignore[no-untyped-def]
            called.append(kwargs)
            return {"ok": True}

        monkeypatch.setattr(
            "monitor_ui.routers.pack_library.KnowledgePackService.apply_pack_to_existing_world",
            staticmethod(fake_apply),
        )
        r = client.post(
            f"/api/ingest/packs/{my_pack.pack_id}/apply/{my_world}",
            json={},
            headers=_csrf(client),
        )
        assert r.status_code == 200 and called

        # foreign pack → 404, handler never runs
        called.clear()
        r = client.post(
            f"/api/ingest/packs/{foreign_pack.pack_id}/apply/{my_world}",
            json={},
            headers=_csrf(client),
        )
        assert r.status_code == 404 and not called
        # owned pack but foreign universe → 404
        called.clear()
        r = client.post(
            f"/api/ingest/packs/{my_pack.pack_id}/apply/{foreign_world}",
            json={},
            headers=_csrf(client),
        )
        assert r.status_code == 404 and not called

    def test_create_stamps_owner(self, client, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        captured = {}

        def fake_create(params):
            captured["owner_id"] = params.owner_id
            return _pack(uuid4(), params.owner_id)

        monkeypatch.setattr(pl_mod, "mongodb_create_knowledge_pack", fake_create)
        monkeypatch.setattr(pl_mod, "_pack_to_dict", lambda p: {"id": str(p.pack_id)})
        r = client.post(
            "/api/ingest/packs",
            json={"name": "My Pack", "pack_type": "custom"},
            headers=_csrf(client),
        )
        assert r.status_code == 201, r.text
        assert captured["owner_id"] == user["id"]
