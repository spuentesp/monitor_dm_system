"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

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
from monitor_data.tenancy import assert_proposal_target_write, assert_proposal_write

log = structlog.get_logger()

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
        deferred=bool(doc.get("deferred", False)),
        defer_reason=doc.get("defer_reason"),
        edit_reason=doc.get("edit_reason"),
        needs_review=bool(doc.get("needs_review", False)),
        review_reason=doc.get("review_reason"),
        review_source=doc.get("review_source"),
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
    assert_proposal_target_write(
        scene_id=params.scene_id,
        story_id=params.story_id,
        content=params.content,
        source=params.source,
        proposer=params.proposer,
        resource="proposed_change",
    )
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
        "source": params.source,
        "proposal_type": params.proposal_type,
        "status": ProposalStatus.PENDING.value,
        "decision_metadata": None,
        "promotion_intent": params.promotion_intent.value if params.promotion_intent else None,
        "interaction_count": params.interaction_count,
        "is_mechanically_bound": params.is_mechanically_bound,
        "needs_review": params.needs_review,
        "review_reason": params.review_reason,
        "review_source": params.review_source,
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
        source=params.source,
        proposal_type=params.proposal_type,
        status=ProposalStatus.PENDING,
        decision_metadata=None,
        promotion_intent=params.promotion_intent,
        interaction_count=params.interaction_count,
        is_mechanically_bound=params.is_mechanically_bound,
        needs_review=params.needs_review,
        review_reason=params.review_reason,
        review_source=params.review_source,
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
    if params.needs_review is not None:
        filter_query["needs_review"] = params.needs_review

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


