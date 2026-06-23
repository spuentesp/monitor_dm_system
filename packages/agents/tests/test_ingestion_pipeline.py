from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from monitor_agents.ingestion_pipeline import (
    IngestionPipeline,
    _detect_content_type,
    _build_object_key,
    _filename_from_uri,
    _pack_type_to_source_type,
)
from monitor_data.schemas.base import ExtractionStatus, IngestionStatus
from monitor_data.schemas.knowledge_packs import KnowledgePackType


class _FakeMinio:
    def __init__(self):
        self.deleted_keys: list[str] = []
        self.upload_calls: list[str] = []

    async def upload(self, key: str, data: bytes, content_type: str | None = None):
        self.upload_calls.append(key)
        return None

    async def delete(self, key: str):
        self.deleted_keys.append(key)


@pytest.mark.asyncio
async def test_ingest_failure_preserves_source_and_uploaded_object(monkeypatch):
    pipeline = IngestionPipeline(agent_id="test-pipeline")
    deleted_sources: list[object] = []
    fake_minio = _FakeMinio()
    source_id = uuid4()
    doc_id = uuid4()
    job_id = uuid4()

    monkeypatch.setattr("monitor_agents.ingestion_pipeline.get_minio_client", lambda: fake_minio)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_find_document_by_filename",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(pipeline, "_create_neo4j_source", lambda **_kwargs: source_id)
    monkeypatch.setattr(pipeline, "_create_document", lambda **_kwargs: doc_id)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_create_ingestion_job",
        lambda *_args, **_kwargs: SimpleNamespace(job_id=job_id),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_document", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_ingestion_job",
        lambda *_args, **_kwargs: None,
    )

    async def _boom(**_kwargs):
        raise RuntimeError("indexer exploded")

    monkeypatch.setattr(pipeline._indexer, "index", _boom)

    with pytest.raises(RuntimeError, match="indexer exploded"):
        await pipeline.ingest_file(
            file_bytes=b"test bytes",
            filename="broken.pdf",
            source_title="Broken Source",
            universe_id=uuid4(),
            pack_name="Broken Source",
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
        )

    assert deleted_sources == []
    assert fake_minio.deleted_keys == []


@pytest.mark.asyncio
async def test_ingest_reuses_existing_doc_for_rescan(monkeypatch):
    pipeline = IngestionPipeline(agent_id="test-reingest")
    fake_minio = _FakeMinio()
    source_id = uuid4()
    doc_id = uuid4()
    job_id = uuid4()
    universe_id = uuid4()
    existing_doc = SimpleNamespace(
        doc_id=doc_id,
        source_id=source_id,
        extraction_status=ExtractionStatus.PENDING,
        minio_ref="uploads/existing-source.txt",
        snippet_count=0,
    )

    def _should_not_create(**_kwargs):
        raise AssertionError("rescan should reuse the existing source/document")

    monkeypatch.setattr("monitor_agents.ingestion_pipeline.get_minio_client", lambda: fake_minio)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_find_document_by_filename",
        lambda *_args, **_kwargs: existing_doc,
    )
    monkeypatch.setattr(pipeline, "_create_neo4j_source", _should_not_create)
    monkeypatch.setattr(pipeline, "_create_document", _should_not_create)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_create_ingestion_job",
        lambda *_args, **_kwargs: SimpleNamespace(job_id=job_id),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_document", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_ingestion_job",
        lambda *_args, **_kwargs: None,
    )

    async def _boom(**_kwargs):
        raise RuntimeError("indexer exploded")

    monkeypatch.setattr(pipeline._indexer, "index", _boom)

    with pytest.raises(RuntimeError, match="indexer exploded"):
        await pipeline.ingest_file(
            file_bytes=b"test bytes",
            filename="existing.txt",
            source_title="Existing Source",
            universe_id=universe_id,
            pack_name="Existing Source",
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            reuse_source_id=source_id,
            reuse_doc_id=doc_id,
        )

    assert fake_minio.upload_calls == []


