"""Starting and resuming book decomposition from the ingest router (I-17)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import IngestionStage
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_ui.main import app
from monitor_ui.routers import ingest

client = TestClient(app)


def _job(status=IngestionStatus.PAUSED, stages=(IngestionStage.DECOMPOSE,)):
    return SimpleNamespace(
        job_id=uuid.uuid4(), doc_id=uuid.uuid4(), status=status, pipeline_stages=list(stages), source_title="Book (decomposition)"
    )


@pytest.fixture
def started():
    minio = AsyncMock()
    minio.download.return_value = b"pdf"
    with (
        patch.object(ingest, "_start_decomposition") as start,
        patch.object(ingest, "get_minio_client", return_value=minio),
        patch.object(ingest, "mongodb_get_document", return_value=SimpleNamespace(minio_ref="key")),
        patch.object(ingest, "stored_pack_type", return_value=KnowledgePackType.RULEBOOK),
    ):
        yield start


def _resume(job):
    with patch.object(ingest, "mongodb_get_ingestion_job", return_value=job):
        return client.post(f"/api/ingest/jobs/{job.job_id}/resume")


@pytest.mark.unit
@pytest.mark.parametrize("status", [IngestionStatus.PAUSED, IngestionStatus.FAILED])
def test_paused_or_failed_decomposition_resumes(started, status):
    job = _job(status)
    response = _resume(job)
    assert response.status_code == 202
    args = started.call_args.args
    assert args[0] == job.job_id and args[1] == b"pdf" and args[3] == "Book"
    assert args[4] == KnowledgePackType.RULEBOOK


@pytest.mark.unit
def test_normal_ingest_job_cannot_be_resumed(started):
    assert _resume(_job(IngestionStatus.FAILED, stages=(IngestionStage.ANALYZE,))).status_code == 409
    started.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("status", [IngestionStatus.RUNNING, IngestionStatus.COMPLETED, IngestionStatus.CANCELLED])
def test_job_in_other_states_cannot_be_resumed(started, status):
    assert _resume(_job(status)).status_code == 409
    started.assert_not_called()


@pytest.mark.unit
def test_job_already_running_here_cannot_be_resumed_twice(started):
    job = _job()
    ingest._decomposition_active.add(str(job.job_id))
    try:
        assert _resume(job).status_code == 409
    finally:
        ingest._decomposition_active.discard(str(job.job_id))
    started.assert_not_called()


@pytest.mark.unit
def test_missing_job_is_not_found(started):
    with patch.object(ingest, "mongodb_get_ingestion_job", return_value=None):
        assert client.post(f"/api/ingest/jobs/{uuid.uuid4()}/resume").status_code == 404


def _finished_ingest(status=IngestionStatus.COMPLETED):
    return SimpleNamespace(status=status, doc_id=uuid.uuid4())


@pytest.mark.unit
def test_flag_off_starts_nothing(monkeypatch):
    monkeypatch.delenv("MONITOR_BOOK_DECOMPOSITION", raising=False)
    with patch.object(ingest, "_start_decomposition") as start, patch.object(ingest, "create_decomposition_job") as create:
        ingest._maybe_start_decomposition(_finished_ingest(), b"x", "book.pdf", "Book", KnowledgePackType.MISC)
    start.assert_not_called()
    create.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("filename", "status", "starts"),
    [
        ("book.PDF", IngestionStatus.COMPLETED, True),
        ("book.pdf", IngestionStatus.PARTIAL, True),
        ("book.txt", IngestionStatus.COMPLETED, False),
        ("book.pdf", IngestionStatus.FAILED, False),
    ],
)
def test_flag_on_starts_only_for_finished_pdfs(monkeypatch, filename, status, starts):
    monkeypatch.setenv("MONITOR_BOOK_DECOMPOSITION", "1")
    with patch.object(ingest, "_start_decomposition") as start, patch.object(ingest, "create_decomposition_job") as create:
        ingest._maybe_start_decomposition(_finished_ingest(status), b"x", filename, "Book", KnowledgePackType.MISC)
    assert start.called is starts and create.called is starts


@pytest.mark.unit
def test_failure_to_start_does_not_break_the_finished_ingest(monkeypatch):
    monkeypatch.setenv("MONITOR_BOOK_DECOMPOSITION", "1")
    with patch.object(ingest, "create_decomposition_job", side_effect=RuntimeError("mongo down")):
        ingest._maybe_start_decomposition(_finished_ingest(), b"x", "book.pdf", "Book", KnowledgePackType.MISC)


@pytest.mark.unit
def test_worker_runs_the_job_off_the_ingest_slot_and_clears_itself():
    job_id, doc = uuid.uuid4(), uuid.uuid4()
    with patch.object(ingest, "run_decomposition_job", new=AsyncMock()) as run:
        ingest._start_decomposition(job_id, b"pdf", doc, "Book", KnowledgePackType.MISC)
        executor = ingest._decomposition_executor
        executor.submit(lambda: None).result(timeout=5)
    run.assert_awaited_once()
    assert str(job_id) not in ingest._decomposition_active
