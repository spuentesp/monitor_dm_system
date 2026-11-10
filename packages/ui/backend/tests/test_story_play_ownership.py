"""Two-user ownership tests for stories, scenes, and play-sessions (Phase 3/4).

Stories/scenes (Neo4j) and play-sessions (Mongo) inherit ownership through
their universe chain: the resource's universe_id is resolved, then checked
against the Postgres registry. Hermetic: FakePostgres + fake Neo4j/Mongo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from monitor_data.schemas.base import SessionStatus
from monitor_data.schemas.play_sessions import PlaySessionResponse
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


class FakeNeo4j:
    """Answers the universe-resolution queries used by ownership helpers."""

    def __init__(self, story_universes: dict[str, str], scene_universes: dict[str, str]) -> None:
        self.story_universes = story_universes
        self.scene_universes = scene_universes

    def execute_read(self, query, params):  # type: ignore[no-untyped-def]
        if "Story" in query:
            uid = self.story_universes.get(params["id"])
            return [{"uid": uid}] if uid else []
        if "Scene" in query:
            uid = self.scene_universes.get(params["id"])
            return [{"uid": uid}] if uid else []
        return []


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    import monitor_ui.auth as _auth_mod

    monkeypatch.setattr(_auth_mod, "_signup_limiter", None)
    monkeypatch.setattr(_auth_mod, "_login_limiter", None)
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
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


class TestStorySceneOwnership:
    def test_unauthenticated_denied(self, client):
        assert client.get("/api/stories").status_code == 401
        assert client.get(f"/api/stories/{uuid4()}").status_code == 401
        assert client.get(f"/api/scenes/{uuid4()}/turns").status_code == 401

    def test_story_endpoints_require_ownership(self, client, fake_db, monkeypatch):
        user_a = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user_a["id"])
        story_id = str(uuid4())
        scene_id = str(uuid4())
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client",
            lambda: FakeNeo4j({story_id: world}, {scene_id: world}),
        )
        # list passes the owned-universe allowlist into the query
        captured = {}

        def fake_list_stories(params):
            captured["universe_ids"] = params.universe_ids
            return SimpleNamespace(stories=[], total=0)

        monkeypatch.setattr("monitor_data.tools.neo4j_tools.neo4j_list_stories", fake_list_stories)
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_list_scenes",
            lambda *a, **k: SimpleNamespace(scenes=[], total=0),
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_recent_turns",
            lambda *a, **k: [],
        )

        r = client.get("/api/stories")
        assert r.status_code == 200
        assert [str(u) for u in captured["universe_ids"]] == [world]

        # owner can read the story's scenes/threads
        assert client.get(f"/api/stories/{story_id}/scenes").status_code == 200
        assert client.get(f"/api/scenes/{scene_id}/turns").status_code == 200

        # B: everything 404s, identical to missing
        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        for path in [
            f"/api/stories/{story_id}",
            f"/api/stories/{story_id}/scenes",
            f"/api/stories/{story_id}/threads",
            f"/api/scenes/{scene_id}/turns",
        ]:
            r = client_b.get(path)
            assert r.status_code == 404 and r.json() == {"detail": "Not found"}, path
        assert client_b.get(f"/api/stories/{uuid4()}").json() == {"detail": "Not found"}
        # B listing with a foreign universe filter → 404
        assert client_b.get("/api/stories", params={"universe_id": world}).status_code == 404
        # B with zero owned worlds → empty list, no unscoped query
        r = client_b.get("/api/stories")
        assert r.status_code == 200 and r.json()["total"] == 0


class TestPlaySessionOwnership:
    def test_unauthenticated_denied(self, client):
        assert client.get("/api/play-sessions").status_code == 401
        assert client.post("/api/play-sessions", json={}).status_code == 401

    def test_create_and_access_require_ownership(self, client, fake_db, monkeypatch):
        user_a = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user_a["id"])
        story_id = str(uuid4())
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client",
            lambda: FakeNeo4j({story_id: world}, {}),
        )
        session_id = uuid4()
        now = datetime.now(UTC)
        created = PlaySessionResponse(
            session_id=session_id,
            story_id=UUID(story_id),
            universe_id=UUID(world),
            session_number=1,
            status=SessionStatus.ACTIVE,
            player_ids=[],
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        monkeypatch.setattr(
            "monitor_ui.routers.play_sessions.mongodb_create_play_session",
            lambda body: created,
        )

        r = client.post(
            "/api/play-sessions",
            json={"story_id": story_id, "universe_id": world, "session_number": 1},
            headers=_csrf(client),
        )
        assert r.status_code == 201, r.text

        # ownership helper reads the session via the Layer 1 tool
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.play_sessions.mongodb_get_play_session",
            lambda sid: created if sid == session_id else None,
        )
        # the router's own top-level import of the same tool
        monkeypatch.setattr(
            "monitor_ui.routers.play_sessions.mongodb_get_play_session",
            lambda sid: created if sid == session_id else None,
        )
        assert client.get(f"/api/play-sessions/{session_id}").status_code == 200

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        assert client_b.get(f"/api/play-sessions/{session_id}").status_code == 404
        assert client_b.get(f"/api/play-sessions/{uuid4()}").status_code == 404
        # create against a foreign universe/story → 404
        foreign_world = _own_world(fake_db, str(uuid4()))
        r = client_b.post(
            "/api/play-sessions",
            json={"story_id": story_id, "universe_id": foreign_world, "session_number": 1},
            headers=_csrf(client_b),
        )
        assert r.status_code == 404

    def test_universe_aggregates_require_ownership(self, client, fake_db):
        user_a = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user_a["id"])
        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        assert client_b.get(f"/api/universes/{world}/play-home").status_code == 404
        assert client_b.get(f"/api/universes/{world}/play-sessions/recent").status_code == 404
        assert client_b.get(f"/api/universes/{uuid4()}/play-home").status_code == 404
