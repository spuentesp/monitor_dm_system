"""A timeout pauses the analysis, a cancel is left alone, resume reuses the job (I-17, I-1).

No real model: ``analyzer.analyze`` and the indexer are faked, and every
Mongo write is captured.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from monitor_data.schemas.base import ExtractionStatus, IngestionStatus
from monitor_data.schemas.knowledge_packs import KnowledgePackType

from monitor_agents.analyzer import AnalysisCancelledError
from monitor_agents.ingestion import agent as agent_module
from monitor_agents.ingestion.agent import IngestionPipeline


class _FakeMinio:
    def __init__(self) -> None:
        self.upload_calls: list[str] = []

    async def upload(self, key: str, data: bytes, content_type: str | None = None) -> None:
        self.upload_calls.append(key)


def _reuse_setup(monkeypatch, *, snippet_count: int = 100):
    """A pipeline over an already-uploaded, already-indexed document."""
    pipeline = IngestionPipeline(agent_id="test-pause")
    fake_minio = _FakeMinio()
    source_id, doc_id, job_id, universe_id = uuid4(), uuid4(), uuid4(), uuid4()
    existing_doc = SimpleNamespace(
        doc_id=doc_id,
        source_id=source_id,
        extraction_status=ExtractionStatus.COMPLETED,
        minio_ref="uploads/existing.pdf",
        snippet_count=snippet_count,
    )
    job_updates: list[object] = []

    def _capture_update(job, params):
        job_updates.append(params)
        return SimpleNamespace(job_id=job, status=params.status or IngestionStatus.RUNNING)

    monkeypatch.setattr("monitor_agents.ingestion.agent.get_minio_client", lambda: fake_minio)
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_find_document_by_filename",
        lambda *_a, **_k: existing_doc,
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_find_document_by_content_hash",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(pipeline, "_create_neo4j_source", lambda **_k: source_id)
    monkeypatch.setattr(pipeline, "_create_document", lambda **_k: doc_id)
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_create_ingestion_job",
        lambda *_a, **_k: SimpleNamespace(job_id=job_id),
    )
    monkeypatch.setattr("monitor_agents.ingestion.agent.mongodb_update_document", lambda *_a, **_k: None)
    monkeypatch.setattr("monitor_agents.ingestion.agent.mongodb_update_ingestion_job", _capture_update)

    async def _no_index(**_k):
        raise AssertionError("indexer must not run when snippets already exist")

    monkeypatch.setattr(pipeline._indexer, "index", _no_index)
    return pipeline, job_id, universe_id, job_updates, existing_doc


@pytest.mark.asyncio
async def test_analysis_timeout_pauses_the_job_as_resumable(monkeypatch):
    pipeline, job_id, universe_id, updates, existing_doc = _reuse_setup(monkeypatch)

    async def _timeout(**_k):
        raise TimeoutError("analysis stage limit reached")

    monkeypatch.setattr(pipeline._analyzer, "analyze", _timeout)
    monkeypatch.setattr(agent_module, "_is_job_cancelled", AsyncMock(return_value=False))

    result = await pipeline.ingest_file(
        file_bytes=b"pdf",
        filename="book.pdf",
        source_title="Book",
        universe_id=universe_id,
        pack_name="Book",
        pack_type=KnowledgePackType.RULEBOOK,
        reuse_source_id=existing_doc.source_id,
        reuse_doc_id=existing_doc.doc_id,
        analyze_timeout_seconds=60,
    )

    statuses = [getattr(update, "status", None) for update in updates]
    assert IngestionStatus.PAUSED in statuses
    assert IngestionStatus.FAILED not in statuses
    paused = next(update for update in updates if getattr(update, "status", None) is IngestionStatus.PAUSED)
    assert any("paused" in entry.lower() for entry in (paused.warnings or []))
    assert any("resume" in entry.lower() for entry in (paused.activity_log or []))
    # No completion timestamp: the job is still open for a resume.
    assert getattr(paused, "completed_at", None) is None
    assert result.status is IngestionStatus.PAUSED


@pytest.mark.asyncio
async def test_a_cancelled_job_is_returned_without_being_marked_failed(monkeypatch):
    pipeline, _job_id, universe_id, updates, existing_doc = _reuse_setup(monkeypatch)

    async def _cancelled_mid_run(**_k):
        raise AnalysisCancelledError("job cancelled between batches")

    cancelled_job = SimpleNamespace(job_id=uuid4(), status=IngestionStatus.CANCELLED)
    monkeypatch.setattr(pipeline._analyzer, "analyze", _cancelled_mid_run)
    monkeypatch.setattr(agent_module, "_is_job_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_get_ingestion_job",
        lambda *_a, **_k: cancelled_job,
    )

    result = await pipeline.ingest_file(
        file_bytes=b"pdf",
        filename="book.pdf",
        source_title="Book",
        universe_id=universe_id,
        pack_name="Book",
        pack_type=KnowledgePackType.RULEBOOK,
        reuse_source_id=existing_doc.source_id,
        reuse_doc_id=existing_doc.doc_id,
    )

    assert result is cancelled_job
    assert all(getattr(update, "status", None) is not IngestionStatus.FAILED for update in updates)


@pytest.mark.asyncio
async def test_a_stage_boundary_cancel_never_overwrites_the_status_with_failed(monkeypatch):
    pipeline, _job_id, universe_id, updates, existing_doc = _reuse_setup(monkeypatch, snippet_count=0)
    monkeypatch.setattr(agent_module, "_is_job_cancelled", AsyncMock(return_value=True))
    doc_updates: list[object] = []
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_update_document",
        lambda *_a, **_k: doc_updates.append(_k),
    )

    with pytest.raises(RuntimeError, match="cancelled"):
        await pipeline.ingest_file(
            file_bytes=b"pdf",
            filename="book.pdf",
            source_title="Book",
            universe_id=universe_id,
            pack_name="Book",
            pack_type=KnowledgePackType.RULEBOOK,
            reuse_source_id=existing_doc.source_id,
            reuse_doc_id=existing_doc.doc_id,
        )

    assert all(getattr(update, "status", None) is not IngestionStatus.FAILED for update in updates)
    assert not any(getattr(update, "extraction_status", None) is ExtractionStatus.FAILED for update in doc_updates)


@pytest.mark.asyncio
async def test_resume_reuses_the_same_job_row_and_skips_reupload(monkeypatch):
    pipeline, job_id, universe_id, updates, existing_doc = _reuse_setup(monkeypatch)
    checklist = ["entities", "rules"]
    resumed_job = SimpleNamespace(
        job_id=job_id,
        doc_id=uuid4(),
        source_id=uuid4(),
        universe_id=universe_id,
        status=IngestionStatus.PAUSED,
        processing_checklist=checklist,
    )
    existing_doc = SimpleNamespace(
        doc_id=resumed_job.doc_id,
        source_id=resumed_job.source_id,
        extraction_status=ExtractionStatus.COMPLETED,
        minio_ref="uploads/existing.pdf",
        snippet_count=50,
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_get_ingestion_job",
        lambda *_a, **_k: resumed_job,
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_get_document",
        lambda *_a, **_k: existing_doc,
    )

    def _no_new_job(*_a, **_k):
        raise AssertionError("a resume must not create a second job row")

    monkeypatch.setattr("monitor_agents.ingestion.agent.mongodb_create_ingestion_job", _no_new_job)
    monkeypatch.setattr(agent_module, "_is_job_cancelled", AsyncMock(return_value=False))

    created: list[object] = []
    analyzed: dict = {}

    async def _fake_analyze(**kwargs):
        analyzed.update(kwargs)
        return SimpleNamespace(
            pack_id=uuid4(),
            status=IngestionStatus.COMPLETED,
            total_batches=3,
            succeeded_batches=3,
            failed_batches=0,
            retried_batches=0,
            total_attempts=3,
            current_provider=None,
            current_model=None,
            last_error=None,
            partial=False,
            failed_sections=[],
        )

    monkeypatch.setattr(pipeline._analyzer, "analyze", _fake_analyze)

    result = await pipeline.ingest_file(
        file_bytes=b"pdf",
        filename="book.pdf",
        source_title="Book",
        universe_id=universe_id,
        pack_name="Book",
        pack_type=KnowledgePackType.RULEBOOK,
        analysis_layers=checklist,
        reuse_source_id=resumed_job.source_id,
        reuse_doc_id=resumed_job.doc_id,
        resume_job_id=job_id,
        on_job_created=created.append,
    )

    # Same job row, no second creation, counters reset for the new attempt.
    assert created == [job_id]
    resets = [
        update
        for update in updates
        if getattr(update, "status", None) is IngestionStatus.RUNNING and getattr(update, "failed_sections", None) == []
    ]
    assert resets, "the resume must reset failed_sections and mark the job running"
    assert resets[0].partial is False
    # The analysis ran on the same job id with the checklist layers.
    assert analyzed["job_id"] == job_id
    assert analyzed["analysis_layers"] == checklist
    assert result is not None
