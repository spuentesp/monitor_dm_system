"""CF-12 route tests: GET/POST /api/stories/{story_id}/arc-recap.

GET is a persisted read (never regenerates — same contract as CF-2's
{"persisted": true}); POST generates/refreshes via RecapAgent and persists.
Hermetic: FakePostgres + patched data-layer tools + patched agent method.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from monitor_data.schemas.arc_recaps import ArcRecap, ArcRecapDetail
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


class FakeNeo4j:
    """Answers the story -> universe resolution used by ownership helpers."""

    def __init__(self, story_universes: dict[str, str]) -> None:
        self.story_universes = story_universes

    def execute_read(self, query, params):  # type: ignore[no-untyped-def]
        if "Story" in query:
            uid = self.story_universes.get(params["id"])
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


def _recap(story_id: UUID, universe_id: UUID, detail: ArcRecapDetail = ArcRecapDetail.STANDARD) -> ArcRecap:
    now = datetime.now(UTC)
    return ArcRecap(
        recap_id=uuid4(),
        story_id=story_id,
        universe_id=universe_id,
        recap_markdown="## Major Arcs\n- The vault opened.\n",
        detail=detail,
        scene_count=4,
        scenes_watermark="1012-03-04T11:00:00+00:00",
        last_scene_id=uuid4(),
        generated_at=now,
        updated_at=now,
    )


def _patch_story_world(monkeypatch: pytest.MonkeyPatch, story_id: str, world: str) -> None:
    monkeypatch.setattr(
        "monitor_data.db.neo4j.get_neo4j_client",
        lambda: FakeNeo4j({story_id: world}),
    )


class TestArcRecapRoutes:
    def test_unauthenticated_denied(self, client):
        story_id = uuid4()
        assert client.get(f"/api/stories/{story_id}/arc-recap").status_code == 401
        assert client.post(f"/api/stories/{story_id}/arc-recap").status_code == 401

    def test_get_returns_persisted_recap_without_regenerating(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user["id"])
        story_id = uuid4()
        _patch_story_world(monkeypatch, str(story_id), world)
        stored = _recap(story_id, UUID(world))

        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_arc_recap",
            lambda sid: stored if sid == story_id else None,
        )
        # any regeneration attempt fails the test
        monkeypatch.setattr(
            "monitor_agents.recap.agent.RecapAgent.generate_arc_recap",
            AsyncMock(side_effect=AssertionError("GET must not regenerate")),
        )

        r = client.get(f"/api/stories/{story_id}/arc-recap")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["persisted"] is True
        assert body["story_id"] == str(story_id)
        assert body["recap"] == stored.recap_markdown
        assert body["detail"] == "standard"
        assert body["scene_count"] == 4
        assert body["scenes_watermark"] == "1012-03-04T11:00:00+00:00"
        assert body["last_scene_id"] == str(stored.last_scene_id)
        assert body["generated_at"]

    def test_get_404_when_no_recap_persisted(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user["id"])
        story_id = uuid4()
        _patch_story_world(monkeypatch, str(story_id), world)
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_arc_recap",
            lambda sid: None,
        )
        r = client.get(f"/api/stories/{story_id}/arc-recap")
        assert r.status_code == 404
        assert "No arc recap" in r.json()["detail"]

    def test_post_generates_and_persists(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user["id"])
        story_id = uuid4()
        _patch_story_world(monkeypatch, str(story_id), world)
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_get_story",
            lambda sid: SimpleNamespace(universe_id=UUID(world)) if sid == story_id else None,
        )
        generated = _recap(story_id, UUID(world), detail=ArcRecapDetail.DETAILED)
        spy = AsyncMock(return_value=generated)
        monkeypatch.setattr("monitor_agents.recap.agent.RecapAgent.generate_arc_recap", spy)

        r = client.post(
            f"/api/stories/{story_id}/arc-recap",
            json={"detail": "detailed"},
            headers=_csrf(client),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["persisted"] is True
        assert body["recap"] == generated.recap_markdown
        assert body["detail"] == "detailed"
        # the agent was asked for the story's universe and the requested detail
        _, kwargs = spy.call_args
        assert kwargs["story_id"] == story_id
        assert kwargs["universe_id"] == UUID(world)
        assert kwargs["detail"] == "detailed"

    def test_post_defaults_to_standard_detail(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user["id"])
        story_id = uuid4()
        _patch_story_world(monkeypatch, str(story_id), world)
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_get_story",
            lambda sid: SimpleNamespace(universe_id=UUID(world)),
        )
        spy = AsyncMock(return_value=_recap(story_id, UUID(world)))
        monkeypatch.setattr("monitor_agents.recap.agent.RecapAgent.generate_arc_recap", spy)

        r = client.post(f"/api/stories/{story_id}/arc-recap", headers=_csrf(client))
        assert r.status_code == 200, r.text
        _, kwargs = spy.call_args
        assert kwargs["detail"] == "standard"

    def test_post_409_when_nothing_to_recap(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user["id"])
        story_id = uuid4()
        _patch_story_world(monkeypatch, str(story_id), world)
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_get_story",
            lambda sid: SimpleNamespace(universe_id=UUID(world)),
        )
        monkeypatch.setattr(
            "monitor_agents.recap.agent.RecapAgent.generate_arc_recap",
            AsyncMock(return_value=None),
        )
        r = client.post(f"/api/stories/{story_id}/arc-recap", headers=_csrf(client))
        assert r.status_code == 409

    def test_post_404_for_unknown_story(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user["id"])
        story_id = uuid4()
        # story resolves to a universe the caller owns, but the story row is gone
        _patch_story_world(monkeypatch, str(story_id), world)
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_get_story",
            lambda sid: None,
        )
        r = client.post(f"/api/stories/{story_id}/arc-recap", headers=_csrf(client))
        assert r.status_code == 404

    def test_foreign_user_gets_404_identical_to_missing(self, client, fake_db, monkeypatch):
        user_a = _signup(client, "a@example.com", "alice")
        world = _own_world(fake_db, user_a["id"])
        story_id = uuid4()
        _patch_story_world(monkeypatch, str(story_id), world)

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        r = client_b.get(f"/api/stories/{story_id}/arc-recap")
        assert r.status_code == 404 and r.json() == {"detail": "Not found"}
        r = client_b.post(f"/api/stories/{story_id}/arc-recap", headers=_csrf(client_b))
        assert r.status_code == 404 and r.json() == {"detail": "Not found"}
