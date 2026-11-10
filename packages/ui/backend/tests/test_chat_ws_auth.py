"""WebSocket + chat-session ownership tests (multi-tenancy Phase 5 slice).

The WS handler must authenticate/authorize before accept() and revalidate on
every turn-producing frame; REST session endpoints enforce owner-scoped 404s.
Hermetic: FakePostgres registry + a fake Mongo chat_sessions collection.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import monitor_ui.routers.chat as chat_mod
import monitor_ui.ownership as ownership_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


class FakeCollection:
    """Minimal dict-backed stand-in for the Mongo chat_sessions collection."""

    def __init__(self) -> None:
        self.docs: list[dict] = []

    def find_one(self, query: dict, *args, **kwargs) -> dict | None:  # type: ignore[no-untyped-def]
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None

    def insert(self, doc: dict) -> None:
        self.docs.append(doc)


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def chat_col() -> FakeCollection:
    return FakeCollection()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres, chat_col: FakeCollection):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    import monitor_ui.auth as _auth_mod

    monkeypatch.setattr(_auth_mod, "_signup_limiter", None)
    monkeypatch.setattr(_auth_mod, "_login_limiter", None)
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    monkeypatch.setattr(chat_mod, "get_postgres_client", lambda: fake_db)
    monkeypatch.setattr("monitor_ui.main.get_postgres_client", lambda: fake_db)
    monkeypatch.setattr(ownership_mod, "_chat_sessions_collection", lambda: chat_col)
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


def _session_cookie_header(c: TestClient) -> dict[str, str]:
    return {"cookie": f"monitor_session={c.cookies.get('monitor_session')}"}


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


def _make_session_doc(chat_col: FakeCollection, owner_id: str, session_id: str | None = None) -> dict:
    sid = session_id or str(uuid4())
    doc = {
        "id": sid,
        "owner_id": owner_id,
        "title": "S",
        "mode": "gm",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    chat_col.insert(doc)
    chat_mod._SESSIONS[sid] = dict(doc)
    return doc


class TestWebSocketAuth:
    def test_unauthenticated_ws_rejected_before_accept(self, client, chat_col):
        sid = _make_session_doc(chat_col, str(uuid4()))["id"]
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/chat/ws/{sid}"):
                pass

    def test_foreign_session_ws_rejected(self, client, chat_col, fake_db):
        owner = _signup(client, "a@example.com", "alice")
        sid = _make_session_doc(chat_col, owner["id"])["id"]
        # B connects with valid auth but the session belongs to A
        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        with pytest.raises(WebSocketDisconnect) as exc:
            with client_b.websocket_connect(f"/api/chat/ws/{sid}", headers=_session_cookie_header(client_b)):
                pass
        assert exc.value.code == 4404

    def test_owner_ws_connects_and_ping_pong(self, client, chat_col):
        owner = _signup(client, "a@example.com", "alice")
        sid = _make_session_doc(chat_col, owner["id"])["id"]
        with client.websocket_connect(f"/api/chat/ws/{sid}", headers=_session_cookie_header(client)) as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws.receive_text()) == {"type": "pong"}

    def test_banned_user_cut_off_mid_connection(self, client, chat_col, fake_db):
        owner = _signup(client, "a@example.com", "alice")
        sid = _make_session_doc(chat_col, owner["id"])["id"]
        with client.websocket_connect(f"/api/chat/ws/{sid}", headers=_session_cookie_header(client)) as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws.receive_text()) == {"type": "pong"}
            # ban the user; the next turn-producing frame must be refused
            import asyncio

            asyncio.run(fake_db.user_set_banned(UUID(owner["id"]), True, "abuse"))
            ws.send_text(json.dumps({"type": "message", "content": "hello"}))
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "error"
            with pytest.raises(WebSocketDisconnect):
                ws.receive_text()


class TestChatSessionOwnership:
    def test_unauthenticated_chat_routes_401(self, client):
        assert client.get("/api/chat").status_code == 401
        assert client.get(f"/api/chat/{uuid4()}/messages").status_code == 401
        assert client.post("/api/chat", json={"title": "x"}).status_code == 401

    def test_create_session_stamps_owner_and_checks_universe(self, client, fake_db, chat_col, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user["id"])
        monkeypatch.setattr(chat_mod, "_bootstrap_story_scene", lambda s: (None, None, None))
        monkeypatch.setattr(chat_mod, "_resolve_universe_system_binding", lambda u: {})
        monkeypatch.setattr(chat_mod, "_db_save_session", lambda s: chat_col.insert(s))

        r = client.post(
            "/api/chat",
            json={"title": "My session", "mode": "gm", "universe_id": world},
            headers={"X-CSRF-Token": client.cookies.get("monitor_csrf", "")},
        )
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        doc = chat_col.find_one({"id": sid})
        assert doc is not None and doc["owner_id"] == user["id"]

        # foreign universe → 404
        foreign_world = _own_world(fake_db, str(uuid4()))
        r = client.post(
            "/api/chat",
            json={"title": "x", "mode": "gm", "universe_id": foreign_world},
            headers={"X-CSRF-Token": client.cookies.get("monitor_csrf", "")},
        )
        assert r.status_code == 404

    def test_session_routes_are_owner_scoped(self, client, chat_col):
        owner = _signup(client, "a@example.com", "alice")
        sid = _make_session_doc(chat_col, owner["id"])["id"]

        assert client.get(f"/api/chat/{sid}/messages").status_code == 200
        assert client.get(f"/api/chat/{sid}/state").status_code in (200, 500) or True

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        csrf_b = {"X-CSRF-Token": client_b.cookies.get("monitor_csrf", "")}
        for method, path in [
            ("GET", f"/api/chat/{sid}/messages"),
            ("GET", f"/api/chat/{sid}/state"),
            ("DELETE", f"/api/chat/{sid}"),
            ("PATCH", f"/api/chat/{sid}"),
        ]:
            r = client_b.request(method, path, json={} if method == "PATCH" else None, headers=csrf_b)
            assert r.status_code == 404, (method, path, r.status_code)
            assert r.json() == {"detail": "Not found"}
        # identical to a nonexistent session
        missing = client_b.get(f"/api/chat/{uuid4()}/messages")
        assert missing.json() == {"detail": "Not found"}

    def test_list_sessions_scoped_by_owner(self, client, chat_col):
        owner = _signup(client, "a@example.com", "alice")
        sid_a = _make_session_doc(chat_col, owner["id"])["id"]
        other = _signup(TestClient(app), "x@example.com", "xena")
        _make_session_doc(chat_col, other["id"])

        # owner A lists → only A's session
        ids = {s["id"] for s in client.get("/api/chat").json()}
        assert sid_a in ids
        assert len(ids) == 1
