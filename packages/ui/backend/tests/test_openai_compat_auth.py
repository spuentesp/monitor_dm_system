"""Auth + resource-ownership tests for the OpenAI-compatible endpoint.

/api/v1/chat/completions is the external-client surface (RisuAI, SillyTavern,
LiteLLM): it must require a valid per-user API token (or browser session) and
scope session mode to characters/conversations the caller owns.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.ownership as ownership_mod
import monitor_ui.routers.openai_compat as oa_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


class FakeCharactersCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def find_one(self, query: dict, *a, **k):  # type: ignore[no-untyped-def]
        for d in self.docs:
            if all(d.get(key) == v for key, v in query.items()):
                return d
        return None


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


def _make_token(c: TestClient) -> str:
    r = c.post(
        "/api/auth/tokens",
        json={"name": "sillytavern"},
        headers={"X-CSRF-Token": c.cookies.get("monitor_csrf", "")},
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


PLAIN_BODY = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}


class TestOpenAICompatAuth:
    def test_unauthenticated_401(self, client):
        r = client.post("/api/v1/chat/completions", json=PLAIN_BODY)
        assert r.status_code == 401

    def test_api_token_plain_mode_allowed(self, client, monkeypatch):
        _signup(client, "a@example.com", "alice")
        token = _make_token(client)
        canned = SimpleNamespace(status_code=200)
        monkeypatch.setattr(oa_mod, "_plain_non_stream", lambda body: _async(canned))
        monkeypatch.setattr(oa_mod, "_plain_stream", lambda body: _async(canned))
        r = client.post("/api/v1/chat/completions", json=PLAIN_BODY, headers=_bearer(token))
        assert r.status_code == 200

    def test_revoked_token_401(self, client, fake_db, monkeypatch):
        _signup(client, "a@example.com", "alice")
        token = _make_token(client)
        token_id = client.get("/api/auth/tokens").json()[0]["id"]
        client.request(
            "DELETE",
            f"/api/auth/tokens/{token_id}",
            headers={"X-CSRF-Token": client.cookies.get("monitor_csrf", "")},
        )
        r = client.post("/api/v1/chat/completions", json=PLAIN_BODY, headers=_bearer(token))
        assert r.status_code == 401

    def test_session_mode_requires_owned_character(self, client, chars, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        token = _make_token(client)
        mine = str(uuid4())
        foreign = str(uuid4())
        chars.docs.append({"id": mine, "owner_id": user["id"]})
        chars.docs.append({"id": foreign, "owner_id": str(uuid4())})

        seen = {}

        async def fake_session(body):
            seen["body"] = body
            return SimpleNamespace(status_code=200)

        monkeypatch.setattr(oa_mod, "_session_non_stream", fake_session)

        body = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "character_id": mine}
        r = client.post("/api/v1/chat/completions", json=body, headers=_bearer(token))
        assert r.status_code == 200
        assert seen["body"].character_id == mine

        # foreign character → 404, session handler never runs
        seen.clear()
        body["character_id"] = foreign
        r = client.post("/api/v1/chat/completions", json=body, headers=_bearer(token))
        assert r.status_code == 404
        assert r.json() == {"detail": "Not found"}
        assert not seen

    def test_resume_requires_owned_conversation(self, client, chars, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        token = _make_token(client)
        my_char = str(uuid4())
        other_char = str(uuid4())
        chars.docs.append({"id": my_char, "owner_id": user["id"]})
        chars.docs.append({"id": other_char, "owner_id": str(uuid4())})

        conv_mine = uuid4()
        conv_foreign = uuid4()

        conv_docs = {
            str(conv_mine): {"conversation_id": str(conv_mine), "client_session": {"character_id": my_char}},
            str(conv_foreign): {"conversation_id": str(conv_foreign), "client_session": {"character_id": other_char}},
        }

        class FakeConvCollection:
            def find_one(self, query, *a, **k):  # type: ignore[no-untyped-def]
                return conv_docs.get(query.get("conversation_id"))

        class FakeMongo:
            def get_collection(self, name):  # type: ignore[no-untyped-def]
                assert name == "conversations"
                return FakeConvCollection()

        monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: FakeMongo())
        monkeypatch.setattr(oa_mod, "_session_non_stream", lambda body: _async(SimpleNamespace(status_code=200)))

        body = {
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "monitor_session_id": str(conv_mine),
        }
        assert client.post("/api/v1/chat/completions", json=body, headers=_bearer(token)).status_code == 200

        body["monitor_session_id"] = str(conv_foreign)
        r = client.post("/api/v1/chat/completions", json=body, headers=_bearer(token))
        assert r.status_code == 404

        body["monitor_session_id"] = str(uuid4())  # nonexistent → same 404
        r = client.post("/api/v1/chat/completions", json=body, headers=_bearer(token))
        assert r.status_code == 404 and r.json() == {"detail": "Not found"}

    def test_banned_user_token_403(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        token = _make_token(client)
        import asyncio

        asyncio.run(fake_db.user_set_banned(UUID(user["id"]), True, "abuse"))
        r = client.post("/api/v1/chat/completions", json=PLAIN_BODY, headers=_bearer(token))
        assert r.status_code == 403


async def _async(value):  # type: ignore[no-untyped-def]
    return value
