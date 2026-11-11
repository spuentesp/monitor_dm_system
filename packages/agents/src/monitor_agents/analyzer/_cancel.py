"""Stop the Analyzer promptly when the job it works for is cancelled (I-17).

The cancel endpoint marks the job cancelled in MongoDB, but a run that never
looked kept calling the model for over an hour and held the single ingest
worker. Every model call the Analyzer makes goes through ``_call_module``,
which asks this module first; once the job is cancelled the run raises
``AnalysisCancelledError`` and no further model call is made.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from monitor_data.schemas.base import IngestionStatus
from monitor_data.tools.mongodb_tools import mongodb_get_ingestion_job

log = structlog.get_logger()

# Statuses an operator or the watchdog can leave a job in. Once any of them is
# visible, the Analyzer must not start another model call. Same set the
# ingestion pipeline checks between stages (``ingestion.agent._is_job_cancelled``).
CANCELLED_STATUSES: frozenset[IngestionStatus] = frozenset(
    {
        IngestionStatus.FAILED,
        IngestionStatus.CANCELLED,
        IngestionStatus.KILLED,
        IngestionStatus.FAILED_NON_RETRYABLE,
        IngestionStatus.BLOCKED_PROVIDER,
    }
)


class AnalysisCancelledError(BaseException):
    """Raised between batches when the job was cancelled; never retried.

    Inherits from ``BaseException`` on purpose — the same reason
    ``asyncio.CancelledError`` does: dozens of existing ``except Exception``
    handlers around individual model calls must not swallow the stop signal
    and keep the run alive. It is caught explicitly where it should end the
    run (``ingest_file``), and it is not a ``KeyboardInterrupt``-style
    operator event: it never escapes to the top of a pipeline unnoticed
    because ``ingest_file`` handles it.
    """


async def job_is_cancelled(job_id: UUID | None) -> bool:
    """True when the job record says the operator stopped this run."""
    if job_id is None:
        return False
    try:
        job = await asyncio.to_thread(mongodb_get_ingestion_job, job_id)
    except Exception as exc:  # noqa: BLE001  # reason: a failed check must not kill a running analysis
        log.warning("analyzer_cancel_check_failed", job_id=str(job_id), error=str(exc)[:200])
        return False
    if job is None:
        return False
    if job.status in CANCELLED_STATUSES:
        log.info("analyzer_job_cancelled", job_id=str(job_id), status=job.status.value)
        return True
    return False
