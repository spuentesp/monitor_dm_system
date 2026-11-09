"""Two-user ownership tests for the routers wired in the final auth sweep
(Phase 3): graph, gm_notes, gm_tools, lorebook, canon_review, parties,
random_tables, templates, game_systems, prompts, tone, prompt_collections,
modes, change_log, architect, character_promotion, forge.

Postgres registry = shared FakePostgres; Neo4j/Mongo touches are patched at
the router module boundary. Verifies 401 unauthenticated, generic 404 for
foreign/universe-unowned resources, and admin gates on operator surfaces.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.ownership as ownership_mod
import monitor_ui.routers.gm_notes as gm_notes_mod
import monitor_ui.routers.graph as graph_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


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


def _seed_world(db: FakePostgres, owner_id: UUID) -> str:
    world_id = str(uuid4())
    asyncio.run(
        db.world_upsert(
            {
                "id": world_id,
                "owner_id": owner_id,
                "multiverse_id": str(uuid4()),
                "label": "World A",
                "active": True,
            }
        )
    )
    return world_id


class TestUnauthenticated:
    def test_all_swept_routers_require_auth(self, client: TestClient):
        uid = str(uuid4())
        gets = [
            "/api/modes",
            "/api/change-log",
            "/api/graph/world",
            f"/api/graph/universes/{uid}/graph",
            f"/api/gm/notes/{uid}",
            "/api/random-tables",
            "/api/tone/profiles",
            "/api/tone/libraries",
            "/api/prompt-collections",
            "/api/prompts/status",
            "/api/templates",
            "/api/systems",
            "/api/parties",
            f"/api/architect/{uid}/coverage",
            "/api/lorebook/entries?character_id=x",
            f"/api/scenes/{uid}/canon-review",
        ]
        for url in gets:
            r = client.get(url)
            assert r.status_code == 401, f"{url} -> {r.status_code}"
        posts = [
            ("/api/parties", {"story_id": uid, "name": "p"}),
            ("/api/gm/hooks", {"universe_id": uid}),
            ("/api/gm/roll", {"expression": "1d20"}),
            ("/api/random-tables", {"name": "t", "entries": []}),
            ("/api/templates", {}),
            ("/api/systems", {"name": "s"}),
            ("/api/tone/tags", {"tag": "x", "category": "mood"}),
            ("/api/canon-review/verdicts", {"items": []}),
            ("/api/forge/demo-world", {}),
            (f"/api/entities/characters/{uid}/promote", {}),
        ]
        for url, body in posts:
            r = client.post(url, json=body)
            assert r.status_code == 401, f"{url} -> {r.status_code}"


class TestUniverseScopedRouters:
    def test_foreign_universe_gets_generic_404(self, client: TestClient, fake_db: FakePostgres):
        alice = _signup(client, "alice@example.com", "alice")
        _signup(client, "bob@example.com", "bob")
        world_id = _seed_world(fake_db, UUID(alice["id"]))

        # Bob is authenticated but does not own the world -> generic 404.
        for url in [
            f"/api/graph/universes/{world_id}/graph",
            f"/api/gm/notes/{world_id}",
            f"/api/architect/{world_id}/coverage",
        ]:
            r = client.get(url)
            assert r.status_code == 404, f"{url} -> {r.status_code}"
            assert r.json()["detail"] == "Not found"
        r = client.get("/api/random-tables", params={"universe_id": world_id})
        assert r.status_code == 404
        r = client.get("/api/tone/libraries", params={"universe_id": world_id})
        assert r.status_code == 404
        r = client.get("/api/lorebook/entries", params={"character_id": f"universe:{world_id}"})
        assert r.status_code == 404
        r = client.get("/api/prompt-collections", params={"universe_id": world_id})
        assert r.status_code == 404
        r = client.post("/api/gm/hooks", json={"universe_id": world_id}, headers=_csrf(client))
        assert r.status_code == 404
        r = client.post(
            "/api/templates",
            json={"universe_id": world_id, "name": "t", "entity_type": "character"},
            headers=_csrf(client),
        )
        assert r.status_code == 404

    def test_foreign_story_party_create_404(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ):
        alice = _signup(client, "alice2@example.com", "alice2")
        _signup(client, "bob2@example.com", "bob2")
        world_id = _seed_world(fake_db, UUID(alice["id"]))
        story_id = str(uuid4())

        async def _fake_universe_of_story(_sid):
            return world_id

        monkeypatch.setattr(ownership_mod, "_universe_of_story", _fake_universe_of_story)
        r = client.post(
            "/api/parties",
            json={"story_id": story_id, "name": "p"},
            headers=_csrf(client),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Not found"

    def test_owner_can_read_gm_notes(self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch):
        alice = _signup(client, "alice3@example.com", "alice3")
        world_id = _seed_world(fake_db, UUID(alice["id"]))
        monkeypatch.setattr(gm_notes_mod, "mongodb_get_gm_note", lambda _uid: None)
        r = client.get(f"/api/gm/notes/{world_id}")
        assert r.status_code == 200
        assert r.json()["content"] == ""

    def test_graph_world_scoped_to_owned(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ):
        alice = _signup(client, "alice4@example.com", "alice4")
        _signup(client, "bob4@example.com", "bob4")
        world_id = _seed_world(fake_db, UUID(alice["id"]))
        monkeypatch.setattr(graph_mod, "neo4j_ensure_omniverse", lambda: {"omniverse_id": str(uuid4())})
        monkeypatch.setattr(graph_mod, "neo4j_list_multiverses", lambda **kw: [])
        monkeypatch.setattr(graph_mod, "neo4j_list_universes", lambda f=None: [])
        monkeypatch.setattr(graph_mod, "neo4j_list_entities", lambda f: SimpleNamespace(entities=[]))
        monkeypatch.setattr(graph_mod, "neo4j_list_relationships", lambda f: SimpleNamespace(relationships=[]))
        # Bob owns nothing: the world graph must be empty, not an error/unscoped.
        r = client.get("/api/graph/world")
        assert r.status_code == 200
        assert r.json()["nodes"] == []
        # A foreign universe_id is a generic 404 even though the node exists.
        r = client.get("/api/graph/world", params={"universe_id": world_id})
        assert r.status_code == 404


class TestCanonReviewOwnership:
    def test_foreign_proposal_verdict_404(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ):
        alice = _signup(client, "alice5@example.com", "alice5")
        _signup(client, "bob5@example.com", "bob5")
        foreign_world = _seed_world(fake_db, UUID(alice["id"]))
        proposal_id = uuid4()
        job_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_proposed_change",
            lambda _pid: SimpleNamespace(
                scene_id=None,
                story_id=None,
                source=f"ingestion_job:{job_id}",
                proposer="ingest",
            ),
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_ingestion_job",
            lambda _jid: SimpleNamespace(universe_id=UUID(foreign_world)),
        )
        r = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "ok"},
            headers=_csrf(client),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Not found"

    def test_by_filter_requires_scope(self, client: TestClient):
        _signup(client, "alice6@example.com", "alice6")
        r = client.post(
            "/api/canon-review/verdicts/by-filter",
            json={"decision": "accepted", "reason": "r", "dry_run": True},
            headers=_csrf(client),
        )
        assert r.status_code == 400


class TestAdminGates:
    def test_operator_writes_require_admin(self, client: TestClient):
        _signup(client, "alice7@example.com", "alice7")
        # prompts router is admin-only entirely
        assert client.get("/api/prompts/status").status_code == 403
        # game system writes are admin-only
        r = client.post("/api/systems", json={"name": "s"}, headers=_csrf(client))
        assert r.status_code == 403
        # global (universe-less) random table creation is admin-only
        r = client.post(
            "/api/random-tables",
            json={"name": "t", "entries": [{"min_roll": 1, "max_roll": 2, "value": "x"}]},
            headers=_csrf(client),
        )
        assert r.status_code == 403
        # tag writes are admin-only
        r = client.post("/api/tone/tags", json={"tag": "x", "category": "mood"}, headers=_csrf(client))
        assert r.status_code == 403
        # global prompt collection creation is admin-only
        r = client.post(
            "/api/prompt-collections",
            json={"name": "c", "category": "session_zero", "entries": []},
            headers=_csrf(client),
        )
        assert r.status_code == 403


class TestCommonGuardDispatch:
    """resource_route_guard maps path/query params to shared resolvers."""

    def test_foreign_template_and_lorebook_entry_404(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ):
        alice = _signup(client, "alice8@example.com", "alice8")
        _signup(client, "bob8@example.com", "bob8")
        world_id = _seed_world(fake_db, UUID(alice["id"]))
        template_id = uuid4()
        entry_id = str(uuid4())
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.templates.mongodb_get_entity_template",
            lambda tid: SimpleNamespace(universe_id=UUID(world_id)),
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.lorebook_tools.mongodb_get_lorebook_entry",
            lambda eid: SimpleNamespace(character_id=f"universe:{world_id}"),
        )
        assert client.get(f"/api/templates/{template_id}").status_code == 404
        assert client.get(f"/api/lorebook/entries/{entry_id}").status_code == 404

    def test_owner_passes_template_guard(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ):
        alice = _signup(client, "alice9@example.com", "alice9")
        world_id = _seed_world(fake_db, UUID(alice["id"]))
        template_id = uuid4()
        tmpl = SimpleNamespace(universe_id=UUID(world_id))
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.templates.mongodb_get_entity_template",
            lambda tid: tmpl,
        )
        # Guard passes for the owner; the endpoint then 500s on the stub shape,
        # which still proves it got past the ownership check (not 404).
        c2 = TestClient(app, raise_server_exceptions=False)
        c2.cookies.update(client.cookies)
        r = c2.get(f"/api/templates/{template_id}")
        assert r.status_code == 500  # past the guard (404 would mean denied)


class TestBodyReferenceChecks:
    """Body-supplied IDs (characters, entities, packs) must be owner-checked."""

    def test_chat_session_with_foreign_character_404(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ):
        # Caller owns the universe, so the universe check passes and the
        # 404 must come from the character check (non-vacuous).
        bob = _signup(client, "bob10@example.com", "bob10")
        world_id = _seed_world(fake_db, UUID(bob["id"]))
        alice_char = str(uuid4())

        class _Chars:
            def find_one(self, query):
                if query.get("id") == alice_char and query.get("owner_id") == str(uuid4()):
                    return {"id": alice_char, "owner_id": str(uuid4())}  # owned by someone else
                return None

        monkeypatch.setattr(ownership_mod, "_characters_collection", lambda: _Chars())
        monkeypatch.setattr(ownership_mod, "_universes_of_entities", lambda ids: {})  # not a world entity either
        r = client.post(
            "/api/chat",
            json={"universe_id": world_id, "character_id": alice_char},
            headers=_csrf(client),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "Not found"

    def test_fact_with_foreign_entity_ref_404(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ):
        alice = _signup(client, "alice11@example.com", "alice11")
        bob_world = _seed_world(fake_db, UUID(_signup(client, "bob11@example.com", "bob11")["id"]))
        alice_world = _seed_world(fake_db, UUID(alice["id"]))
        foreign_entity = uuid4()
        monkeypatch.setattr(
            ownership_mod,
            "_universes_of_entities",
            lambda ids: {str(foreign_entity): alice_world},
        )
        r = client.post(
            f"/api/entities/entities/{bob_world}/facts",
            json={"statement": "x", "entity_ids": [str(foreign_entity)]},
            headers=_csrf(client),
        )
        assert r.status_code == 404

    def test_party_with_foreign_member_404(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ):
        alice = _signup(client, "alice12@example.com", "alice12")
        bob_world = _seed_world(fake_db, UUID(_signup(client, "bob12@example.com", "bob12")["id"]))
        alice_world = _seed_world(fake_db, UUID(alice["id"]))
        story_id = str(uuid4())
        foreign_entity = uuid4()

        async def _fake_universe_of_story(_sid):
            return bob_world

        monkeypatch.setattr(ownership_mod, "_universe_of_story", _fake_universe_of_story)
        monkeypatch.setattr(ownership_mod, "_universes_of_entities", lambda ids: {str(foreign_entity): alice_world})
        r = client.post(
            "/api/parties",
            json={"story_id": story_id, "name": "p", "initial_member_ids": [str(foreign_entity)]},
            headers=_csrf(client),
        )
        assert r.status_code == 404

    def test_publish_ignores_client_min_score(self, client: TestClient):
        import inspect

        import monitor_ui.routers.pack_library as pl_mod

        sig = inspect.signature(pl_mod.publish_pack)
        assert "min_score" not in sig.parameters


class TestGraphNodeResolvers:
    """entity/fact/axiom/event/relationship/sheet path params are owner-checked."""

    def test_foreign_fact_and_entity_get_404(self, client, fake_db, monkeypatch):
        alice = _signup(client, "alice13@example.com", "alice13")
        _signup(client, "bob13@example.com", "bob13")
        world = _seed_world(fake_db, UUID(alice["id"]))
        fact_id = str(uuid4())
        entity_id = str(uuid4())

        class _Neo:
            def execute_read(self, q, params):
                if "Fact" in q:
                    return [{"uid": world}]
                if "Entity" in q:
                    return [{"id": params["ids"][0], "uid": world}]
                return []

        monkeypatch.setattr("monitor_data.db.neo4j.get_neo4j_client", lambda: _Neo())
        # patch at ownership import site
        import monitor_data.db.neo4j as neo_mod

        monkeypatch.setattr(neo_mod, "get_neo4j_client", lambda: _Neo())
        monkeypatch.setattr(ownership_mod, "_universes_of_entities", lambda ids: {str(i): world for i in ids})
        r = client.get(f"/api/entities/entities/{entity_id}")
        assert r.status_code == 404
        r = client.delete(f"/api/entities/entities/facts/{fact_id}?force=true", headers=_csrf(client))
        assert r.status_code == 404

    def test_playable_character_accepts_card_or_owned_entity(self, client, fake_db, monkeypatch):
        bob = _signup(client, "bob14@example.com", "bob14")
        world = _seed_world(fake_db, UUID(bob["id"]))
        card_id = str(uuid4())
        entity_id = str(uuid4())

        class _Chars:
            def find_one(self, q):
                if q.get("id") == card_id and q.get("owner_id") == str(UUID(bob["id"])):
                    return {"id": card_id}
                return None

        monkeypatch.setattr(ownership_mod, "_characters_collection", lambda: _Chars())
        monkeypatch.setattr(ownership_mod, "_universes_of_entities", lambda ids: {str(entity_id): world})
        principal = (
            ownership_mod.Principal(user_id=UUID(bob["id"]), is_admin=False, via="session")
            if hasattr(ownership_mod, "Principal")
            else None
        )
        from monitor_ui.auth import Principal

        principal = Principal(user_id=UUID(bob["id"]), is_admin=False, via="session")
        import asyncio

        asyncio.run(ownership_mod.require_playable_character(fake_db, principal, card_id))  # card: ok
        asyncio.run(ownership_mod.require_playable_character(fake_db, principal, entity_id))  # entity: ok
        with pytest.raises(Exception):
            asyncio.run(ownership_mod.require_playable_character(fake_db, principal, str(uuid4())))
