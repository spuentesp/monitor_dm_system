"""Ingestion job health endpoints.

The ``/jobs/health`` endpoint answers the operator question "is anything
stuck?" without having to read ingestion logs or query
``qdrant_count`` / ``ss`` separately. Returns:

- ``watchdog``:  result of the last watchdog tick (counts)
- ``current`` :  counts of jobs by status right now
- ``stale``   :  list of currently-stale running job ids (read-only;
                  the watchdog itself fails them on its own clock)

This is solid read-only — no mutation, no operator-action affordance.
Cancellation is in the existing ``/jobs/{job_id}/cancel`` route.
"""

from __future__ import annotations

from typing import Any
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from monitor_data.schemas.ingestion_jobs import IngestionStatus    # type: ignore
from pydantic import BaseModel

router = APIRouter(prefix="/jobs", tags=["ingestion-jobs"])


class WatchdogHealth(BaseModel):
    enabled: bool
    is_running: bool
    last_scanned: int = 0
    last_failed: int = 0
    last_skipped: int = 0


class StatusCounts(BaseModel):
    pending: int = 0
    running: int = 0
    failed: int = 0
    completed: int = 0
    partial: int = 0
    flagged_duplicate: int = 0
    blocked_provider: int = 0


class StaleJobRef(BaseModel):
    job_id: str
    source_title: str
    last_progress_at: datetime | None = None
    stale_for_min: float


class JobsHealthResponse(BaseModel):
    watchdog: WatchdogHealth
    counts: StatusCounts
    stale: list[StaleJobRef]
    generated_at: datetime


def _get_jobs_collection_dep() -> Any:  # pragma: no cover - app-level wiring    # type: ignore
    """Returns the MongoDB ingestion_jobs collection. The dep is bound
    at startup so this module stays agnostic to DB clients."""
    from monitor_ui.main import get_jobs_collection

    return get_jobs_collection()    # type: ignore


def _stale_threshold_seconds() -> float:
    import os

    return float(os.environ.get("MONITOR_INGEST_STALE_AFTER_SECONDS", str(45 * 60)))


def _watchdog_enabled() -> bool:
    import os

    return os.environ.get("MONITOR_INGEST_WATCHDOG_ENABLED", "0").lower() in (
        "true",
        "1",
        "yes",
    )


@router.get("/health", response_model=JobsHealthResponse)
async def get_jobs_health(coll=Depends(_get_jobs_collection_dep)) -> JobsHealthResponse:    # type: ignore
    """Snapshot the ingest job registry — counts + stale jobs.

    ``/jobs/health`` is the single endpoint an operator needs to see
    "what is happening" without reading log streams.
    """
    counts = StatusCounts()
    for status_value in IngestionStatus.__members__.values():
        n = coll.count_documents({"status": status_value.value})
        match status_value.value:
            case IngestionStatus.PENDING.value:
                counts.pending = n
            case IngestionStatus.RUNNING.value:
                counts.running = n
            case IngestionStatus.FAILED.value:
                counts.failed = n
            case IngestionStatus.COMPLETED.value:
                counts.completed = n
            case IngestionStatus.PARTIAL.value:
                counts.partial = n
            case IngestionStatus.FLAGGED_DUPLICATE.value:
                counts.flagged_duplicate = n
            case IngestionStatus.BLOCKED_PROVIDER.value:
                counts.blocked_provider = n

    # Find currently-stale running jobs (read-only; the watchdog will
    # flip them on its own clock).
    cutoff = datetime.now(UTC) - timedelta(seconds=_stale_threshold_seconds())
    stale: list[StaleJobRef] = []
    cursor = coll.find({"status": IngestionStatus.RUNNING.value})
    for doc in cursor:
        last_progress = doc.get("stage_last_progress_at") or doc.get("started_at")
        if last_progress is None:
            continue
        if last_progress.tzinfo is None:
            last_progress = last_progress.replace(tzinfo=UTC)
        if last_progress < cutoff:
            stale_for = (datetime.now(UTC) - last_progress).total_seconds() / 60.0
            stale.append(
                StaleJobRef(
                    job_id=str(doc.get("job_id") or doc.get("_id")),
                    source_title=doc.get("source_title", ""),
                    last_progress_at=last_progress,
                    stale_for_min=round(stale_for, 1),
                )
            )

    # Last watchdog tick summary (if the watchdog is wired).
    from monitor_ui.watchdog import get_watchdog

    wd = get_watchdog()
    wh = WatchdogHealth(
        enabled=_watchdog_enabled(),
        is_running=wd.is_running() if wd else False,
        last_scanned=wd.last_result().scanned if wd else 0,
        last_failed=wd.last_result().failed if wd else 0,
        last_skipped=wd.last_result().skipped if wd else 0,
    )

    return JobsHealthResponse(
        watchdog=wh,
        counts=counts,
        stale=sorted(stale, key=lambda s: s.stale_for_min, reverse=True),
        generated_at=datetime.now(UTC),
    )


__all__ = ["router"]
