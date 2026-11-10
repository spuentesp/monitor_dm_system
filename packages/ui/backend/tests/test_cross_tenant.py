"""Cross-tenant suite (multi-tenancy Phase 6).

Two users, A and B. For every resource kind, B's read / list / update /
delete of A's resource must answer 404 or 403 and A's data must be
unchanged.

Two layers:

1. ``TestCrossTenantByKind`` — one test per brief resource kind, seeding
   A's resource into the data-layer boundary fakes and asserting both the
   status codes and that A's data survives untouched.
2. ``test_generated_route_table_sweep`` — generated from the app's route
   table: EVERY registered route carrying a resource-id parameter is called
   as B with A's id and must answer 403/404. A new route with a resource id
   is therefore covered automatically; the only exclusions are listed in
   ``SWEEP_EXEMPT`` with a reason.

The data layer is faked at the module boundary the resolvers import from
(``monitor_data.tools.mongodb_tools...`` / ``monitor_data.db.neo4j``), so
the real ``resource_route_guard`` + ``_SCOPE_RESOLVERS`` code runs.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import monitor_ui.ownership as ownership_mod
import monitor_ui.routers.character_storage as cs_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app as main_app
from fake_postgres import FakePostgres


# ---------------------------------------------------------------------------
# Generic fake Mongo collection (query matcher + write log)
# ---------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, *a, **k):  # type: ignore[no-untyped-def]
        return self

    def skip(self, n: int):  # type: ignore[no-untyped-def]
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int):  # type: ignore[no-untyped-def]
        self._docs = self._docs[:n]
        return self

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._docs)


class FakeCollection:
    """find_one/find/count/insert/update/delete with a write log."""

    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs: list[dict] = list(docs or [])
        self.writes: list[tuple[str, dict]] = []

    @staticmethod
    def _match(doc: dict, query: dict) -> bool:
        def _ok(k: str, v: object) -> bool:
            if isinstance(v, dict) and "$in" in v:
                return doc.get(k) in v["$in"]
            return doc.get(k) == v

        return all(_ok(k, v) for k, v in query.items())

    def find_one(self, query: dict, *a, **k):  # type: ignore[no-untyped-def]
        for d in self.docs:
            if self._match(d, query):
                return d
        return None

    def find(self, query: dict, *a, **k):  # type: ignore[no-untyped-def]
        return FakeCursor([d for d in self.docs if self._match(d, query)])

    def count_documents(self, query: dict) -> int:
        return sum(1 for d in self.docs if self._match(d, query))

    def insert_one(self, doc: dict) -> None:
        self.writes.append(("insert", doc))
        self.docs.append(doc)

    def update_one(self, query: dict, update: dict, *a, **k):  # type: ignore[no-untyped-def]
        self.writes.append(("update", query))
        for d in self.docs:
            if self._match(d, query):
                d.update(update.get("$set", {}))

    def delete_one(self, query: dict, *a, **k):  # type: ignore[no-untyped-def]
        self.writes.append(("delete", query))
        for i, d in enumerate(self.docs):
            if self._match(d, query):
                del self.docs[i]
                break


# ---------------------------------------------------------------------------
# Fake Neo4j client: answers the ownership resolvers' Cypher lookups
# ---------------------------------------------------------------------------


class FakeNeo4j:
    """Answers the resolver queries by node label/id → universe."""

    def __init__(self) -> None:
        self.universe_of: dict[str, str] = {}  # node id -> universe id
        self.label_of: dict[str, str] = {}
        self.relationships: dict[str, tuple[str, str]] = {}
        self.entities: dict[str, str] = {}  # entity id -> universe id

    def execute_read(self, query: str, parameters: dict | None = None):  # type: ignore[no-untyped-def]
        params = parameters or {}
        if "WHERE e.id IN $ids" in query:
            ids = params.get("ids", [])
            return [{"id": i, "uid": self.entities.get(i)} for i in ids if i in self.entities]
        if "MATCH (e:Entity" in query:
            eid = params.get("id")
            uid = self.entities.get(str(eid))
            return [{"id": eid, "uid": uid}] if uid else []
        if "MATCH (r:Relationship" in query:
            rel = self.relationships.get(str(params.get("id")))
            return [{"fid": rel[0], "tid": rel[1]}] if rel else []
        for label in ("Story", "Scene", "Fact", "Axiom", "Event"):
            if f"MATCH (n:{label}" in query or f"MATCH (s:{label}" in query or f"MATCH (sc:{label}" in query:
                nid = str(params.get("id"))
                uid = self.universe_of.get(nid)
                key = "uid"
                return [{key: uid}] if uid else []
        return []

    def execute_write(self, query: str, parameters: dict | None = None):  # type: ignore[no-untyped-def]
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def neo() -> FakeNeo4j:
    return FakeNeo4j()


@pytest.fixture
def chars() -> FakeCollection:
    return FakeCollection()


@pytest.fixture
def chat_sessions() -> FakeCollection:
    return FakeCollection()


@pytest.fixture
def monkey_data(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakePostgres,
    neo: FakeNeo4j,
    chars: FakeCollection,
    chat_sessions: FakeCollection,
) -> dict[str, Any]:
    """Patch every data-layer boundary the ownership resolvers read."""
    monkeypatch.setattr(ownership_mod, "_characters_collection", lambda: chars)
    monkeypatch.setattr(ownership_mod, "_chat_sessions_collection", lambda: chat_sessions)
    monkeypatch.setattr(cs_mod, "_coll", lambda: chars)
    monkeypatch.setattr("monitor_data.db.neo4j.get_neo4j_client", lambda: neo)
    return {"chars": chars, "chat_sessions": chat_sessions, "neo": neo, "db": fake_db}


@pytest.fixture
def users(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakePostgres,
    monkey_data: dict[str, Any],
):
    """Two signed-up users A and B with independent cookie jars."""
    monkeypatch.setenv("MONITOR_AUTH_DISABLED", "false")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    import monitor_ui.auth as auth_mod

    monkeypatch.setattr(auth_mod, "_signup_limiter", None)
    monkeypatch.setattr(auth_mod, "_login_limiter", None)
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    main_app.dependency_overrides[get_postgres] = _fake_get_postgres
    a = TestClient(main_app, raise_server_exceptions=False)
    b = TestClient(main_app, raise_server_exceptions=False)
    user_a = _signup(a, "a@example.com", "alice")
    user_b = _signup(b, "b@example.com", "bob")
    yield SimpleNamespace(a=a, b=b, a_id=user_a["id"], b_id=user_b["id"])
    main_app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict:
    if not c.cookies.get("monitor_csrf"):
        c.get("/api/auth/config")
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
        headers=_csrf(c),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


# ---------------------------------------------------------------------------
# Seeding: one A-owned resource per kind
# ---------------------------------------------------------------------------


def _seed_all(
    users, fake_db: FakePostgres, neo: FakeNeo4j, chars: FakeCollection, chat_sessions: FakeCollection
) -> dict[str, str]:
    """Create A's resources for every kind; return kind -> id maps."""
    a_id = str(users.a_id)
    universe_id = str(uuid4())
    fake_db.worlds[universe_id] = {
        "id": universe_id,
        "owner_id": UUID(a_id),
        "multiverse_id": None,
        "label": "A's world",
        "active": True,
        "kind": "world",
    }
    multiverse_id = str(uuid4())
    fake_db.multiverses[multiverse_id] = {
        "id": multiverse_id,
        "owner_id": UUID(a_id),
        "label": "A's multiverse",
        "active": True,
    }

    story_id = str(uuid4())
    scene_id = str(uuid4())
    neo.universe_of[story_id] = universe_id
    neo.label_of[story_id] = "Story"
    neo.universe_of[scene_id] = universe_id
    neo.label_of[scene_id] = "Scene"

    entity_id = str(uuid4())
    neo.entities[entity_id] = universe_id

    fact_id = str(uuid4())
    neo.universe_of[fact_id] = universe_id
    neo.label_of[fact_id] = "Fact"

    character_id = str(uuid4())
    chars.docs.append(
        {
            "id": character_id,
            "owner_id": a_id,
            "name": "A's hero",
            "description": "d",
            "personality": "p",
            "status": "active",
            "versions": [],
        }
    )
    persona_id = str(uuid4())
    chars.docs.append(
        {
            "id": persona_id,
            "owner_id": a_id,
            "name": "A's persona",
            "is_ooc_persona": True,
            "status": "active",
            "versions": [],
        }
    )

    session_id = str(uuid4())
    chat_sessions.docs.append({"id": session_id, "owner_id": a_id, "name": "A's chat"})

    play_session_id = str(uuid4())
    pack_id = str(uuid4())
    job_id = str(uuid4())
    source_id = str(uuid4())
    asset_id = str(uuid4())
    template_id = str(uuid4())
    entry_id = str(uuid4())
    note_universe_id = universe_id
    sheet_id = str(uuid4())
    party_id = str(uuid4())
    collection_id = str(uuid4())
    proposal_id = str(uuid4())

    return {
        "universe": universe_id,
        "multiverse": multiverse_id,
        "story": story_id,
        "scene": scene_id,
        "entity": entity_id,
        "fact": fact_id,
        "character": character_id,
        "persona": persona_id,
        "session": session_id,
        "play_session": play_session_id,
        "pack": pack_id,
        "job": job_id,
        "source": source_id,
        "asset": asset_id,
        "template": template_id,
        "entry": entry_id,
        "note": note_universe_id,
        "sheet": sheet_id,
        "party": party_id,
        "collection": collection_id,
        "proposal": proposal_id,
    }


