"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.base import (
    Authority,
    ProposalStatus,
    ProposalType,
)
from monitor_data.schemas.proposed_changes import (
    DecisionMetadata,
    Evidence,
    ProposedChangeCreate,
    ProposedChangeFilter,
    ProposedChangeListResponse,
    ProposedChangeResponse,
    ProposedChangeUpdate,
)

# =============================================================================
# PROPOSED CHANGE OPERATIONS
# =============================================================================


def _coerce_proposal_status(raw: str) -> ProposalStatus:
    """Normalise proposal status from MongoDB, handling legacy values."""
    # CanonKeeper auto-commit sets status='committed' which predates the enum.
    # Treat it as ACCEPTED for API consumers.
    if raw == "committed":
        return ProposalStatus.ACCEPTED
    return ProposalStatus(raw)


def _convert_proposed_change_doc_to_response(
    doc: dict[str, Any],
) -> ProposedChangeResponse:
    """
    Convert a proposed change document from MongoDB to a ProposedChangeResponse.

    Args:
        doc: ProposedChange data from MongoDB document

    Returns:
        ProposedChangeResponse object
    """
    # Convert evidence list
    evidence = [Evidence(type=e["type"], ref_id=UUID(e["ref_id"])) for e in doc.get("evidence", [])]

    # Normalize legacy proposal documents created before the unified schema.
    raw_change_type = doc.get("change_type") or doc.get("proposal_type") or ProposalType.FACT.value
    legacy_type_map = {
        "create_axiom": ProposalType.FACT.value,
        "create_lore_fact": ProposalType.FACT.value,
        "create_entity_archetype": ProposalType.ENTITY.value,
    }
    normalized_change_type = legacy_type_map.get(raw_change_type, raw_change_type)
    content = doc.get("content") or doc.get("payload") or {}

    # Convert decision metadata if present
    decision_metadata = None
    if doc.get("decision_metadata"):
        dm = doc["decision_metadata"]
        decision_metadata = DecisionMetadata(
            decided_by=dm["decided_by"],
            decided_at=dm["decided_at"],
            reason=dm["reason"],
            canonical_ref=(UUID(dm["canonical_ref"]) if dm.get("canonical_ref") else None),
        )

    return ProposedChangeResponse(
        proposal_id=UUID(doc["proposal_id"]),
        scene_id=UUID(doc["scene_id"]) if doc.get("scene_id") else None,
        story_id=UUID(doc["story_id"]) if doc.get("story_id") else None,
        turn_id=UUID(doc["turn_id"]) if doc.get("turn_id") else None,
        change_type=normalized_change_type,
        content=content,
        evidence=evidence,
        confidence=doc.get("confidence", content.get("confidence", 1.0)),
        authority=doc.get("authority", Authority.SYSTEM.value),
        proposer=doc.get("proposer", "Unknown"),
        status=_coerce_proposal_status(doc.get("status", ProposalStatus.PENDING.value)),
        decision_metadata=decision_metadata,
        promotion_intent=doc.get("promotion_intent"),
        interaction_count=doc.get("interaction_count", 1),
        is_mechanically_bound=doc.get("is_mechanically_bound", False),
        source=doc.get("source"),
        proposal_type=doc.get("proposal_type"),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at") or doc["created_at"],
    )


