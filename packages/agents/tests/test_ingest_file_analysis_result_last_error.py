"""Regression test: ingest_file's hand-built final_batches dict must not
smuggle a raw string into IngestionJobUpdate.last_error.

Live bug (2026-07-22): the exact same crash as
test_ingestion_job_update_last_error_collision.py, but on a SECOND live
Settlers Supplement run immediately after that first fix was merged --
proving LLMExecutionSummary.as_job_update() was not the only source.
ingest_file() builds its own final_batches dict directly from
analysis_result (an AnalysisRunResult), which also carries a plain-string
last_error field, and was re-exposing it under the same colliding key.
"""

from __future__ import annotations

from uuid import uuid4

from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import IngestionJobUpdate

from monitor_agents.analyzer._models import AnalysisRunResult


def test_ingestion_job_update_accepts_analysis_result_with_string_last_error():
    """Mirrors ingestion_pipeline.py's final_batches dict literal exactly."""
    analysis_result = AnalysisRunResult(
        pack_id=uuid4(),
        status=IngestionStatus.PARTIAL,
        total_batches=5,
        succeeded_batches=4,
        failed_batches=1,
        last_error="litellm.RateLimitError: some transient batch failure",
    )

    final_batches = {
        "total_batches": getattr(analysis_result, "total_batches", 0),
        "succeeded_batches": getattr(analysis_result, "succeeded_batches", 0),
        "failed_batches": getattr(analysis_result, "failed_batches", 0),
        "retried_batches": getattr(analysis_result, "retried_batches", 0),
        "total_attempts": getattr(analysis_result, "total_attempts", 0),
        "current_provider": getattr(analysis_result, "current_provider", None),
        "current_model": getattr(analysis_result, "current_model", None),
        "partial": bool(getattr(analysis_result, "partial", False)),
        "failed_sections": list(getattr(analysis_result, "failed_sections", []) or []),
    }

    update = IngestionJobUpdate(status=analysis_result.status, progress=1.0, **final_batches)

    assert update.status is IngestionStatus.PARTIAL
    assert update.last_error is None
