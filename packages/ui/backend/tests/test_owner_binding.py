"""The acting owner is bound by the UI and surfaces in client errors (A.1 / B.3).

- ``resolve_principal`` binds the owner to the request/turn context and
  explicitly unbinds it in auth-disabled local mode.
- The loop builders pass the session owner into the loop constructors.
- A tool-boundary owner refusal maps to the generic 404 and an over-budget
  owner maps to a readable 429 on HTTP; the chat WebSocket answers a
  readable ``error`` event.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import json
import pytest
from fastapi.testclient import TestClient

import monitor_ui.routers.chat as chat_mod
import monitor_ui.ownership as ownership_mod
from monitor_data.tenancy import OwnerViolationError, get_owner_id, set_owner_id
from monitor_data.usage import QuotaExceededError
from monitor_ui.auth import get_postgres, resolve_principal
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


@pytest.fixture(autouse=True)
def _reset_owner_context() -> Any:
    yield
    set_owner_id(None)


class FakeChatCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def find_one(self, query: dict, *args: object, **kwargs: object) -> dict | None:
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None

    def insert(self, doc: dict) -> None:
        self.docs.append(dict(doc))


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def chat_col() -> FakeChatCollection:
    return FakeChatCollection()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres, chat_col: FakeChatCollection):
    monkeypatch.setenv("MONITOR_AUTH_DISABLED", "false")
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
        c.get("/api/auth/config")
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
        headers={"X-CSRF-Token": c.cookies.get("monitor_csrf", "")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


class TestOwnerBinding:
    def test_authenticated_request_binds_the_owner_context(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        me = _signup(client, "a@example.com", "alice")
        seen: list[str | None] = []

        async def _draft_card(**kwargs: object) -> dict:
            seen.append(get_owner_id())
            return {"name": "Detective"}

        monkeypatch.setattr("monitor_ui.routers.character_conversation.draft_card", _draft_card)
        r = client.post("/api/entities/characters/draft", json={"concept": "x"}, headers=_csrf(client))
        assert r.status_code == 200, r.text
        assert seen == [me["id"]]

    def test_resolve_principal_binds_and_local_mode_unbinds(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        me = _signup(client, "a@example.com", "alice")

        async def _bound_after_session() -> tuple[str, str | None]:
            principal = await resolve_principal(
                authorization=None,
                cookies={"monitor_session": client.cookies.get("monitor_session")},
                settings=get_settings(),
                db=fake_db,
            )
            return str(principal.user_id), get_owner_id()

        uid, bound = asyncio.run(_bound_after_session())
        assert uid == me["id"]
        assert bound == me["id"]

        # Auth-disabled local mode: the owner is explicitly unbound.
        monkeypatch.setenv("MONITOR_AUTH_DISABLED", "true")
        get_settings.cache_clear()

        async def _bound_after_local() -> str | None:
            await resolve_principal(authorization=None, cookies={}, settings=get_settings(), db=fake_db)
            return get_owner_id()

        assert asyncio.run(_bound_after_local()) is None
        get_settings.cache_clear()

    def test_get_scene_loop_passes_the_session_owner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from monitor_ui.routers.chat_loops import get_scene_loop

        owner = str(uuid4())
        session = {
            "owner_id": owner,
            "universe_id": str(uuid4()),
            "story_id": str(uuid4()),
            "play_mode": "narrative",
        }
        loop = get_scene_loop(
            str(uuid4()),
            session,
            scene_id=str(uuid4()),
            story_id=session["story_id"],
        )
        assert loop.owner_id == owner


class TestErrorMapping:
    def test_owner_violation_maps_to_generic_404(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _signup(client, "a@example.com", "alice")

        async def _boom(**kwargs: object) -> dict:
            raise OwnerViolationError("refusing memory write: foreign universe")

        monkeypatch.setattr("monitor_ui.routers.character_conversation.draft_card", _boom)
        r = client.post("/api/entities/characters/draft", json={"concept": "x"}, headers=_csrf(client))
        assert r.status_code == 404
        assert r.json()["detail"] == "Not found"

    def test_quota_exceeded_maps_to_readable_429(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _signup(client, "a@example.com", "alice")

        async def _boom(**kwargs: object) -> dict:
            raise QuotaExceededError("token", 5000)

        monkeypatch.setattr("monitor_ui.routers.character_conversation.draft_card", _boom)
        r = client.post("/api/entities/characters/draft", json={"concept": "x"}, headers=_csrf(client))
        assert r.status_code == 429
        assert "Daily token limit reached (5000 tokens)" in r.json()["detail"]

    def test_ws_turn_quota_refusal_is_a_readable_error_event(
        self, client: TestClient, chat_col: FakeChatCollection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        me = _signup(client, "a@example.com", "alice")
        sid = str(uuid4())
        chat_col.insert({"id": sid, "owner_id": me["id"], "title": "S"})
        chat_mod._SESSIONS[sid] = {"id": sid, "owner_id": me["id"], "phase": "active_play"}

        async def _boom(*args: object, **kwargs: object) -> tuple[str, dict]:
            raise QuotaExceededError("call", 3)

        monkeypatch.setattr(chat_mod, "_run_scene_turn", _boom)
        cookie = {"cookie": f"monitor_session={client.cookies.get('monitor_session')}"}
        with client.websocket_connect(f"/api/chat/ws/{sid}", headers=cookie) as ws:
            ws.send_text(json.dumps({"type": "message", "content": "hello"}))
            # start/composing frames precede the turn; the quota refusal is the
            # readable error event the brief requires.
            for _ in range(5):
                frame = json.loads(ws.receive_text())
                if frame["type"] == "error":
                    break
            assert frame["type"] == "error"
            assert frame["error_class"] == "quota_exceeded"
            assert "Daily model-call limit reached (3 calls)" in frame["detail"]
