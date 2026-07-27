"""
MongoDB tools for Entity Merge Candidates (I-13: Cross-Source Synthesis).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

Provides tools for:
- Detecting and listing merge candidates across sources
- Storing and retrieving merge candidate groups
- Creating merge proposals for CanonKeeper review
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.merge_candidates import (
    EntityMergeCandidate,
    MergeConfidence,
    MergeProposal,
    MergeProposalStatus,
)
from monitor_data.utils.entity_similarity import find_merge_candidates as _find_candidates

# =============================================================================
# MERGE CANDIDATE OPERATIONS
# =============================================================================


def _coerce_merge_confidence(value: float) -> MergeConfidence:
    """Convert numeric confidence to enum level."""
    if value > 0.85:
        return MergeConfidence.HIGH
    elif value >= 0.7:
        return MergeConfidence.MEDIUM
    elif value >= 0.5:
        return MergeConfidence.LOW
    return MergeConfidence.UNCERTAIN


def _convert_candidate_doc_to_model(
    doc: dict[str, Any],
) -> EntityMergeCandidate:
    """Convert MongoDB document to EntityMergeCandidate model."""
    return EntityMergeCandidate(
        candidate_id=UUID(doc["candidate_id"]),
        universe_id=UUID(doc["universe_id"]),
        entity_ids=[UUID(e) for e in doc["entity_ids"]],
        merge_confidence=doc["merge_confidence"],
        confidence_level=_coerce_merge_confidence(doc["merge_confidence"]),
        similarity_metrics=doc.get("similarity_metrics", {}),
        conflicting_fields=doc.get("conflicting_fields", []),
        agreed_fields=doc.get("agreed_fields", []),
        source_pack_ids=[UUID(p) for p in doc.get("source_pack_ids", [])],
        created_at=doc["created_at"],
        reviewed_at=doc.get("reviewed_at"),
    )


def mongodb_list_merge_candidates(
    universe_id: UUID,
    min_confidence: float = 0.7,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[EntityMergeCandidate]:
    """
    List merge candidates for a universe.

    Args:
        universe_id: Target universe
        min_confidence: Minimum merge confidence to return
        status: Optional filter by review status (None for unreviewed)
        limit: Max results to return
        offset: Pagination offset

    Returns:
        List of EntityMergeCandidate
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("entity_merge_candidates")

    query: dict[str, Any] = {
        "universe_id": str(universe_id),
        "merge_confidence": {"$gte": min_confidence},
    }
    if status:
        query["status"] = status

    cursor = collection.find(query).sort("merge_confidence", -1).skip(offset).limit(limit)

    return [_convert_candidate_doc_to_model(doc) for doc in cursor]


def mongodb_get_merge_candidate(
    candidate_id: UUID,
) -> EntityMergeCandidate | None:
    """
    Get a single merge candidate by ID.

    Args:
        candidate_id: Candidate ID to retrieve

    Returns:
        EntityMergeCandidate or None if not found
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("entity_merge_candidates")

    doc = collection.find_one({"candidate_id": str(candidate_id)})
    if not doc:
        return None

    return _convert_candidate_doc_to_model(doc)


def mongodb_save_merge_candidate(
    candidate: EntityMergeCandidate,
) -> EntityMergeCandidate:
    """
    Save a merge candidate to MongoDB.

    Args:
        candidate: Candidate to save

    Returns:
        Saved EntityMergeCandidate
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("entity_merge_candidates")

    doc = {
        "candidate_id": str(candidate.candidate_id),
        "universe_id": str(candidate.universe_id),
        "entity_ids": [str(e) for e in candidate.entity_ids],
        "merge_confidence": candidate.merge_confidence,
        "similarity_metrics": candidate.similarity_metrics,
        "conflicting_fields": candidate.conflicting_fields,
        "agreed_fields": candidate.agreed_fields,
        "source_pack_ids": [str(p) for p in candidate.source_pack_ids],
        "created_at": candidate.created_at,
        "reviewed_at": candidate.reviewed_at,
        "status": "pending",
    }

    collection.update_one(
        {"candidate_id": doc["candidate_id"]},
        {"$set": doc},
        upsert=True,
    )

    return candidate


