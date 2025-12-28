"""
MongoDB MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose MongoDB operations via the MCP server.
Documents, snippets, and ingest proposals are managed in MongoDB.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.documents import (
    DocumentCreate,
    DocumentResponse,
    DocumentFilter,
    DocumentListResponse,
)
from monitor_data.schemas.snippets import (
    SnippetCreate,
    SnippetResponse,
    SnippetFilter,
    SnippetListResponse,
)
from monitor_data.schemas.ingest_proposals import (
    IngestProposalCreate,
    IngestProposalUpdate,
    IngestProposalResponse,
    IngestProposalFilter,
    IngestProposalListResponse,
)
from monitor_data.schemas.base import DocumentStatus, IngestProposalStatus


# =============================================================================
# DOCUMENT OPERATIONS
# =============================================================================


def mongodb_create_document(params: DocumentCreate) -> DocumentResponse:
    """
    Create a new Document in MongoDB.

    Authority: Any agent
    Use Case: DL-8

    Args:
        params: Document creation parameters

    Returns:
        DocumentResponse with created document data
    """
    client = get_mongodb_client()
    collection = client.get_collection("documents")

    doc_id = uuid4()
    created_at = datetime.now(timezone.utc)

    document = {
        "doc_id": str(doc_id),
        "source_id": str(params.source_id),
        "universe_id": str(params.universe_id),
        "minio_ref": params.minio_ref,
        "title": params.title,
        "filename": params.filename,
        "file_type": params.file_type,
        "extraction_status": DocumentStatus.PENDING.value,
        "metadata": params.metadata,
        "created_at": created_at,
        "extracted_at": None,
    }

    collection.insert_one(document)

    return DocumentResponse(
        doc_id=doc_id,
        source_id=params.source_id,
        universe_id=params.universe_id,
        minio_ref=params.minio_ref,
        title=params.title,
        filename=params.filename,
        file_type=params.file_type,
        extraction_status=DocumentStatus.PENDING,
        metadata=params.metadata,
        created_at=created_at,
        extracted_at=None,
    )


def mongodb_get_document(doc_id: UUID) -> Optional[DocumentResponse]:
    """
    Get a Document by ID.

    Authority: Any agent (read-only)
    Use Case: DL-8

    Args:
        doc_id: UUID of the document

    Returns:
        DocumentResponse if found, None otherwise
    """
    client = get_mongodb_client()
    collection = client.get_collection("documents")

    doc = collection.find_one({"doc_id": str(doc_id)})

    if not doc:
        return None

    return DocumentResponse(
        doc_id=UUID(doc["doc_id"]),
        source_id=UUID(doc["source_id"]),
        universe_id=UUID(doc["universe_id"]),
        minio_ref=doc["minio_ref"],
        title=doc["title"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        extraction_status=DocumentStatus(doc["extraction_status"]),
        metadata=doc.get("metadata", {}),
        created_at=doc["created_at"],
        extracted_at=doc.get("extracted_at"),
    )


def mongodb_list_documents(filters: DocumentFilter) -> DocumentListResponse:
    """
    List documents with optional filters.

    Authority: Any agent (read-only)
    Use Case: DL-8

    Args:
        filters: Filter parameters for documents

    Returns:
        DocumentListResponse with documents and pagination info
    """
    client = get_mongodb_client()
    collection = client.get_collection("documents")

    # Build query filter
    query: Dict[str, Any] = {}

    if filters.source_id is not None:
        query["source_id"] = str(filters.source_id)

    if filters.universe_id is not None:
        query["universe_id"] = str(filters.universe_id)

    if filters.file_type is not None:
        query["file_type"] = filters.file_type

    if filters.extraction_status is not None:
        query["extraction_status"] = filters.extraction_status.value

    # Count total matching documents
    total = collection.count_documents(query)

    # Build sort order
    sort_direction = -1 if filters.sort_order == "desc" else 1

    # Get paginated documents
    cursor = (
        collection.find(query)
        .sort(filters.sort_by, sort_direction)
        .skip(filters.offset)
        .limit(filters.limit)
    )

    documents = []
    for doc in cursor:
        documents.append(
            DocumentResponse(
                doc_id=UUID(doc["doc_id"]),
                source_id=UUID(doc["source_id"]),
                universe_id=UUID(doc["universe_id"]),
                minio_ref=doc["minio_ref"],
                title=doc["title"],
                filename=doc["filename"],
                file_type=doc["file_type"],
                extraction_status=DocumentStatus(doc["extraction_status"]),
                metadata=doc.get("metadata", {}),
                created_at=doc["created_at"],
                extracted_at=doc.get("extracted_at"),
            )
        )

    return DocumentListResponse(
        documents=documents,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


# =============================================================================
# SNIPPET OPERATIONS
# =============================================================================


def mongodb_create_snippet(params: SnippetCreate) -> SnippetResponse:
    """
    Create a new Snippet in MongoDB.

    Authority: Any agent
    Use Case: DL-8

    Args:
        params: Snippet creation parameters

    Returns:
        SnippetResponse with created snippet data
    """
    client = get_mongodb_client()
    collection = client.get_collection("snippets")

    snippet_id = uuid4()
    created_at = datetime.now(timezone.utc)

    snippet = {
        "snippet_id": str(snippet_id),
        "doc_id": str(params.doc_id),
        "source_id": str(params.source_id),
        "text": params.text,
        "page": params.page,
        "section": params.section,
        "chunk_index": params.chunk_index,
        "metadata": params.metadata,
        "created_at": created_at,
    }

    collection.insert_one(snippet)

    return SnippetResponse(
        snippet_id=snippet_id,
        doc_id=params.doc_id,
        source_id=params.source_id,
        text=params.text,
        page=params.page,
        section=params.section,
        chunk_index=params.chunk_index,
        metadata=params.metadata,
        created_at=created_at,
    )


def mongodb_list_snippets(filters: SnippetFilter) -> SnippetListResponse:
    """
    List snippets with optional filters.

    Authority: Any agent (read-only)
    Use Case: DL-8

    Args:
        filters: Filter parameters for snippets

    Returns:
        SnippetListResponse with snippets and pagination info
    """
    client = get_mongodb_client()
    collection = client.get_collection("snippets")

    # Build query filter
    query: Dict[str, Any] = {}

    if filters.doc_id is not None:
        query["doc_id"] = str(filters.doc_id)

    if filters.source_id is not None:
        query["source_id"] = str(filters.source_id)

    if filters.page is not None:
        query["page"] = filters.page

    # Count total matching snippets
    total = collection.count_documents(query)

    # Build sort order
    sort_direction = -1 if filters.sort_order == "desc" else 1

    # Get paginated snippets
    cursor = (
        collection.find(query)
        .sort(filters.sort_by, sort_direction)
        .skip(filters.offset)
        .limit(filters.limit)
    )

    snippets = []
    for snip in cursor:
        snippets.append(
            SnippetResponse(
                snippet_id=UUID(snip["snippet_id"]),
                doc_id=UUID(snip["doc_id"]),
                source_id=UUID(snip["source_id"]),
                text=snip["text"],
                page=snip.get("page"),
                section=snip.get("section"),
                chunk_index=snip["chunk_index"],
                metadata=snip.get("metadata", {}),
                created_at=snip["created_at"],
            )
        )

    return SnippetListResponse(
        snippets=snippets,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


# =============================================================================
# INGEST PROPOSAL OPERATIONS
# =============================================================================


def mongodb_create_ingest_proposal(params: IngestProposalCreate) -> IngestProposalResponse:
    """
    Create a new IngestProposal in MongoDB.

    Authority: Any agent
    Use Case: DL-8

    Args:
        params: IngestProposal creation parameters

    Returns:
        IngestProposalResponse with created proposal data
    """
    client = get_mongodb_client()
    collection = client.get_collection("ingest_proposals")

    proposal_id = uuid4()
    created_at = datetime.now(timezone.utc)

    proposal = {
        "proposal_id": str(proposal_id),
        "proposal_type": params.proposal_type.value,
        "universe_id": str(params.universe_id),
        "content": params.content,
        "confidence": params.confidence,
        "evidence_snippet_ids": [str(sid) for sid in params.evidence_snippet_ids],
        "status": IngestProposalStatus.PENDING.value,
        "decision_reason": None,
        "canonical_id": None,
        "metadata": params.metadata,
        "created_at": created_at,
        "updated_at": None,
    }

    collection.insert_one(proposal)

    return IngestProposalResponse(
        proposal_id=proposal_id,
        proposal_type=params.proposal_type,
        universe_id=params.universe_id,
        content=params.content,
        confidence=params.confidence,
        evidence_snippet_ids=params.evidence_snippet_ids,
        status=IngestProposalStatus.PENDING,
        decision_reason=None,
        canonical_id=None,
        metadata=params.metadata,
        created_at=created_at,
        updated_at=None,
    )


def mongodb_list_ingest_proposals(filters: IngestProposalFilter) -> IngestProposalListResponse:
    """
    List ingest proposals with optional filters.

    Authority: Any agent (read-only)
    Use Case: DL-8

    Args:
        filters: Filter parameters for ingest proposals

    Returns:
        IngestProposalListResponse with proposals and pagination info
    """
    client = get_mongodb_client()
    collection = client.get_collection("ingest_proposals")

    # Build query filter
    query: Dict[str, Any] = {}

    if filters.universe_id is not None:
        query["universe_id"] = str(filters.universe_id)

    if filters.proposal_type is not None:
        query["proposal_type"] = filters.proposal_type.value

    if filters.status is not None:
        query["status"] = filters.status.value

    if filters.min_confidence is not None:
        query["confidence"] = {"$gte": filters.min_confidence}

    # Count total matching proposals
    total = collection.count_documents(query)

    # Build sort order
    sort_direction = -1 if filters.sort_order == "desc" else 1

    # Get paginated proposals
    cursor = (
        collection.find(query)
        .sort(filters.sort_by, sort_direction)
        .skip(filters.offset)
        .limit(filters.limit)
    )

    proposals = []
    for prop in cursor:
        proposals.append(
            IngestProposalResponse(
                proposal_id=UUID(prop["proposal_id"]),
                proposal_type=prop["proposal_type"],
                universe_id=UUID(prop["universe_id"]),
                content=prop["content"],
                confidence=prop["confidence"],
                evidence_snippet_ids=[UUID(sid) for sid in prop["evidence_snippet_ids"]],
                status=IngestProposalStatus(prop["status"]),
                decision_reason=prop.get("decision_reason"),
                canonical_id=UUID(prop["canonical_id"]) if prop.get("canonical_id") else None,
                metadata=prop.get("metadata", {}),
                created_at=prop["created_at"],
                updated_at=prop.get("updated_at"),
            )
        )

    return IngestProposalListResponse(
        proposals=proposals,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


def mongodb_update_ingest_proposal(
    proposal_id: UUID, params: IngestProposalUpdate
) -> IngestProposalResponse:
    """
    Update an IngestProposal status (primarily for acceptance/rejection).

    Authority: CanonKeeper only
    Use Case: DL-8

    Args:
        proposal_id: UUID of the proposal to update
        params: Fields to update

    Returns:
        IngestProposalResponse with updated proposal data

    Raises:
        ValueError: If proposal doesn't exist
    """
    client = get_mongodb_client()
    collection = client.get_collection("ingest_proposals")

    # Check if proposal exists
    existing = collection.find_one({"proposal_id": str(proposal_id)})
    if not existing:
        raise ValueError(f"IngestProposal {proposal_id} not found")

    updated_at = datetime.now(timezone.utc)

    # Build update document
    update_doc: Dict[str, Any] = {
        "status": params.status.value,
        "updated_at": updated_at,
    }

    if params.decision_reason is not None:
        update_doc["decision_reason"] = params.decision_reason

    if params.canonical_id is not None:
        update_doc["canonical_id"] = str(params.canonical_id)

    # Update the proposal
    collection.update_one(
        {"proposal_id": str(proposal_id)},
        {"$set": update_doc}
    )

    # Fetch and return updated proposal
    updated = collection.find_one({"proposal_id": str(proposal_id)})

    return IngestProposalResponse(
        proposal_id=UUID(updated["proposal_id"]),
        proposal_type=updated["proposal_type"],
        universe_id=UUID(updated["universe_id"]),
        content=updated["content"],
        confidence=updated["confidence"],
        evidence_snippet_ids=[UUID(sid) for sid in updated["evidence_snippet_ids"]],
        status=IngestProposalStatus(updated["status"]),
        decision_reason=updated.get("decision_reason"),
        canonical_id=UUID(updated["canonical_id"]) if updated.get("canonical_id") else None,
        metadata=updated.get("metadata", {}),
        created_at=updated["created_at"],
        updated_at=updated.get("updated_at"),
    )
