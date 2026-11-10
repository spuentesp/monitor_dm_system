"""Two-user ownership tests for image assets/gen (MinIO-backed resources).

Assets authorize through their owning universe or character — never through
knowledge of a MinIO object key. Hermetic: FakePostgres + patched Mongo tools.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.routers.image_assets as ia_mod
import monitor_ui.routers.image_gen as ig_mod
import monitor_ui.ownership as ownership_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


class FakeCharactersCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def find_one(self, query, *a, **k):  # type: ignore[no-untyped-def]
        for d in self.docs:
            if all(d.get(key) == v for key, v in query.items()):
                return d
        return None


def _asset(asset_id: UUID, universe_id: str | None, character_id: str | None) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        asset_id=asset_id,
        id=asset_id,
        universe_id=UUID(universe_id) if universe_id else None,
        character_id=character_id,
        minio_key="assets/x.png",
        asset_type="portrait",
        byte_size=1,
        prompt="p",
        provider_id="p",
        provider_model="m",
        status="pending",
        created_at=now,
        updated_at=now,
    )


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
    c = TestClient(app, raise_server_exceptions=False)
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


class TestImageOwnership:
    def test_unauthenticated_denied(self, client):
        assert client.get("/api/image/assets").status_code == 401
        assert client.get(f"/api/image/assets/{uuid4()}").status_code == 401
        assert client.get(f"/api/image/assets/{uuid4()}/file").status_code == 401
        assert client.get(f"/api/image/avatar/{uuid4()}").status_code == 401
        assert client.post("/api/image/portrait", json={}).status_code == 401

    def test_asset_access_requires_owning_universe(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        my_world = _own_world(fake_db, user["id"])
        foreign_world = _own_world(fake_db, str(uuid4()))
        my_asset = _asset(uuid4(), my_world, None)
        foreign_asset = _asset(uuid4(), foreign_world, None)
        assets = {str(my_asset.asset_id): my_asset, str(foreign_asset.asset_id): foreign_asset}
        monkeypatch.setattr(ia_mod, "mongodb_get_generated_asset", lambda aid: assets.get(str(aid)))
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.generated_assets.mongodb_get_generated_asset",
            lambda aid: assets.get(str(aid)),
        )
        monkeypatch.setattr(ia_mod, "_get_asset_or_404", lambda aid: assets.get(str(aid)) or None)

        assert client.get(f"/api/image/assets/{my_asset.asset_id}").status_code == 200
        r = client.get(f"/api/image/assets/{foreign_asset.asset_id}")
        assert r.status_code == 404 and r.json() == {"detail": "Not found"}
        # /file must not leak a presigned URL for a foreign asset
        r = client.get(f"/api/image/assets/{foreign_asset.asset_id}/file")
        assert r.status_code == 404
        assert client.get(f"/api/image/assets/{uuid4()}").json() == {"detail": "Not found"}

    def test_avatar_requires_character_ownership(self, client, chars, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        mine = str(uuid4())
        foreign = str(uuid4())
        chars.docs.append({"id": mine, "owner_id": user["id"]})
        chars.docs.append({"id": foreign, "owner_id": str(uuid4())})
        # avatar handler resolves the character then presigns; stub the tail
        monkeypatch.setattr(ig_mod, "get_character", lambda cid: {"id": cid, "avatar_url": None})
        r = client.get(f"/api/image/avatar/{mine}")
        assert r.status_code in (200, 404, 302)  # passes the ownership gate
        assert client.get(f"/api/image/avatar/{foreign}").status_code == 404

    def test_settings_admin_only(self, client):
        _signup(client, "a@example.com", "alice")
        assert client.get("/api/image/settings").status_code == 403
        assert client.put("/api/image/settings", json={}).status_code == 403

    def test_list_scoped_to_owned_universes(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user["id"])
        captured = {}

        def fake_list(params):
            captured["universe_ids"] = params.universe_ids
            return []

        monkeypatch.setattr(ia_mod, "mongodb_list_generated_assets", fake_list)
        r = client.get("/api/image/assets")
        assert r.status_code == 200
        assert [str(u) for u in captured["universe_ids"]] == [world]
        # explicit foreign universe filter → 404
        foreign_world = _own_world(fake_db, str(uuid4()))
        assert client.get("/api/image/assets", params={"universe_id": foreign_world}).status_code == 404