def mongodb_mark_candidate_reviewed(
    candidate_id: UUID,
) -> bool:
    """
    Mark a merge candidate as reviewed by user.

    Args:
        candidate_id: Candidate that was reviewed

    Returns:
        True if updated, False if not found
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("entity_merge_candidates")

    result = collection.update_one(
        {"candidate_id": str(candidate_id)},
        {
            "$set": {
                "reviewed_at": datetime.now(UTC),
                "status": "reviewed",
            }
        },
    )

    return result.modified_count > 0


def mongodb_delete_merge_candidate(
    candidate_id: UUID,
) -> bool:
    """
    Delete a merge candidate.

    Args:
        candidate_id: Candidate to delete

    Returns:
        True if deleted, False if not found
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("entity_merge_candidates")

    result = collection.delete_one({"candidate_id": str(candidate_id)})
    return result.deleted_count > 0


# =============================================================================
# MERGE DETECTION FROM ENTITIES
# =============================================================================


def mongodb_detect_merge_candidates(
    entities: list[dict[str, Any]],
    universe_id: UUID,
    min_confidence: float = 0.7,
) -> list[EntityMergeCandidate]:
    """
    Detect merge candidates from a list of entity dicts.

    This runs similarity detection on entities (e.g., from multiple packs)
    and returns candidate groups.

    Args:
        entities: List of entity dicts with 'id', 'name', 'entity_type', etc.
        universe_id: Universe these entities belong to
        min_confidence: Minimum similarity threshold

    Returns:
        List of EntityMergeCandidate
    """
    raw_candidates = _find_candidates(entities, min_confidence=min_confidence)

    candidates = []
    for raw in raw_candidates:
        # Collect source pack IDs from entities
        source_pack_ids = set()
        for e in entities:
            if str(e["id"]) in [str(id) for id in raw["entity_ids"]] and "pack_id" in e:
                source_pack_ids.add(e["pack_id"])

        entity_ids = [UUID(e_id) for e_id in raw["entity_ids"]]
        metrics = raw["similarity_metrics"]

        # Determine conflicting and agreed fields
        conflicting = []
        agreed: list[Any] = []
        if "properties" in metrics and metrics["properties"] < 1.0:
            conflicting.append("properties")
        if "description" in metrics and metrics["description"] < 0.85:
            conflicting.append("description")
        if "entity_type" in metrics and metrics["entity_type"] < 1.0:
            conflicting.append("entity_type")

        candidate = EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=universe_id,
            entity_ids=entity_ids,
            merge_confidence=raw["merge_confidence"],
            confidence_level=_coerce_merge_confidence(raw["merge_confidence"]),
            similarity_metrics=metrics,
            conflicting_fields=conflicting,
            agreed_fields=agreed,
            source_pack_ids=[UUID(p) for p in source_pack_ids],
            created_at=datetime.now(UTC),
        )
        candidates.append(candidate)

    return candidates


# =============================================================================
# MERGE PROPOSAL OPERATIONS
# =============================================================================


def mongodb_create_merge_proposal(
    merged_name: str,
    merged_entity_type: str,
    merged_description: str,
    merged_properties: dict[str, Any],
    merged_tags: list[str],
    source_entity_ids: list[UUID],
    source_pack_ids: list[UUID],
    resolution_notes: dict[str, str],
    universe_id: UUID,
    candidate_id: UUID | None = None,
    user_reviewed_confidence: float = 1.0,
) -> MergeProposal:
    """
    Create a merge proposal for CanonKeeper review.

    This doesn't directly merge - it creates a proposal document that
    CanonKeeper will evaluate and apply if approved.

    Args:
        merged_name: Name for the merged entity
        merged_entity_type: Entity type for the merged entity
        merged_description: Description for the merged entity
        merged_properties: Properties for the merged entity
        merged_tags: Tags for the merged entity
        source_entity_ids: Entities being merged (for traceability)
        source_pack_ids: Packs that contributed source entities
        resolution_notes: User's notes on each field decision
        universe_id: Target universe for the merge
        candidate_id: Optional source candidate ID
        user_reviewed_confidence: Confidence after user review

    Returns:
        MergeProposal ready for CanonKeeper
    """
    proposal_id = uuid4()
    created_at = datetime.now(UTC)

    proposal = MergeProposal(
        proposal_id=proposal_id,
        candidate_id=candidate_id or uuid4(),
        universe_id=universe_id,
        status=MergeProposalStatus.PENDING,
        merged_entity_name=merged_name,
        merged_entity_type=merged_entity_type,
        merged_description=merged_description,
        merged_properties=merged_properties,
        merged_tags=merged_tags,
        source_entity_ids=source_entity_ids,
        source_pack_ids=source_pack_ids,
        resolution_notes=resolution_notes,
        user_reviewed_confidence=user_reviewed_confidence,
        created_at=created_at,
        updated_at=created_at,
    )

    # Store in MongoDB
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("merge_proposals")

    doc = {
        "proposal_id": str(proposal.proposal_id),
        "candidate_id": str(proposal.candidate_id),
        "universe_id": str(proposal.universe_id),
        "status": proposal.status.value,
        "merged_entity_name": proposal.merged_entity_name,
        "merged_entity_type": proposal.merged_entity_type,
        "merged_description": proposal.merged_description,
        "merged_properties": proposal.merged_properties,
        "merged_tags": proposal.merged_tags,
        "source_entity_ids": [str(e) for e in proposal.source_entity_ids],
        "source_pack_ids": [str(p) for p in proposal.source_pack_ids],
        "resolution_notes": proposal.resolution_notes,
        "user_reviewed_confidence": proposal.user_reviewed_confidence,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }

    collection.insert_one(doc)
    return proposal


