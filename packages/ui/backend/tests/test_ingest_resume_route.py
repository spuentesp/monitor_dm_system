"""Paused analysis: decomposition still starts, resume requeues, timeout pauses (I-17).

Every database and pipeline call is faked; nothing here starts a real ingest.
"""

from __future__ import annotations

import concurrent.futures
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import IngestionStage
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_ui.routers import ingest

pytestmark = pytest.mark.usefixtures("local_auth_mode")


def _finished_ingest(status=IngestionStatus.COMPLETED):
    return SimpleNamespace(status=status, doc_id=uuid.uuid4(), source_id=uuid.uuid4())


def _analysis_job(status=IngestionStatus.PAUSED, *, total_attempts: int = 42):
    return SimpleNamespace(
        job_id=uuid.uuid4(),
        doc_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        universe_id=uuid.uuid4(),
        status=status,
        pipeline_stages=[IngestionStage.UPLOAD, IngestionStage.EXTRACT, IngestionStage.EMBED, IngestionStage.ANALYZE],
        stages_completed=[IngestionStage.UPLOAD, IngestionStage.EXTRACT, IngestionStage.EMBED],
        processing_checklist=["entities", "rules"],
        source_title="Book",
        total_attempts=total_attempts,
    )


class _InlineExecutor:
    """Runs submitted work immediately so route tests are deterministic."""

    def submit(self, fn, /, *args, **kwargs):
        future: concurrent.futures.Future = concurrent.futures.Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001  # reason: mirror ThreadPoolExecutor error delivery
            future.set_exception(exc)
        return future


@pytest.fixture
def inline_executor(monkeypatch):
    executor = _InlineExecutor()
    monkeypatch.setattr(ingest, "_ingest_executor", executor)
    yield executor
    ingest._clear_ingest_slot()
    ingest._ingest_futures.clear()


# ---------------------------------------------------------------------------
# Task 16: decomposition after a partial / resumable analysis
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "starts"),
    [
        (IngestionStatus.COMPLETED, True),
        (IngestionStatus.PARTIAL, True),
        (IngestionStatus.PAUSED, True),
        (IngestionStatus.FAILED, False),
        (IngestionStatus.CANCELLED, False),
    ],
)
def test_decomposition_starts_for_finished_partial_and_paused_analyses(monkeypatch, status, starts):
    monkeypatch.setenv("MONITOR_BOOK_DECOMPOSITION", "1")
    with (
        patch.object(ingest, "_start_decomposition") as start,
        patch.object(ingest, "create_decomposition_job") as create,
    ):
        ingest._maybe_start_decomposition(_finished_ingest(status), b"x", "book.pdf", "Book", KnowledgePackType.MISC)
    assert start.called is starts
    assert create.called is starts


# ---------------------------------------------------------------------------
# Task 14: resume of a paused analysis job
# ---------------------------------------------------------------------------


def test_resume_requeues_the_analysis_with_saved_batch_reuse(inline_executor):
    from fastapi.testclient import TestClient
    from monitor_ui.main import app

    client = TestClient(app)
    job = _analysis_job()
    doc = SimpleNamespace(minio_ref="uploads/book.pdf", filename="book.pdf", file_type="application/pdf")
    captured: dict = {}

    def _capture_run(**kwargs):
        captured.update(kwargs)

    with (
        patch.object(ingest, "mongodb_get_ingestion_job", return_value=job),
        patch.object(ingest, "mongodb_get_document", return_value=doc),
        patch.object(ingest, "get_minio_client") as minio,
        patch.object(ingest, "stored_pack_type", return_value=KnowledgePackType.RULEBOOK),
        patch.object(ingest, "_run_ingest_in_thread", side_effect=_capture_run),
    ):
        minio.return_value.download = AsyncMock(return_value=b"pdf-bytes")
        response = client.post(f"/api/ingest/jobs/{job.job_id}/resume")

    assert response.status_code == 202
    # Cross-component boundary: the worker is invoked with the resume wiring.
    assert captured["resume_job_id"] == job.job_id
    assert captured["reuse_doc_id"] == job.doc_id
    assert captured["reuse_source_id"] == job.source_id
    assert captured["file_bytes"] == b"pdf-bytes"
    assert captured["selected_layers"] == ["entities", "rules"]
    assert captured["estimated_calls"] == 42
    assert captured["pack_type_enum"] is KnowledgePackType.RULEBOOK


@pytest.mark.unit
def test_resume_rejects_a_failed_analysis_job():
    from fastapi.testclient import TestClient
    from monitor_ui.main import app

    client = TestClient(app)
    job = _analysis_job(IngestionStatus.FAILED)
    with patch.object(ingest, "mongodb_get_ingestion_job", return_value=job):
        response = client.post(f"/api/ingest/jobs/{job.job_id}/resume")
    assert response.status_code == 409


@pytest.mark.unit
def test_resume_rejects_a_running_analysis_job():
    from fastapi.testclient import TestClient
    from monitor_ui.main import app

    client = TestClient(app)
    job = _analysis_job(IngestionStatus.RUNNING)
    with patch.object(ingest, "mongodb_get_ingestion_job", return_value=job):
        response = client.post(f"/api/ingest/jobs/{job.job_id}/resume")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Tasks 14-15: the worker's wiring
# ---------------------------------------------------------------------------