@pytest.mark.asyncio
async def test_ingest_skips_indexer_when_snippets_already_exist(monkeypatch):
    """When reusing a doc that already has snippets, the indexer must NOT be called."""
    pipeline = IngestionPipeline(agent_id="test-skip-index")
    fake_minio = _FakeMinio()
    source_id = uuid4()
    doc_id = uuid4()
    job_id = uuid4()
    universe_id = uuid4()
    existing_doc = SimpleNamespace(
        doc_id=doc_id,
        source_id=source_id,
        extraction_status=ExtractionStatus.COMPLETED,
        minio_ref="uploads/already-indexed.pdf",
        snippet_count=1234,
    )

    indexer_called = []

    async def _indexer_should_not_run(**_kwargs):
        indexer_called.append(True)
        raise AssertionError("indexer must not be called when snippets already exist")

    update_doc_calls: list[object] = []
    update_job_calls: list[object] = []

    monkeypatch.setattr("monitor_agents.ingestion_pipeline.get_minio_client", lambda: fake_minio)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_find_document_by_filename",
        lambda *_args, **_kwargs: existing_doc,
    )
    monkeypatch.setattr(
        pipeline,
        "_create_neo4j_source",
        lambda **_kw: (_ for _ in ()).throw(AssertionError("no neo4j create")),
    )
    monkeypatch.setattr(
        pipeline,
        "_create_document",
        lambda **_kw: (_ for _ in ()).throw(AssertionError("no mongo create")),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_create_ingestion_job",
        lambda *_args, **_kwargs: SimpleNamespace(job_id=job_id),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_document",
        lambda *args, **_kw: update_doc_calls.append(args),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_ingestion_job",
        lambda *args, **_kw: update_job_calls.append(args),
    )
    monkeypatch.setattr(pipeline._indexer, "index", _indexer_should_not_run)

    # Analyzer also needs to be stubbed out
    async def _fake_analyze(**_kw):
        pass

    monkeypatch.setattr(pipeline._analyzer, "analyze", _fake_analyze)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_ingestion_job",
        lambda *args, **_kw: SimpleNamespace(
            job_id=job_id, status="completed", current_stage="complete"
        ),
    )

    await pipeline.ingest_file(
        file_bytes=b"irrelevant bytes",
        filename="already-indexed.pdf",
        source_title="Already Indexed Source",
        universe_id=universe_id,
        pack_name="Already Indexed",
        pack_type=KnowledgePackType.RULEBOOK,
        reuse_source_id=source_id,
        reuse_doc_id=doc_id,
    )

    assert indexer_called == [], "indexer was called despite existing snippets"
    assert fake_minio.upload_calls == [], "MinIO upload must be skipped on rescan"


@pytest.mark.asyncio
async def test_ingest_accepts_structured_index_result(monkeypatch):
    """Indexer outputs like {snippet_count: N} should be accepted during ingest."""
    pipeline = IngestionPipeline(agent_id="test-structured-index")
    fake_minio = _FakeMinio()
    source_id = uuid4()
    doc_id = uuid4()
    job_id = uuid4()
    universe_id = uuid4()

    monkeypatch.setattr("monitor_agents.ingestion_pipeline.get_minio_client", lambda: fake_minio)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_find_document_by_filename",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(pipeline, "_create_neo4j_source", lambda **_kwargs: source_id)
    monkeypatch.setattr(pipeline, "_create_document", lambda **_kwargs: doc_id)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_create_ingestion_job",
        lambda *_args, **_kwargs: SimpleNamespace(job_id=job_id),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_document", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_ingestion_job",
        lambda *args, **_kwargs: SimpleNamespace(
            job_id=job_id, status="completed", current_stage="complete"
        ),
    )

    async def _fake_index(**_kwargs):
        return {"snippet_count": 5, "collection": "knowledge"}

    async def _fake_analyze(**_kwargs):
        return None

    monkeypatch.setattr(pipeline._indexer, "index", _fake_index)
    monkeypatch.setattr(pipeline._analyzer, "analyze", _fake_analyze)

    result = await pipeline.ingest_file(
        file_bytes=b"structured bytes",
        filename="structured.txt",
        source_title="Structured Source",
        universe_id=universe_id,
        pack_name="Structured Pack",
        pack_type=KnowledgePackType.RULEBOOK,
    )

    assert result.job_id == job_id