def mongodb_create_proposed_change(
    params: ProposedChangeCreate,
) -> ProposedChangeResponse:
    """
    Create a new ProposedChange document in MongoDB.

    Authority: * (all agents can propose changes)
    Use Case: DL-5

    Args:
        params: ProposedChange creation parameters

    Returns:
        ProposedChangeResponse with created proposal data

    Raises:
        ValueError: If scene_id or story_id doesn't exist or neither is provided
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify scene exists if scene_id provided
    if params.scene_id:
        scenes_collection = mongo_client.get_collection("scenes")
        scene_doc = scenes_collection.find_one({"scene_id": str(params.scene_id)})
        if not scene_doc:
            raise ValueError(f"Scene {params.scene_id} not found")

    # Verify story exists if story_id provided (and no scene_id)
    if params.story_id and not params.scene_id:
        story_query = "MATCH (s:Story {id: $story_id}) RETURN s.id as id"
        result = neo4j_client.execute_read(story_query, {"story_id": str(params.story_id)})
        if not result:
            raise ValueError(f"Story {params.story_id} not found")

    # Create proposal
    proposal_id = uuid4()
    created_at = datetime.now(UTC)

    proposal_doc = {
        "proposal_id": str(proposal_id),
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "story_id": str(params.story_id) if params.story_id else None,
        "turn_id": str(params.turn_id) if params.turn_id else None,
        "change_type": params.change_type.value,
        "content": params.content,
        "evidence": [{"type": e.type, "ref_id": str(e.ref_id)} for e in params.evidence],
        "confidence": params.confidence,
        "authority": params.authority.value,
        "proposer": params.proposer,
        "status": ProposalStatus.PENDING.value,
        "decision_metadata": None,
        "promotion_intent": params.promotion_intent.value if params.promotion_intent else None,
        "interaction_count": params.interaction_count,
        "is_mechanically_bound": params.is_mechanically_bound,
        "created_at": created_at,
        "updated_at": created_at,
    }

    # Insert into MongoDB
    proposed_changes_collection = mongo_client.get_collection("proposed_changes")
    proposed_changes_collection.insert_one(proposal_doc)

    # If scene_id provided, add this proposal to the scene's proposed_changes list
    if params.scene_id:
        scenes_collection = mongo_client.get_collection("scenes")
        scenes_collection.update_one(
            {"scene_id": str(params.scene_id)},
            {
                "$push": {"proposed_changes": str(proposal_id)},
                "$set": {"updated_at": created_at},
            },
        )

    return ProposedChangeResponse(
        proposal_id=proposal_id,
        scene_id=params.scene_id,
        story_id=params.story_id,
        turn_id=params.turn_id,
        change_type=params.change_type,
        content=params.content,
        evidence=params.evidence,
        confidence=params.confidence,
        authority=params.authority,
        proposer=params.proposer,
        status=ProposalStatus.PENDING,
        decision_metadata=None,
        promotion_intent=params.promotion_intent,
        interaction_count=params.interaction_count,
        is_mechanically_bound=params.is_mechanically_bound,
        created_at=created_at,
        updated_at=created_at,
    )


def mongodb_get_proposed_change(proposal_id: UUID) -> ProposedChangeResponse | None:
    """
    Retrieve a ProposedChange by ID.

    Authority: * (all agents)
    Use Case: DL-5

    Args:
        proposal_id: UUID of the proposal to retrieve

    Returns:
        ProposedChangeResponse if found, None otherwise
    """
    mongo_client = get_mongodb_client()
    proposed_changes_collection = mongo_client.get_collection("proposed_changes")

    proposal_doc = proposed_changes_collection.find_one({"proposal_id": str(proposal_id)})
    if not proposal_doc:
        return None

    return _convert_proposed_change_doc_to_response(proposal_doc)


def mongodb_list_proposed_changes(
    params: ProposedChangeFilter,
) -> ProposedChangeListResponse:
    """
    List proposed changes with filtering, sorting, and pagination.

    Authority: * (all agents)
    Use Case: DL-5

    Args:
        params: Filter and pagination parameters

    Returns:
        ProposedChangeListResponse with list of proposals and pagination info
    """
    mongo_client = get_mongodb_client()
    proposed_changes_collection = mongo_client.get_collection("proposed_changes")

    # Build filter query
    filter_query: dict[str, Any] = {}

    if params.scene_id is not None:
        filter_query["scene_id"] = str(params.scene_id)

    if params.story_id is not None:
        filter_query["story_id"] = str(params.story_id)

    if params.status is not None:
        filter_query["status"] = params.status.value

    if params.change_type is not None:
        filter_query["change_type"] = params.change_type.value

    if params.source is not None:
        filter_query["source"] = params.source

    # Count total matching documents
    total = proposed_changes_collection.count_documents(filter_query)

    # Build sort
    sort_field = params.sort_by if params.sort_by in ["created_at", "confidence"] else "created_at"
    sort_order = -1 if params.sort_order == "desc" else 1

    # Query with pagination
    cursor = (
        proposed_changes_collection.find(filter_query)
        .sort(sort_field, sort_order)
        .skip(params.offset)
        .limit(params.limit)
    )

    proposed_changes = [_convert_proposed_change_doc_to_response(doc) for doc in cursor]

    return ProposedChangeListResponse(
        proposed_changes=proposed_changes,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_update_proposed_change(proposal_id: UUID, params: ProposedChangeUpdate) -> ProposedChangeResponse:
    """
    Update a ProposedChange status (accept or reject).

    Authority: CanonKeeper only
    Use Case: DL-5

    Valid status transitions: pending → accepted OR pending → rejected
    Once accepted or rejected, status cannot be changed.

    Args:
        proposal_id: UUID of the proposal to update
        params: Update parameters with new status and decision metadata

    Returns:
        ProposedChangeResponse with updated proposal data

    Raises:
        ValueError: If proposal doesn't exist or invalid status transition
    """
    mongo_client = get_mongodb_client()
    proposed_changes_collection = mongo_client.get_collection("proposed_changes")

    # Verify proposal exists
    proposal_doc = proposed_changes_collection.find_one({"proposal_id": str(proposal_id)})
    if not proposal_doc:
        raise ValueError(f"Proposal {proposal_id} not found")

    # Validate status transition
    current_status = ProposalStatus(proposal_doc["status"])
    new_status = params.status

    # Only allow transitions from pending to accepted or rejected
    if current_status != ProposalStatus.PENDING:
        raise ValueError(
            f"Cannot update proposal with status {current_status.value}. "
            f"Only pending proposals can be accepted or rejected."
        )

    if new_status not in [ProposalStatus.ACCEPTED, ProposalStatus.REJECTED]:
        raise ValueError(
            f"Invalid status transition to {new_status.value}. "
            f"Can only transition from pending to accepted or rejected."
        )

    # Build update document
    updated_at = datetime.now(UTC)
    decision_metadata_doc = {
        "decided_by": params.decision_metadata.decided_by,
        "decided_at": params.decision_metadata.decided_at,
        "reason": params.decision_metadata.reason,
        "canonical_ref": (
            str(params.decision_metadata.canonical_ref) if params.decision_metadata.canonical_ref else None
        ),
    }

    update_doc = {
        "status": new_status.value,
        "decision_metadata": decision_metadata_doc,
        "updated_at": updated_at,
    }

    # Update proposal
    proposed_changes_collection.update_one({"proposal_id": str(proposal_id)}, {"$set": update_doc})

    # Return updated proposal
    updated_proposal = mongodb_get_proposed_change(proposal_id)
    if updated_proposal is None:
        raise ValueError(f"Proposal {proposal_id} not found after update")

    return updated_proposal
