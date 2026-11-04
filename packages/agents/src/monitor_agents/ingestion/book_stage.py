"""Run book decomposition as its own background job, behind a flag (I-17).

Decomposition can take hours, so it can't run inside the 45-minute ingest job. It gets a separate
job record, which can pause and resume, and the normal pipeline is unchanged.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import structlog
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.book_graph import BookRecord, BookRecordType, BookTree
from monitor_data.schemas.ingestion_jobs import (
    DecompositionProgress,
    IngestionJobCreate,
    IngestionJobResponse,
    IngestionJobUpdate,
    IngestionStage,
    LastError,
    LastErrorCategory,
)
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_data.tools.mongodb_tools.book_decomposition import (
    mongodb_list_book_records,
    mongodb_upsert_book_records,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_ingestion_job,
    mongodb_get_ingestion_job,
    mongodb_update_ingestion_job,
)

from monitor_agents.book_decomposition.extractor import (
    DspyWindowExtractor,
    build_lm,
    prompt_fingerprint,
)
from monitor_agents.book_decomposition.knowledge_graph import DspyGraphModel, GraphModel
from monitor_agents.book_decomposition.ledger import LogBusy
from monitor_agents.book_decomposition.pacing import RunGuard
from monitor_agents.book_decomposition.review import DspyReviewModel
from monitor_agents.book_decomposition.service import (
    DecomposeResult,
    DecomposeStatus,
    decompose_book,
)

log = structlog.get_logger()

_DEFAULT_EXTRACT_MODEL = "mistral/mistral-medium-latest"
_DEFAULT_REVIEW_MODEL = "mistral/mistral-large-latest"
_DEFAULT_MAX_OUTPUT_TOKENS = 2_000_000
_REQUESTS_PER_MINUTE = 20.0
_SETTINGS_KEY = "settings"
_HEARTBEAT_SECONDS = 60.0


def _default_graph_model(model: str, guard: RunGuard) -> GraphModel:
    return DspyGraphModel(build_lm(model), guard)


def book_decomposition_enabled() -> bool:
    return os.environ.get("MONITOR_BOOK_DECOMPOSITION", "0").strip().lower() in ("1", "true", "yes")


def book_structure_enabled() -> bool:
    return os.environ.get("MONITOR_BOOK_NEO4J", "0").strip().lower() in ("1", "true", "yes")


def is_decomposition_job(job: IngestionJobResponse) -> bool:
    return IngestionStage.DECOMPOSE in job.pipeline_stages


def stored_pack_type(doc_id: UUID) -> KnowledgePackType:
    """Read the pack type chosen at upload, so a resumed run keeps it."""
    for record in mongodb_list_book_records(str(doc_id), BookRecordType.REPORT):
        if record.key == _SETTINGS_KEY:
            return KnowledgePackType(record.data["pack_type"])
    return KnowledgePackType.MISC


def create_decomposition_job(
    source_job: IngestionJobResponse, pack_type: KnowledgePackType = KnowledgePackType.MISC
) -> IngestionJobResponse:
    """Create the job that tracks decomposing a book that was just ingested."""
    mongodb_upsert_book_records(
        str(source_job.doc_id),
        BookRecordType.REPORT,
        [BookRecord(key=_SETTINGS_KEY, data={"pack_type": pack_type.value})],
    )
    job = mongodb_create_ingestion_job(
        IngestionJobCreate(
            universe_id=source_job.universe_id,
            source_id=source_job.source_id,
            doc_id=source_job.doc_id,
            source_title=f"{source_job.source_title} (decomposition)",
            pipeline_stages=[IngestionStage.DECOMPOSE],
        )
    )
    return mongodb_update_ingestion_job(
        job.job_id,
        IngestionJobUpdate(status=IngestionStatus.RUNNING, current_stage=IngestionStage.DECOMPOSE),
    )


def _is_cancelled(job_id: UUID) -> bool:
    job = mongodb_get_ingestion_job(job_id)
    return job is None or job.status in (IngestionStatus.CANCELLED, IngestionStatus.KILLED)


def _model_key(model: str) -> str:
    return re.sub(r"[^\w.-]+", "_", model)


async def run_decomposition_job(
    job_id: UUID,
    pdf_bytes: bytes,
    *,
    doc_id: UUID,
    title: str,
    pack_type: KnowledgePackType = KnowledgePackType.MISC,
    source_id: UUID | None = None,
    heartbeat_seconds: float = _HEARTBEAT_SECONDS,
    make_extractor: Callable[[str], object] | None = None,
    make_review_model: Callable[[str, RunGuard], object] | None = None,
    make_graph_model: Callable[[str, RunGuard], GraphModel] | None = None,
) -> None:
    """Run or resume a decomposition job, and record how it ended on the job."""
    guard = RunGuard(
        max_output_tokens=int(os.environ.get("MONITOR_BOOK_MAX_OUTPUT_TOKENS", _DEFAULT_MAX_OUTPUT_TOKENS)),
        requests_per_minute=_REQUESTS_PER_MINUTE,
    )
    extract_model = os.environ.get("MONITOR_BOOK_EXTRACT_MODEL", _DEFAULT_EXTRACT_MODEL)
    review_model_name = os.environ.get("MONITOR_BOOK_REVIEW_MODEL", _DEFAULT_REVIEW_MODEL)
    prefix = _model_key(extract_model)

    async def record_structure(tree: BookTree) -> None:
        # Only CanonKeeper writes to Neo4j. This is optional, so a failure can't stop the book.
        from monitor_agents.canonkeeper.agent import CanonKeeper

        try:
            await CanonKeeper(agent_id="book-structure").record_book_structure(tree, source_id)  # type: ignore[arg-type]  # reason: only used when source_id is set
        except Exception as exc:  # noqa: BLE001  # reason: optional record; the failure goes on the job and the run continues
            log.warning("book_structure_failed", job_id=str(job_id), error=str(exc)[:300])
            mongodb_update_ingestion_job(
                job_id, IngestionJobUpdate(warnings=[f"Book structure not stored: {exc}"[:300]])
            )

    def on_progress(progress: DecompositionProgress) -> None:
        if _is_cancelled(job_id):
            guard.stop("Cancelled by user")
            return
        total = progress.sentences_total or 1
        mongodb_update_ingestion_job(
            job_id,
            IngestionJobUpdate(
                decomposition=progress,
                progress=min(progress.sentences_done / total, 0.99),
            ),
        )

    heartbeat = asyncio.create_task(_keep_job_alive(job_id, heartbeat_seconds))
    try:
        mongodb_update_ingestion_job(
            job_id,
            IngestionJobUpdate(
                status=IngestionStatus.RUNNING,
                current_stage=IngestionStage.DECOMPOSE,
                activity_log=["Decomposing the book"],
            ),
        )
        extractor = make_extractor(extract_model) if make_extractor else DspyWindowExtractor(lm=build_lm(extract_model))
        review_model = (
            make_review_model(review_model_name, guard)
            if make_review_model
            else DspyReviewModel(build_lm(review_model_name), guard=guard)
        )
        result = await decompose_book(
            pdf_bytes,
            doc_id=doc_id,
            job_id=job_id,
            title=title,
            pack_type=pack_type,
            extractor=extractor,  # type: ignore[arg-type]  # reason: the factories return these protocols
            review_model=review_model,  # type: ignore[arg-type]  # reason: the factories return these protocols
            guard=guard,
            run_key=f"{prefix}-{prompt_fingerprint()}",
            accept_run=lambda key: key.startswith(f"{prefix}-"),
            check_coverage=os.environ.get("MONITOR_BOOK_COVERAGE", "0") == "1",
            on_progress=on_progress,
            on_tree=record_structure if source_id is not None and book_structure_enabled() else None,
            graph_model=(
                (make_graph_model or _default_graph_model)(review_model_name, guard)
                if os.environ.get("MONITOR_BOOK_GRAPH", "0") == "1"
                else None
            ),
        )
        _record_result(job_id, result)
    except LogBusy as exc:
        # Another worker owns this book, and its job status belongs to that worker.
        log.warning("book_decomposition_busy", job_id=str(job_id), error=str(exc))
    except Exception as exc:
        log.exception("book_decomposition_failed", job_id=str(job_id))
        if not _is_cancelled(job_id):
            mongodb_update_ingestion_job(
                job_id,
                IngestionJobUpdate(
                    status=IngestionStatus.FAILED,
                    errors=[f"{type(exc).__name__}: {exc}"[:500]],
                    last_error=LastError(
                        category=LastErrorCategory.UNKNOWN,
                        message=f"{type(exc).__name__}: {exc}"[:500],
                        failed_at=datetime.now(UTC),
                    ),
                    completed_at=datetime.now(UTC),
                ),
            )
    finally:
        heartbeat.cancel()


async def _keep_job_alive(job_id: UUID, seconds: float) -> None:
    """Tell the stale-job watchdog this worker is alive, during long stretches like review.

    If the process dies, this stops, the watchdog fails the job, and it can then be resumed.
    """
    while True:
        await asyncio.sleep(seconds)
        try:
            await asyncio.to_thread(mongodb_update_ingestion_job, job_id, IngestionJobUpdate())
        except Exception as exc:  # noqa: BLE001  # reason: the next beat retries; a missed beat can't harm the run
            log.warning("book_heartbeat_failed", job_id=str(job_id), error=str(exc)[:200])


def _record_result(job_id: UUID, result: DecomposeResult) -> None:
    if _is_cancelled(job_id):
        return
    if result.status == DecomposeStatus.PAUSED:
        mongodb_update_ingestion_job(
            job_id,
            IngestionJobUpdate(
                status=IngestionStatus.PAUSED,
                decomposition=result.progress,
                activity_log=[f"Paused: {result.progress.pause_reason}"],
            ),
        )
        return
    quarantined = result.status == DecomposeStatus.COMPLETE_WITH_QUARANTINE
    mongodb_update_ingestion_job(
        job_id,
        IngestionJobUpdate(
            status=IngestionStatus.PARTIAL if quarantined else IngestionStatus.COMPLETED,
            partial=quarantined,
            progress=1.0,
            stages_completed=[IngestionStage.DECOMPOSE],
            decomposition=result.progress,
            pack_id=result.pack_id,
            completed_at=datetime.now(UTC),
            activity_log=[
                f"Decomposition finished: {result.progress.claims_kept} claims kept, "
                f"{result.progress.sentences_quarantined} sentences need a person"
            ],
        ),
    )
