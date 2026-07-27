"""Auto-extracted MongoDB tools sub-module."""

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.base import (
    ExtractionStatus,
)
from monitor_data.schemas.documents import (
    DocumentCreate,
    DocumentResponse,
    DocumentUpdate,
)

# =============================================================================
# DOCUMENT OPERATIONS  (tracks ingestion state, lives in MongoDB)
# =============================================================================


def mongodb_find_document_by_filename(filename: str, universe_id: UUID) -> DocumentResponse | None:
    """
    Find a Document by filename within a universe.

    Used by the IngestionPipeline to detect re-uploads of the same file
    and avoid creating orphaned duplicate Source/Document records.

    Args:
        filename:    Original filename to look up.
        universe_id: Scope the search to a specific universe.

    Returns:
        The most recent matching DocumentResponse, or None.
    """
    client = get_mongodb_client()
    doc = client["documents"].find_one(
        {"filename": filename, "universe_id": str(universe_id)},
        sort=[("created_at", -1)],
    )
    if not doc:
        return None
    return DocumentResponse(
        doc_id=UUID(doc["doc_id"]),
        source_id=UUID(doc["source_id"]),
        universe_id=UUID(doc["universe_id"]),
        title=doc["title"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        minio_ref=doc["minio_ref"],
        file_size_bytes=doc.get("file_size_bytes"),
        content_hash=doc.get("content_hash"),
        extraction_status=ExtractionStatus(doc["extraction_status"]),
        snippet_count=doc.get("snippet_count", 0),
        extraction_error=doc.get("extraction_error"),
        created_at=doc["created_at"],
        extracted_at=doc.get("extracted_at"),
    )


def mongodb_find_document_by_content_hash(content_hash: str) -> DocumentResponse | None:
    """
    Find a Document by content hash, system-wide (not scoped to a universe).

    INGESTION_PIPELINE_AUDIT.md Finding 7: the same real content was
    re-uploaded repeatedly under different filenames (``Death_in_Space.pdf``
    vs ``Death_in_Space_Core_Rules.pdf``) and across many throwaway
    universe_ids — filename+universe scoping (``mongodb_find_document_by_filename``)
    doesn't catch either case. Hash-based lookup does.

    Returns:
        The most recent matching DocumentResponse, or None.
    """
    client = get_mongodb_client()
    doc = client["documents"].find_one(
        {"content_hash": content_hash},
        sort=[("created_at", -1)],
    )
    if not doc:
        return None
    return DocumentResponse(
        doc_id=UUID(doc["doc_id"]),
        source_id=UUID(doc["source_id"]),
        universe_id=UUID(doc["universe_id"]),
        title=doc["title"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        minio_ref=doc["minio_ref"],
        file_size_bytes=doc.get("file_size_bytes"),
        content_hash=doc.get("content_hash"),
        extraction_status=ExtractionStatus(doc["extraction_status"]),
        snippet_count=doc.get("snippet_count", 0),
        extraction_error=doc.get("extraction_error"),
        created_at=doc["created_at"],
        extracted_at=doc.get("extracted_at"),
    )


def mongodb_create_document(params: DocumentCreate) -> DocumentResponse:
    """
    Create a Document record in MongoDB.

    Called by the IngestionPipeline immediately after a file is uploaded to
    MinIO and a Neo4j Source node has been created.  Tracks extraction status
    and snippet counts throughout the ingestion lifecycle.

    Authority: IngestionPipeline
    Use Case: DL-B1 (ingestion pipeline)

    Args:
        params: Document creation parameters

    Returns:
        DocumentResponse with new doc_id
    """
    client = get_mongodb_client()
    docs_collection = client["documents"]

    doc_id = params.doc_id or uuid4()
    now = datetime.now(UTC)

    doc = {
        "doc_id": str(doc_id),
        "source_id": str(params.source_id),
        "universe_id": str(params.universe_id),
        "title": params.title,
        "filename": params.filename,
        "file_type": params.file_type,
        "minio_ref": params.minio_ref,
        "file_size_bytes": params.file_size_bytes,
        "content_hash": params.content_hash,
        "extraction_status": ExtractionStatus.PENDING.value,
        "snippet_count": 0,
        "extraction_error": None,
        "created_at": now,
        "extracted_at": None,
    }
    docs_collection.insert_one(doc)

    return DocumentResponse(
        doc_id=doc_id,
        source_id=params.source_id,
        universe_id=params.universe_id,
        title=params.title,
        filename=params.filename,
        file_type=params.file_type,
        minio_ref=params.minio_ref,
        file_size_bytes=params.file_size_bytes,
        content_hash=params.content_hash,
        extraction_status=ExtractionStatus.PENDING,
        snippet_count=0,
        created_at=now,
    )


def mongodb_get_document(doc_id: UUID) -> DocumentResponse | None:
    """
    Get a Document record by its doc_id.

    Args:
        doc_id: UUID of the document

    Returns:
        DocumentResponse or None if not found
    """
    client = get_mongodb_client()
    doc = client["documents"].find_one({"doc_id": str(doc_id)})
    if not doc:
        return None
    return DocumentResponse(
        doc_id=UUID(doc["doc_id"]),
        source_id=UUID(doc["source_id"]),
        universe_id=UUID(doc["universe_id"]),
        title=doc["title"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        minio_ref=doc["minio_ref"],
        file_size_bytes=doc.get("file_size_bytes"),
        content_hash=doc.get("content_hash"),
        extraction_status=ExtractionStatus(doc["extraction_status"]),
        snippet_count=doc.get("snippet_count", 0),
        extraction_error=doc.get("extraction_error"),
        created_at=doc["created_at"],
        extracted_at=doc.get("extracted_at"),
    )


def mongodb_list_documents(limit: int = 200) -> list[DocumentResponse]:
    """Return all Document records, newest first."""
    client = get_mongodb_client()
    docs = list(client["documents"].find({}, sort=[("created_at", -1)], limit=limit))
    results = []
    for doc in docs:
        with suppress(Exception):
            results.append(
                DocumentResponse(
                    doc_id=UUID(doc["doc_id"]),
                    source_id=UUID(doc["source_id"]),
                    universe_id=UUID(doc["universe_id"]),
                    title=doc["title"],
                    filename=doc["filename"],
                    file_type=doc["file_type"],
                    minio_ref=doc["minio_ref"],
                    file_size_bytes=doc.get("file_size_bytes"),
                    content_hash=doc.get("content_hash"),
                    extraction_status=ExtractionStatus(doc["extraction_status"]),
                    snippet_count=doc.get("snippet_count", 0),
                    extraction_error=doc.get("extraction_error"),
                    created_at=doc["created_at"],
                    extracted_at=doc.get("extracted_at"),
                )
            )
    return results


def mongodb_update_document(doc_id: UUID, params: DocumentUpdate) -> bool:
    """
    Update extraction status and metadata on a Document record.

    Args:
        doc_id: UUID of the document to update
        params: Fields to update (only non-None fields are applied)

    Returns:
        True if the document was found and updated, False otherwise
    """
    client = get_mongodb_client()
    update_fields: dict[str, Any] = {}

    if params.extraction_status is not None:
        update_fields["extraction_status"] = params.extraction_status.value
    if params.extracted_at is not None:
        update_fields["extracted_at"] = params.extracted_at
    if params.snippet_count is not None:
        update_fields["snippet_count"] = params.snippet_count
    if params.extraction_error is not None:
        update_fields["extraction_error"] = params.extraction_error

    if not update_fields:
        return True

    result = client["documents"].update_one({"doc_id": str(doc_id)}, {"$set": update_fields})
    return result.matched_count > 0


# =============================================================================
# CANON VERDICT AUDIT TRAIL
# =============================================================================


def mongodb_record_verdict(
    scene_id: UUID,
    proposal_id: str,
    decision: str,
    reasoning: str,
    decided_at: str,
    canon_node_type: str | None = None,
) -> dict[str, Any]:
    """
    Persist a CanonKeeper verdict to MongoDB for audit trail.

    Authority: CanonKeeper only
    Collection: canon_verdicts

    Args:
        scene_id:       Scene context for this verdict batch.
        proposal_id:    ID of the proposal that was evaluated.
        decision:       "accepted" or "rejected".
        reasoning:      CanonKeeper's reasoning text.
        decided_at:     ISO timestamp of decision.
        canon_node_type: Type of node created/rejected (optional).

    Returns:
        Dict with verdict_id and status.
    """
    client = get_mongodb_client()
    verdict_id = uuid4()
    now = datetime.now(UTC)

    doc = {
        "verdict_id": str(verdict_id),
        "scene_id": str(scene_id),
        "proposal_id": proposal_id,
        "decision": decision,
        "reasoning": reasoning,
        "canon_node_type": canon_node_type,
        "decided_at": decided_at,
        "recorded_at": now,
    }
    client["canon_verdicts"].insert_one(doc)
    return {"verdict_id": str(verdict_id), "status": "recorded"}