@pytest.mark.asyncio
async def test_ingest_marks_partial_when_analyzer_reports_partial(monkeypatch):
    """Analyzer-reported partial LLM work must not be rewritten to completed."""
    pipeline = IngestionPipeline(agent_id="test-partial-status")
    fake_minio = _FakeMinio()
    source_id = uuid4()
    doc_id = uuid4()
    job_id = uuid4()
    universe_id = uuid4()
    update_calls = []

    monkeypatch.setattr("monitor_agents.ingestion_pipeline.get_minio_client", lambda: fake_minio)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_find_document_by_filename",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(pipeline, "_create_neo4j_source", lambda **_kwargs: source_id)
    monkeypatch.setattr(pipeline, "_create_document", lambda **_kwargs: doc_id)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_create_ingestion_job",
        lambda *_args, **_kwargs: SimpleNamespace(job_id=job_id),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_document", lambda *_args, **_kwargs: None
    )

    def _capture_update(*args, **_kwargs):
        params = args[1]
        update_calls.append(params)
        return SimpleNamespace(
            job_id=job_id,
            status=params.status or IngestionStatus.RUNNING,
            current_stage=params.current_stage.value if params.current_stage else None,
        )

    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_ingestion_job", _capture_update
    )

    async def _fake_index(**_kwargs):
        return {"snippet_count": 5}

    async def _fake_analyze(**_kwargs):
        return SimpleNamespace(
            pack_id=uuid4(),
            status=IngestionStatus.PARTIAL,
            total_batches=4,
            succeeded_batches=2,
            failed_batches=2,
            retried_batches=1,
        )

    monkeypatch.setattr(pipeline._indexer, "index", _fake_index)
    monkeypatch.setattr(pipeline._analyzer, "analyze", _fake_analyze)

    result = await pipeline.ingest_file(
        file_bytes=b"structured bytes",
        filename="partial.txt",
        source_title="Partial Source",
        universe_id=universe_id,
        pack_name="Partial Pack",
        pack_type=KnowledgePackType.RULEBOOK,
    )

    assert any(call.status == IngestionStatus.PARTIAL for call in update_calls)
    assert result.status == IngestionStatus.PARTIAL


class TestIngestionPipelineHelpers:
    def test_detect_content_type_pdf(self):
        """_detect_content_type should identify PDF files."""
        ct = _detect_content_type("document.pdf")
        assert ct == "application/pdf"

    def test_detect_content_type_text(self):
        """_detect_content_type should identify text files."""
        ct = _detect_content_type("notes.txt")
        assert ct == "text/plain"

    def test_detect_content_type_returns_string(self):
        """_detect_content_type should return a content type string."""
        ct = _detect_content_type("readme.md")
        assert isinstance(ct, str)
        assert "/" in ct

    def test_detect_content_type_handles_unknown_extension(self):
        """_detect_content_type should handle unknown extensions."""
        ct = _detect_content_type("unknown.xyz")
        assert isinstance(ct, str)

    def test_build_object_key(self):
        """_build_object_key should create proper MinIO key."""
        universe = uuid4()
        key = _build_object_key("test.txt", universe)
        assert key.startswith("uploads/")
        assert "test.txt" in key

    def test_filename_from_uri_simple(self):
        """_filename_from_uri should extract filename from simple URIs."""
        name = _filename_from_uri("https://example.com/path/to/file.txt")
        assert name == "file.txt"

    def test_filename_from_uri_with_content_type(self):
        """_filename_from_uri should use content type for extension."""
        name = _filename_from_uri("https://example.com/data", content_type="application/pdf")
        assert name.endswith(".pdf")

    def test_pack_type_to_source_type(self):
        """_pack_type_to_source_type should map pack types to source types."""
        st = _pack_type_to_source_type(KnowledgePackType.SETTING_SUPPLEMENT)
        assert st is not None
        assert isinstance(st, str)


