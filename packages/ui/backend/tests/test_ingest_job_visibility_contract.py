"""F2-4(a) regression tests: the ingestion-job visibility contract.

I-7 (Source Library job history) / I-12 (Delete Ingest Job list).

The REST (``/jobs``, ``/jobs/{id}``) and SSE (``/jobs/{id}/stream``)
serializers both funnel through ``_job_to_dict``.  It used to drop
``pack_id``, ``total_attempts``, ``failed_sections`` and ``universe_id``,
and it leaked the structured ``LastError`` Pydantic object into both
``last_error`` and ``error`` — which crashed the SSE ``json.dumps`` and
broke the frontend's ``last_error?: string | null`` type.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import (
    IngestionJobResponse,
    IngestionJobUpdate,
    IngestionStage,
    LastError,
    LastErrorCategory,
)

from monitor_ui.routers.ingest import stream_job
from monitor_ui.routers.ingest_shared import _job_to_dict


def _job(**overrides) -> IngestionJobResponse:
    now = datetime.now(UTC)
    base = dict(
        job_id=uuid4(),
        universe_id=uuid4(),
        source_id=uuid4(),
        doc_id=uuid4(),
        source_title="Test Source",
        status=IngestionStatus.FAILED,
        pipeline_stages=[IngestionStage.EXTRACT, IngestionStage.ANALYZE],
        started_at=now,
        created_at=now,
    )
    base.update(overrides)
    return IngestionJobResponse(**base)


class TestJobToDictVisibilityContract:
    def test_exposes_pack_id_attempts_failed_sections_and_universe_id(self):
        pack_id = uuid4()
        job = _job(
            pack_id=pack_id,
            total_attempts=17,
            failed_sections=[{"section_path": "Ch 1", "stage": "analyze", "reason": "timeout"}],
        )

        payload = _job_to_dict(job)

        assert payload["pack_id"] == str(pack_id)
        assert payload["universe_id"] == str(job.universe_id)
        assert payload["total_attempts"] == 17
        assert payload["failed_sections"] == [{"section_path": "Ch 1", "stage": "analyze", "reason": "timeout"}]

    def test_structured_last_error_serialized_as_json_object(self):
        job = _job(
            last_error=LastError(
                category=LastErrorCategory.EMBEDDING_PREFLIGHT_FAILED,
                message="embedding model 'nomic-embed-text' not found",
                detail="ollama /api/show: model missing",
            )
        )

        payload = _job_to_dict(job)

        # last_error must be a plain JSON-safe dict, not a Pydantic object.
        assert isinstance(payload["last_error"], dict)
        assert payload["last_error"]["category"] == "embedding_preflight_failed"
        assert payload["last_error"]["message"] == "embedding model 'nomic-embed-text' not found"
        assert payload["last_error"]["detail"] == "ollama /api/show: model missing"
        assert isinstance(payload["last_error"]["failed_at"], str)
        # The whole payload must survive json.dumps (the SSE serializer path).
        json.dumps(payload)

    def test_error_field_is_display_safe_string_from_last_error_message(self):
        job = _job(
            last_error=LastError(
                category=LastErrorCategory.PROVIDER_BLOCKED,
                message="provider blocked after 3 retries",
            )
        )

        payload = _job_to_dict(job)

        assert payload["error"] == "provider blocked after 3 retries"
        assert isinstance(payload["error"], str)

    def test_error_falls_back_to_errors_list_when_no_last_error(self):
        job = _job(errors=["extract stage exploded"])

        payload = _job_to_dict(job)

        assert payload["last_error"] is None
        assert payload["error"] == "extract stage exploded"

    def test_error_is_none_when_no_failure_recorded(self):
        job = _job(status=IngestionStatus.COMPLETED)

        payload = _job_to_dict(job)

        assert payload["last_error"] is None
        assert payload["error"] is None


class TestStreamJobSseSerialization:
    @pytest.mark.asyncio
    async def test_sse_payload_with_structured_last_error_does_not_crash(self, monkeypatch: pytest.MonkeyPatch):
        """The SSE generator's json.dumps(_job_to_dict(job)) must not crash on
        a structured LastError, and the emitted payload must parse back with
        last_error as an object and error as a string."""
        job = _job(
            pack_id=uuid4(),
            total_attempts=9,
            failed_sections=[{"section_path": "Ch 9", "stage": "analyze", "reason": "x"}],
            last_error=LastError(
                category=LastErrorCategory.ANALYZER_FAILED,
                message="analyzer blew up",
            ),
        )

        monkeypatch.setattr(
            "monitor_ui.routers.ingest.mongodb_get_ingestion_job",
            lambda _uid: job,
        )

        response = await stream_job(str(job.job_id))

        events = [chunk async for chunk in response.body_iterator]
        # status=failed is terminal: exactly one data event, then the stream ends.
        assert len(events) == 1
        assert events[0].startswith("data: ")
        payload = json.loads(events[0][len("data: ") :])

        assert payload["pack_id"] == str(job.pack_id)
        assert payload["total_attempts"] == 9
        assert payload["failed_sections"] == [{"section_path": "Ch 9", "stage": "analyze", "reason": "x"}]
        assert payload["last_error"]["category"] == "analyzer_failed"
        assert payload["last_error"]["message"] == "analyzer blew up"
        assert payload["error"] == "analyzer blew up"


class TestIngestionJobUpdateAcceptsVisibilityFields:
    """The update schema round-trips the fields the analyzer sends via
    ``ExecutionSummary.as_job_update()`` (splatted into IngestionJobUpdate)."""

    def test_update_schema_accepts_total_attempts_and_failed_sections(self):
        params = IngestionJobUpdate(
            total_attempts=23,
            failed_sections=[{"section_path": "Ch 2", "stage": "embed", "reason": "y"}],
        )

        assert params.total_attempts == 23
        assert params.failed_sections[0]["section_path"] == "Ch 2"