def test_the_worker_passes_the_call_estimate_into_the_stage_limit(monkeypatch):
    monkeypatch.setattr(ingest, "_JOB_TIMEOUT_SECS", 24 * 60 * 60)
    captured: dict = {}

    async def _fake_ingest_file(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status=IngestionStatus.COMPLETED, doc_id=uuid.uuid4(), source_id=uuid.uuid4())

    pipeline = SimpleNamespace(ingest_file=_fake_ingest_file)
    with patch.object(ingest, "IngestionPipeline", return_value=pipeline):
        ingest._run_ingest_in_thread(
            queue_token="estimate-token",
            file_bytes=b"pdf",
            filename="book.pdf",
            source_title="Book",
            universe_uid=None,
            pack_type_enum=KnowledgePackType.RULEBOOK,
            selected_layers=["rules"],
            content_type="application/pdf",
            estimated_calls=500,
        )

    assert captured["analyze_timeout_seconds"] == ingest.analyze_timeout_for_job(24 * 60 * 60, 500)
    # …which differs from the no-estimate stage default on this long job.
    assert captured["analyze_timeout_seconds"] != ingest.analyze_timeout_for_job(24 * 60 * 60)
    ingest._clear_ingest_slot()


def test_a_whole_job_timeout_pauses_instead_of_failing(monkeypatch):
    captured_updates: list[object] = []

    def _capture_update(job_id, params):
        captured_updates.append(params)
        return SimpleNamespace(job_id=job_id, status=params.status)

    job_id = uuid.uuid4()

    async def _fake_ingest_file(**kwargs):
        kwargs["on_job_created"](job_id)
        raise TimeoutError("whole-job limit reached")

    pipeline = SimpleNamespace(ingest_file=_fake_ingest_file)
    with (
        patch.object(ingest, "IngestionPipeline", return_value=pipeline),
        patch("monitor_data.tools.mongodb_tools.mongodb_update_ingestion_job", side_effect=_capture_update),
    ):
        ingest._run_ingest_in_thread(
            queue_token="timeout-token",
            file_bytes=b"pdf",
            filename="book.pdf",
            source_title="Book",
            universe_uid=None,
            pack_type_enum=KnowledgePackType.RULEBOOK,
            selected_layers=["rules"],
            content_type="application/pdf",
        )

    statuses = [getattr(update, "status", None) for update in captured_updates]
    assert IngestionStatus.PAUSED in statuses
    assert IngestionStatus.FAILED not in statuses
    paused = next(update for update in captured_updates if getattr(update, "status", None) is IngestionStatus.PAUSED)
    assert any("resume" in entry.lower() for entry in (paused.activity_log or []))
    assert getattr(paused, "completed_at", None) is None
    ingest._clear_ingest_slot()


def test_the_worker_sends_a_resume_through_the_pipeline(monkeypatch):
    captured: dict = {}
    resume_job_id = uuid.uuid4()

    async def _fake_ingest_file(**kwargs):
        captured.update(kwargs)
        kwargs["on_job_created"](resume_job_id)
        return SimpleNamespace(status=IngestionStatus.COMPLETED, doc_id=uuid.uuid4(), source_id=uuid.uuid4())

    pipeline = SimpleNamespace(ingest_file=_fake_ingest_file)
    with patch.object(ingest, "IngestionPipeline", return_value=pipeline):
        ingest._run_ingest_in_thread(
            queue_token="resume-token",
            file_bytes=b"pdf",
            filename="book.pdf",
            source_title="Book",
            universe_uid=None,
            pack_type_enum=KnowledgePackType.RULEBOOK,
            selected_layers=["rules"],
            content_type="application/pdf",
            resume_job_id=resume_job_id,
        )

    assert captured["resume_job_id"] == resume_job_id
    assert captured["analyze_timeout_seconds"] == ingest.analyze_timeout_for_job(ingest._JOB_TIMEOUT_SECS, None)
    ingest._clear_ingest_slot()


# ---------------------------------------------------------------------------
# Rescan hands the previous run's real call count to the stage limit
# ---------------------------------------------------------------------------


def test_rescan_reuses_saved_batches_and_passes_the_old_call_count():
    from fastapi.testclient import TestClient
    from monitor_ui.main import app

    client = TestClient(app)
    source_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    prev_job = SimpleNamespace(
        job_id=uuid.uuid4(),
        source_id=source_id,
        doc_id=doc_id,
        universe_id=uuid.uuid4(),
        source_title="Book",
        total_attempts=77,
    )
    doc = SimpleNamespace(
        doc_id=doc_id,
        source_id=source_id,
        filename="book.pdf",
        file_type="application/pdf",
        minio_ref="uploads/book.pdf",
        title="Book",
        universe_id=prev_job.universe_id,
    )
    captured: dict = {}

    def _capture_run(**kwargs):
        captured.update(kwargs)

    jobs_result = SimpleNamespace(jobs=[prev_job])
    mongo_collection = MagicMock()
    with (
        patch.object(ingest, "mongodb_list_ingestion_jobs", return_value=jobs_result),
        patch.object(ingest, "mongodb_get_document", return_value=doc),
        patch.object(ingest, "get_minio_client") as minio,
        patch.object(ingest, "neo4j_get_universe", return_value=SimpleNamespace(multiverse_id=uuid.uuid4())),
        patch.object(ingest, "_run_ingest_in_thread", side_effect=_capture_run),
        patch.object(
            ingest, "get_mongodb_client", return_value=SimpleNamespace(get_collection=lambda _n: mongo_collection)
        ),
        patch.object(ingest, "_ingest_executor", _InlineExecutor()),
    ):
        minio.return_value.download = AsyncMock(return_value=b"pdf-bytes")
        response = client.post(f"/api/ingest/sources/{source_id}/rescan")

    assert response.status_code == 202
    # Saved batches live on the document, so the rescan reuses them; the old
    # run's attempt count scales the new stage limit (I-17 tasks 14-15).
    assert captured["reuse_doc_id"] == doc_id
    assert captured["reuse_source_id"] == source_id
    assert captured["estimated_calls"] == 77
    ingest._clear_ingest_slot()
    ingest._ingest_futures.clear()
