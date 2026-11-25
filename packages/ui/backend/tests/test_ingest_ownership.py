"""Two-user ownership tests for ingest sources and jobs (Phase 4 slice).

Ingestion jobs and documents are rootless Mongo records carrying ``owner_id``,
stamped at upload; reads/actions are owner-scoped with generic 404s.
Hermetic: FakePostgres + patched Mongo tools at the router namespace AND at
the data-layer namespace (the router-level ``resource_route_guard`` resolves
job/source ownership through ``monitor_ui.ownership``, which imports the
tools from their source module).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import monitor_ui.routers.ingest as ingest_mod
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import (
    IngestionJobFilter,
    IngestionJobListResponse,
    IngestionJobResponse,
)
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from fake_postgres import FakePostgres


def _job(job_id: UUID, source_id: UUID, universe_id: UUID, owner_id: str | None) -> IngestionJobResponse:
    now = datetime.now(UTC)
    return IngestionJobResponse(
        job_id=job_id,
        universe_id=universe_id,
        source_id=source_id,
        doc_id=uuid4(),
        owner_id=owner_id,
        source_title="t",
        status=IngestionStatus.PENDING,
        pipeline_stages=[],
        started_at=now,
        created_at=now,
        updated_at=now,
    )


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


def _own_multiverse(fake_db: FakePostgres, owner_id: str) -> str:
    mid = str(uuid4())
    fake_db.multiverses[mid] = {
        "id": mid,
        "owner_id": UUID(owner_id),
        "label": "mv",
        "active": True,
    }
    return mid


class TestIngestAuthz:
    def test_unauthenticated_denied(self, client):
        assert client.get("/api/ingest/sources").status_code == 401
        assert client.get("/api/ingest/jobs").status_code == 401
        assert client.get(f"/api/ingest/jobs/{uuid4()}").status_code == 401
        assert client.post(f"/api/ingest/jobs/{uuid4()}/cancel").status_code == 401

    def test_force_unlock_is_admin_only(self, client):
        _signup(client, "a@example.com", "alice")
        assert client.post("/api/ingest/unlock", headers=_csrf(client)).status_code == 403

    def test_lists_are_owner_scoped(self, client, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        captured = {}

        def fake_list_jobs(params: IngestionJobFilter):
            captured["owner_id"] = params.owner_id
            return IngestionJobListResponse(jobs=[], total=0, limit=params.limit, offset=params.offset)

        monkeypatch.setattr(ingest_mod, "mongodb_list_ingestion_jobs", fake_list_jobs)
        monkeypatch.setattr(ingest_mod, "mongodb_list_documents", lambda *a, **k: [])
        r = client.get("/api/ingest/jobs")
        assert r.status_code == 200
        assert captured["owner_id"] == user["id"]
        r = client.get("/api/ingest/sources")
        assert r.status_code == 200

    def test_job_get_and_cancel_require_ownership(self, client, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        my_job = _job(uuid4(), uuid4(), uuid4(), user["id"])
        foreign_job = _job(uuid4(), uuid4(), uuid4(), str(uuid4()))
        jobs = {str(my_job.job_id): my_job, str(foreign_job.job_id): foreign_job}
        monkeypatch.setattr(ingest_mod, "mongodb_get_ingestion_job", lambda uid: jobs.get(str(uid)))
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_ingestion_job", lambda uid: jobs.get(str(uid))
        )
        monkeypatch.setattr(ingest_mod, "_job_to_dict", lambda j: {"id": str(j.job_id)})

        assert client.get(f"/api/ingest/jobs/{my_job.job_id}").status_code == 200
        r = client.get(f"/api/ingest/jobs/{foreign_job.job_id}")
        assert r.status_code == 404 and r.json() == {"detail": "Not found"}
        assert client.get(f"/api/ingest/jobs/{uuid4()}").json() == {"detail": "Not found"}

        # cancel: foreign → 404, and the mongo update path is never reached
        def fail_update(*a, **k):  # type: ignore[no-untyped-def]
            raise AssertionError("must not reach mongo update for foreign job")

        monkeypatch.setattr(ingest_mod, "get_mongodb_client", lambda: type("M", (), {"get_collection": fail_update})())
        r = client.post(f"/api/ingest/jobs/{foreign_job.job_id}/cancel", headers=_csrf(client))
        assert r.status_code == 404

    def test_delete_source_requires_ownership(self, client, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        source_id = uuid4()
        foreign_source = uuid4()

        def fake_list_jobs(params):
            jobs = [
                _job(uuid4(), source_id, uuid4(), user["id"]),
                _job(uuid4(), foreign_source, uuid4(), str(uuid4())),
            ]
            filtered = [j for j in jobs if params.source_id is None or j.source_id == params.source_id]
            return IngestionJobListResponse(
                jobs=filtered[: params.limit], total=len(filtered), limit=params.limit, offset=params.offset
            )

        monkeypatch.setattr(ingest_mod, "mongodb_list_ingestion_jobs", fake_list_jobs)
        monkeypatch.setattr(ingest_mod, "mongodb_list_documents", lambda *a, **k: [])
        monkeypatch.setattr("monitor_data.tools.mongodb_tools.mongodb_list_ingestion_jobs", fake_list_jobs)
        monkeypatch.setattr("monitor_data.tools.mongodb_tools.mongodb_list_documents", lambda *a, **k: [])

        client_b = TestClient(app, raise_server_exceptions=False)
        _signup(client_b, "b@example.com", "bob")
        r = client_b.request("DELETE", f"/api/ingest/sources/{source_id}", headers=_csrf(client_b))
        assert r.status_code == 404
        # owner can delete (handler proceeds into mongo, which is real → 500 via
        # raise_server_exceptions=False, but NOT 401/403/404)
        r = client.request("DELETE", f"/api/ingest/sources/{source_id}", headers=_csrf(client))
        assert r.status_code not in (401, 403, 404)

    def test_upload_into_foreign_multiverse_rejected(self, client, fake_db):
        user = _signup(client, "a@example.com", "alice")
        foreign_mv = _own_multiverse(fake_db, str(uuid4()))
        r = client.post(
            "/api/ingest/sources/upload",
            files={"file": ("a.txt", b"hello", "text/plain")},
            data={"multiverse_id": foreign_mv},
            headers=_csrf(client),
        )
        assert r.status_code == 404
        # owned multiverse passes the ownership gate (fails later hermetically)
        my_mv = _own_multiverse(fake_db, user["id"])
        r = client.post(
            "/api/ingest/sources/upload",
            files={"file": ("a.txt", b"hello", "text/plain")},
            data={"multiverse_id": my_mv},
            headers=_csrf(client),
        )
        assert r.status_code not in (401, 403, 404)

    def test_upload_with_foreign_story_rejected(self, client, monkeypatch):
        _signup(client, "a@example.com", "alice")

        async def _missing_story(_sid):
            return None

        monkeypatch.setattr("monitor_ui.ownership._universe_of_story", _missing_story)
        r = client.post(
            "/api/ingest/sources/upload",
            files={"file": ("a.txt", b"hello", "text/plain")},
            data={"story_id": str(uuid4())},
            headers=_csrf(client),
        )
        assert r.status_code == 404

    def test_upload_with_owned_story_passes_gate(self, client, fake_db, monkeypatch):
        user = _signup(client, "a@example.com", "alice")
        world_id = str(uuid4())
        fake_db.worlds[world_id] = {
            "id": world_id,
            "owner_id": UUID(user["id"]),
            "label": "w",
            "active": True,
        }

        async def _owned_story(_sid):
            return world_id

        monkeypatch.setattr("monitor_ui.ownership._universe_of_story", _owned_story)
        r = client.post(
            "/api/ingest/sources/upload",
            files={"file": ("a.txt", b"hello", "text/plain")},
            data={"story_id": str(uuid4())},
            headers=_csrf(client),
        )
        assert r.status_code not in (401, 403, 404)


# ---------------------------------------------------------------------------
# UX-1: the job-owner rule is a strict creator match everywhere
# ---------------------------------------------------------------------------


class TestIngestJobOwnerRule:
    @pytest.mark.asyncio
    async def test_universe_owner_is_not_the_creator(self, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch):
        """Owning the job's universe grants NOTHING — creator match only.

        This pins the divergence the old creator-or-universe resolver left
        open: a foreign user who happens to own the job's universe must
        still get the generic 404.
        """
        from fastapi import HTTPException

        from monitor_ui.auth import Principal
        from monitor_ui.ownership import require_ingestion_job_owner

        creator = str(uuid4())
        universe_owner = str(uuid4())
        universe_id = uuid4()
        job = _job(uuid4(), uuid4(), universe_id, creator)
        # The foreign user owns the job's universe in the registry.
        fake_db.world_upsert({"id": str(universe_id), "owner_id": UUID(universe_owner), "active": True})
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_ingestion_job",
            lambda jid: job,
        )

        foreign = Principal(user_id=universe_owner, is_admin=False, via="session")
        with pytest.raises(HTTPException) as exc:
            await require_ingestion_job_owner(fake_db, foreign, str(job.job_id))
        assert exc.value.status_code == 404

        # The creator passes.
        principal = Principal(user_id=creator, is_admin=False, via="session")
        await require_ingestion_job_owner(fake_db, principal, str(job.job_id))

    @pytest.mark.asyncio
    async def test_ownerless_job_fails_closed(self, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch):
        from fastapi import HTTPException

        from monitor_ui.auth import Principal
        from monitor_ui.ownership import require_ingestion_job_owner

        universe_id = uuid4()
        universe_owner = str(uuid4())
        job = _job(uuid4(), uuid4(), universe_id, None)
        fake_db.world_upsert({"id": str(universe_id), "owner_id": UUID(universe_owner), "active": True})
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_ingestion_job",
            lambda jid: job,
        )

        principal = Principal(user_id=universe_owner, is_admin=False, via="session")
        with pytest.raises(HTTPException) as exc:
            await require_ingestion_job_owner(fake_db, principal, str(job.job_id))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_job_fails_closed(self, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch):
        from fastapi import HTTPException

        from monitor_ui.auth import Principal
        from monitor_ui.ownership import require_ingestion_job_owner

        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_ingestion_job",
            lambda jid: None,
        )
        principal = Principal(user_id=str(uuid4()), is_admin=False, via="session")
        with pytest.raises(HTTPException) as exc:
            await require_ingestion_job_owner(fake_db, principal, str(uuid4()))
        assert exc.value.status_code == 404

    def test_stamp_job_owner_writes_the_creator(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[tuple[object, object]] = []
        monkeypatch.setattr(
            ingest_mod,
            "mongodb_set_ingestion_job_owner",
            lambda job_id, owner_id: calls.append((job_id, owner_id)),
        )
        job_id = uuid4()
        owner = str(uuid4())
        ingest_mod._stamp_job_owner(job_id, owner)
        assert calls == [(job_id, owner)]

    def test_stamp_job_owner_noop_without_owner(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[tuple[object, object]] = []
        monkeypatch.setattr(
            ingest_mod,
            "mongodb_set_ingestion_job_owner",
            lambda job_id, owner_id: calls.append((job_id, owner_id)),
        )
        ingest_mod._stamp_job_owner(uuid4(), None)
        assert calls == []

    def test_job_route_creator_passes_with_foreign_universe(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """The creator reads their job even though nobody owns its universe."""
        user = _signup(client, "creator@example.com", "creator")
        job = _job(uuid4(), uuid4(), uuid4(), user["id"])
        monkeypatch.setattr(
            ingest_mod, "mongodb_get_ingestion_job", lambda uid: job if str(uid) == str(job.job_id) else None
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_ingestion_job",
            lambda uid: job if str(uid) == str(job.job_id) else None,
        )
        monkeypatch.setattr(ingest_mod, "_job_to_dict", lambda j: {"id": str(j.job_id), "owner_id": j.owner_id})
        res = client.get(f"/api/ingest/jobs/{job.job_id}")
        assert res.status_code == 200, res.text
        assert res.json()["owner_id"] == user["id"]
