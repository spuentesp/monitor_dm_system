"""Settings created by ingest / pack apply are registered to their creator.

``_create_setting`` and ``_ensure_universe_for_multiverse`` only write Neo4j.
Without a Postgres ownership row the creator cannot see or write the new
setting once auth is on (owned_world_ids would not list it). Hermetic:
FakePostgres plus patched Neo4j helpers.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import monitor_ui.routers.ingest_shared as shared
from fake_postgres import FakePostgres
from monitor_ui.auth import Principal


def _user() -> Principal:
    return Principal(user_id=uuid4(), is_admin=False, via="session")


@pytest.mark.asyncio
async def test_register_setting_owner_records_multiverse_and_universe() -> None:
    db = FakePostgres()
    principal = _user()
    mv_id, uni_id = uuid4(), uuid4()

    await shared.register_setting_owner(db, principal, mv_id, uni_id, "Dune")

    assert db.multiverses[str(mv_id)]["owner_id"] == principal.user_id
    world = await db.world_get_for_owner(str(uni_id), principal.user_id)
    assert world is not None
    assert world["label"] == "Dune — Canon"
    # Another user does not own it.
    assert await db.world_get_for_owner(str(uni_id), uuid4()) is None


@pytest.mark.asyncio
async def test_register_setting_owner_is_noop_in_local_mode() -> None:
    db = FakePostgres()
    local = Principal(user_id=uuid4(), is_admin=True, via="local")

    await shared.register_setting_owner(db, local, uuid4(), uuid4(), "Dune")

    assert db.multiverses == {} and db.worlds == {}


@pytest.mark.asyncio
async def test_register_universe_owner_registers_new_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakePostgres()
    principal = _user()
    mv_id, uni_id = uuid4(), uuid4()
    monkeypatch.setattr(shared, "neo4j_get_universe", lambda _uid: SimpleNamespace(name="Arrakis — Canon"))

    await shared.register_universe_owner(db, principal, mv_id, uni_id)

    world = await db.world_get_for_owner(str(uni_id), principal.user_id)
    assert world is not None and world["label"] == "Arrakis — Canon"


@pytest.mark.asyncio
async def test_register_universe_owner_leaves_an_existing_row_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakePostgres()
    principal = _user()
    mv_id, uni_id = uuid4(), uuid4()
    await db.world_upsert(
        {"id": str(uni_id), "owner_id": principal.user_id, "multiverse_id": str(mv_id), "label": "Kept", "active": True}
    )
    calls: list[dict] = []

    async def _spy_bindings(bindings: dict) -> None:
        calls.append(bindings)

    monkeypatch.setattr(db, "world_bindings_upsert", _spy_bindings)

    await shared.register_universe_owner(db, principal, mv_id, uni_id)

    assert (await db.world_get_for_owner(str(uni_id), principal.user_id))["label"] == "Kept"
    assert calls == []  # bindings of an existing world are never reset


class TestRoutesRegisterNewSettings:
    """The routes that create settings call the registration helpers."""

    def test_upload_with_new_setting_registers_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi.testclient import TestClient

        import monitor_ui.routers.ingest as ingest_mod
        from monitor_ui.auth import get_postgres
        from monitor_ui.config import get_settings
        from monitor_ui.main import app

        fake_db = FakePostgres()
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
        monkeypatch.setenv("MONITOR_SIGNUP_MODE", "open")
        import monitor_ui.auth as auth_mod

        monkeypatch.setattr(auth_mod, "_signup_limiter", None)
        get_settings.cache_clear()

        async def _fake_get_postgres() -> FakePostgres:
            return fake_db

        mv_id, uni_id = uuid4(), uuid4()
        monkeypatch.setattr(ingest_mod, "_create_setting", lambda **_kw: (mv_id, uni_id))
        registered: list[tuple] = []

        async def _spy(db, principal, m, u, name):  # type: ignore[no-untyped-def]
            registered.append((principal.user_id, m, u, name))

        monkeypatch.setattr(ingest_mod, "register_setting_owner", _spy)
        app.dependency_overrides[get_postgres] = _fake_get_postgres
        try:
            c = TestClient(app, raise_server_exceptions=False)
            c.get("/api/auth/config")
            r = c.post(
                "/api/auth/signup",
                json={"email": "a@example.com", "username": "alice", "password": "correct horse battery"},
                headers={"X-CSRF-Token": c.cookies.get("monitor_csrf", "")},
            )
            assert r.status_code == 201, r.text
            user_id = UUID(r.json()["id"])
            c.post(
                "/api/ingest/sources/upload",
                files={"file": ("a.txt", b"hello", "text/plain")},
                data={"new_setting_name": "Dune"},
                headers={"X-CSRF-Token": c.cookies.get("monitor_csrf", "")},
            )
        finally:
            app.dependency_overrides.pop(get_postgres, None)
            get_settings.cache_clear()

        # Whatever happens after (no MinIO here), the new setting was registered
        # to the uploader before anything else touched it.
        assert registered == [(user_id, mv_id, uni_id, "Dune")]