def mongodb_get_merge_proposal(
    proposal_id: UUID,
) -> MergeProposal | None:
    """
    Get a merge proposal by ID.

    Args:
        proposal_id: Proposal to retrieve

    Returns:
        MergeProposal or None if not found
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("merge_proposals")

    doc = collection.find_one({"proposal_id": str(proposal_id)})
    if not doc:
        return None

    return MergeProposal(
        proposal_id=UUID(doc["proposal_id"]),
        candidate_id=UUID(doc["candidate_id"]),
        universe_id=UUID(doc["universe_id"]),
        status=MergeProposalStatus(doc["status"]),
        merged_entity_name=doc["merged_entity_name"],
        merged_entity_type=doc["merged_entity_type"],
        merged_description=doc["merged_description"],
        merged_properties=doc.get("merged_properties", {}),
        merged_tags=doc.get("merged_tags", []),
        source_entity_ids=[UUID(e) for e in doc["source_entity_ids"]],
        source_pack_ids=[UUID(p) for p in doc.get("source_pack_ids", [])],
        resolution_notes=doc.get("resolution_notes", {}),
        user_reviewed_confidence=doc.get("user_reviewed_confidence", 1.0),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def mongodb_list_merge_proposals(
    universe_id: UUID,
    status: MergeProposalStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[MergeProposal]:
    """
    List merge proposals for a universe.

    Args:
        universe_id: Target universe
        status: Optional filter by status
        limit: Max results
        offset: Pagination offset

    Returns:
        List of MergeProposal
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("merge_proposals")

    query: dict[str, Any] = {"universe_id": str(universe_id)}
    if status:
        query["status"] = status.value

    cursor = collection.find(query).sort("created_at", -1).skip(offset).limit(limit)

    proposals = []
    for doc in cursor:
        proposals.append(
            MergeProposal(
                proposal_id=UUID(doc["proposal_id"]),
                candidate_id=UUID(doc["candidate_id"]),
                universe_id=UUID(doc["universe_id"]),
                status=MergeProposalStatus(doc["status"]),
                merged_entity_name=doc["merged_entity_name"],
                merged_entity_type=doc["merged_entity_type"],
                merged_description=doc["merged_description"],
                merged_properties=doc.get("merged_properties", {}),
                merged_tags=doc.get("merged_tags", []),
                source_entity_ids=[UUID(e) for e in doc["source_entity_ids"]],
                source_pack_ids=[UUID(p) for p in doc.get("source_pack_ids", [])],
                resolution_notes=doc.get("resolution_notes", {}),
                user_reviewed_confidence=doc.get("user_reviewed_confidence", 1.0),
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )
        )

    return proposals


def mongodb_update_merge_proposal_status(
    proposal_id: UUID,
    status: MergeProposalStatus,
) -> bool:
    """
    Update the status of a merge proposal.

    Args:
        proposal_id: Proposal to update
        status: New status

    Returns:
        True if updated, False if not found
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("merge_proposals")

    result = collection.update_one(
        {"proposal_id": str(proposal_id)},
        {
            "$set": {
                "status": status.value,
                "updated_at": datetime.now(UTC),
            }
        },
    )

    return result.modified_count > 0
