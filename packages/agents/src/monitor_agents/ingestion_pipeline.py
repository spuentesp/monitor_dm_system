"""
IngestionPipeline Agent — orchestrates the full document ingestion flow.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.indexer, monitor_agents.analyzer

The pipeline wires together every stage from raw file bytes to canon proposals:

    ┌─────────────┐
    │  Raw bytes  │  (PDF, EPUB, DOCX, MD, TXT, HTML, image, URI)
    └──────┬──────┘
           │ 1. Upload to MinIO
           │ 2. Create Source node in Neo4j (via MCP)
           │ 3. Create Document record in MongoDB
           │ 4. Create IngestionJob (progress tracker)
           ▼
    ┌──────────────┐
    │   Indexer    │  5. Chunk + embed → Qdrant snippets/knowledge collection
    └──────┬───────┘
           │ 6. Update IngestionJob (snippet_count, stage=embed→analyze)
           ▼
    ┌──────────────┐
    │   Analyzer   │  7. Multi-query Qdrant → DSPy extraction → KnowledgePack
    └──────┬───────┘
           │ 8. KnowledgePack (status=ready) in MongoDB
           │ 9. Optionally: auto-apply → ProposedChanges in MongoDB
           ▼
    ┌───────────────┐
    │ CanonKeeper   │  10. Evaluate proposals → commit to Neo4j (on-demand)
    │ (on-demand)   │      (NOT called here — triggered separately by scene_loop
    └───────────────┘       or by the user via the Source Curator UI)

Usage::

    pipeline = IngestionPipeline()
    job = await pipeline.ingest_file(
        file_bytes=open("phb.pdf", "rb").read(),
        filename="phb.pdf",
        source_title="D&D 5e Player's Handbook",
        universe_id=universe_id,
        pack_name="D&D 5e PHB",
        pack_type=KnowledgePackType.RULEBOOK,
        auto_apply=False,          # leave for curator to review first
    )
    print(f"Job {job.job_id}: {job.status}")

    # Later, user reviews the KnowledgePack and applies it:
    from monitor_data.tools.mongodb_tools import mongodb_apply_knowledge_pack
    result = mongodb_apply_knowledge_pack(
        pack_id,
        ApplyKnowledgePackRequest(multiverse_id=..., conflict_resolution="merge"),
    )

Authority:
    MinIO:   write (upload raw file)
    MongoDB: write (Document, IngestionJob, KnowledgePack, ProposedChanges)
    Qdrant:  write via Indexer (knowledge collection)
    Neo4j:   write via MCP tools (Source node only, via neo4j_create_source)
             ALL other Neo4j writes go through CanonKeeper
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from monitor_agents.analyzer import Analyzer
from monitor_agents.base import BaseAgent
from monitor_agents.indexer import Indexer
from monitor_data.db.minio import get_minio_client
from monitor_data.schemas.base import (
    ExtractionStatus,
    IngestionStatus,
    KnowledgeTreeType,
    SourceCanonLevel,
    SourcePriority,
    SourceType,
)
from monitor_data.schemas.documents import DocumentCreate, DocumentUpdate, SourceCreate
from monitor_data.schemas.ingestion_jobs import (
    IngestionJobCreate,
    IngestionJobUpdate,
    IngestionJobResponse,
    IngestionStage,
)
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_data.tools.mongodb_tools import (
    mongodb_create_document,
    mongodb_create_ingestion_job,
    mongodb_find_document_by_filename,
    mongodb_get_ingestion_job,
    mongodb_update_document,
    mongodb_update_ingestion_job,
)
from monitor_data.tools.neo4j_tools import neo4j_create_source

logger = logging.getLogger(__name__)

# Maximum file size accepted by the pipeline (default 200 MB).
# Override via environment variable MONITOR_MAX_INGEST_FILE_BYTES.
_MAX_FILE_SIZE_BYTES: int = 200 * 1024 * 1024

# Per-stage timeout for the analyzer (default 30 min). Generous enough not to
# false-fail a large rulebook, but tighter than the 45-min whole-job timeout so
# a wedged provider fails the analyze stage with a clear message first.
_ANALYZE_STAGE_TIMEOUT_SECS: int = int(os.environ.get("MONITOR_ANALYZE_TIMEOUT", str(30 * 60)))


async def _is_job_cancelled(job_id: UUID) -> bool:
    """Return True if the job has been externally marked failed/cancelled."""
    try:
        job = await asyncio.to_thread(mongodb_get_ingestion_job, job_id)
        if job is not None and job.status.value in (
            "failed",
            "cancelled",
            "killed",
            "failed_non_retryable",
            "blocked_provider",
        ):
            logger.info("Job %s detected as cancelled — stopping pipeline", job_id)
            return True
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Job cancellation check failed for %s (will continue): %s", job_id, exc)
        return False


def _extract_snippet_count(index_result: Any) -> int:
    """Accept legacy int and structured indexer results without breaking ingestion."""
    if index_result is None:
        return 0
    if isinstance(index_result, bool):
        return int(index_result)
    if isinstance(index_result, (int, float)):
        return int(index_result)
    if isinstance(index_result, dict):
        for key in ("snippet_count", "count", "indexed", "total"):
            value = index_result.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        raise TypeError(f"Unsupported structured index result: {index_result!r}")

    for attr in ("snippet_count", "count", "indexed", "total"):
        if hasattr(index_result, attr):
            try:
                return int(getattr(index_result, attr))
            except (TypeError, ValueError):
                continue

    try:
        return int(index_result)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"Unsupported index result: {index_result!r}") from exc


class IngestionPipeline(BaseAgent):
    """
    Orchestrates the full document ingestion pipeline.

    Composes Indexer + Analyzer + Neo4j Source creation.
    STATELESS — all persistent state goes to databases.
    """

    def __init__(self, agent_id: str = "ingestion-pipeline-1") -> None:
        super().__init__(agent_type="IngestionPipeline", agent_id=agent_id)
        self._indexer = Indexer(agent_id=f"{agent_id}-indexer")
        self._analyzer = Analyzer(agent_id=f"{agent_id}-analyzer")

    async def run(self) -> None:
        pass  # driven externally

    # ------------------------------------------------------------------
    # Primary entry points
    # ------------------------------------------------------------------

    def get_job(self, job_id: UUID) -> Optional[IngestionJobResponse]:
        """Fetch an ingestion job by ID."""
        return mongodb_get_ingestion_job(job_id)

    def apply_pack(
        self,
        pack_id: UUID,
        multiverse_id: UUID,
        universe_id: Optional[UUID] = None,
        conflict_resolution: str = "merge",
        apply_axioms: bool = True,
        apply_entities: bool = True,
        apply_lore_facts: bool = True,
        apply_plot_threads: bool = True,
        proposer: str = "Agent",
    ) -> Dict[str, Any]:
        """
        Apply a KnowledgePack — create ProposedChanges for CanonKeeper evaluation.
        """
        from monitor_data.tools.mongodb_tools import mongodb_apply_knowledge_pack
        from monitor_data.schemas.knowledge_packs import ApplyKnowledgePackRequest

        return mongodb_apply_knowledge_pack(
            pack_id,
            ApplyKnowledgePackRequest(
                multiverse_id=multiverse_id,
                universe_id=universe_id,
                conflict_resolution=conflict_resolution,
                apply_axioms=apply_axioms,
                apply_entities=apply_entities,
                apply_lore_facts=apply_lore_facts,
                apply_plot_threads=apply_plot_threads,
                proposer=proposer,
            ),
        )

    async def ingest_file(
        self,
        file_bytes: bytes,
        filename: str,
        source_title: str,
        universe_id: UUID,
        pack_name: str,
        pack_type: KnowledgePackType = KnowledgePackType.SETTING_SUPPLEMENT,
        multiverse_id: Optional[UUID] = None,
        analysis_layers: Optional[List[str]] = None,
        auto_apply: bool = False,
        content_type: Optional[str] = None,
        reuse_source_id: Optional[UUID] = None,
        reuse_doc_id: Optional[UUID] = None,
    ) -> IngestionJobResponse:
        """
        Ingest a raw file through the full pipeline.

        Stages executed:
            1. Upload file to MinIO
            2. Create Neo4j Source node
            3. Create MongoDB Document record
            4. Create IngestionJob (progress tracker)
            5. Indexer: chunk + embed → Qdrant
            6. Analyzer: extract knowledge → KnowledgePack
            7. Optionally: auto-apply KnowledgePack → ProposedChanges

        Args:
            file_bytes:    Raw file content.
            filename:      Original filename (used for format detection).
            source_title:  Human-readable source name (e.g. "D&D 5e PHB").
            universe_id:   Neo4j universe to scope the source to.
            pack_name:     Display name for the resulting KnowledgePack.
            pack_type:     What kind of source this is.
            multiverse_id: Optional multiverse for auto-applying the KnowledgePack.
            auto_apply:    If True, immediately creates ProposedChanges from the pack.
            content_type:  MIME type override (auto-detected from filename if None).

        Returns:
            IngestionJobResponse tracking pipeline progress.

        Raises:
            ValueError: If the file format is not supported.
        """
        content_type = content_type or _detect_content_type(filename)
        selected_layers = list(
            dict.fromkeys(
                (analysis_layers or ["axioms", "entities", "lore", "game_system", "rules"])
            )
        )

        # ── Guard: reject oversized files before touching any database ────
        if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
            limit_mb = _MAX_FILE_SIZE_BYTES / (1024 * 1024)
            actual_mb = len(file_bytes) / (1024 * 1024)
            raise ValueError(
                f"File '{filename}' is {actual_mb:.1f} MB, exceeding the "
                f"{limit_mb:.0f} MB limit. Split the document or set "
                f"MONITOR_MAX_INGEST_FILE_BYTES to a higher value."
            )

        # ── Guard: reject duplicate uploads ──────────────────────────────
        existing_doc = await asyncio.to_thread(
            mongodb_find_document_by_filename,
            filename,
            universe_id,
        )
        reusing_existing_doc = (
            existing_doc is not None
            and reuse_doc_id is not None
            and existing_doc.doc_id == reuse_doc_id
            and (reuse_source_id is None or existing_doc.source_id == reuse_source_id)
        )
        if (
            existing_doc is not None
            and existing_doc.extraction_status != ExtractionStatus.FAILED
            and not reusing_existing_doc
        ):
            job = await asyncio.to_thread(
                mongodb_create_ingestion_job,
                IngestionJobCreate(
                    universe_id=universe_id,
                    source_id=existing_doc.source_id,
                    doc_id=existing_doc.doc_id,
                    source_title=source_title,
                    processing_checklist=selected_layers,
                ),
            )
            return await asyncio.to_thread(
                mongodb_update_ingestion_job,
                job.job_id,
                IngestionJobUpdate(
                    status=IngestionStatus.FLAGGED_DUPLICATE,
                    progress=1.0,
                    errors=[
                        "A document with this filename already exists. Skipped to prevent queue deadlock."
                    ],
                    activity_log=["Flagged as duplicate."],
                    completed_at=datetime.now(timezone.utc),
                ),
            )

        # Sentinel variables — the except handler cleans up only what was
        # successfully created, preventing orphaned Neo4j/MongoDB records.
        source_id: Optional[UUID] = None
        doc_id: Optional[UUID] = None
        job_id: Optional[UUID] = None
        object_key: Optional[str] = None
        minio = get_minio_client()

        try:
            if reusing_existing_doc:
                if existing_doc is None:
                    raise ValueError("Cannot reuse document: existing document was not found")
                source_id = reuse_source_id or existing_doc.source_id
                doc_id = reuse_doc_id or existing_doc.doc_id
                object_key = getattr(existing_doc, "minio_ref", None)
                existing_snippet_count: int = existing_doc.snippet_count or 0
                logger.info(
                    "Reusing existing source/doc for re-ingest of '%s' (source=%s, doc=%s, existing_snippets=%d)",
                    source_title,
                    source_id,
                    doc_id,
                    existing_snippet_count,
                )
            else:
                # ── Stage 1: Upload to MinIO ─────────────────────────────────
                object_key = _build_object_key(filename, universe_id)
                await minio.upload(
                    key=object_key,
                    data=file_bytes,
                    content_type=content_type,
                )

                # ── Stage 2: Create Neo4j Source node ───────────────────────
                source_id = await asyncio.to_thread(
                    self._create_neo4j_source,
                    universe_id=universe_id,
                    title=source_title,
                    minio_ref=object_key,
                    source_type=_pack_type_to_source_type(pack_type),
                )

                # ── Stage 3: Create MongoDB Document record ──────────────────
                doc_id = await asyncio.to_thread(
                    self._create_document,
                    source_id=source_id,
                    universe_id=universe_id,
                    title=source_title,
                    filename=filename,
                    object_key=object_key,
                    file_size_bytes=len(file_bytes),
                )
                existing_snippet_count = 0

            # ── Stage 4: Create IngestionJob ─────────────────────────────
            # When reusing an existing doc WITH snippets already in Qdrant,
            # preserve the snippet_count so we can skip re-indexing below.
            _preserve_snippets = reusing_existing_doc and existing_snippet_count > 0
            await asyncio.to_thread(
                mongodb_update_document,
                doc_id,
                DocumentUpdate(
                    extraction_status=ExtractionStatus.EXTRACTING,
                    snippet_count=existing_snippet_count if _preserve_snippets else None,
                    extraction_error=None,
                ),
            )

            job = await asyncio.to_thread(
                mongodb_create_ingestion_job,
                IngestionJobCreate(
                    universe_id=universe_id,
                    source_id=source_id,
                    doc_id=doc_id,
                    source_title=source_title,
                    processing_checklist=selected_layers,
                ),
            )
            job_id = job.job_id
            await asyncio.to_thread(
                mongodb_update_ingestion_job,
                job_id,
                IngestionJobUpdate(
                    current_stage=IngestionStage.UPLOAD,
                    progress=0.05,
                    snippet_count=None,
                    entities_extracted=None,
                    axioms_extracted=None,
                    proposals_generated=None,
                    proposals_accepted=None,
                    proposals_rejected=None,
                    activity_log=[
                        f"Created source record for '{source_title}'",
                        f"Stored file '{filename}' in object storage",
                        f"Checklist: {', '.join(selected_layers)}",
                    ],
                ),
            )

            # ── Stage 5: Index (Indexer) ─────────────────────────────
            if _preserve_snippets:
                # Reusing an existing doc whose snippets are already in Qdrant —
                # skip the expensive chunk+embed stage entirely.
                snippet_count = existing_snippet_count
                logger.info(
                    "Skipping chunk+embed for '%s': reusing %d existing Qdrant snippets",
                    source_title,
                    snippet_count,
                )
                await asyncio.to_thread(
                    mongodb_update_document,
                    doc_id,
                    DocumentUpdate(
                        extraction_status=ExtractionStatus.COMPLETED,
                        snippet_count=snippet_count,
                        extraction_error=None,
                    ),
                )
                await asyncio.to_thread(
                    mongodb_update_ingestion_job,
                    job_id,
                    IngestionJobUpdate(
                        status=IngestionStatus.RUNNING,
                        snippet_count=snippet_count,
                        entities_extracted=None,
                        axioms_extracted=None,
                        proposals_generated=None,
                        proposals_accepted=None,
                        proposals_rejected=None,
                        stages_completed=[
                            IngestionStage.UPLOAD,
                            IngestionStage.EXTRACT,
                            IngestionStage.EMBED,
                        ],
                        progress=0.35,
                        activity_log=[
                            f"Reusing {snippet_count} existing Qdrant snippets — skipping chunk+embed",
                        ],
                    ),
                )
            else:
                if await _is_job_cancelled(job_id):
                    raise RuntimeError("Job was cancelled before indexing started")
                await asyncio.to_thread(
                    mongodb_update_ingestion_job,
                    job_id,
                    IngestionJobUpdate(
                        status=IngestionStatus.RUNNING,
                        current_stage=IngestionStage.EMBED,
                        progress=0.1,
                        snippet_count=None,
                        entities_extracted=None,
                        axioms_extracted=None,
                        proposals_generated=None,
                        proposals_accepted=None,
                        proposals_rejected=None,
                        activity_log=["Chunking and embedding document content"],
                    ),
                )

                index_result = await self._indexer.index(
                    file_bytes=file_bytes,
                    filename=filename,
                    source_name=source_title,
                    metadata={
                        "universe_id": str(universe_id),
                        "source_id": str(source_id),
                        "doc_id": str(doc_id),
                        "job_id": str(job_id),
                    },
                )
                snippet_count = _extract_snippet_count(index_result)
                await asyncio.to_thread(
                    mongodb_update_document,
                    doc_id,
                    DocumentUpdate(
                        extraction_status=ExtractionStatus.COMPLETED,
                        snippet_count=snippet_count,
                        extraction_error=None,
                        extracted_at=datetime.now(timezone.utc),
                    ),
                )

                await asyncio.to_thread(
                    mongodb_update_ingestion_job,
                    job_id,
                    IngestionJobUpdate(
                        snippet_count=snippet_count,
                        entities_extracted=None,
                        axioms_extracted=None,
                        proposals_generated=None,
                        proposals_accepted=None,
                        proposals_rejected=None,
                        stages_completed=[
                            IngestionStage.UPLOAD,
                            IngestionStage.EXTRACT,
                            IngestionStage.EMBED,
                        ],
                        progress=0.35,
                        activity_log=[f"Chunking complete: {snippet_count} snippets indexed"],
                    ),
                )

            # ── Stage 6: Analyze (Analyzer) ──────────────────────────
            if await _is_job_cancelled(job_id):
                raise RuntimeError("Job was cancelled before analysis started")
            # Per-stage guard: the analyzer fans out many LLM calls; a wedged
            # provider should fail *this stage* with a clear message rather than
            # silently riding the 45-minute whole-job timeout.
            try:
                analysis_result = await asyncio.wait_for(
                    self._analyzer.analyze(
                        job_id=job_id,
                        source_name=source_title,
                        source_document_ids=[doc_id],
                        pack_name=pack_name,
                        pack_type=pack_type,
                        universe_id=universe_id,
                        multiverse_id=multiverse_id,
                        analysis_layers=selected_layers,
                        auto_apply=auto_apply,
                    ),
                    timeout=_ANALYZE_STAGE_TIMEOUT_SECS,
                )
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"Analysis stage timed out after {_ANALYZE_STAGE_TIMEOUT_SECS // 60} "
                    "minutes — the LLM provider may be unreachable or overloaded."
                ) from exc

            final_status = (
                getattr(analysis_result, "status", IngestionStatus.COMPLETED)
                or IngestionStatus.COMPLETED
            )
            final_batches = {
                "total_batches": getattr(analysis_result, "total_batches", 0),
                "succeeded_batches": getattr(analysis_result, "succeeded_batches", 0),
                "failed_batches": getattr(analysis_result, "failed_batches", 0),
                "retried_batches": getattr(analysis_result, "retried_batches", 0),
                "current_provider": getattr(analysis_result, "current_provider", None),
                "current_model": getattr(analysis_result, "current_model", None),
                "last_error": getattr(analysis_result, "last_error", None),
                "partial": bool(getattr(analysis_result, "partial", False)),
            }
            # ── Stage 7 (optional): Auto-canonize via CanonKeeper ────────
            canonize_count = 0
            canonize_errors = 0
            # Canonize on PARTIAL too: when some extraction batches fail (e.g. one
            # malformed LLM response), the successful batches still produced valid
            # proposals — commit them rather than discarding the whole ingest.
            if (
                final_status in (IngestionStatus.COMPLETED, IngestionStatus.PARTIAL)
                and auto_apply
                and multiverse_id is not None
                and _auto_canonize_enabled()
            ):
                try:
                    canonize_count, canonize_errors = await self._auto_canonize(
                        job_id=job_id,
                        multiverse_id=multiverse_id,
                        universe_id=universe_id,
                        analysis_result=analysis_result,
                    )
                except Exception as canon_exc:  # noqa: BLE001
                    logger.warning("Auto-canonization failed for job %s: %s", job_id, canon_exc)

            if final_status == IngestionStatus.COMPLETED:
                canonize_suffix = (
                    f"; {canonize_count} proposals canonized" if canonize_count > 0 else ""
                )
                final_message = (
                    "Ingestion pipeline completed successfully; "
                    "knowledge pack ready for review" + canonize_suffix
                )
            elif final_status == IngestionStatus.PARTIAL:
                final_message = (
                    f"Ingestion completed with partial LLM results; "
                    f"{final_batches['failed_batches']} batch(es) failed permanently"
                )
            elif final_status == IngestionStatus.BLOCKED_PROVIDER:
                final_message = (
                    "Provider blocked during analysis; partial pack retained for operator review"
                )
            elif final_status == IngestionStatus.FAILED_NON_RETRYABLE:
                final_message = (
                    "Analysis stopped after a non-retryable provider/configuration failure"
                )
            else:
                final_message = f"Ingestion finished with status={final_status.value}"

            final = await asyncio.to_thread(
                mongodb_update_ingestion_job,
                job_id,
                IngestionJobUpdate(
                    status=final_status,
                    progress=1.0,
                    snippet_count=None,
                    entities_extracted=None,
                    axioms_extracted=None,
                    proposals_generated=None,
                    proposals_accepted=None,
                    proposals_rejected=None,
                    completed_at=datetime.now(timezone.utc),
                    activity_log=[final_message],
                    **final_batches,
                ),
            )
            return final

        except Exception as exc:
            error_msg = _truncate_error(exc)
            if doc_id is not None:
                try:
                    await asyncio.to_thread(
                        mongodb_update_document,
                        doc_id,
                        DocumentUpdate(
                            extraction_status=ExtractionStatus.FAILED,
                            snippet_count=None,
                            extraction_error=error_msg,
                            extracted_at=datetime.now(timezone.utc),
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to update document %s status to FAILED", doc_id)
            if job_id is not None:
                try:
                    await asyncio.to_thread(
                        mongodb_update_ingestion_job,
                        job_id,
                        IngestionJobUpdate(
                            status=IngestionStatus.FAILED,
                            progress=None,
                            snippet_count=None,
                            entities_extracted=None,
                            axioms_extracted=None,
                            proposals_generated=None,
                            proposals_accepted=None,
                            proposals_rejected=None,
                            errors=[error_msg],
                            activity_log=[f"Pipeline failed: {error_msg}"],
                            completed_at=datetime.now(timezone.utc),
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to update job %s status to FAILED", job_id)
            # Preserve the uploaded source + object on failure so the user can
            # still see the book in the library and retry ingestion later.
            logger.warning(
                "Preserving failed ingest artifacts for retry (source_id=%s, doc_id=%s, object_key=%s)",
                source_id,
                doc_id,
                object_key,
            )
            raise

    async def ingest_uri(
        self,
        uri: str,
        source_title: str,
        universe_id: UUID,
        pack_name: str,
        pack_type: KnowledgePackType = KnowledgePackType.WIKI,
        multiverse_id: Optional[UUID] = None,
        analysis_layers: Optional[List[str]] = None,
        auto_apply: bool = False,
    ) -> IngestionJobResponse:
        """
        Fetch a URI and ingest its content through the full pipeline.

        Args:
            uri:           HTTP/HTTPS URL to fetch.
            source_title:  Human-readable source name.
            universe_id:   Neo4j universe scope.
            pack_name:     KnowledgePack display name.
            pack_type:     Source type (default: WIKI).
            multiverse_id: Optional multiverse for auto-apply.
            analysis_layers: Which extraction layers to run (default: all).
            auto_apply:    Create ProposedChanges immediately.

        Returns:
            IngestionJobResponse.
        """
        import httpx

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "MONITOR-Ingestion/1.0"},
        ) as client:
            response = await client.get(uri)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "text/html").split(";")[0]
            file_bytes = response.content
            filename = _filename_from_uri(uri, content_type)

        return await self.ingest_file(
            file_bytes=file_bytes,
            filename=filename,
            source_title=source_title,
            universe_id=universe_id,
            pack_name=pack_name,
            pack_type=pack_type,
            multiverse_id=multiverse_id,
            analysis_layers=analysis_layers,
            auto_apply=auto_apply,
            content_type=content_type,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_neo4j_source(
        self,
        universe_id: UUID,
        title: str,
        minio_ref: str,
        source_type: str,
    ) -> UUID:
        """Create a Source node in Neo4j and return its ID."""
        response = neo4j_create_source(
            SourceCreate(
                universe_id=universe_id,
                title=title,
                edition=None,
                provenance=minio_ref,
                source_type=SourceType(source_type),
                priority=_pack_source_priority_from_source_type(source_type),
                knowledge_tree_type=_pack_tree_type_from_source_type(source_type),
                canon_level=SourceCanonLevel.PROPOSED,
            )
        )
        return response.id

    def _create_document(
        self,
        source_id: UUID,
        universe_id: UUID,
        title: str,
        filename: str,
        object_key: str,
        file_size_bytes: int,
    ) -> UUID:
        """Create a Document record in MongoDB and return its ID."""
        response = mongodb_create_document(
            DocumentCreate(
                source_id=source_id,
                universe_id=universe_id,
                title=title,
                filename=filename,
                file_type=Path(filename).suffix.lstrip(".").lower() or "bin",
                minio_ref=object_key,
                file_size_bytes=file_size_bytes,
            )
        )
        return response.doc_id

    async def _auto_canonize(
        self,
        *,
        job_id: UUID,
        multiverse_id: UUID,
        universe_id: Optional[UUID],
        analysis_result: Any,
    ) -> tuple[int, int]:
        """
        Run CanonKeeper on the proposals generated during ingestion.

        Returns (committed_count, error_count).
        """
        from monitor_data.db.mongodb import get_mongodb_client
        from monitor_agents.canonkeeper import CanonKeeper

        mongodb = get_mongodb_client()
        proposals_coll = mongodb.get_collection("proposed_changes")

        # Find all pending proposals for this ingestion.
        #
        # NOTE: ProposedChanges created by mongodb_apply_knowledge_pack are scoped
        # by multiverse_id/universe_id, NOT job_id — the documents never carry a
        # job_id field. Filtering by job_id therefore matched nothing and silently
        # skipped canonization. Scope by the universe (and multiverse) being
        # ingested into instead, which is the unit the proposals actually belong to.
        query: Dict[str, Any] = {"status": "pending", "multiverse_id": str(multiverse_id)}
        if universe_id is not None:
            query["universe_id"] = str(universe_id)
        proposals_cursor = proposals_coll.find(query)
        proposals = list(proposals_cursor)

        if not proposals:
            logger.info("No pending proposals to canonize for job %s", job_id)
            return 0, 0

        logger.info(
            "Auto-canonizing %d proposals for job %s",
            len(proposals),
            job_id,
        )

        keeper = CanonKeeper(agent_id=f"auto-canonize-{job_id}")

        # Use the bulk-commit path, NOT the runtime evaluate_proposals path.
        # The pack was already extracted/validated by the Analyzer, so the
        # heavyweight per-proposal LLM evaluation (~4 calls each) is wasteful.
        # bulk_commit_proposals does a single batched contradiction check
        # against PRE-EXISTING canon (a no-op for a fresh universe) and then
        # commits in dependency order.
        result = await keeper.bulk_commit_proposals(
            proposals,
            universe_id=universe_id,
            contradiction_check=True,
        )
        committed = result["committed"]
        rejected = result.get("rejected", 0)
        errors = len(result.get("errors", [])) + rejected

        logger.info(
            "Auto-canonization complete for job %s: %d committed, %d rejected, %d errors",
            job_id,
            committed,
            rejected,
            len(result.get("errors", [])),
        )
        return committed, errors


# =============================================================================
# MODULE-LEVEL HELPERS
# =============================================================================


def _truncate_error(exc: Exception, limit: int = 4000) -> str:
    """Build a concise error string that preserves type + start/end context.

    Unlike a naive ``str(exc)[:N]``, this keeps the exception class name
    and, when the message is too long, retains both the first and last
    segments so that truncation doesn't hide the root cause that often
    appears at the tail of a traceback.

    Exceptions marked ``user_facing = True`` (e.g. ``PdfExtractionError``)
    already carry a human-readable message, so their class name is dropped —
    the user sees "This file could not be opened as a PDF…", not
    "PdfExtractionError: This file…".
    """
    body = str(exc)
    if getattr(exc, "user_facing", False):
        return body[:limit]
    prefix = type(exc).__name__
    full = f"{prefix}: {body}"
    if len(full) <= limit:
        return full
    # Reserve space for class name + separator + ellipsis marker
    overhead = len(prefix) + len(": ") + len(" [...] ")
    budget = limit - overhead
    half = budget // 2
    return f"{prefix}: {body[:half]} [...] {body[-half:]}"


def _detect_content_type(filename: str) -> str:
    """Guess MIME type from filename, defaulting to octet-stream."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _build_object_key(filename: str, universe_id: UUID) -> str:
    """Build a namespaced MinIO object key."""
    safe_name = Path(filename).name.replace(" ", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"uploads/{universe_id}/{ts}_{safe_name}"


def _filename_from_uri(uri: str, content_type: Optional[str] = None) -> str:
    """Extract a filename from a URI path.

    If the URI yields an extensionless segment (e.g. ``/wiki/Elves``),
    an extension is appended based on *content_type* so that
    ``detect_format()`` can route to the correct extractor.
    """
    path = uri.split("?")[0].rstrip("/")
    name = path.split("/")[-1] or "index.html"
    if "." not in name and content_type:
        ct = content_type.lower().split(";")[0].strip()
        ext = mimetypes.guess_extension(ct, strict=False)
        if ext:
            name = name + ext
    return name


def _pack_type_to_source_type(pack_type: KnowledgePackType) -> str:
    """Map KnowledgePackType to a valid SourceType enum value."""
    mapping: Dict[KnowledgePackType, str] = {
        KnowledgePackType.RULEBOOK: SourceType.RULEBOOK.value,
        KnowledgePackType.SETTING_SUPPLEMENT: SourceType.SUPPLEMENT.value,
        KnowledgePackType.ADVENTURE_MODULE: SourceType.ADVENTURE.value,
        KnowledgePackType.HOMEBREW: SourceType.SUPPLEMENT.value,
        KnowledgePackType.SESSION_NOTES: SourceType.SESSION.value,
        KnowledgePackType.WIKI: SourceType.LORE.value,
        KnowledgePackType.CUSTOM: SourceType.MANUAL.value,
    }
    return mapping.get(pack_type, SourceType.MANUAL.value)


def _pack_source_priority_from_source_type(source_type: str) -> SourcePriority:
    mapping = {
        SourceType.RULEBOOK.value: SourcePriority.CORE,
        SourceType.SUPPLEMENT.value: SourcePriority.SUPPLEMENT,
        SourceType.ADVENTURE.value: SourcePriority.ADVENTURE,
        SourceType.LORE.value: SourcePriority.SUPPLEMENT,
        SourceType.SESSION.value: SourcePriority.CUSTOM,
        SourceType.MANUAL.value: SourcePriority.CUSTOM,
    }
    return mapping.get(source_type, SourcePriority.CUSTOM)


def _pack_tree_type_from_source_type(source_type: str) -> KnowledgeTreeType:
    if source_type in {
        SourceType.RULEBOOK.value,
        SourceType.SUPPLEMENT.value,
        SourceType.LORE.value,
        SourceType.ADVENTURE.value,
    }:
        return KnowledgeTreeType.TEMPLATE
    return KnowledgeTreeType.DYNAMIC


def _auto_canonize_enabled() -> bool:
    """Check if auto-canonization is enabled via environment or settings."""
    return os.environ.get("MONITOR_AUTO_CANONIZE", "true").lower() in ("true", "1", "yes")