@pytest.fixture
def seeded(
    monkeypatch: pytest.MonkeyPatch,
    users,
    fake_db: FakePostgres,
    neo: FakeNeo4j,
    chars: FakeCollection,
    chat_sessions: FakeCollection,
):
    ids = _seed_all(users, fake_db, neo, chars, chat_sessions)
    # A's chat session also lives in the in-process caches the chat router
    # reads after its ownership check — so a missing check is a visible leak,
    # not an accidental 404 on a cold cache.
    import monitor_ui.routers.chat as chat_mod

    monkeypatch.setitem(
        chat_mod._SESSIONS,
        ids["session"],
        {"id": ids["session"], "title": "A's chat", "mode": "narrative", "owner_id": str(users.a_id)},
    )
    monkeypatch.setitem(chat_mod._MESSAGES, ids["session"], [])
    return ids


def _assert_store_unchanged(before: list[dict], after: list[dict]) -> None:
    assert after == before, "A's data changed on a cross-tenant attempt"


# ---------------------------------------------------------------------------
# Per-kind cross-tenant cases
# ---------------------------------------------------------------------------


class TestCrossTenantByKind:
    def test_universe_read_update_delete(self, users, seeded, fake_db: FakePostgres) -> None:
        uid = seeded["universe"]
        before = dict(fake_db.worlds[uid])
        for method, path in [
            ("GET", f"/api/universes/universes/{uid}"),
            ("PUT", f"/api/universes/universes/{uid}"),
            ("DELETE", f"/api/universes/universes/{uid}"),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), json={"name": "hijack"})
            assert r.status_code in (403, 404), (method, path, r.status_code)
        assert fake_db.worlds[uid] == before

    def test_universe_list_is_scoped(self, users, seeded) -> None:
        ids = [u.get("id") for u in users.b.get("/api/universes/universes").json()]
        assert seeded["universe"] not in ids

    def test_story_read_update(self, users, seeded) -> None:
        sid = seeded["story"]
        for method, path, kwargs in [
            ("GET", f"/api/stories/{sid}", {}),
            ("PATCH", f"/api/stories/{sid}", {"json": {"title": "hijack"}}),
            ("GET", f"/api/stories/{sid}/scenes", {}),
            ("GET", f"/api/stories/{sid}/threads", {}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code in (403, 404), (method, path, r.status_code)

    def test_scene_read(self, users, seeded) -> None:
        r = users.b.get(f"/api/scenes/scenes/{seeded['scene']}/turns", headers=_csrf(users.b))
        assert r.status_code in (403, 404), r.status_code

    def test_chat_session_read_update_delete(self, users, seeded, chat_sessions: FakeCollection) -> None:
        sid = seeded["session"]
        before = [dict(d) for d in chat_sessions.docs]
        for method, path, kwargs in [
            ("GET", f"/api/chat/{sid}/state", {}),
            ("GET", f"/api/chat/{sid}/messages", {}),
            ("PATCH", f"/api/chat/{sid}", {"json": {"name": "hijack"}}),
            ("DELETE", f"/api/chat/{sid}", {}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code in (403, 404), (method, path, r.status_code)
        _assert_store_unchanged(before, [dict(d) for d in chat_sessions.docs])
        assert chat_sessions.find_one({"id": sid})["owner_id"] == str(users.a_id)

    def test_chat_list_is_scoped(self, users, seeded) -> None:
        sessions = users.b.get("/api/chat").json()
        assert all(s.get("id") != seeded["session"] for s in sessions)

    def test_character_read_update_delete(self, users, seeded, chars: FakeCollection) -> None:
        cid = seeded["character"]
        before = [dict(d) for d in chars.docs]
        for method, path, kwargs in [
            ("GET", f"/api/entities/characters/{cid}", {}),
            ("PUT", f"/api/entities/characters/{cid}", {"json": {"name": "hijack"}}),
            ("DELETE", f"/api/entities/characters/{cid}", {}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code in (403, 404), (method, path, r.status_code)
        _assert_store_unchanged(before, [dict(d) for d in chars.docs])
        assert chars.find_one({"id": cid})["name"] == "A's hero"

    def test_character_list_is_scoped(self, users, seeded) -> None:
        ids = [c.get("id") for c in users.b.get("/api/entities/characters").json()]
        assert seeded["character"] not in ids
        assert seeded["persona"] not in ids

    def test_persona_read(self, users, seeded) -> None:
        pid = seeded["persona"]
        r = users.b.get(f"/api/entities/characters/{pid}", headers=_csrf(users.b))
        assert r.status_code in (403, 404), r.status_code

    def test_conversation_send_is_blocked(self, users, seeded) -> None:
        """B cannot chat with A's character (conversation routes carry character_id)."""
        r = users.b.post(
            f"/api/entities/characters/{seeded['character']}/conversations/{uuid4()}/send",
            json={"text": "hello"},
            headers=_csrf(users.b),
        )
        assert r.status_code in (403, 404), r.status_code

    def test_pack_read_update_delete(self, users, seeded, monkeypatch: pytest.MonkeyPatch) -> None:
        pack = SimpleNamespace(id=seeded["pack"], owner_id=str(users.a_id))
        monkeypatch.setattr("monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack", lambda pid: pack)
        pid = seeded["pack"]
        for method, path, kwargs in [
            ("GET", f"/api/ingest/packs/{pid}", {}),
            ("PUT", f"/api/ingest/packs/{pid}", {"json": {"name": "hijack"}}),
            ("DELETE", f"/api/ingest/packs/{pid}", {}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code in (403, 404), (method, path, r.status_code)

    def test_ingest_job_read_update(
        self, users, seeded, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = SimpleNamespace(
            job_id=UUID(seeded["job"]),
            owner_id=str(users.a_id),
            universe_id=seeded["universe"],
            source_id=UUID(seeded["source"]),
        )
        monkeypatch.setattr("monitor_data.tools.mongodb_tools.mongodb_get_ingestion_job", lambda jid: job)
        jid = seeded["job"]
        for method, path, kwargs in [
            ("GET", f"/api/ingest/jobs/{jid}", {}),
            ("POST", f"/api/ingest/jobs/{jid}/cancel", {}),
            ("DELETE", f"/api/ingest/jobs/{jid}", {}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code in (403, 404), (method, path, r.status_code)

    def test_note_read_update(self, users, seeded) -> None:
        nid = seeded["note"]
        for method, path, kwargs in [
            ("GET", f"/api/gm/notes/{nid}", {}),
            ("PUT", f"/api/gm/notes/{nid}", {"json": {"note": "hijack"}}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code in (403, 404), (method, path, r.status_code)

    def test_image_read_update(self, users, seeded, monkeypatch: pytest.MonkeyPatch) -> None:
        asset = SimpleNamespace(id=UUID(seeded["asset"]), universe_id=seeded["universe"], character_id=None)
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.generated_assets.mongodb_get_generated_asset",
            lambda aid: asset,
        )
        aid = seeded["asset"]
        for method, path, kwargs in [
            ("GET", f"/api/image/assets/{aid}", {}),
            ("POST", f"/api/image/assets/{aid}/approve", {}),
            ("POST", f"/api/image/assets/{aid}/reject", {}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code in (403, 404), (method, path, r.status_code)

    def test_template_read_update_delete(self, users, seeded, monkeypatch: pytest.MonkeyPatch) -> None:
        template = SimpleNamespace(id=UUID(seeded["template"]), universe_id=seeded["universe"])
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.templates.mongodb_get_entity_template",
            lambda tid: template,
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.character_templates.mongodb_get_character_template",
            lambda tid, owner_id=None: None,
        )
        tid = seeded["template"]
        for method, path, kwargs in [
            ("GET", f"/api/templates/{tid}", {}),
            ("PATCH", f"/api/templates/{tid}", {"json": {"name": "hijack"}}),
            ("DELETE", f"/api/templates/{tid}", {}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code in (403, 404), (method, path, r.status_code)

    def test_provider_requires_admin(self, users, seeded) -> None:
        """Providers are admin-owned and shared: a non-admin B gets 403."""
        for method, path, kwargs in [
            ("GET", "/api/llm/providers", {}),
            ("PUT", f"/api/llm/providers/{uuid4()}", {"json": {"name": "hijack"}}),
            ("DELETE", f"/api/llm/providers/{uuid4()}", {}),
        ]:
            r = users.b.request(method, path, headers=_csrf(users.b), **kwargs)
            assert r.status_code == 403, (method, path, r.status_code)

    def test_api_token_delete_is_owner_predicated(self, users, fake_db: FakePostgres) -> None:
        row = asyncio_run(
            fake_db.api_token_create(
                {
                    "user_id": UUID(str(users.a_id)),
                    "name": "A's token",
                    "token_prefix": "mt_ab",
                    "token_hash": "hash-" + str(uuid4()),
                }
            )
        )
        token_id = row["id"]
        r = users.b.request("DELETE", f"/api/auth/tokens/{token_id}", headers=_csrf(users.b))
        assert r.status_code == 404, r.status_code
        # A's token is untouched and still listed.
        listed = users.a.get("/api/auth/tokens").json()
        assert any(t["id"] == str(token_id) for t in listed)


def asyncio_run(coro):  # type: ignore[no-untyped-def]
    import asyncio

    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Generated sweep from the route table
# ---------------------------------------------------------------------------

# Path/query parameter name -> the seeded kind whose id must be substituted.
PARAM_KIND = {
    "universe_id": "universe",
    "multiverse_id": "multiverse",
    "mv_id": "multiverse",
    "story_id": "story",
    "scene_id": "scene",
    "entity_id": "entity",
    "fact_id": "fact",
    "axiom_id": "fact",
    "event_id": "fact",
    "character_id": "character",
    "pack_id": "pack",
    "job_id": "job",
    "ingestion_job_id": "job",
    "source_id": "source",
    "asset_id": "asset",
    "template_id": "template",
    "entry_id": "entry",
    "sheet_id": "sheet",
    "party_id": "party",
    "collection_id": "collection",
    "proposal_id": "proposal",
}

# Routes the generated sweep skips, with the reason they are safe.
SWEEP_EXEMPT: dict[tuple[str, str], str] = {
    ("POST", "/api/universes/universes/{universe_id}/snapshots/{snapshot_id}/restore"): (
        "snapshot ids are separate resources; covered by the universe_id guard on the same route"
    ),
    ("DELETE", "/api/universes/universes/{universe_id}/snapshots/{snapshot_id}"): (
        "snapshot ids are separate resources; covered by the universe_id guard on the same route"
    ),
    ("GET", "/api/universes/universes/{universe_id}/snapshots/compare"): (
        "snapshot ids are separate resources; covered by the universe_id guard on the same route"
    ),
    ("PATCH", "/api/ingest/packs/{pack_id}/entities/{index}"): "numeric index, not a resource id",
    ("PATCH", "/api/ingest/packs/{pack_id}/relationships/{index}"): "numeric index, not a resource id",
    ("DELETE", "/api/ingest/packs/{pack_id}/{collection}/{index}"): "numeric index, not a resource id",
}

# Minimal bodies so generated POST/PUT/PATCH requests pass validation and
# reach the ownership checks. Anything missing shows up as a 422 failure.
BODIES: dict[tuple[str, str], dict] = {
    ("POST", "/api/ingest/jobs/{job_id}/held-claims/{claim_id}"): {"decision": "accept"},
    ("POST", "/api/chat/{session_id}/send"): {"content": "hello"},
    ("POST", "/api/chat/{session_id}/greet"): {},
}

# Required query parameters for generated requests (seeded substitution).
QUERIES: dict[tuple[str, str], dict] = {
    ("POST", "/api/chat/{session_id}/greet"): {"character_id": "character"},
}


def _sweep_cases(app: FastAPI) -> list[tuple[str, str, str, dict[str, str]]]:
    """(method, path-template, kind-param, substituted path) for every route
    carrying a resource-id parameter."""
    cases: list[tuple[str, str, str, dict[str, str]]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted(m for m in (route.methods or set()) if m != "HEAD")
        for method in methods:
            params = set(re.findall(r"{([^}:]+)(?::[^}]*)?}", route.path))
            kinds = {p: PARAM_KIND[p] for p in params & set(PARAM_KIND)}
            if "session_id" in params:
                kinds["session_id"] = "play_session" if route.path.startswith("/api/play-sessions/") else "session"
            if not kinds:
                continue
            cases.append((method, route.path, ",".join(sorted(kinds)), kinds))
    return cases


def test_generated_route_table_sweep(users, seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    """B's request to every resource-id route answers 403/404 (auto-covered).

    Substitutes A's seeded ids into each route template. New routes with
    resource-id parameters are picked up automatically; exclusions require
    an entry in ``SWEEP_EXEMPT`` with a reason.
    """
    # Data-layer fakes for the resolver lookups not covered by the per-kind fakes.
    job = SimpleNamespace(job_id=UUID(seeded["job"]), owner_id=str(users.a_id), universe_id=seeded["universe"])
    monkeypatch.setattr("monitor_data.tools.mongodb_tools.mongodb_get_ingestion_job", lambda jid: job)
    pack = SimpleNamespace(id=seeded["pack"], owner_id=str(users.a_id))
    monkeypatch.setattr("monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack", lambda pid: pack)
    asset = SimpleNamespace(id=UUID(seeded["asset"]), universe_id=seeded["universe"], character_id=None)
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.generated_assets.mongodb_get_generated_asset", lambda aid: asset
    )
    template = SimpleNamespace(id=UUID(seeded["template"]), universe_id=seeded["universe"])
    monkeypatch.setattr("monitor_data.tools.mongodb_tools.templates.mongodb_get_entity_template", lambda tid: template)
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_templates.mongodb_get_character_template",
        lambda tid, owner_id=None: None,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.lorebook_tools.mongodb_get_lorebook_entry",
        lambda eid: SimpleNamespace(character_id=seeded["character"]),
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.mongodb_get_proposed_change",
        lambda pid: SimpleNamespace(scene_id=None, story_id=UUID(seeded["story"]), source=None, proposer=None),
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.play_sessions.mongodb_get_play_session",
        lambda sid: SimpleNamespace(universe_id=seeded["universe"]),
    )
    monkeypatch.setattr(
        "monitor_data.tools.neo4j_tools.parties.neo4j_list_parties",
        lambda f: [SimpleNamespace(story_id=UUID(seeded["story"]))],
    )
    monkeypatch.setattr("monitor_data.tools.mongodb_tools.mongodb_list_documents", lambda **k: [])
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.mongodb_list_ingestion_jobs",
        lambda f: SimpleNamespace(jobs=[job]),
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.prompt_collections.mongodb_get_prompt_collection",
        lambda cid: SimpleNamespace(universe_id=seeded["universe"], is_builtin=False),
    )
    # character sheets resolve through the entity's universe
    sheet_doc = {"id": seeded["sheet"], "entity_id": seeded["entity"]}
    fake_mongo = SimpleNamespace(get_collection=lambda name: SimpleNamespace(find_one=lambda q, *a, **k: sheet_doc))
    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: fake_mongo)

    failures: list[str] = []
    for method, path_template, kind_params, kinds in _sweep_cases(main_app):
        if (method, path_template) in SWEEP_EXEMPT:
            continue
        path = path_template
        for param, kind in kinds.items():
            path = path.replace("{" + param + "}", seeded[kind])
        # any remaining placeholder is not an ownable id (index, claim, ...)
        path = re.sub(r"\{[^}]+\}", str(uuid4()), path)
        body = BODIES.get((method, path_template))
        query = {k: seeded[v] for k, v in QUERIES.get((method, path_template), {}).items()}
        kwargs: dict[str, Any] = {"headers": _csrf(users.b)}
        if query:
            kwargs["params"] = query
        if method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = body if body is not None else {}
        r = users.b.request(method, path, **kwargs)
        if r.status_code not in (403, 404):
            failures.append(f"{method} {path_template} -> {r.status_code} (params: {kind_params})")
    assert not failures, "Cross-tenant sweep failures (B was not rejected):\n" + "\n".join(sorted(failures))


def test_sweep_exemptions_are_stale_free() -> None:
    """SWEEP_EXEMPT must not keep entries for routes that no longer exist."""
    registered = set()
    for route in main_app.routes:
        if isinstance(route, APIRoute):
            for m in route.methods or set():
                if m != "HEAD":
                    registered.add((m, route.path))
    stale = [f"{m} {p}" for m, p in SWEEP_EXEMPT if (m, p) not in registered]
    assert not stale, f"SWEEP_EXEMPT entries without a registered route: {stale}"


def test_guard_present_on_every_resource_route() -> None:
    """Structural half of "the suite fails if a guard is removed".

    Any route carrying a resource-id parameter must run
    ``resource_route_guard`` (admin-only operator routes are exempt). With
    the behavioral sweep above, removing a guard fails this suite.
    """
    from monitor_ui.auth import require_admin
    from test_route_auth_coverage import _dependency_calls, _routes

    resolver_keys = set(ownership_mod._SCOPE_RESOLVERS) | {"session_id"}
    unguarded: list[str] = []
    for route, path, methods in _routes(main_app):
        if not isinstance(route, APIRoute):
            continue
        calls = _dependency_calls(route)
        if require_admin in calls:
            continue
        names = set(re.findall(r"{([^}:]+)(?::[^}]*)?}", route.path))
        matched = names & resolver_keys
        if matched and ownership_mod.resource_route_guard not in calls:
            unguarded.append(f"{','.join(methods):<12} {path} <- {sorted(matched)}")
    assert not unguarded, "Routes with resource-id params but no resource_route_guard:\n" + "\n".join(sorted(unguarded))
