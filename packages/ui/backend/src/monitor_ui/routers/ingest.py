"""
Data ingestion router — real pipeline integration.

Wires the FastAPI endpoints to the IngestionPipeline agent (Layer 2).

Upload flow:
  1. POST /sources/upload  — ingest the file into a standalone KnowledgePack
  2. GET  /packs           — review saved packs in the Pack Library
  3. POST /packs/{id}/apply/new-world | /packs/{id}/apply/{universe_id}
                             — apply a pack to a new or existing world via CanonKeeper
                               (review flow: apply → accept proposals → commit)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from monitor_agents.ingestion.agent import IngestionPipeline
from monitor_data.db.minio import get_minio_client
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.postgres import get_postgres_client
from monitor_data.schemas.ingestion_jobs import IngestionJobFilter
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_data.schemas.llm_config import LLMTaskAttemptResponse
from monitor_data.tools.mongodb_tools import (
    mongodb_get_document,
    mongodb_get_ingestion_job,
    mongodb_list_documents,
    mongodb_list_ingestion_jobs,
)
from monitor_data.tools.neo4j_tools import neo4j_delete_source, neo4j_get_universe

from .ingest_shared import (
    _create_setting,
    _default_processing_checklist,
    _ensure_universe_for_multiverse,
    _job_to_dict,
    _source_from_doc,
    _source_from_job,
    db_op,
    validate_uuid,
)
from .pack_library import router as pack_router

# Pack Library routes live in `pack_library.py`, which is included here to
# preserve the existing `/api/ingest/*` surface while keeping this module lean.
router = APIRouter()
logger = logging.getLogger(__name__)

# Thread pool for running the ingest pipeline without blocking the event loop.
# Configurable, but defaults to 1 so LLM-heavy ingestion remains safe and predictable.
_INGEST_MAX_WORKERS = max(1, int(os.environ.get("MONITOR_INGEST_MAX_WORKERS", "1")))


def _build_ingest_executor() -> concurrent.futures.ThreadPoolExecutor:
    return concurrent.futures.ThreadPoolExecutor(
        max_workers=_INGEST_MAX_WORKERS,
        thread_name_prefix="ingest",
    )


_ingest_executor: concurrent.futures.ThreadPoolExecutor | None = _build_ingest_executor()

# Queue + active worker bookkeeping.
# RLock keeps the guard safe even if helper code re-enters while capturing job state.
_ingest_lock = threading.RLock()
_ingest_active_title: str | None = None
_ingest_active_job_id: str | None = None  # tracks the current job for cancellation
_ingest_active_requests: dict[str, dict[str, Any]] = {}
_ingest_pending_requests: list[dict[str, Any]] = []

# Overall job timeout (seconds). Set MONITOR_INGEST_TIMEOUT to override.
# Default: 45 minutes — enough for the largest PDFs on modest hardware.
_JOB_TIMEOUT_SECS = int(os.environ.get("MONITOR_INGEST_TIMEOUT", str(45 * 60)))

# Shared status mapping, world bootstrap, and response-shaping helpers live in
# `ingest_shared.py` so this router stays focused on source/job orchestration.


def _sync_ingest_state() -> None:
    """Keep the legacy single-title fields in sync with queue/worker state."""
    global _ingest_active_title, _ingest_active_job_id

    if _ingest_active_requests:
        first = next(iter(_ingest_active_requests.values()))
        _ingest_active_title = first.get("title")
        _ingest_active_job_id = first.get("job_id")
    elif _ingest_pending_requests:
        first = _ingest_pending_requests[0]
        _ingest_active_title = first.get("title")
        _ingest_active_job_id = first.get("job_id")
    else:
        _ingest_active_title = None
        _ingest_active_job_id = None


def prepare_ingest_runtime() -> None:
    """Recreate the shared executor after reloads or test shutdowns."""
    global _ingest_executor
    if _ingest_executor is None:
        _ingest_executor = _build_ingest_executor()


def _interrupt_ingest_runtime(reason: str, *, close_executor: bool) -> dict[str, Any]:
    """Clear in-memory ingest state and fail any queued/running DB jobs."""
    global _ingest_executor

    with _ingest_lock:
        prev = _ingest_active_title
        pending_count = len(_ingest_pending_requests)
        active_count = len(_ingest_active_requests)

    _clear_ingest_slot()

    recovered_jobs = 0
    try:
        mongodb = get_mongodb_client()
        result = mongodb.get_collection("ingestion_jobs").update_many(
            {"status": {"$in": ["pending", "running"]}},
            {
                "$set": {
                    "status": "failed",
                    "completed_at": datetime.now(UTC),
                },
                "$push": {"errors": {"$each": [reason], "$slice": -50}},
            },
        )
        recovered_jobs = int(result.modified_count)
    except Exception as exc:
        logger.warning("Could not mark stale ingestion jobs failed during runtime cleanup: %s", exc)

    if close_executor and _ingest_executor is not None:
        executor = _ingest_executor
        _ingest_executor = None
        executor.shutdown(wait=False, cancel_futures=True)

    return {
        "unlocked": True,
        "was_locked_by": prev,
        "cleared_pending": pending_count,
        "cleared_active": active_count,
        "recovered_jobs": recovered_jobs,
    }


def shutdown_ingest_runtime(
    reason: str = "Process was interrupted; server shutdown while the job was queued or running",
) -> dict[str, Any]:
    """Fail queued/running ingest work and close the shared executor during app shutdown."""
    return _interrupt_ingest_runtime(reason, close_executor=True)


def _reserve_ingest_slot(source_title: str | None, *, source_id: str | None = None) -> str:
    """Queue an ingestion request and return its queue token."""
    title = (source_title or "ingestion").strip() or "ingestion"
    token = str(uuid4())
    entry = {
        "token": token,
        "title": title,
        "source_id": source_id,
        "job_id": None,
        "queued_at": datetime.now(UTC).isoformat(),
    }
    with _ingest_lock:
        _ingest_pending_requests.append(entry)
        _sync_ingest_state()
        queued_count = len(_ingest_pending_requests)
    logger.info(
        "Queued ingest request '%s' (token=%s, pending=%d, active=%d, max_workers=%d)",
        title,
        token,
        queued_count,
        len(_ingest_active_requests),
        _INGEST_MAX_WORKERS,
    )
    return token


def _rename_ingest_request(token: str, title: str) -> None:
    """Update the human-readable title for a queued/active ingest request."""
    with _ingest_lock:
        for entry in _ingest_pending_requests:
            if entry["token"] == token:
                entry["title"] = title
                _sync_ingest_state()
                return
        if token in _ingest_active_requests:
            _ingest_active_requests[token]["title"] = title
            _sync_ingest_state()


def _mark_ingest_started(token: str, title: str) -> None:
    """Move a queued request into the active worker set."""
    with _ingest_lock:
        entry = next((item for item in _ingest_pending_requests if item["token"] == token), None)
        if entry is not None:
            _ingest_pending_requests.remove(entry)
        else:
            entry = {
                "token": token,
                "title": title,
                "source_id": None,
                "job_id": None,
                "queued_at": datetime.now(UTC).isoformat(),
            }
        entry["title"] = title
        entry["started_at"] = datetime.now(UTC).isoformat()
        _ingest_active_requests[token] = entry
        _sync_ingest_state()


def _attach_job_id_to_request(token: str, job_id: str | None) -> None:
    """Store the real MongoDB job id once the worker creates it."""
    with _ingest_lock:
        if token in _ingest_active_requests:
            _ingest_active_requests[token]["job_id"] = job_id
        else:
            for entry in _ingest_pending_requests:
                if entry["token"] == token:
                    entry["job_id"] = job_id
                    break
        _sync_ingest_state()


def _clear_ingest_slot(*, queue_token: str | None = None, expected_title: str | None = None) -> None:
    """Remove a queued/active ingest request when setup fails or work finishes."""
    removed_title: str | None = None
    with _ingest_lock:
        if queue_token is not None:
            for idx, entry in enumerate(list(_ingest_pending_requests)):
                if entry["token"] == queue_token:
                    removed_title = entry["title"]
                    del _ingest_pending_requests[idx]
                    break
            if removed_title is None and queue_token in _ingest_active_requests:
                removed_title = _ingest_active_requests.pop(queue_token)["title"]
        elif expected_title is not None:
            for idx, entry in enumerate(list(_ingest_pending_requests)):
                if entry["title"] == expected_title:
                    removed_title = entry["title"]
                    del _ingest_pending_requests[idx]
                    break
            if removed_title is None:
                for token, entry in list(_ingest_active_requests.items()):
                    if entry["title"] == expected_title:
                        removed_title = entry["title"]
                        del _ingest_active_requests[token]
                        break
        else:
            _ingest_pending_requests.clear()
            _ingest_active_requests.clear()
        _sync_ingest_state()
    if removed_title is not None:
        logger.info("Released ingest slot for '%s'", removed_title)


def _run_ingest_in_thread(
    *,
    queue_token: str,
    file_bytes: bytes,
    filename: str,
    source_title: str,
    universe_uid: UUID | None,
    pack_type_enum: KnowledgePackType,
    selected_layers: list[str],
    content_type: str | None,
    reuse_source_id: UUID | None = None,
    reuse_doc_id: UUID | None = None,
) -> None:
    """Run the ingest pipeline in a dedicated thread with its own event loop.

    This prevents the long-running sync+async pipeline calls from blocking
    uvicorn's main event loop.  The _ingest_lock ensures only one pipeline
    runs at a time.  An overall timeout of _JOB_TIMEOUT_SECS is enforced via
    asyncio.wait_for so a stalled LLM call cannot block the executor forever.
    """
    global _ingest_active_title, _ingest_active_job_id

    # Capture the job id once the pipeline records it so the cancel endpoint
    # can look it up even while ingest is in flight.
    _captured_job_id: list[str | None] = [None]

    async def _run() -> None:
        pipeline = IngestionPipeline()

        async def _ingest_with_capture() -> None:
            # We wrap ingest_file and capture the job_id as soon as MongoDB
            # creates it by patching the symbol that `IngestionPipeline` actually uses.
            import monitor_agents.ingestion.agent as _pipeline_module

            _orig_create_job = _pipeline_module.mongodb_create_ingestion_job  # type: ignore

            def _patched_create_job(params):  # type: ignore[no-untyped-def]
                result = _orig_create_job(params)
                _captured_job_id[0] = str(result.job_id)
                _attach_job_id_to_request(queue_token, _captured_job_id[0])
                logger.info(
                    "Created ingestion job %s for '%s'",
                    _captured_job_id[0],
                    source_title,
                )
                return result

            _pipeline_module.mongodb_create_ingestion_job = _patched_create_job  # type: ignore
            try:
                # 1. Standard ingestion pipeline
                await pipeline.ingest_file(
                    file_bytes=file_bytes,
                    filename=filename,
                    source_title=source_title,
                    universe_id=universe_uid,  # type: ignore
                    pack_name=source_title,
                    pack_type=pack_type_enum,
                    analysis_layers=selected_layers,
                    auto_apply=False,
                    content_type=content_type,
                    reuse_source_id=reuse_source_id,
                    reuse_doc_id=reuse_doc_id,
                )

                # 2. Record in World Library for the Architect
                if universe_uid:
                    try:
                        from monitor_agents.utils.world_library import WorldLibrary
                        from monitor_data.tools.neo4j_tools.core import (
                            neo4j_get_universe,
                        )

                        library = WorldLibrary()
                        universe = neo4j_get_universe(universe_uid)

                        if universe:
                            await library.add_source(
                                multiverse_id=universe.multiverse_id,  # type: ignore
                                source_type="file",
                                uri=filename,
                                system_name=universe.system_name or "generic",  # type: ignore
                                metadata={
                                    "title": source_title,
                                    "universe_id": str(universe_uid),
                                },
                            )
                    except Exception as exc:
                        logger.debug("Failed to record file in WorldLibrary: %s", exc)

            finally:
                _pipeline_module.mongodb_create_ingestion_job = _orig_create_job  # type: ignore

        try:
            await asyncio.wait_for(_ingest_with_capture(), timeout=_JOB_TIMEOUT_SECS)
        except TimeoutError:
            logger.error(
                "Ingestion timed out after %ds for '%s' (job=%s)",
                _JOB_TIMEOUT_SECS,
                source_title,
                _captured_job_id[0],
            )
            # Mark the job failed so the UI reflects the timeout.
            if _captured_job_id[0]:
                try:
                    from monitor_data.schemas.base import (
                        IngestionStatus,
                    )
                    from monitor_data.schemas.ingestion_jobs import (
                        IngestionJobUpdate,
                    )
                    from monitor_data.tools.mongodb_tools import (
                        mongodb_update_ingestion_job,
                    )

                    mongodb_update_ingestion_job(
                        UUID(_captured_job_id[0]),
                        IngestionJobUpdate(
                            status=IngestionStatus.FAILED,
                            errors=[f"Job timed out after {_JOB_TIMEOUT_SECS // 60} minutes"],
                            completed_at=datetime.now(UTC),
                        ),
                    )
                except Exception:
                    pass
        except Exception as exc:
            logger.exception("Background ingestion failed for '%s': %s", source_title, exc)

    _mark_ingest_started(queue_token, source_title)
    logger.info("Ingestion worker started for '%s'", source_title)
    try:
        asyncio.run(_run())
    finally:
        if _captured_job_id[0] is None:
            logger.error(
                "Ingestion for '%s' finished without creating a MongoDB job record — "
                "the pipeline likely failed before stage 4 (check logs above for the cause). "
                "The job will NOT appear in the UI Jobs tab.",
                source_title,
            )
        _clear_ingest_slot(queue_token=queue_token)
        logger.info(
            "Ingestion worker finished for '%s' (job=%s)",
            source_title,
            _captured_job_id[0],
        )


def _check_ingest_busy() -> None:
    """Raise 409 Conflict if any ingestion is active or queued."""
    with _ingest_lock:
        if _ingest_active_requests or _ingest_pending_requests:
            active_count = len(_ingest_active_requests)
            queued_count = len(_ingest_pending_requests)
            active_title = _ingest_active_title or "ingestion"
            raise HTTPException(
                409,
                f"Ingestion busy: {active_count} running / {queued_count} queued. Current head item: '{active_title}'.",
            )


def _build_pending_job_placeholder(
    title: str,
    *,
    token: str | None = None,
    source_id: str | None = None,
    queued_at: str | None = None,
    queue_position: int | None = None,
    running: bool = False,
) -> dict[str, Any]:
    """Surface queued or starting ingest work before the real MongoDB job appears."""
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-") or "ingest"
    now = queued_at or datetime.now(UTC).isoformat()
    placeholder_id = f"pending:{token or slug}"
    if running:
        activity_log = [
            "Worker claimed queued ingestion request",
            "Creating MongoDB job record and starting pipeline",
        ]
        status = "running"
        current_stage = "starting"
    else:
        queue_note = f"Queue position: {queue_position}" if queue_position is not None else "Waiting in queue"
        activity_log = [
            "Worker slot reserved",
            queue_note,
            "Waiting for an ingest worker to pick up this source",
        ]
        status = "pending"
        current_stage = "queued"

    return {
        "id": placeholder_id,
        "source_id": source_id or placeholder_id,
        "source_title": title,
        "job_type": "extract",
        "status": status,
        "progress": 0,
        "current_stage": current_stage,
        "stages_completed": [],
        "processing_checklist": [],
        "activity_log": activity_log,
        "warnings": [],
        "errors": [],
        "snippet_count": 0,
        "entities_extracted": 0,
        "axioms_extracted": 0,
        "proposals_generated": 0,
        "started_at": now,
        "completed_at": None,
        "duration_seconds": None,
        "error": None,
    }


def _build_source_document_job_placeholder(source: dict[str, Any]) -> dict[str, Any]:
    """Show saved source documents in the Jobs view when no job row exists yet."""
    metadata = source.get("metadata") or {}
    checklist = metadata.get("processing_checklist")
    processing_checklist = (
        [item.strip() for item in checklist if isinstance(item, str) and item.strip()]
        if isinstance(checklist, list)
        else []
    )

    source_status = source.get("status") or "pending"
    is_failed = source_status == "error"
    errors = [source.get("error_message")] if is_failed and source.get("error_message") else []
    source_id = str(source.get("id") or f"source:{uuid4()}")

    return {
        "id": str(metadata.get("job_id") or f"source:{source_id}"),
        "source_id": source_id,
        "source_title": source.get("title") or source.get("filename") or "Untitled source",
        "job_type": "extract",
        "status": "failed" if is_failed else "saved",
        "progress": 0,
        "current_stage": None if is_failed else "saved",
        "stages_completed": [],
        "processing_checklist": processing_checklist,
        "activity_log": (
            ["Saved source is waiting for recovery or re-ingest"]
            if is_failed
            else [
                "Source file saved in library",
                "Start ingest from this card or from the Library tab",
            ]
        ),
        "warnings": [],
        "errors": errors,
        "snippet_count": 0,
        "entities_extracted": 0,
        "axioms_extracted": 0,
        "proposals_generated": 0,
        "started_at": source.get("uploaded_at") or datetime.now(UTC).isoformat(),
        "completed_at": source.get("indexed_at"),
        "duration_seconds": None,
        "error": errors[0] if errors else None,
    }


def _normalize_selected_layers(raw_layers: Any, pack_type_enum: KnowledgePackType) -> list[str]:
    """Accept FastAPI defaults or raw iterables and return a clean layer list."""
    candidates = raw_layers if isinstance(raw_layers, list) else _default_processing_checklist(pack_type_enum)
    return [str(layer).strip().lower() for layer in candidates if isinstance(layer, str) and layer.strip()]


def _normalize_bool_flag(raw: Any, *, default: bool = True) -> bool:
    """Parse FastAPI form/query booleans safely when handlers are called directly in tests."""
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    return default


async def _save_uploaded_source_only(
    *,
    file_bytes: bytes,
    filename: str,
    source_title: str,
    universe_uid: UUID,
    pack_type_enum: KnowledgePackType,
    content_type: str | None,
) -> dict[str, UUID | str]:
    """Store a source in MinIO + Mongo/Neo4j without running the heavy ingest pipeline yet."""
    safe_name = Path(filename).name.replace(" ", "_")
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    object_key = f"uploads/{universe_uid}/{ts}_{safe_name}"

    minio = get_minio_client()
    await minio.upload(
        key=object_key,
        data=file_bytes,
        content_type=content_type or "application/octet-stream",
    )

    source_type_map = {
        KnowledgePackType.RULEBOOK: "rulebook",
        KnowledgePackType.SETTING_SUPPLEMENT: "supplement",
        KnowledgePackType.ADVENTURE_MODULE: "adventure",
        KnowledgePackType.HOMEBREW: "supplement",
        KnowledgePackType.SESSION_NOTES: "session",
        KnowledgePackType.WIKI: "lore",
        KnowledgePackType.CUSTOM: "manual",
    }

    pipeline = IngestionPipeline(agent_id="ingestion-save-only")
    source_id = await asyncio.to_thread(
        pipeline._create_neo4j_source,
        universe_id=universe_uid,
        title=source_title,
        minio_ref=object_key,
        source_type=source_type_map.get(pack_type_enum, "manual"),
    )
    doc_id = await asyncio.to_thread(
        pipeline._create_document,
        source_id=source_id,
        universe_id=universe_uid,
        title=source_title,
        filename=filename,
        object_key=object_key,
        file_size_bytes=len(file_bytes),
    )
    logger.info(
        "Saved source '%s' for later ingestion (source=%s, doc=%s)",
        source_title,
        source_id,
        doc_id,
    )
    return {
        "source_id": source_id,
        "doc_id": doc_id,
        "universe_id": universe_uid,
        "object_key": object_key,
    }


@router.post("/unlock", status_code=200)
async def force_unlock_ingest() -> dict:  # type: ignore
    """Force-clear the ingestion queue and fail any orphaned pending/running DB jobs."""
    return _interrupt_ingest_runtime(
        "Force-unlocked by user; queue state was reset",
        close_executor=False,
    )


# ─── Source endpoints ─────────────────────────────────────────


@router.get("/sources")
async def list_sources() -> list[dict]:  # type: ignore
    with db_op("Could not reach database"):
        result = await asyncio.to_thread(
            mongodb_list_ingestion_jobs,
            IngestionJobFilter(limit=100, sort_order="desc"),
        )

    seen: set[str] = set()
    sources = []
    for job in result.jobs:
        sid = str(job.source_id)
        if sid in seen:
            continue
        seen.add(sid)
        sources.append(_source_from_job(job))

    # Include documents that pre-date or are missing ingestion_job records
    try:
        all_docs = await asyncio.to_thread(mongodb_list_documents)
    except Exception:
        all_docs = []

    seen_file_keys: set[tuple[str, str]] = {(s["filename"], str(s["metadata"].get("universe_id", ""))) for s in sources}
    for doc in all_docs:
        sid = str(doc.source_id)
        file_key = (doc.filename, str(doc.universe_id) if doc.universe_id else "")
        if sid in seen or file_key in seen_file_keys:
            continue
        seen.add(sid)
        seen_file_keys.add(file_key)
        sources.append(_source_from_doc(doc))

    return sources


@router.get("/sources/{source_id}")
async def get_source(source_id: str) -> dict:  # type: ignore
    uid = validate_uuid(source_id, "source_id")
    with db_op("Database unavailable"):
        result = await asyncio.to_thread(
            mongodb_list_ingestion_jobs,
            IngestionJobFilter(source_id=uid, limit=1, sort_order="desc"),
        )
    if result.jobs:
        return _source_from_job(result.jobs[0])

    with db_op("Database unavailable"):
        all_docs = await asyncio.to_thread(mongodb_list_documents)

    doc = next((item for item in all_docs if str(item.source_id) == str(uid)), None)
    if not doc:
        raise HTTPException(404, "Source not found")
    return _source_from_doc(doc)


@router.post("/sources/upload", status_code=201)
async def upload_source(
    file: UploadFile = File(...),
    scan_type: str = Form(default="setting_supplement"),
    analysis_layers: list[str] | None = Form(default=None),
    ingest_now: bool = Form(default=True),
    # New setting (creates Multiverse + Universe)
    new_setting_name: str | None = Form(default=None),
    new_setting_system: str | None = Form(default=None),
    # Existing setting (finds or creates Universe under it)
    multiverse_id: str | None = Form(default=None),
    title: str | None = Form(default=None),
) -> dict:  # type: ignore
    """
    Upload a document and optionally run the full ingestion pipeline.

    By default the document is ingested as a standalone Knowledge Pack in the
    Pack Library. Callers may set `ingest_now=false` to save the book into the
    library first and trigger ingestion later from the Library tab.
    """
    scan_type_value = scan_type if isinstance(scan_type, str) else "setting_supplement"
    requested_title = title.strip() if isinstance(title, str) and title.strip() else None
    requested_setting_name = (
        new_setting_name.strip() if isinstance(new_setting_name, str) and new_setting_name.strip() else None
    )
    requested_setting_system = (
        new_setting_system.strip() if isinstance(new_setting_system, str) and new_setting_system.strip() else None
    )
    requested_multiverse_id = (
        multiverse_id.strip() if isinstance(multiverse_id, str) and multiverse_id.strip() else None
    )

    try:
        pack_type_enum = KnowledgePackType(scan_type_value)
    except ValueError:
        pack_type_enum = KnowledgePackType.SETTING_SUPPLEMENT

    filename = file.filename or "unknown"
    source_title = requested_title or filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
    should_ingest = _normalize_bool_flag(ingest_now, default=True)
    queue_token: str | None = None
    queue_position: int | None = None
    saved_source: dict[str, UUID | str] | None = None

    if should_ingest:
        queue_token = _reserve_ingest_slot(source_title)
        with _ingest_lock:
            queue_position = next(
                (index + 1 for index, entry in enumerate(_ingest_pending_requests) if entry["token"] == queue_token),
                None,
            )

    try:
        selected_layers = _normalize_selected_layers(analysis_layers, pack_type_enum)

        # Enforce upload size limit — must match IngestionPipeline._MAX_FILE_SIZE_BYTES
        # (default 200 MB, overridable via MONITOR_MAX_INGEST_FILE_BYTES).
        import os as _os

        _MAX_UPLOAD_BYTES = int(_os.environ.get("MONITOR_MAX_INGEST_FILE_BYTES", str(200 * 1024 * 1024)))
        file_bytes = await file.read()
        if len(file_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"File too large ({len(file_bytes) / (1024 * 1024):.0f} MB). "
                f"Maximum upload size is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            )

        universe_uid: UUID | None = None
        try:
            if requested_setting_name:
                _, universe_uid = _create_setting(
                    name=requested_setting_name,
                    system_name=requested_setting_system or requested_setting_name,
                )
            elif requested_multiverse_id:
                universe_uid = _ensure_universe_for_multiverse(UUID(requested_multiverse_id))
            else:
                # Standalone upload — auto-create a setting from the source title
                _, universe_uid = _create_setting(
                    name=source_title,
                    system_name=source_title,
                )
        except Exception as exc:
            raise HTTPException(500, f"Could not resolve setting: {exc}") from exc

        if should_ingest:
            try:
                logger.info(
                    "Queueing upload ingest for '%s' (%s, %d bytes, layers=%s)",
                    source_title,
                    filename,
                    len(file_bytes),
                    ", ".join(selected_layers),
                )
                prepare_ingest_runtime()
                loop = asyncio.get_running_loop()
                executor = _ingest_executor
                if executor is None:
                    raise RuntimeError("Ingest executor is unavailable during shutdown")
                loop.run_in_executor(
                    executor,
                    lambda: _run_ingest_in_thread(
                        queue_token=queue_token,  # type: ignore
                        file_bytes=file_bytes,
                        filename=filename,
                        source_title=source_title,
                        universe_uid=universe_uid,
                        pack_type_enum=pack_type_enum,
                        selected_layers=selected_layers,
                        content_type=file.content_type,
                    ),
                )
            except Exception as exc:
                raise HTTPException(500, f"Could not queue ingestion pipeline: {exc}") from exc
        else:
            saved_source = await _save_uploaded_source_only(
                file_bytes=file_bytes,
                filename=filename,
                source_title=source_title,
                universe_uid=universe_uid,
                pack_type_enum=pack_type_enum,
                content_type=file.content_type,
            )
    except HTTPException:
        if queue_token:
            _clear_ingest_slot(queue_token=queue_token)
        raise
    except Exception as exc:
        if queue_token:
            _clear_ingest_slot(queue_token=queue_token)
        raise HTTPException(500, f"Unexpected upload failure: {exc}") from exc

    queued_at = datetime.now(UTC).isoformat()
    if not should_ingest:
        assert saved_source is not None
        return {
            "id": str(saved_source["source_id"]),
            "title": source_title,
            "filename": filename,
            "source_type": scan_type_value,
            "status": "saved",
            "size_bytes": len(file_bytes),
            "page_count": None,
            "entity_count": 0,
            "relation_count": 0,
            "canon_level": "proposed",
            "error_message": None,
            "uploaded_at": queued_at,
            "indexed_at": None,
            "tags": [],
            "metadata": {
                "job_id": None,
                "doc_id": str(saved_source["doc_id"]),
                "universe_id": str(saved_source["universe_id"]),
                "processing_checklist": selected_layers,
                "queued": False,
                "queue_token": None,
                "queue_position": None,
                "max_workers": _INGEST_MAX_WORKERS,
                "standalone": False,
                "ingest_requested": False,
            },
        }

    # Match the placeholder ID logic used in _build_pending_job_placeholder
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in source_title).strip("-") or "ingest"
    placeholder_id = f"pending:{queue_token or slug}"

    return {
        "id": placeholder_id,
        "title": source_title,
        "filename": filename,
        "source_type": scan_type_value,
        "status": "processing",
        "size_bytes": len(file_bytes),
        "page_count": None,
        "entity_count": 0,
        "relation_count": 0,
        "canon_level": "proposed",
        "error_message": None,
        "uploaded_at": queued_at,
        "indexed_at": None,
        "tags": [],
        "metadata": {
            "job_id": None,
            "universe_id": str(universe_uid) if universe_uid else None,
            "processing_checklist": selected_layers,
            "queued": True,
            "queue_token": queue_token,
            "queue_position": queue_position,
            "max_workers": _INGEST_MAX_WORKERS,
            "standalone": universe_uid is None,
            "ingest_requested": True,
        },
    }


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: str) -> None:
    """Delete all records for a source from MongoDB and Qdrant."""
    uid = validate_uuid(source_id, "source_id")

    with _ingest_lock:
        source_busy = any(
            entry.get("source_id") == str(uid)
            for entry in [*_ingest_pending_requests, *_ingest_active_requests.values()]
        )
    if source_busy:
        raise HTTPException(409, "This source is currently queued or running and cannot be deleted yet.")

    with db_op("Database unavailable"):
        mongodb = get_mongodb_client()
        mongodb.get_collection("ingestion_jobs").delete_many({"source_id": str(uid)})
        mongodb.get_collection("documents").delete_many({"source_id": str(uid)})

    # Remove Neo4j Source node and its relationships
    try:
        neo4j_delete_source(uid)
    except Exception as exc:
        logger.warning("Could not delete Neo4j Source node %s: %s", uid, exc)

    # Remove Qdrant vectors for this source to avoid stale embeddings
    try:
        from monitor_data.db.qdrant import get_qdrant_client
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchValue,
        )

        qclient = get_qdrant_client()
        qdrant = qclient.get_client()
        await qdrant.delete(
            collection_name="snippets",
            points_selector=Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=str(uid)))]),
        )
        logger.info("Deleted Qdrant snippets for source %s", uid)
    except Exception as exc:
        logger.warning("Could not delete Qdrant snippets for %s: %s", uid, exc)


@router.post("/sources/{source_id}/rescan", status_code=202)
async def rescan_source(
    source_id: str,
    scan_type: str = "setting_supplement",
    analysis_layers: list[str] | None = Query(default=None),
) -> dict:  # type: ignore
    """Re-run the analysis pipeline on an already-uploaded source file.

    Retrieves the stored file from object storage and kicks off a new
    ingest job without requiring the user to re-upload the PDF.
    """
    global _ingest_active_title, _ingest_active_job_id

    src_uid = validate_uuid(source_id, "source_id")

    reservation_title = f"source:{str(src_uid)[:8]}"
    queue_token = _reserve_ingest_slot(reservation_title, source_id=str(src_uid))
    with _ingest_lock:
        queue_position = next(
            (index + 1 for index, entry in enumerate(_ingest_pending_requests) if entry["token"] == queue_token),
            None,
        )

    try:
        # Find the most recent job for this source to get file info
        with db_op("Database unavailable"):
            jobs_result = mongodb_list_ingestion_jobs(IngestionJobFilter(source_id=src_uid, limit=1, sort_order="desc"))

        prev_job = jobs_result.jobs[0] if jobs_result.jobs else None
        universe_uid = prev_job.universe_id if prev_job else None
        source_title = (prev_job.source_title if prev_job else None) or str(src_uid)[:8]
        _rename_ingest_request(queue_token, source_title)

        # Fetch the stored file — look up document by source_id directly when no job exists
        doc = None
        if prev_job:
            with db_op("Could not retrieve document record"):
                doc = mongodb_get_document(prev_job.doc_id)
        if not doc:
            # Orphan document (no job record) — find by source_id
            with db_op("Could not retrieve document"):
                all_docs = mongodb_list_documents()
                doc = next((d for d in all_docs if str(d.source_id) == str(src_uid)), None)
        if not doc:
            raise HTTPException(404, "Source document record not found")

        if universe_uid is None:
            universe_uid = doc.universe_id
        if source_title == str(src_uid)[:8]:
            source_title = doc.title or source_title

        # Verify the universe still exists; re-create a setting if it was deleted
        if universe_uid is not None:
            try:
                existing = neo4j_get_universe(universe_uid)
            except Exception:
                existing = None
            if existing is None:
                logger.info(
                    "Universe %s no longer exists; creating new setting for rescan of '%s'",
                    universe_uid,
                    source_title,
                )
                try:
                    _, universe_uid = _create_setting(
                        name=source_title,
                        system_name=source_title,
                    )
                except Exception as exc:
                    raise HTTPException(500, f"Could not re-create setting: {exc}") from exc
        else:
            # No universe at all — create one like a fresh upload
            try:
                _, universe_uid = _create_setting(
                    name=source_title,
                    system_name=source_title,
                )
            except Exception as exc:
                raise HTTPException(500, f"Could not create setting: {exc}") from exc

        minio = get_minio_client()
        try:
            file_bytes = await minio.download(doc.minio_ref)
        except Exception as exc:
            detail = str(exc)
            if "NoSuchKey" in detail:
                raise HTTPException(
                    404,
                    "Stored source file is missing from object storage. Re-upload the document to ingest it again.",
                ) from exc
            raise HTTPException(500, f"Could not retrieve stored file: {exc}") from exc

        # Clean up old transient ingestion-job rows so the rescan does not create
        # duplicate job entries in the UI. Keep the stored Document/PDF metadata so
        # previously ingested files remain visible and recoverable.
        try:
            mongodb = get_mongodb_client()
            mongodb.get_collection("ingestion_jobs").delete_many({"source_id": str(src_uid)})
        except Exception as exc:
            logger.warning(
                "Could not clean up old ingestion jobs for rescan of %s: %s",
                src_uid,
                exc,
            )

        # Preserve the existing Neo4j Source node and Mongo document for re-ingest.
        # We only clear derived vector/job artifacts before rerunning the pipeline.

        # KEEP existing Qdrant vectors and snippet_count intact so the pipeline's
        # skip-embed guard (_preserve_snippets) fires and re-analysis starts
        # immediately without the expensive ~3-minute chunk+embed stage.
        # The old approach deleted vectors + reset snippet_count=0, forcing a full
        # re-embed on every rescan even though the source text hadn't changed.

        try:
            pack_type_enum = KnowledgePackType(scan_type)
        except ValueError:
            pack_type_enum = KnowledgePackType.SETTING_SUPPLEMENT

        selected_layers = _normalize_selected_layers(analysis_layers, pack_type_enum)

        # Map bare file extension to proper MIME type
        import mimetypes as _mimetypes

        rescan_content_type = doc.file_type
        if rescan_content_type and "/" not in rescan_content_type:
            guessed = _mimetypes.guess_type(f"file.{rescan_content_type}")[0]
            rescan_content_type = guessed or f"application/{rescan_content_type}"

        try:
            logger.info(
                "Queueing rescan ingest for '%s' (%s bytes, layers=%s)",
                source_title,
                len(file_bytes),
                ", ".join(selected_layers),
            )
            prepare_ingest_runtime()
            loop = asyncio.get_running_loop()
            executor = _ingest_executor
            if executor is None:
                raise RuntimeError("Ingest executor is unavailable during shutdown")
            loop.run_in_executor(
                executor,
                lambda: _run_ingest_in_thread(
                    queue_token=queue_token,
                    file_bytes=file_bytes,
                    filename=doc.filename or f"{source_id}.pdf",
                    source_title=source_title,
                    universe_uid=universe_uid,
                    pack_type_enum=pack_type_enum,
                    selected_layers=selected_layers,
                    content_type=rescan_content_type,
                    reuse_source_id=src_uid,
                    reuse_doc_id=doc.doc_id,
                ),
            )
        except Exception as exc:
            raise HTTPException(500, f"Could not queue rescan pipeline: {exc}") from exc

        return {
            "status": "processing",
            "source_id": source_id,
            "source_title": source_title,
            "message": f"Rescan queued for '{source_title}'",
            "queue_position": queue_position,
            "max_workers": _INGEST_MAX_WORKERS,
        }
    except HTTPException:
        _clear_ingest_slot(queue_token=queue_token)
        raise
    except Exception as exc:
        _clear_ingest_slot(queue_token=queue_token)
        raise HTTPException(500, f"Unexpected rescan failure: {exc}") from exc


# ─── Job endpoints ────────────────────────────────────────────


@router.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str) -> dict:  # type: ignore
    """Cancel a running ingestion job.

    Immediately marks the job as cancelled in MongoDB so the UI reflects the
    operator action truthfully. The background worker will see the cancelled
    status at its next stage-boundary check and stop without committing
    further results.

    If the job is not currently running, returns 409.
    """
    uid = validate_uuid(job_id, "job_id")
    with db_op("Database unavailable"):
        mongodb = get_mongodb_client()
        jobs_col = mongodb.get_collection("ingestion_jobs")
        result = jobs_col.update_one(
            {
                "job_id": str(uid),
                "status": {"$in": ["running", "retrying", "backing_off"]},
            },
            {
                "$set": {
                    "status": "cancelled",
                    "completed_at": datetime.now(UTC),
                    # Structured shape required by LastError / _hydrate_last_error
                    # (data-layer/tools/mongodb_tools/ingestion_jobs.py) -- a bare
                    # string here writes fine (this is a raw pymongo update, not
                    # validated by IngestionJobUpdate) but _hydrate_last_error
                    # explicitly raises ValueError on any non-dict last_error,
                    # permanently breaking every future read of this job
                    # (mongodb_get_ingestion_job, `monitor ingest status`, the UI
                    # job list/detail view). Matches watchdog.py's shape.
                    "last_error": {
                        "category": "unknown",
                        "message": "Cancelled by user",
                        "failed_at": datetime.now(UTC),
                        "detail": "Job cancelled via the /cancel endpoint.",
                    },
                },
                "$push": {"errors": {"$each": ["Cancelled by user"], "$slice": -50}},
            },
        )
        if result.matched_count == 0:
            # Job not found or not running — check if it exists at all
            existing = jobs_col.find_one({"job_id": str(uid)})
            if existing is None:
                raise HTTPException(404, "Job not found")
            raise HTTPException(409, f"Job is not running (status={existing['status']})")

    # Release just the matching in-memory active request so the queue can advance.
    with _ingest_lock:
        for token, entry in list(_ingest_active_requests.items()):
            if entry.get("job_id") == str(uid):
                del _ingest_active_requests[token]
                break
        _sync_ingest_state()

    return {"job_id": job_id, "status": "cancelled", "message": "Job cancelled"}


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str) -> None:
    """Delete a single ingestion job record from MongoDB.

    Only terminal-state jobs (completed, failed, cancelled, etc.) can be
    deleted.  Running or pending jobs must be cancelled first.
    """
    uid = validate_uuid(job_id, "job_id")
    try:
        from monitor_data.tools.mongodb_tools import mongodb_delete_ingestion_job

        deleted = mongodb_delete_ingestion_job(uid)
        if not deleted:
            raise HTTPException(404, "Job not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.delete("/jobs", status_code=200)
async def purge_failed_jobs() -> dict:  # type: ignore
    """Delete all failed/error ingestion jobs from MongoDB.

    Returns a count of how many records were removed.
    """
    with db_op("Database unavailable"):
        mongodb = get_mongodb_client()
        jobs_col = mongodb.get_collection("ingestion_jobs")
        result = jobs_col.delete_many(
            {
                "status": {
                    "$in": [
                        "failed",
                        "cancelled",
                        "killed",
                        "failed_non_retryable",
                        "blocked_provider",
                    ]
                }
            }
        )
        return {"deleted": result.deleted_count}


@router.post("/cache/clear", status_code=200)
async def clear_llm_cache() -> dict:  # type: ignore
    """Clear DSPy caches, the LLM registry cache, and the Redis runtime cache.

    The DSPy runtime caches LLM call results in ``~/.dspy_cache`` (diskcache).
    The LLM registry caches resolved provider clients in memory so that
    provider changes (disabling a model, switching roles) take effect only
    after this endpoint is called.

    Redis is optional and only stores ephemeral runtime state; clearing it is
    safe and simply forces the next request to rebuild hot-path context.
    """
    import dspy
    from monitor_agents.dspy_runtime import clear_bg_registry_cache
    from monitor_data.db.redis import clear_runtime_cache

    cleared: dict[str, Any] = {
        "dspy_cache": False,
        "memory_cache": False,
        "registry_cache": False,
        "runtime_cache": 0,
    }
    try:
        cache = dspy.cache
        if hasattr(cache, "disk_cache") and hasattr(cache.disk_cache, "clear"):
            cache.disk_cache.clear()
            cleared["dspy_cache"] = True
            logger.info("Cleared DSPy disk cache via diskcache API")
        if hasattr(cache, "reset_memory_cache"):
            cache.reset_memory_cache()
            cleared["memory_cache"] = True
            logger.info("Cleared DSPy in-memory cache")
    except Exception as exc:
        logger.warning("Could not clear DSPy cache: %s", exc)
        cleared["error"] = str(exc)

    # Purge the background LLM registry so provider changes take effect.
    cleared["registry_cache"] = clear_bg_registry_cache()
    if cleared["registry_cache"]:
        logger.info("Cleared background LLM registry cache")

    cleared["runtime_cache"] = clear_runtime_cache()
    if cleared["runtime_cache"]:
        logger.info("Cleared Redis runtime cache entries: %s", cleared["runtime_cache"])

    return {"cleared": cleared}


@router.get("/jobs")
async def list_jobs() -> list[dict]:  # type: ignore
    with db_op("Database unavailable"):
        result = await asyncio.to_thread(
            mongodb_list_ingestion_jobs,
            IngestionJobFilter(limit=200, sort_order="desc"),
        )

    jobs = [_job_to_dict(j) for j in result.jobs]
    with _ingest_lock:
        active_entries = [dict(entry) for entry in _ingest_active_requests.values()]
        pending_entries = [dict(entry) for entry in _ingest_pending_requests]

    visible_job_ids = {job["id"] for job in jobs}
    visible_source_ids = {job["source_id"] for job in jobs}

    placeholders: list[dict[str, Any]] = []

    # Deduplicate active/pending items by token AND source_id
    for entry in active_entries:
        token = entry.get("token")
        job_id = entry.get("job_id")
        source_id = entry.get("source_id")

        if job_id in visible_job_ids:
            continue
        if source_id in visible_source_ids and not job_id:
            # Already have a job for this source, don't show placeholder
            continue

        placeholder = _build_pending_job_placeholder(
            entry["title"],
            token=token,
            source_id=source_id,
            queued_at=entry.get("started_at") or entry.get("queued_at"),
            running=True,
        )
        placeholders.append(placeholder)
        if source_id:
            visible_source_ids.add(source_id)

    for index, entry in enumerate(pending_entries, start=1):
        token = entry.get("token")
        source_id = entry.get("source_id")

        if source_id in visible_source_ids:
            continue

        placeholder = _build_pending_job_placeholder(
            entry["title"],
            token=token,
            source_id=source_id,
            queued_at=entry.get("queued_at"),
            queue_position=index,
            running=False,
        )
        placeholders.append(placeholder)
        if source_id:
            visible_source_ids.add(source_id)

    with db_op("Database unavailable"):
        all_docs = await asyncio.to_thread(mongodb_list_documents)

    for doc in all_docs:
        try:
            source = _source_from_doc(doc)
        except Exception as exc:
            logger.warning(
                "Skipping malformed document %s in list_jobs: %s",
                getattr(doc, "doc_id", "?"),
                exc,
            )
            continue
        if source["id"] in visible_source_ids:
            continue
        if source["status"] not in {"saved", "processing", "error"}:
            continue
        placeholders.append(_build_source_document_job_placeholder(source))

    return placeholders + jobs


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:  # type: ignore
    uid = validate_uuid(job_id, "job_id")
    with db_op("Database unavailable"):
        job = await asyncio.to_thread(mongodb_get_ingestion_job, uid)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_dict(job)


@router.get("/jobs/{job_id}/attempts")
async def list_job_attempts(
    job_id: str,
    stage: str | None = Query(default=None),
    batch_id: str | None = Query(default=None),
    provider_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[LLMTaskAttemptResponse]:
    """Return durable attempt-level LLM execution history for a specific ingest job."""
    try:
        parsed_job_id = str(UUID(job_id))
    except ValueError:
        # Placeholder IDs like `pending:<token>` do not have a durable ledger yet.
        return []

    normalized_stage = stage if isinstance(stage, str) else None
    normalized_batch_id = batch_id if isinstance(batch_id, str) else None
    normalized_provider_id = provider_id if isinstance(provider_id, str) else None

    postgres = get_postgres_client()
    with db_op("Could not load LLM attempt history"):
        rows = await postgres.llm_task_attempts_list(
            job_id=parsed_job_id,
            stage=normalized_stage,
            batch_id=normalized_batch_id,
            provider_id=normalized_provider_id,
            limit=limit,
        )

    return [LLMTaskAttemptResponse(**row) for row in rows]


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):  # type: ignore
    """SSE stream that pushes job status updates until the job reaches a
    terminal state (completed / failed).  The frontend can listen to this
    instead of polling every 3 s for much faster feedback.

    Each SSE event is a JSON-encoded ``_job_to_dict`` payload.
    """
    uid = validate_uuid(job_id, "job_id")

    async def _event_generator():  # type: ignore
        import json as _json

        _TERMINAL = {
            "completed",
            "partial",
            "failed",
            "failed_non_retryable",
            "blocked_provider",
            "killed",
            "cancelled",
        }
        _POLL_INTERVAL = 1  # seconds between DB checks for snappier UI updates
        _MAX_STARTUP_RETRIES = 10  # Wait up to 10s for the job to appear in DB

        job = None
        for _attempt in range(_MAX_STARTUP_RETRIES):
            try:
                job = await asyncio.to_thread(mongodb_get_ingestion_job, uid)
                if job:
                    break
            except Exception:
                pass
            await asyncio.sleep(1)

        if job is None:
            yield 'event: error\ndata: {"error": "job not found"}\n\n'
            return

        while True:
            try:
                job = await asyncio.to_thread(mongodb_get_ingestion_job, uid)
            except Exception:
                yield 'event: error\ndata: {"error": "database unavailable"}\n\n'
                return
            if job is None:
                # Job was deleted or disappeared
                yield 'event: error\ndata: {"error": "job record missing"}\n\n'
                return

            payload = _json.dumps(_job_to_dict(job))
            yield f"data: {payload}\n\n"
            if job.status.value in _TERMINAL:
                return
            await asyncio.sleep(_POLL_INTERVAL)

    return StreamingResponse(
        _event_generator(),  # type: ignore
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# I-6: Binary Assets (MinIO)
# ---------------------------------------------------------------------------


@router.post("/assets/upload", status_code=201)
async def upload_asset(
    file: UploadFile = File(...),
    source_id: str | None = Form(default=None),
    universe_id: str | None = Form(default=None),
    asset_type: str = Form(default="image"),
    label: str | None = Form(default=None),
) -> dict:  # type: ignore
    """
    Upload a binary asset (image, audio, PDF raw) to MinIO.

    Stores the file in MinIO and records metadata in MongoDB `binary_assets`
    collection. Returns the asset metadata including a presigned URL.
    """
    minio = get_minio_client()
    mongo = get_mongodb_client()

    asset_uid = uuid4()
    filename = file.filename or "unknown"
    content_type = file.content_type or "application/octet-stream"
    file_bytes = await file.read()

    # Size limit: 500 MB for assets
    _MAX_ASSET_BYTES = int(os.environ.get("MONITOR_MAX_ASSET_BYTES", str(500 * 1024 * 1024)))
    if len(file_bytes) > _MAX_ASSET_BYTES:
        raise HTTPException(
            413,
            f"Asset too large ({len(file_bytes) / (1024 * 1024):.0f} MB). "
            f"Maximum size is {_MAX_ASSET_BYTES // (1024 * 1024)} MB.",
        )

    # Build MinIO key: assets/{source_id_or_untracked}/{uuid}_{filename}
    parent = "untracked"
    if source_id:
        parent = source_id
    elif universe_id:
        parent = f"universe_{universe_id}"
    object_key = f"assets/{parent}/{asset_uid}_{filename}"

    await minio.upload(object_key, file_bytes)

    # Generate presigned URL (valid 1h)
    presigned = await minio.presigned_url(object_key, expires_sec=3600)

    asset_doc = {
        "_id": str(asset_uid),
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(file_bytes),
        "object_key": object_key,
        "asset_type": asset_type,
        "label": label or filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title(),
        "source_id": source_id,
        "universe_id": universe_id,
        "presigned_url": presigned,
        "created_at": datetime.now(UTC).isoformat(),
        "deleted": False,
    }
    with db_op("Database error"):
        mongo.get_collection("binary_assets").insert_one(asset_doc)

    # Return without MongoDB internals
    return {
        "id": str(asset_uid),
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(file_bytes),
        "object_key": object_key,
        "asset_type": asset_type,
        "label": asset_doc["label"],
        "source_id": source_id,
        "universe_id": universe_id,
        "presigned_url": presigned,
        "created_at": asset_doc["created_at"],
    }


@router.get("/assets")
async def list_assets(
    source_id: str | None = Query(default=None),
    universe_id: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:  # type: ignore
    """List binary assets with optional filters."""
    mongo = get_mongodb_client()
    query: dict[str, Any] = {"deleted": False}
    if source_id:
        query["source_id"] = source_id
    if universe_id:
        query["universe_id"] = universe_id
    if asset_type:
        query["asset_type"] = asset_type

    cursor = mongo.get_collection("binary_assets").find(query).sort("created_at", -1).skip(offset).limit(limit)
    with db_op("Database error"):
        total = mongo.get_collection("binary_assets").count_documents(query)
    items = []
    async for doc in cursor:  # type: ignore
        # Refresh presigned URL
        minio = get_minio_client()
        presigned = await minio.presigned_url(doc["object_key"], expires_sec=3600)
        items.append(
            {
                "id": doc["_id"],
                "filename": doc.get("filename", ""),
                "content_type": doc.get("content_type", ""),
                "size_bytes": doc.get("size_bytes", 0),
                "object_key": doc.get("object_key", ""),
                "asset_type": doc.get("asset_type", ""),
                "label": doc.get("label", ""),
                "source_id": doc.get("source_id"),
                "universe_id": doc.get("universe_id"),
                "presigned_url": presigned,
                "created_at": doc.get("created_at", ""),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str) -> dict:  # type: ignore
    """Get a single binary asset by ID with a fresh presigned URL."""
    mongo = get_mongodb_client()
    with db_op("Database error"):
        doc = mongo.get_collection("binary_assets").find_one({"_id": asset_id, "deleted": False})
    if not doc:
        raise HTTPException(404, f"Asset {asset_id} not found")

    minio = get_minio_client()
    presigned = await minio.presigned_url(doc["object_key"], expires_sec=3600)
    return {
        "id": doc["_id"],
        "filename": doc.get("filename", ""),
        "content_type": doc.get("content_type", ""),
        "size_bytes": doc.get("size_bytes", 0),
        "object_key": doc.get("object_key", ""),
        "asset_type": doc.get("asset_type", ""),
        "label": doc.get("label", ""),
        "source_id": doc.get("source_id"),
        "universe_id": doc.get("universe_id"),
        "presigned_url": presigned,
        "created_at": doc.get("created_at", ""),
    }


@router.delete("/assets/{asset_id}", status_code=200)
async def delete_asset(asset_id: str) -> dict:  # type: ignore
    """Soft-delete a binary asset (marks deleted, retains metadata)."""
    mongo = get_mongodb_client()
    with db_op("Database error"):
        doc = mongo.get_collection("binary_assets").find_one({"_id": asset_id, "deleted": False})
    if not doc:
        raise HTTPException(404, f"Asset {asset_id} not found")

    # Soft delete — keep metadata, mark deleted
    with db_op("Database error"):
        mongo.get_collection("binary_assets").update_one(
            {"_id": asset_id},
            {
                "$set": {
                    "deleted": True,
                    "deleted_at": datetime.now(UTC).isoformat(),
                }
            },
        )
    return {"id": asset_id, "status": "deleted"}


@router.post("/assets/{asset_id}/replace", status_code=200)
async def replace_asset(
    asset_id: str,
    file: UploadFile = File(...),
) -> dict:  # type: ignore
    """Replace the binary content of an existing asset (keeps metadata)."""
    mongo = get_mongodb_client()
    with db_op("Database error"):
        doc = mongo.get_collection("binary_assets").find_one({"_id": asset_id, "deleted": False})
    if not doc:
        raise HTTPException(404, f"Asset {asset_id} not found")

    minio = get_minio_client()
    file_bytes = await file.read()

    # Upload new version to same key
    await minio.upload(doc["object_key"], file_bytes)

    # Update metadata
    presigned = await minio.presigned_url(doc["object_key"], expires_sec=3600)
    with db_op("Database error"):
        mongo.get_collection("binary_assets").update_one(
            {"_id": asset_id},
            {
                "$set": {
                    "filename": file.filename or doc.get("filename", ""),
                    "content_type": file.content_type or doc.get("content_type", ""),
                    "size_bytes": len(file_bytes),
                    "presigned_url": presigned,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            },
        )
    return {
        "id": asset_id,
        "filename": file.filename or doc.get("filename", ""),
        "size_bytes": len(file_bytes),
        "presigned_url": presigned,
        "status": "replaced",
    }


# Pack Library routes live in `pack_library.py`, which is included here to
# preserve the existing `/api/ingest/*` surface while keeping this module lean.
router.include_router(pack_router)
