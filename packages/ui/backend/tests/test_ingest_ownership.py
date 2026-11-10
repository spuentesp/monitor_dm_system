"""Two-user ownership tests for ingest sources and jobs (Phase 4 slice).

Ingestion jobs and documents are rootless Mongo records carrying ``owner_id``,
stamped at upload; reads/actions are owner-scoped with generic 404s.
Hermetic: FakePostgres + patched Mongo tools at the router namespace.
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
    get_settings.cache_clear()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    c = TestClient(app, raise_server_exceptions=False)
    yield c
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
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