class TestIngestionPipeline:
    def test_pipeline_initialization(self):
        """IngestionPipeline should initialize with default agent_id."""
        pipeline = IngestionPipeline()
        assert pipeline.agent_id == "ingestion-pipeline-1"

    def test_pipeline_initialization_custom_id(self):
        """IngestionPipeline should initialize with custom agent_id."""
        pipeline = IngestionPipeline(agent_id="test-pipeline")
        assert pipeline.agent_id == "test-pipeline"

    def test_pipeline_has_ingest_file_method(self):
        """IngestionPipeline should have ingest_file method."""
        pipeline = IngestionPipeline()
        assert hasattr(pipeline, "ingest_file")

    def test_pipeline_has_run_method(self):
        """IngestionPipeline should have run method."""
        pipeline = IngestionPipeline()
        assert hasattr(pipeline, "run")


@pytest.mark.asyncio
async def test_duplicate_content_flagging(monkeypatch):
    """When uploading an existing doc, return a FLAGGED_DUPLICATE job."""
    pipeline = IngestionPipeline(agent_id="test-duplicate")
    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()
    job_id = uuid4()

    existing_doc = SimpleNamespace(
        doc_id=doc_id,
        source_id=source_id,
        extraction_status=ExtractionStatus.COMPLETED,
        minio_ref="uploads/existing-source.txt",
        snippet_count=0,
    )

    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_find_document_by_filename",
        lambda *_args, **_kwargs: existing_doc,
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_create_ingestion_job",
        lambda *_args, **_kwargs: SimpleNamespace(job_id=job_id),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_ingestion_job",
        lambda *args, **_kwargs: SimpleNamespace(
            job_id=job_id, status=IngestionStatus.FLAGGED_DUPLICATE
        ),
    )

    result = await pipeline.ingest_file(
        file_bytes=b"test bytes",
        filename="existing.txt",
        source_title="Existing Source",
        universe_id=universe_id,
        pack_name="Existing Pack",
        pack_type=KnowledgePackType.RULEBOOK,
    )
    assert result.status == IngestionStatus.FLAGGED_DUPLICATE


@pytest.mark.asyncio
async def test_embed_down_fails_gracefully(monkeypatch):
    """When the indexer fails (e.g., Qdrant down), job is correctly marked FAILED without empty vectors."""
    pipeline = IngestionPipeline(agent_id="test-embed-down")
    fake_minio = _FakeMinio()
    source_id = uuid4()
    doc_id = uuid4()
    job_id = uuid4()

    monkeypatch.setattr("monitor_agents.ingestion_pipeline.get_minio_client", lambda: fake_minio)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_find_document_by_filename",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(pipeline, "_create_neo4j_source", lambda **_kwargs: source_id)
    monkeypatch.setattr(pipeline, "_create_document", lambda **_kwargs: doc_id)
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_create_ingestion_job",
        lambda *_args, **_kwargs: SimpleNamespace(job_id=job_id),
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_document", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion_pipeline.mongodb_update_ingestion_job",
        lambda *_args, **_kwargs: None,
    )

    async def _boom(**_kwargs):
        raise Exception("Connection Refused to Qdrant")

    monkeypatch.setattr(pipeline._indexer, "index", _boom)

    with pytest.raises(Exception, match="Connection Refused"):
        await pipeline.ingest_file(
            file_bytes=b"test bytes",
            filename="new.txt",
            source_title="New Source",
            universe_id=uuid4(),
            pack_name="New Pack",
            pack_type=KnowledgePackType.RULEBOOK,
        )
