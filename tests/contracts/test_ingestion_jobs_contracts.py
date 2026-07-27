"""Contract tests for the IngestionJob schemas.

Verifies that ingestion_jobs Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce numeric / length / pattern constraints,
- reject invalid enum values where applicable.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import (
    IngestionJobCreate,
    IngestionJobFilter,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionJobUpdate,
    IngestionStage,
    LastError,
    LastErrorCategory,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# =============================================================================
# IngestionStage
# =============================================================================


class TestIngestionStage:
    def test_all_stages(self):
        assert IngestionStage.UPLOAD.value == "upload"
        assert IngestionStage.EXTRACT.value == "extract"
        assert IngestionStage.EMBED.value == "embed"
        assert IngestionStage.ANALYZE.value == "analyze"
        assert IngestionStage.PROPOSE.value == "propose"
        assert IngestionStage.CANONIZE.value == "canonize"
        assert IngestionStage.INDEX.value == "index"

    def test_iteration(self):
        stages = list(IngestionStage)
        assert len(stages) == 7


# =============================================================================
# IngestionJobCreate
# =============================================================================


class TestIngestionJobCreate:
    def test_minimal(self):
        j = IngestionJobCreate(
            universe_id=uuid4(),
            source_id=uuid4(),
            doc_id=uuid4(),
        )
        assert j.universe_id is not None
        assert j.source_id is not None
        assert j.doc_id is not None
        assert j.source_title == ""
        assert j.job_id is None
        # default pipeline stages is the full ordered list
        assert len(j.pipeline_stages) == 7
        assert j.pipeline_stages[0] == IngestionStage.UPLOAD
        assert j.processing_checklist == []

    def test_explicit_job_id(self):
        jid = uuid4()
        j = IngestionJobCreate(
            universe_id=uuid4(),
            source_id=uuid4(),
            doc_id=uuid4(),
            job_id=jid,
        )
        assert j.job_id == jid

    def test_with_title(self):
        j = IngestionJobCreate(
            universe_id=uuid4(),
            source_id=uuid4(),
            doc_id=uuid4(),
            source_title="Pathfinder 2e Core Rulebook",
        )
        assert j.source_title == "Pathfinder 2e Core Rulebook"

    def test_custom_pipeline_stages(self):
        stages = [IngestionStage.UPLOAD, IngestionStage.EXTRACT, IngestionStage.EMBED]
        j = IngestionJobCreate(
            universe_id=uuid4(),
            source_id=uuid4(),
            doc_id=uuid4(),
            pipeline_stages=stages,
        )
        assert j.pipeline_stages == stages

    def test_with_checklist(self):
        j = IngestionJobCreate(
            universe_id=uuid4(),
            source_id=uuid4(),
            doc_id=uuid4(),
            processing_checklist=["entities", "axioms", "game_system"],
        )
        assert len(j.processing_checklist) == 3

    def test_required_universe_id(self):
        with pytest.raises(ValidationError):
            IngestionJobCreate(source_id=uuid4(), doc_id=uuid4())  # type: ignore[call-arg]

    def test_required_source_id(self):
        with pytest.raises(ValidationError):
            IngestionJobCreate(universe_id=uuid4(), doc_id=uuid4())  # type: ignore[call-arg]

    def test_required_doc_id(self):
        with pytest.raises(ValidationError):
            IngestionJobCreate(universe_id=uuid4(), source_id=uuid4())  # type: ignore[call-arg]

    def test_invalid_stage_rejected(self):
        with pytest.raises(ValidationError):
            IngestionJobCreate(
                universe_id=uuid4(),
                source_id=uuid4(),
                doc_id=uuid4(),
                pipeline_stages=["bogus"],  # type: ignore[list-item]
            )


# =============================================================================
# IngestionJobUpdate
# =============================================================================


class TestIngestionJobUpdate:
    def test_empty(self):
        u = IngestionJobUpdate()
        assert u.status is None
        assert u.current_stage is None
        assert u.progress is None
        assert u.stages_completed is None

    def test_progress_bounds(self):
        with pytest.raises(ValidationError):
            IngestionJobUpdate(progress=-0.01)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(progress=1.01)

    def test_progress_mid(self):
        u = IngestionJobUpdate(progress=0.5)
        assert u.progress == 0.5

    def test_progress_zero(self):
        u = IngestionJobUpdate(progress=0.0)
        assert u.progress == 0.0

    def test_progress_one(self):
        u = IngestionJobUpdate(progress=1.0)
        assert u.progress == 1.0

    def test_negative_counters_rejected(self):
        with pytest.raises(ValidationError):
            IngestionJobUpdate(snippet_count=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(entities_extracted=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(axioms_extracted=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(proposals_generated=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(proposals_accepted=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(proposals_rejected=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(total_batches=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(succeeded_batches=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(failed_batches=-1)
        with pytest.raises(ValidationError):
            IngestionJobUpdate(retried_batches=-1)

    def test_status_enum(self):
        u = IngestionJobUpdate(status=IngestionStatus.RUNNING)
        assert u.status == IngestionStatus.RUNNING

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            IngestionJobUpdate(status="bogus")  # type: ignore[arg-type]

    def test_with_completion(self):
        ts = datetime.now(UTC)
        error = LastError(category=LastErrorCategory.TIMEOUT, message="timeout")
        u = IngestionJobUpdate(completed_at=ts, next_retry_at=ts, last_error=error)
        assert u.completed_at == ts
        assert u.last_error == error


# =============================================================================
# IngestionJobResponse
# =============================================================================


class TestIngestionJobResponse:
    def _kwargs(self, **overrides):
        base = {
            "job_id": uuid4(),
            "universe_id": uuid4(),
            "source_id": uuid4(),
            "doc_id": uuid4(),
            "status": IngestionStatus.RUNNING,
            "pipeline_stages": list(IngestionStage),
            "started_at": datetime.now(UTC),
            "created_at": datetime.now(UTC),
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        r = IngestionJobResponse(**self._kwargs())
        assert r.source_title == ""
        assert r.current_stage is None
        assert r.stages_completed == []
        assert r.progress == 0.0
        assert r.snippet_count == 0
        assert r.entities_extracted == 0
        assert r.axioms_extracted == 0
        assert r.game_system_found is False
        assert r.world_template_found is False
        assert r.proposals_generated == 0
        assert r.proposals_accepted == 0
        assert r.proposals_rejected == 0
        assert r.total_batches == 0
        assert r.succeeded_batches == 0
        assert r.failed_batches == 0
        assert r.retried_batches == 0
        assert r.partial is False
        assert r.errors == []
        assert r.warnings == []
        assert r.activity_log == []
        assert r.processing_checklist == []
        assert r.completed_at is None
        assert r.duration_seconds is None
        assert r.pack_id is None

    def test_full(self):
        ts = datetime.now(UTC)
        r = IngestionJobResponse(
            **self._kwargs(
                source_title="PF2e Core",
                status=IngestionStatus.COMPLETED,
                current_stage=IngestionStage.INDEX,
                progress=1.0,
                snippet_count=2847,
                entities_extracted=412,
                axioms_extracted=89,
                game_system_found=True,
                world_template_found=True,
                proposals_generated=501,
                proposals_accepted=412,
                proposals_rejected=89,
                total_batches=10,
                succeeded_batches=10,
                failed_batches=0,
                retried_batches=0,
                partial=False,
                completed_at=ts,
                duration_seconds=123.4,
            )
        )
        assert r.snippet_count == 2847
        assert r.entities_extracted == 412
        assert r.game_system_found is True
        assert r.completed_at == ts
        assert r.duration_seconds == 123.4

    def test_required_job_id(self):
        with pytest.raises(ValidationError):
            IngestionJobResponse(
                universe_id=uuid4(),
                source_id=uuid4(),
                doc_id=uuid4(),
                status=IngestionStatus.PENDING,
                pipeline_stages=[],
                started_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )


# =============================================================================
# IngestionJobFilter
# =============================================================================


class TestIngestionJobFilter:
    def test_defaults(self):
        f = IngestionJobFilter()
        assert f.universe_id is None
        assert f.source_id is None
        assert f.status is None
        assert f.limit == 50
        assert f.offset == 0
        assert f.sort_order == "desc"

    def test_with_filters(self):
        f = IngestionJobFilter(
            universe_id=uuid4(),
            status=IngestionStatus.COMPLETED,
            limit=100,
            sort_order="asc",
        )
        assert f.status == IngestionStatus.COMPLETED
        assert f.sort_order == "asc"

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            IngestionJobFilter(limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            IngestionJobFilter(limit=201)

    def test_offset_min(self):
        with pytest.raises(ValidationError):
            IngestionJobFilter(offset=-1)

    def test_invalid_sort_order(self):
        with pytest.raises(ValidationError):
            IngestionJobFilter(sort_order="bogus")


# =============================================================================
# IngestionJobListResponse
# =============================================================================


class TestIngestionJobListResponse:
    def test_empty(self):
        r = IngestionJobListResponse(jobs=[], total=0, limit=50, offset=0)
        assert r.jobs == []
        assert r.total == 0

    def test_with_job(self):
        job = IngestionJobResponse(
            job_id=uuid4(),
            universe_id=uuid4(),
            source_id=uuid4(),
            doc_id=uuid4(),
            status=IngestionStatus.PENDING,
            pipeline_stages=[],
            started_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        r = IngestionJobListResponse(jobs=[job], total=1, limit=50, offset=0)
        assert len(r.jobs) == 1
        assert r.total == 1
