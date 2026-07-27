"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import (
    IngestionJobCreate,
    IngestionJobFilter,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionJobUpdate,
    IngestionStage,
    LastError,
)

# =============================================================================
# INGESTION JOB TOOLS
# =============================================================================


def _hydrate_last_error(raw: Any) -> LastError | None:
    """Re-hydrate a ``last_error`` field from Mongo into a typed
    :class:`LastError`.

    The DB stores the structured dict written by
    ``mongodb_update_ingestion_job``. There is no legacy support for
    older string rows — if a row carries a string-shaped ``last_error``
    from a pre-2026-07-22 row, this raises explicitly so the migration
    is forced rather than hidden."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return LastError(**raw)
    raise ValueError(
        f"ingestion_jobs.last_error must be a structured dict or null, "
        f"got {type(raw).__name__}: {raw!r}. Existing rows must be migrated."
    )


def _convert_ingestion_job_doc(doc: dict[str, Any]) -> IngestionJobResponse:
    """Convert MongoDB ingestion job document to response schema."""
    return IngestionJobResponse(
        job_id=UUID(doc["job_id"]),
        universe_id=UUID(doc["universe_id"]),
        source_id=UUID(doc["source_id"]),
        doc_id=UUID(doc["doc_id"]),
        source_title=doc.get("source_title", ""),
        status=IngestionStatus(doc["status"]),
        current_stage=IngestionStage(doc["current_stage"]) if doc.get("current_stage") else None,
        pipeline_stages=[IngestionStage(s) for s in doc.get("pipeline_stages", [])],
        stages_completed=[IngestionStage(s) for s in doc.get("stages_completed", [])],
        progress=doc.get("progress", 0.0),
        snippet_count=doc.get("snippet_count", 0),
        entities_extracted=doc.get("entities_extracted", 0),
        axioms_extracted=doc.get("axioms_extracted", 0),
        game_system_found=doc.get("game_system_found", False),
        world_template_found=doc.get("world_template_found", False),
        proposals_generated=doc.get("proposals_generated", 0),
        proposals_accepted=doc.get("proposals_accepted", 0),
        proposals_rejected=doc.get("proposals_rejected", 0),
        total_batches=doc.get("total_batches", 0),
        succeeded_batches=doc.get("succeeded_batches", 0),
        failed_batches=doc.get("failed_batches", 0),
        retried_batches=doc.get("retried_batches", 0),
        total_attempts=doc.get("total_attempts", 0),
        current_provider=doc.get("current_provider"),
        current_model=doc.get("current_model"),
        last_error=_hydrate_last_error(doc.get("last_error")),
        next_retry_at=doc.get("next_retry_at"),
        partial=doc.get("partial", False),
        kill_reason=doc.get("kill_reason"),
        errors=doc.get("errors", []),
        warnings=doc.get("warnings", []),
        activity_log=doc.get("activity_log", []),
        processing_checklist=doc.get("processing_checklist", []),
        failed_sections=doc.get("failed_sections", []),
        started_at=doc["started_at"],
        completed_at=doc.get("completed_at"),
        duration_seconds=doc.get("duration_seconds"),
        created_at=doc["created_at"],
        pack_id=UUID(doc["pack_id"]) if doc.get("pack_id") else None,
    )


def mongodb_create_ingestion_job(params: IngestionJobCreate) -> IngestionJobResponse:
    """
    Create a new ingestion job to track pipeline progress.

    Called at the start of an ingestion run.  The job ID can then be used
    to report progress via mongodb_update_ingestion_job.

    Args:
        params: Job creation parameters (universe_id, source_id, doc_id, stages)

    Returns:
        IngestionJobResponse with the new job_id
    """
    mongodb = get_mongodb_client()
    jobs_collection = mongodb.get_collection("ingestion_jobs")

    now = datetime.now(UTC)
    job_id = params.job_id or uuid4()

    doc = {
        "job_id": str(job_id),
        "universe_id": str(params.universe_id),
        "source_id": str(params.source_id),
        "doc_id": str(params.doc_id),
        "source_title": params.source_title,
        "status": IngestionStatus.PENDING.value,
        "current_stage": None,
        "pipeline_stages": [s.value for s in params.pipeline_stages],
        "stages_completed": [],
        "progress": 0.0,
        "snippet_count": 0,
        "entities_extracted": 0,
        "axioms_extracted": 0,
        "game_system_found": False,
        "world_template_found": False,
        "proposals_generated": 0,
        "proposals_accepted": 0,
        "proposals_rejected": 0,
        "total_batches": 0,
        "succeeded_batches": 0,
        "failed_batches": 0,
        "retried_batches": 0,
        "total_attempts": 0,
        "current_provider": None,
        "current_model": None,
        "last_error": None,
        "next_retry_at": None,
        "partial": False,
        "kill_reason": None,
        "errors": [],
        "warnings": [],
        "activity_log": ["Job created", "Waiting to start ingestion pipeline"],
        "processing_checklist": list(params.processing_checklist or []),
        "failed_sections": [],
        "started_at": now,
        "completed_at": None,
        "duration_seconds": None,
        "created_at": now,
    }

    jobs_collection.insert_one(doc)

    return _convert_ingestion_job_doc(doc)


def mongodb_get_ingestion_job(job_id: UUID) -> IngestionJobResponse | None:
    """
    Get an ingestion job by ID.

    Args:
        job_id: IngestionJob UUID

    Returns:
        IngestionJobResponse or None if not found
    """
    mongodb = get_mongodb_client()
    jobs_collection = mongodb.get_collection("ingestion_jobs")
    doc = jobs_collection.find_one({"job_id": str(job_id)})
    if not doc:
        return None
    return _convert_ingestion_job_doc(doc)


def mongodb_update_ingestion_job(job_id: UUID, params: IngestionJobUpdate) -> IngestionJobResponse:
    """
    Update ingestion job progress.

    Used by pipeline agents to report stage completions, snippet counts,
    entity extraction results, and final status.

    Args:
        job_id: IngestionJob UUID
        params: Fields to update (all optional)

    Returns:
        Updated IngestionJobResponse

    Raises:
        ValueError: If job not found
    """
    mongodb = get_mongodb_client()
    jobs_collection = mongodb.get_collection("ingestion_jobs")

    def _normalize_log_entries(entries: list[Any], *, limit: int) -> list[str]:
        normalized: list[str] = []
        for entry in entries:
            text = str(entry).strip()
            if not text:
                continue
            normalized.append(text[:limit])
        return normalized

    fields_set = set(getattr(params, "model_fields_set", set()))
    update_fields: dict[str, Any] = {}
    if params.status is not None:
        update_fields["status"] = params.status.value
    if params.current_stage is not None:
        update_fields["current_stage"] = params.current_stage.value
    if params.progress is not None:
        update_fields["progress"] = max(0.0, min(float(params.progress), 1.0))
    if params.stages_completed is not None:
        update_fields["stages_completed"] = [s.value for s in params.stages_completed]
    if params.snippet_count is not None:
        update_fields["snippet_count"] = params.snippet_count
    if params.entities_extracted is not None:
        update_fields["entities_extracted"] = params.entities_extracted
    if params.axioms_extracted is not None:
        update_fields["axioms_extracted"] = params.axioms_extracted
    if params.game_system_found is not None:
        update_fields["game_system_found"] = params.game_system_found
    if params.world_template_found is not None:
        update_fields["world_template_found"] = params.world_template_found
    if params.proposals_generated is not None:
        update_fields["proposals_generated"] = params.proposals_generated
    if params.proposals_accepted is not None:
        update_fields["proposals_accepted"] = params.proposals_accepted
    if params.proposals_rejected is not None:
        update_fields["proposals_rejected"] = params.proposals_rejected
    if params.total_batches is not None:
        update_fields["total_batches"] = params.total_batches
    if params.succeeded_batches is not None:
        update_fields["succeeded_batches"] = params.succeeded_batches
    if params.failed_batches is not None:
        update_fields["failed_batches"] = params.failed_batches
    if params.retried_batches is not None:
        update_fields["retried_batches"] = params.retried_batches
    if params.total_attempts is not None:
        update_fields["total_attempts"] = params.total_attempts
    if "current_provider" in fields_set:
        update_fields["current_provider"] = params.current_provider
    if "current_model" in fields_set:
        update_fields["current_model"] = params.current_model
    if "last_error" in fields_set:
        update_fields["last_error"] = (
            params.last_error.model_dump(mode="json") if params.last_error is not None else None
        )
    if "next_retry_at" in fields_set:
        update_fields["next_retry_at"] = params.next_retry_at
    if "partial" in fields_set:
        update_fields["partial"] = bool(params.partial)
    if "kill_reason" in fields_set:
        update_fields["kill_reason"] = params.kill_reason
    if "pack_id" in fields_set and params.pack_id is not None:
        update_fields["pack_id"] = str(params.pack_id)
    if params.processing_checklist is not None:
        update_fields["processing_checklist"] = list(params.processing_checklist)
    if params.failed_sections is not None:
        # Full-replacement $set: the analyzer re-sends the complete capped
        # (<=200) list on every update, so last write wins by design.
        update_fields["failed_sections"] = [dict(s) for s in params.failed_sections]

    # errors, warnings, activity_log: use $push/$each to atomically append
    # without reading first — preserving entries from prior pipeline stages.
    push_fields: dict[str, Any] = {}
    if params.errors is not None:
        errors = _normalize_log_entries(list(params.errors), limit=600)
        if errors:
            push_fields["errors"] = {"$each": errors, "$slice": -50}
    if params.warnings is not None:
        warnings = _normalize_log_entries(list(params.warnings), limit=400)
        if warnings:
            push_fields["warnings"] = {"$each": warnings, "$slice": -100}
    if params.activity_log is not None:
        activity_log = _normalize_log_entries(list(params.activity_log), limit=400)
        if activity_log:
            push_fields["activity_log"] = {"$each": activity_log, "$slice": -200}

    if params.completed_at is not None:
        update_fields["completed_at"] = params.completed_at
        if params.status in (
            IngestionStatus.COMPLETED,
            IngestionStatus.FAILED,
            IngestionStatus.PARTIAL,
            IngestionStatus.FAILED_NON_RETRYABLE,
            IngestionStatus.BLOCKED_PROVIDER,
            IngestionStatus.CANCELLED,
            IngestionStatus.KILLED,
        ):
            # Calculate total duration with safe timezone normalization
            existing_doc = jobs_collection.find_one({"job_id": str(job_id)})
            if existing_doc:
                started = existing_doc["started_at"]
                completed = params.completed_at
                if getattr(started, "tzinfo", None) is None:
                    started = started.replace(tzinfo=UTC)
                if getattr(completed, "tzinfo", None) is None:
                    completed = completed.replace(tzinfo=UTC)
                delta = completed - started
                update_fields["duration_seconds"] = delta.total_seconds()

    update_op: dict[str, Any] = {}
    if update_fields:
        update_op["$set"] = update_fields
    if push_fields:
        update_op["$push"] = push_fields
    if not update_op:
        update_op = {"$set": {}}  # no-op but keeps find_one_and_update valid

    doc = jobs_collection.find_one_and_update(
        {"job_id": str(job_id)},
        update_op,
        return_document=True,
    )
    if not doc:
        raise ValueError(f"IngestionJob {job_id} not found")
    return _convert_ingestion_job_doc(doc)


def mongodb_list_ingestion_jobs(params: IngestionJobFilter) -> IngestionJobListResponse:
    """
    List ingestion jobs with optional filtering.

    Args:
        params: Filter options (universe_id, source_id, status, pagination)

    Returns:
        IngestionJobListResponse with matching jobs
    """
    mongodb = get_mongodb_client()
    jobs_collection = mongodb.get_collection("ingestion_jobs")

    query: dict[str, Any] = {}
    if params.universe_id:
        query["universe_id"] = str(params.universe_id)
    if params.source_id:
        query["source_id"] = str(params.source_id)
    if params.status:
        query["status"] = params.status.value

    sort_dir = -1 if params.sort_order == "desc" else 1
    total = jobs_collection.count_documents(query)
    cursor = jobs_collection.find(query).sort("started_at", sort_dir).skip(params.offset).limit(params.limit)

    jobs = [_convert_ingestion_job_doc(doc) for doc in cursor]

    return IngestionJobListResponse(
        jobs=jobs,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_delete_ingestion_job(job_id: UUID) -> bool:
    """
    Delete an ingestion job record.

    Only jobs in a terminal state (completed, failed, cancelled, killed,
    failed_non_retryable, blocked_provider) can be deleted.  Running or
    pending jobs must be cancelled first.

    The source file and derived KnowledgePack are NOT affected.

    Args:
        job_id: IngestionJob UUID

    Returns:
        True if deleted, False if not found

    Raises:
        ValueError: If job is still in a non-terminal state
    """
    mongodb = get_mongodb_client()
    jobs_collection = mongodb.get_collection("ingestion_jobs")

    doc = jobs_collection.find_one({"job_id": str(job_id)})
    if not doc:
        return False

    status = doc.get("status", "")
    terminal = {
        "completed",
        "failed",
        "cancelled",
        "killed",
        "failed_non_retryable",
        "blocked_provider",
    }
    if status not in terminal:
        raise ValueError(
            f"Job {job_id} is in '{status}' state. Only terminal jobs can be deleted. Cancel the job first."
        )

    jobs_collection.delete_one({"job_id": str(job_id)})
    return True
