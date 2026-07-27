"""Regression test: IngestionJobUpdate(**summary.as_job_update()) must never
raise, even when a batch failure set LLMExecutionSummary.last_error.

Live bug (2026-07-22): the real `monitor ingest file` CLI command crashed at
progress=0.95 (canonize stage, right at the finish line) with
pydantic_core.ValidationError: IngestionJobUpdate.last_error expects a
LastError model, but LLMExecutionSummary.as_job_update() was splatting a
bare string under that same key. Not scenario-specific -- this hits any real
ingestion where at least one LLM batch retries during analysis.
"""

from __future__ import annotations

from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import IngestionJobUpdate

from monitor_agents.analyzer._models import LLMExecutionSummary


def test_as_job_update_omits_last_error_key():
    summary = LLMExecutionSummary(total_batches=3, failed_batches=1, last_error="boom")
    update = summary.as_job_update()
    assert "last_error" not in update


def test_ingestion_job_update_accepts_summary_with_string_last_error():
    """The exact crash reproduction: a batch failed, summary.last_error is a
    non-empty string, and the result gets splatted into IngestionJobUpdate
    exactly as ingestion_pipeline.py's final success-path update does.
    """
    summary = LLMExecutionSummary(
        total_batches=5,
        succeeded_batches=4,
        failed_batches=1,
        last_error="litellm.RateLimitError: some transient batch failure",
    )

    update = IngestionJobUpdate(status=summary.final_status(), progress=1.0, **summary.as_job_update())

    assert update.status is IngestionStatus.PARTIAL
    assert update.last_error is None
