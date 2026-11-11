"""CF-14 share routes — authz, abuse, and rate-limit regressions (G07).

Style of ``test_cf_authz_regressions.py``: FakePostgres registry, signup'd
users, hermetic fake Neo4j for story→universe resolution, and a fake
ShareAgent so only the HTTP surface (guards, status mapping, rate limiting)
is under test — spoiler filtering itself lives in
``packages/agents/tests/test_player_share.py``.

Run:
    uv run pytest packages/ui/backend/tests/test_player_share_routes.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from fake_postgres import FakePostgres
from monitor_agents.player_share import ShareAccessError, ShareError, ShareTokenError
from monitor_data.schemas.player_share import (
    PlayerShare,
    PlayerView,
    ShareArtifactType,
    SharedArtifact,
)
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from monitor_ui.routers import player_view


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Neo4j:
    """Story → universe resolution for require_story_owner (execute_read)."""

    def __init__(self, story_universes: dict[str, str]) -> None:
        self.story_universes = story_universes

    def execute_read(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        uid = self.story_universes.get(str(params.get("id"))) if "Story" in query else None
        return [{"uid": uid}] if uid else []


def _share_doc(**over: Any) -> PlayerShare:
    base: dict[str, Any] = {
        "id": str(uuid4()),
        "story_id": str(uuid4()),
        "universe_id": str(uuid4()),
        "owner_id": "gm",
        "token": "public-token-abcdefghijklmnop",
        "revoked": False,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": None,
    }
    base.update(over)
    return PlayerShare.model_validate(base)


def _artifact_doc(**over: Any) -> SharedArtifact:
    base: dict[str, Any] = {
        "id": str(uuid4()),
        "story_id": str(uuid4()),
        "universe_id": str(uuid4()),
        "owner_id": "gm",
        "artifact_type": "recap",
        "title": "Session 4 recap",
        "content": "They opened the sealed door.",
        "spoiler_level": "party",
        "scope_character_id": None,
        "source_fact_ids": [],
        "session_id": None,
        "published": True,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    base.update(over)
    return SharedArtifact.model_validate(base)


def _view(story_id: UUID, **over: Any) -> PlayerView:
    return PlayerView.model_validate(
        {"story_id": str(story_id), "character_id": None, "artifacts": [], "characters": [], **over}
    )


@pytest.fixture
def agent_state() -> SimpleNamespace:
    """Per-test knobs + call log for the fake ShareAgent."""
    return SimpleNamespace(
        share=None,  # PlayerShare handed to resolve_share
        view=None,  # PlayerView returned by build_player_view
        artifact=None,  # SharedArtifact returned by get_visible_artifact
        export_md="# Session 4 recap\n\nThey opened the sealed door.\n",
        token_error=False,
        access_error=False,
        ensure_share=None,
        publish_result=None,  # (share, artifact)
        unpublish_ok=True,
        revoke_ok=True,
        calls=[],
    )


def _patch_share_agent(monkeypatch: pytest.MonkeyPatch, state: SimpleNamespace) -> None:
    class FakeShareAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def resolve_share(self, token: str) -> PlayerShare:
            state.calls.append(("resolve_share", token))
            if state.token_error:
                raise ShareTokenError("revoked")
            if state.share is None:
                raise ShareTokenError("unknown")
            return state.share

        async def build_player_view(self, story_id: UUID, token: str, character_id: UUID | None = None) -> PlayerView:
            state.calls.append(("build_player_view", str(story_id), character_id))
            if state.token_error or state.view is None:
                raise ShareTokenError("no view")
            return state.view

        async def get_visible_artifact(
            self,
            story_id: UUID,
            token: str,
            artifact_id: UUID,
            character_id: UUID | None = None,
            expected_type: ShareArtifactType | None = None,
        ) -> SharedArtifact:
            state.calls.append(("get_visible_artifact", str(artifact_id), expected_type))
            if state.access_error or state.artifact is None:
                raise ShareAccessError("no artifact")
            if expected_type is not None and state.artifact.artifact_type is not expected_type:
                raise ShareAccessError("wrong type")
            if state.artifact.story_id != story_id:
                raise ShareAccessError("foreign story")
            return state.artifact

        def export_markdown(self, artifact: SharedArtifact) -> str:
            return state.export_md

        async def ensure_share(self, *, universe_id: UUID, story_id: UUID, owner_id: str) -> PlayerShare:
            state.calls.append(("ensure_share", str(story_id), owner_id))
            if state.ensure_share is None:
                raise ShareError("no share")
            return state.ensure_share

        async def publish(self, **kwargs: Any) -> tuple[PlayerShare, SharedArtifact]:
            state.calls.append(("publish", kwargs))
            if state.publish_result is None:
                raise ShareError("publish failed")
            return state.publish_result

        async def unpublish(self, *, artifact_id: UUID, universe_id: UUID, owner_id: str) -> bool:
            state.calls.append(("unpublish", str(artifact_id)))
            return state.unpublish_ok

        async def revoke(self, *, story_id: UUID, universe_id: UUID, owner_id: str) -> bool:
            state.calls.append(("revoke", str(story_id)))
            return state.revoke_ok

    monkeypatch.setattr("monitor_ui.routers.player_view.ShareAgent", FakeShareAgent)
    monkeypatch.setattr("monitor_ui.routers.gm_tools.ShareAgent", FakeShareAgent)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, agent_state: SimpleNamespace):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    player_view._share_limiter = None

    fake_db = FakePostgres()

    async def _db() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _db
    _patch_share_agent(monkeypatch, agent_state)
    yield TestClient(app), fake_db
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()
    player_view._share_limiter = None


def _signup(c: TestClient, email: str, username: str) -> dict[str, Any]:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


def _register_world(fake_db: FakePostgres, owner_id: str) -> str:
    world = str(uuid4())
    fake_db.worlds[world] = {
        "id": world,
        "owner_id": UUID(owner_id),
        "multiverse_id": str(uuid4()),
        "label": "w",
        "active": True,
    }
    return world


# ---------------------------------------------------------------------------
# Public surface — token is the credential, no login required
# ---------------------------------------------------------------------------


class TestPublicShareRoutes:
    def test_index_needs_no_authentication(self, client: Any, agent_state: SimpleNamespace) -> None:
        c, _ = client
        story_id = uuid4()
        agent_state.share = _share_doc(story_id=str(story_id))
        agent_state.view = _view(story_id)
        r = c.get("/api/share/public-token-abcdefghijklmnop")
        assert r.status_code == 200, r.text
        assert r.json()["story_id"] == str(story_id)

    def test_unknown_token_is_404(self, client: Any, agent_state: SimpleNamespace) -> None:
        c, _ = client
        agent_state.token_error = True
        r = c.get("/api/share/definitely-not-a-token")
        assert r.status_code == 404
        assert r.json() == {"detail": "Not found"}

    def test_revoked_token_is_404_not_403(self, client: Any, agent_state: SimpleNamespace) -> None:
        # Revocation must not advertise that the token ever existed.
        c, _ = client
        agent_state.token_error = True
        r = c.get("/api/share/revoked-token-value")
        assert r.status_code == 404
        assert "revoked" not in r.text.lower()

    def test_malformed_character_id_is_400(self, client: Any, agent_state: SimpleNamespace) -> None:
        c, _ = client
        story_id = uuid4()
        agent_state.share = _share_doc(story_id=str(story_id))
        agent_state.view = _view(story_id)
        r = c.get("/api/share/tok", params={"character_id": "not-a-uuid"})
        assert r.status_code == 400

    def test_recap_route_rejects_handout_ids(self, client: Any, agent_state: SimpleNamespace) -> None:
        # Type checking happens in the agent (faked here to raise on mismatch).
        c, _ = client
        story_id = uuid4()
        agent_state.share = _share_doc(story_id=str(story_id))
        agent_state.artifact = _artifact_doc(story_id=str(story_id), artifact_type="handout")
        r = c.get(f"/api/share/tok/recap/{uuid4()}")
        assert r.status_code == 404

    def test_unpublished_artifact_detail_is_404(self, client: Any, agent_state: SimpleNamespace) -> None:
        c, _ = client
        story_id = uuid4()
        agent_state.share = _share_doc(story_id=str(story_id))
        agent_state.access_error = True  # agent refuses drafts/foreign/invisible
        r = c.get(f"/api/share/tok/handout/{uuid4()}")
        assert r.status_code == 404

    def test_export_markdown_downloads(self, client: Any, agent_state: SimpleNamespace) -> None:
        c, _ = client
        story_id = uuid4()
        agent_state.share = _share_doc(story_id=str(story_id))
        agent_state.artifact = _artifact_doc(story_id=str(story_id))
        r = c.get(f"/api/share/tok/export/{uuid4()}.md")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert "They opened the sealed door." in r.text

    def test_rate_limit_returns_429(
        self, client: Any, agent_state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c, _ = client
        story_id = uuid4()
        agent_state.share = _share_doc(story_id=str(story_id))
        agent_state.view = _view(story_id)
        monkeypatch.setenv("SHARE_RATE_LIMIT", "2")
        get_settings.cache_clear()
        player_view._share_limiter = None

        token = "rate-limited-token-xyz"
        assert c.get(f"/api/share/{token}").status_code == 200
        assert c.get(f"/api/share/{token}").status_code == 200
        third = c.get(f"/api/share/{token}")
        assert third.status_code == 429

        # Cleanup so later tests see the default limit on a fresh limiter.
        monkeypatch.delenv("SHARE_RATE_LIMIT", raising=False)
        get_settings.cache_clear()
        player_view._share_limiter = None


# ---------------------------------------------------------------------------
# GM-side endpoints — authentication + ownership
# ---------------------------------------------------------------------------


class TestGmShareAuthz:
    def test_publish_requires_authentication(self, client: Any) -> None:
        c, _ = client
        r = c.post(
            "/api/gm/share/publish",
            json={
                "universe_id": str(uuid4()),
                "story_id": str(uuid4()),
                "artifact_type": "recap",
                "title": "Recap",
                "content": "Body",
            },
        )
        assert r.status_code in (401, 403)

    def test_link_requires_authentication(self, client: Any) -> None:
        c, _ = client
        r = c.get(
            "/api/gm/share/link",
            params={"universe_id": str(uuid4()), "story_id": str(uuid4())},
        )
        assert r.status_code in (401, 403)

    def test_revoke_requires_authentication(self, client: Any) -> None:
        c, _ = client
        r = c.post(
            "/api/gm/share/revoke",
            json={"universe_id": str(uuid4()), "story_id": str(uuid4())},
        )
        assert r.status_code in (401, 403)

    def test_foreign_universe_publish_is_404(
        self, client: Any, agent_state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c, fake_db = client
        user_a = _signup(c, "a@example.com", "alice")
        world_a = _register_world(fake_db, user_a["id"])
        story_a = uuid4()
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client",
            lambda: _Neo4j({str(story_a): world_a}),
        )

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        r = client_b.post(
            "/api/gm/share/publish",
            json={
                "universe_id": world_a,  # Alice's universe
                "story_id": str(story_a),
                "artifact_type": "recap",
                "title": "Recap",
                "content": "Body",
            },
            headers=_csrf(client_b),
        )
        assert r.status_code == 404
        assert ("publish",) not in [tuple(x[:1]) for x in agent_state.calls]

    def test_foreign_story_link_is_404(
        self, client: Any, agent_state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c, fake_db = client
        user_a = _signup(c, "a@example.com", "alice")
        world_a = _register_world(fake_db, user_a["id"])
        story_a = uuid4()
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client",
            lambda: _Neo4j({str(story_a): world_a}),
        )

        client_b = TestClient(app)
        user_b = _signup(client_b, "b@example.com", "bob")
        world_b = _register_world(fake_db, user_b["id"])
        # Bob owns world_b but points at Alice's story.
        r = client_b.get(
            "/api/gm/share/link",
            params={"universe_id": world_b, "story_id": str(story_a)},
            headers=_csrf(client_b),
        )
        assert r.status_code == 404

    def test_foreign_universe_revoke_is_404(
        self, client: Any, agent_state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c, fake_db = client
        user_a = _signup(c, "a@example.com", "alice")
        world_a = _register_world(fake_db, user_a["id"])
        story_a = uuid4()
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client",
            lambda: _Neo4j({str(story_a): world_a}),
        )

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        r = client_b.post(
            "/api/gm/share/revoke",
            json={"universe_id": world_a, "story_id": str(story_a)},
            headers=_csrf(client_b),
        )
        assert r.status_code == 404
        assert not any(name == "revoke" for name, *_ in agent_state.calls)

    def test_foreign_universe_unpublish_is_404(self, client: Any, agent_state: SimpleNamespace) -> None:
        c, fake_db = client
        user_a = _signup(c, "a@example.com", "alice")
        world_a = _register_world(fake_db, user_a["id"])

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        artifact_id = uuid4()
        r = client_b.post(
            "/api/gm/share/unpublish",
            json={"universe_id": world_a, "artifact_id": str(artifact_id)},
            headers=_csrf(client_b),
        )
        assert r.status_code == 404
        assert not any(name == "unpublish" for name, *_ in agent_state.calls)

    def test_unpublish_miss_is_404(
        self, client: Any, agent_state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c, fake_db = client
        user = _signup(c, "a@example.com", "alice")
        world = _register_world(fake_db, user["id"])
        agent_state.unpublish_ok = False  # tool predicate miss (foreign/missing)
        r = c.post(
            "/api/gm/share/unpublish",
            json={"universe_id": world, "artifact_id": str(uuid4())},
            headers=_csrf(c),
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GM-side happy paths (fake agent; guards are real)
# ---------------------------------------------------------------------------


class TestGmShareHappyPath:
    def test_publish_returns_share_link(
        self, client: Any, agent_state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c, fake_db = client
        user = _signup(c, "a@example.com", "alice")
        world = _register_world(fake_db, user["id"])
        story_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client",
            lambda: _Neo4j({str(story_id): world}),
        )
        share = _share_doc(story_id=str(story_id), universe_id=world)
        artifact = _artifact_doc(story_id=str(story_id), universe_id=world)
        agent_state.publish_result = (share, artifact)

        r = c.post(
            "/api/gm/share/publish",
            json={
                "universe_id": world,
                "story_id": str(story_id),
                "artifact_type": "recap",
                "title": "Session 4 recap",
                "content": "They opened the sealed door.",
            },
            headers=_csrf(c),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["published"] is True
        assert body["token"] == share.token
        assert body["share_path"] == f"/share/{share.token}"
        assert body["artifact_id"] == str(artifact.id)

        # Ownership guards ran before the agent was touched.
        assert any(name == "publish" for name, *_ in agent_state.calls)

    def test_link_mints_token_for_owner(
        self, client: Any, agent_state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c, fake_db = client
        user = _signup(c, "a@example.com", "alice")
        world = _register_world(fake_db, user["id"])
        story_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client",
            lambda: _Neo4j({str(story_id): world}),
        )
        agent_state.ensure_share = _share_doc(story_id=str(story_id), universe_id=world, owner_id=user["id"])

        r = c.get(
            "/api/gm/share/link",
            params={"universe_id": world, "story_id": str(story_id)},
            headers=_csrf(c),
        )
        assert r.status_code == 200, r.text
        assert r.json()["share_path"].startswith("/share/")

    def test_revoke_ok_for_owner(
        self, client: Any, agent_state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        c, fake_db = client
        user = _signup(c, "a@example.com", "alice")
        world = _register_world(fake_db, user["id"])
        story_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client",
            lambda: _Neo4j({str(story_id): world}),
        )
        agent_state.revoke_ok = True
        r = c.post(
            "/api/gm/share/revoke",
            json={"universe_id": world, "story_id": str(story_id)},
            headers=_csrf(c),
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"story_id": str(story_id), "revoked": True}
