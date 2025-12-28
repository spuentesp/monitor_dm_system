"""
MongoDB MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose MongoDB operations via the MCP server.
ProposedChange operations: any agent can create, only CanonKeeper can update status.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4

from pymongo import ReturnDocument

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.proposed_changes import (
    ProposedChangeCreate,
    ProposedChangeUpdate,
    ProposedChangeResponse,
    ProposedChangeFilter,
    ProposedChangeListResponse,
    EvidenceRef,
)
from monitor_data.schemas.base import ProposalStatus


# =============================================================================
# PROPOSED CHANGE OPERATIONS
# =============================================================================


def mongodb_create_proposed_change(params: ProposedChangeCreate) -> ProposedChangeResponse:
    """
    Create a new ProposedChange document in MongoDB.

    Authority: Any agent (*)
    Use Case: DL-5

    Args:
        params: ProposedChange creation parameters

    Returns:
        ProposedChangeResponse with created document data

    Raises:
        ValueError: If validation fails
    """
    client = get_mongodb_client()
    collection = client.db["proposed_changes"]

    proposal_id = uuid4()
    created_at = datetime.now(timezone.utc)

    # Build document
    document = {
        "proposal_id": str(proposal_id),
        "change_type": params.change_type.value,
        "content": params.content,
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "story_id": str(params.story_id) if params.story_id else None,
        "universe_id": str(params.universe_id),
        "turn_id": str(params.turn_id) if params.turn_id else None,
        "confidence": params.confidence,
        "authority": params.authority.value,
        "evidence_refs": [
            {"type": ref.type, "ref_id": str(ref.ref_id)}
            for ref in params.evidence_refs
        ],
        "proposed_by": params.proposed_by,
        "status": ProposalStatus.PENDING.value,
        "decision_reason": None,
        "canonical_ref": None,
        "decided_by": None,
        "created_at": created_at,
        "decided_at": None,
    }

    # Insert document
    collection.insert_one(document)

    # Return response
    return ProposedChangeResponse(
        proposal_id=proposal_id,
        change_type=params.change_type,
        content=params.content,
        scene_id=params.scene_id,
        story_id=params.story_id,
        universe_id=params.universe_id,
        turn_id=params.turn_id,
        confidence=params.confidence,
        authority=params.authority,
        evidence_refs=params.evidence_refs,
        proposed_by=params.proposed_by,
        status=ProposalStatus.PENDING,
        decision_reason=None,
        canonical_ref=None,
        decided_by=None,
        created_at=created_at,
        decided_at=None,
    )


def mongodb_get_proposed_change(proposal_id: UUID) -> Optional[ProposedChangeResponse]:
    """
    Get a ProposedChange document by ID.

    Authority: Any agent (*)
    Use Case: DL-5

    Args:
        proposal_id: UUID of the proposed change

    Returns:
        ProposedChangeResponse if found, None otherwise
    """
    client = get_mongodb_client()
    collection = client.db["proposed_changes"]

    document = collection.find_one({"proposal_id": str(proposal_id)})

    if not document:
        return None

    return _document_to_response(document)


def mongodb_list_proposed_changes(
    filters: Optional[ProposedChangeFilter] = None,
) -> ProposedChangeListResponse:
    """
    List proposed changes with optional filtering and pagination.

    Authority: Any agent (*)
    Use Case: DL-5

    Args:
        filters: Optional filter parameters (scene_id, status, change_type, limit, offset)

    Returns:
        ProposedChangeListResponse with proposals and pagination info
    """
    client = get_mongodb_client()
    collection = client.db["proposed_changes"]

    if filters is None:
        filters = ProposedChangeFilter()

    # Build query filter
    query: Dict[str, Any] = {}

    if filters.scene_id:
        query["scene_id"] = str(filters.scene_id)

    if filters.story_id:
        query["story_id"] = str(filters.story_id)

    if filters.universe_id:
        query["universe_id"] = str(filters.universe_id)

    if filters.status:
        query["status"] = filters.status.value

    if filters.change_type:
        query["change_type"] = filters.change_type.value

    # Count total
    total = collection.count_documents(query)

    # Get documents with pagination
    cursor = (
        collection.find(query)
        .sort("created_at", -1)
        .skip(filters.offset)
        .limit(filters.limit)
    )

    proposals = [_document_to_response(doc) for doc in cursor]

    return ProposedChangeListResponse(
        proposals=proposals,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


def mongodb_update_proposed_change(
    proposal_id: UUID, params: ProposedChangeUpdate
) -> ProposedChangeResponse:
    """
    Update a ProposedChange document (status transition).

    Authority: CanonKeeper only
    Use Case: DL-5

    Args:
        proposal_id: UUID of the proposed change
        params: Update parameters (status, decision_reason, canonical_ref)

    Returns:
        ProposedChangeResponse with updated document data

    Raises:
        ValueError: If proposal doesn't exist or invalid status transition
    """
    client = get_mongodb_client()
    collection = client.db["proposed_changes"]

    # Validate status transition rules
    if params.status == ProposalStatus.PENDING:
        raise ValueError(
            "Cannot transition to 'pending' status. "
            "Valid transitions are: pending → accepted, pending → rejected."
        )

    # Validate canonical_ref for accepted proposals
    if params.status == ProposalStatus.ACCEPTED and not params.canonical_ref:
        raise ValueError(
            "canonical_ref is required when accepting a proposal. "
            "It must reference the created Neo4j node/edge ID."
        )

    # Build update atomically using find_one_and_update with status validation
    decided_at = datetime.now(timezone.utc)
    update_doc = {
        "$set": {
            "status": params.status.value,
            "decision_reason": params.decision_reason,
            "canonical_ref": str(params.canonical_ref) if params.canonical_ref else None,
            "decided_by": params.decided_by,
            "decided_at": decided_at,
        }
    }

    # Use find_one_and_update for atomic operation with status validation
    # Only update if current status is PENDING
    updated_doc = collection.find_one_and_update(
        {
            "proposal_id": str(proposal_id),
            "status": ProposalStatus.PENDING.value,  # Only update pending proposals
        },
        update_doc,
        return_document=ReturnDocument.AFTER,  # Return document after update
    )

    if not updated_doc:
        # Either proposal doesn't exist or status is not PENDING
        existing = collection.find_one({"proposal_id": str(proposal_id)})
        if not existing:
            raise ValueError(f"ProposedChange {proposal_id} not found")
        
        current_status = ProposalStatus(existing["status"])
        raise ValueError(
            f"Cannot update ProposedChange with status '{current_status.value}'. "
            "Only 'pending' proposals can be updated to 'accepted' or 'rejected'."
        )

    return _document_to_response(updated_doc)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _document_to_response(document: Dict[str, Any]) -> ProposedChangeResponse:
    """
    Convert a MongoDB document to ProposedChangeResponse.

    Args:
        document: Raw MongoDB document

    Returns:
        ProposedChangeResponse object
    """
    return ProposedChangeResponse(
        proposal_id=UUID(document["proposal_id"]),
        change_type=document["change_type"],
        content=document["content"],
        scene_id=UUID(document["scene_id"]) if document.get("scene_id") else None,
        story_id=UUID(document["story_id"]) if document.get("story_id") else None,
        universe_id=UUID(document["universe_id"]),
        turn_id=UUID(document["turn_id"]) if document.get("turn_id") else None,
        confidence=document["confidence"],
        authority=document["authority"],
        evidence_refs=[
            EvidenceRef(type=ref["type"], ref_id=UUID(ref["ref_id"]))
            for ref in document.get("evidence_refs", [])
        ],
        proposed_by=document["proposed_by"],
        status=document["status"],
        decision_reason=document.get("decision_reason"),
        canonical_ref=UUID(document["canonical_ref"]) if document.get("canonical_ref") else None,
        decided_by=document.get("decided_by"),
        created_at=document["created_at"],
        decided_at=document.get("decided_at"),
    )