def mongodb_flag_proposal_review(
    proposal_id: UUID,
    needs_review: bool = True,
    reason: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """
    Stamp (or clear) the advisory review flag on a proposal.

    Authority: CanonKeeper only
    Collection: proposed_changes

    G-9 Phase 2. This never changes the proposal's status and never blocks
    acceptance — it only makes the proposal visible to a human reviewer. The
    flag is set by the deterministic transition rules and, once Phase 3 lands,
    by the implication-level check too.

    Args:
        proposal_id: The proposal to flag.
        needs_review: True to flag, False to clear.
        reason: Why it was flagged (human-readable).
        source: Which rule flagged it (e.g. 'transition_rule').

    Returns:
        Dict with the proposal_id and the flag state.
    """
    assert_proposal_write(proposal_id, resource="proposed_change")
    client = get_mongodb_client()
    coll = client.get_collection("proposed_changes")
    if not coll.find_one({"proposal_id": str(proposal_id)}, {"proposal_id": 1}):
        raise ValueError(f"Proposal {proposal_id} not found")

    coll.update_one(
        {"proposal_id": str(proposal_id)},
        {
            "$set": {
                "needs_review": needs_review,
                "review_reason": reason,
                "review_source": source,
                "updated_at": datetime.now(UTC),
            }
        },
    )
    return {
        "proposal_id": str(proposal_id),
        "needs_review": needs_review,
        "review_reason": reason,
        "review_source": source,
    }


def mongodb_defer_proposed_change(
    proposal_id: UUID,
    reason: str,
    deferred_by: str = "GM",
) -> ProposedChangeResponse:
    """Mark a pending proposal as deferred without deciding it.

    Deferred proposals stay pending so they can still be edited, accepted, or
    rejected later. The reason is kept separate from decision metadata because
    no final verdict has been made.
    """
    assert_proposal_write(proposal_id, resource="proposed_change")
    mongo_client = get_mongodb_client()
    coll = mongo_client.get_collection("proposed_changes")
    doc = coll.find_one({"proposal_id": str(proposal_id)})
    if not doc:
        raise ValueError(f"Proposal {proposal_id} not found")
    current_status = _coerce_proposal_status(doc.get("status", ProposalStatus.PENDING.value))
    if current_status != ProposalStatus.PENDING:
        raise ValueError(
            f"Cannot defer proposal with status {current_status.value}. Only pending proposals can be deferred."
        )

    coll.update_one(
        {"proposal_id": str(proposal_id)},
        {
            "$set": {
                "deferred": True,
                "defer_reason": reason,
                "deferred_by": deferred_by,
                "updated_at": datetime.now(UTC),
            }
        },
    )
    updated = mongodb_get_proposed_change(proposal_id)
    if updated is None:
        raise ValueError(f"Proposal {proposal_id} not found after defer")
    return updated


def mongodb_edit_proposed_change(
    proposal_id: UUID,
    content_patch: dict[str, Any],
    reason: str | None = None,
    edited_by: str = "GM",
) -> ProposedChangeResponse:
    """Edit a pending proposal's content before a final verdict.

    The patch is merged shallowly into ``content`` and, when present, into the
    extraction ``payload`` used by CanonKeeper's commit handlers. This keeps
    "edit before accept" from silently changing only the display copy.
    """
    assert_proposal_write(proposal_id, resource="proposed_change")
    if not content_patch:
        raise ValueError("content_patch must not be empty")

    mongo_client = get_mongodb_client()
    coll = mongo_client.get_collection("proposed_changes")
    doc = coll.find_one({"proposal_id": str(proposal_id)})
    if not doc:
        raise ValueError(f"Proposal {proposal_id} not found")
    current_status = _coerce_proposal_status(doc.get("status", ProposalStatus.PENDING.value))
    if current_status != ProposalStatus.PENDING:
        raise ValueError(
            f"Cannot edit proposal with status {current_status.value}. "
            f"Only pending proposals can be edited before a verdict."
        )

    current_content = doc.get("content") or {}
    if not isinstance(current_content, dict):
        raise ValueError("Proposal content is not editable")
    new_content = {**current_content, **content_patch}
    if "statement" in content_patch and not str(new_content.get("statement") or "").strip():
        raise ValueError("statement must not be empty")

    updates: dict[str, Any] = {
        "content": new_content,
        "edit_reason": reason,
        "edited_by": edited_by,
        "updated_at": datetime.now(UTC),
    }
    current_payload = doc.get("payload")
    if isinstance(current_payload, dict):
        updates["payload"] = {**current_payload, **content_patch}

    coll.update_one({"proposal_id": str(proposal_id)}, {"$set": updates})
    updated = mongodb_get_proposed_change(proposal_id)
    if updated is None:
        raise ValueError(f"Proposal {proposal_id} not found after edit")
    return updated


def mongodb_retract_proposed_change(
    proposal_id: UUID,
    reason: str = "struck at the table",
    retracted_by: str = "GM",
    entry_id: str | None = None,
) -> ProposedChangeResponse:
    """Retract a pending proposal at the table (G03 — CF-1 amendment).

    Pending → rejected with ``decision_metadata.reason`` so CF-8 shows *why*
    the proposal disappeared (the plan's ``rejected_by_gm`` disposition:
    status ``rejected``, ``decided_by`` = the GM/retracting actor). ``entry_id``
    records which session entry this retract belongs to when it was caused by
    striking that entry.

    Authority: CaptureInsightAgent / CanonKeeper via MCP; GM correction flow.

    Raises:
        ValueError: proposal missing, or not pending (only pending can be
            retracted — an accepted/rejected verdict is terminal).
    """
    assert_proposal_write(proposal_id, resource="proposed_change")
    mongo_client = get_mongodb_client()
    coll = mongo_client.get_collection("proposed_changes")
    doc = coll.find_one({"proposal_id": str(proposal_id)})
    if not doc:
        raise ValueError(f"Proposal {proposal_id} not found")
    current_status = _coerce_proposal_status(doc.get("status", ProposalStatus.PENDING.value))
    if current_status != ProposalStatus.PENDING:
        raise ValueError(
            f"Cannot retract proposal with status {current_status.value}. Only pending proposals can be retracted."
        )

    updated_at = datetime.now(UTC)
    update_doc: dict[str, Any] = {
        "status": ProposalStatus.REJECTED.value,
        "decision_metadata": {
            "decided_by": retracted_by,
            "decided_at": updated_at,
            "reason": reason,
            "canonical_ref": None,
        },
        "updated_at": updated_at,
    }
    if entry_id is not None:
        update_doc["retracted_for_entry"] = entry_id
    coll.update_one({"proposal_id": str(proposal_id)}, {"$set": update_doc})
    log.info("proposal_retracted", proposal_id=str(proposal_id), entry_id=entry_id, reason=reason)

    updated = mongodb_get_proposed_change(proposal_id)
    if updated is None:
        raise ValueError(f"Proposal {proposal_id} not found after retract")
    return updated


def mongodb_restore_retracted_proposal(
    proposal_id: UUID,
    reason: str = "struck at the table",
    retracted_by: str = "GM",
) -> ProposedChangeResponse:
    """Undo a GM retract: rejected → pending, only for a matching retraction.

    Guards both ways: the proposal must be rejected, and its decision
    metadata must match the retract (actor + reason). A regular CF-8 rejection
    for any other reason is never flipped back. Used by the strike-undo flow
    (G03).

    Authority: CaptureInsightAgent / CanonKeeper via MCP; GM correction flow.

    Raises:
        ValueError: proposal missing, not rejected, or not the matching
            retract.
    """
    assert_proposal_write(proposal_id, resource="proposed_change")
    mongo_client = get_mongodb_client()
    coll = mongo_client.get_collection("proposed_changes")
    doc = coll.find_one({"proposal_id": str(proposal_id)})
    if not doc:
        raise ValueError(f"Proposal {proposal_id} not found")
    current_status = _coerce_proposal_status(doc.get("status", ProposalStatus.PENDING.value))
    if current_status != ProposalStatus.REJECTED:
        raise ValueError(
            f"Cannot restore proposal with status {current_status.value}. Only a rejected retract can be restored."
        )
    decision = doc.get("decision_metadata") or {}
    if str(decision.get("decided_by") or "") != retracted_by or str(decision.get("reason") or "") != reason:
        raise ValueError(
            f"Proposal {proposal_id} was not retracted by '{retracted_by}' with reason '{reason}'; refusing to restore."
        )

    updated_at = datetime.now(UTC)
    coll.update_one(
        {"proposal_id": str(proposal_id)},
        {
            "$set": {
                "status": ProposalStatus.PENDING.value,
                "decision_metadata": None,
                "updated_at": updated_at,
            },
            "$unset": {"retracted_for_entry": ""},
        },
    )
    log.info("proposal_retract_restored", proposal_id=str(proposal_id))
    updated = mongodb_get_proposed_change(proposal_id)
    if updated is None:
        raise ValueError(f"Proposal {proposal_id} not found after restore")
    return updated


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
    assert_proposal_write(proposal_id, resource="proposed_change")
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
