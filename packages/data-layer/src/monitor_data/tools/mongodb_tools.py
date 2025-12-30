"""
MongoDB MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose MongoDB operations via the MCP server.
MongoDB stores narrative artifacts (scenes, turns) and proposals.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.scenes import (
    SceneCreate,
    SceneUpdate,
    SceneResponse,
    SceneFilter,
    SceneListResponse,
    TurnCreate,
    TurnResponse,
)
from monitor_data.schemas.proposed_changes import (
    ProposedChangeCreate,
    ProposedChangeUpdate,
    ProposedChangeResponse,
    ProposedChangeFilter,
    ProposedChangeListResponse,
    Evidence,
    DecisionMetadata,
)
from monitor_data.schemas.base import SceneStatus, ProposalStatus


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _convert_turn_dict_to_response(turn_dict: Dict[str, Any]) -> TurnResponse:
    """
    Convert a turn dictionary from MongoDB to a TurnResponse object.

    Args:
        turn_dict: Turn data from MongoDB document

    Returns:
        TurnResponse object
    """
    return TurnResponse(
        turn_id=UUID(turn_dict["turn_id"]),
        speaker=turn_dict["speaker"],
        entity_id=UUID(turn_dict["entity_id"]) if turn_dict.get("entity_id") else None,
        text=turn_dict["text"],
        timestamp=turn_dict["timestamp"],
        resolution_ref=(
            UUID(turn_dict["resolution_ref"])
            if turn_dict.get("resolution_ref")
            else None
        ),
    )


def _convert_scene_doc_to_response(scene_doc: Dict[str, Any]) -> SceneResponse:
    """
    Convert a scene document from MongoDB to a SceneResponse object.

    Args:
        scene_doc: Scene data from MongoDB document

    Returns:
        SceneResponse object
    """
    # Convert turns from dict to TurnResponse
    turns = [
        _convert_turn_dict_to_response(turn_dict)
        for turn_dict in scene_doc.get("turns", [])
    ]

    return SceneResponse(
        scene_id=UUID(scene_doc["scene_id"]),
        story_id=UUID(scene_doc["story_id"]),
        universe_id=UUID(scene_doc["universe_id"]),
        title=scene_doc["title"],
        purpose=scene_doc["purpose"],
        status=SceneStatus(scene_doc["status"]),
        order=scene_doc.get("order"),
        location_ref=(
            UUID(scene_doc["location_ref"]) if scene_doc.get("location_ref") else None
        ),
        participating_entities=[
            UUID(eid) for eid in scene_doc.get("participating_entities", [])
        ],
        turns=turns,
        proposed_changes=[UUID(pid) for pid in scene_doc.get("proposed_changes", [])],
        canonical_outcomes=[
            UUID(cid) for cid in scene_doc.get("canonical_outcomes", [])
        ],
        summary=scene_doc.get("summary", ""),
        created_at=scene_doc["created_at"],
        updated_at=scene_doc["updated_at"],
        completed_at=scene_doc.get("completed_at"),
    )


# =============================================================================
# SCENE OPERATIONS
# =============================================================================


def mongodb_create_scene(params: SceneCreate) -> SceneResponse:
    """
    Create a new Scene document in MongoDB.

    Authority: CanonKeeper and Narrator agents
    Use Case: DL-4

    Args:
        params: Scene creation parameters

    Returns:
        SceneResponse with created scene data

    Raises:
        ValueError: If story_id doesn't exist in Neo4j or universe_id is invalid
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify story exists in Neo4j
    verify_story_query = """
    MATCH (s:Story {id: $story_id})
    MATCH (u:Universe {id: $universe_id})
    RETURN s.id as story_id, u.id as universe_id
    """
    result = neo4j_client.execute_read(
        verify_story_query,
        {"story_id": str(params.story_id), "universe_id": str(params.universe_id)},
    )
    if not result:
        raise ValueError(
            f"Story {params.story_id} or Universe {params.universe_id} not found"
        )

    # Verify participating entities if provided
    if params.participating_entities:
        entity_check_query = """
        MATCH (e {id: $entity_id})
        WHERE e:EntityArchetype OR e:EntityInstance
        RETURN e.id as id
        """
        for entity_id in params.participating_entities:
            result = neo4j_client.execute_read(
                entity_check_query, {"entity_id": str(entity_id)}
            )
            if not result:
                raise ValueError(f"Entity {entity_id} not found")

    # Verify location_ref if provided
    if params.location_ref:
        location_check_query = """
        MATCH (e:EntityInstance {id: $location_id})
        RETURN e.id as id
        """
        result = neo4j_client.execute_read(
            location_check_query, {"location_id": str(params.location_ref)}
        )
        if not result:
            raise ValueError(f"Location entity {params.location_ref} not found")

    # Create scene in MongoDB
    scene_id = uuid4()
    created_at = datetime.now(timezone.utc)

    scene_doc = {
        "scene_id": str(scene_id),
        "story_id": str(params.story_id),
        "universe_id": str(params.universe_id),
        "title": params.title,
        "purpose": params.purpose,
        "status": params.status.value,
        "order": params.order,
        "location_ref": str(params.location_ref) if params.location_ref else None,
        "participating_entities": [str(eid) for eid in params.participating_entities],
        "turns": [],
        "proposed_changes": [],
        "canonical_outcomes": [],
        "summary": "",
        "created_at": created_at,
        "updated_at": created_at,
        "completed_at": None,
    }

    scenes_collection = mongo_client.get_collection("scenes")
    scenes_collection.insert_one(scene_doc)

    return SceneResponse(
        scene_id=scene_id,
        story_id=params.story_id,
        universe_id=params.universe_id,
        title=params.title,
        purpose=params.purpose,
        status=params.status,
        order=params.order,
        location_ref=params.location_ref,
        participating_entities=params.participating_entities,
        turns=[],
        proposed_changes=[],
        canonical_outcomes=[],
        summary="",
        created_at=created_at,
        updated_at=created_at,
        completed_at=None,
    )


def mongodb_get_scene(scene_id: UUID) -> Optional[SceneResponse]:
    """
    Retrieve a Scene by ID with all turns.

    Authority: All agents
    Use Case: DL-4

    Args:
        scene_id: UUID of the scene to retrieve

    Returns:
        SceneResponse if found, None otherwise
    """
    mongo_client = get_mongodb_client()
    scenes_collection = mongo_client.get_collection("scenes")

    scene_doc = scenes_collection.find_one({"scene_id": str(scene_id)})
    if not scene_doc:
        return None

    return _convert_scene_doc_to_response(scene_doc)


def mongodb_update_scene(scene_id: UUID, params: SceneUpdate) -> SceneResponse:
    """
    Update a Scene's mutable fields with status transition enforcement.

    Authority: CanonKeeper and Narrator agents
    Use Case: DL-4

    Valid status transitions: active → finalizing → completed

    Args:
        scene_id: UUID of the scene to update
        params: Fields to update

    Returns:
        SceneResponse with updated scene data

    Raises:
        ValueError: If scene doesn't exist or invalid status transition
    """
    mongo_client = get_mongodb_client()
    scenes_collection = mongo_client.get_collection("scenes")

    # Verify scene exists
    scene_doc = scenes_collection.find_one({"scene_id": str(scene_id)})
    if not scene_doc:
        raise ValueError(f"Scene {scene_id} not found")

    # Validate status transition if status is being updated
    if params.status is not None:
        current_status = SceneStatus(scene_doc["status"])
        new_status = params.status

        # Define valid transitions
        valid_transitions = {
            SceneStatus.ACTIVE: [SceneStatus.FINALIZING, SceneStatus.COMPLETED],
            SceneStatus.FINALIZING: [SceneStatus.COMPLETED],
            SceneStatus.COMPLETED: [],  # No transitions from completed
        }

        if new_status != current_status:
            if new_status not in valid_transitions.get(current_status, []):
                raise ValueError(
                    f"Invalid status transition from {current_status.value} to {new_status.value}. "
                    f"Valid transitions: {[s.value for s in valid_transitions.get(current_status, [])]}"
                )

    # Build update document
    update_doc: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}

    if params.title is not None:
        update_doc["title"] = params.title

    if params.purpose is not None:
        update_doc["purpose"] = params.purpose

    if params.status is not None:
        update_doc["status"] = params.status.value
        # If completing the scene, set completed_at
        if params.status == SceneStatus.COMPLETED:
            update_doc["completed_at"] = datetime.now(timezone.utc)

    if params.summary is not None:
        update_doc["summary"] = params.summary

    # Update scene
    scenes_collection.update_one({"scene_id": str(scene_id)}, {"$set": update_doc})

    # Return updated scene
    updated_scene = mongodb_get_scene(scene_id)
    if updated_scene is None:
        raise ValueError(f"Scene {scene_id} not found after update")

    return updated_scene


def mongodb_list_scenes(params: SceneFilter) -> SceneListResponse:
    """
    List scenes with filtering, sorting, and pagination.

    Authority: All agents
    Use Case: DL-4

    Args:
        params: Filter and pagination parameters

    Returns:
        SceneListResponse with list of scenes and pagination info
    """
    mongo_client = get_mongodb_client()
    scenes_collection = mongo_client.get_collection("scenes")

    # Build filter query
    filter_query: Dict[str, Any] = {}

    if params.story_id is not None:
        filter_query["story_id"] = str(params.story_id)

    if params.universe_id is not None:
        filter_query["universe_id"] = str(params.universe_id)

    if params.status is not None:
        filter_query["status"] = params.status.value

    # Count total matching documents
    total = scenes_collection.count_documents(filter_query)

    # Build sort
    sort_field = (
        params.sort_by if params.sort_by in ["created_at", "order"] else "created_at"
    )
    sort_order = -1 if params.sort_order == "desc" else 1

    # Query with pagination
    cursor = (
        scenes_collection.find(filter_query)
        .sort(sort_field, sort_order)
        .skip(params.offset)
        .limit(params.limit)
    )

    scenes = [_convert_scene_doc_to_response(scene_doc) for scene_doc in cursor]

    return SceneListResponse(
        scenes=scenes, total=total, limit=params.limit, offset=params.offset
    )


def mongodb_append_turn(scene_id: UUID, params: TurnCreate) -> TurnResponse:
    """
    Append a turn to a scene with proper ordering.

    Authority: * (all agents; typically Narrator and Orchestrator)
    Use Case: DL-4

    Args:
        scene_id: UUID of the scene to append turn to
        params: Turn creation parameters

    Returns:
        TurnResponse with created turn data

    Raises:
        ValueError: If scene doesn't exist or scene is completed
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()
    scenes_collection = mongo_client.get_collection("scenes")

    # Verify scene exists
    scene_doc = scenes_collection.find_one({"scene_id": str(scene_id)})
    if not scene_doc:
        raise ValueError(f"Scene {scene_id} not found")

    # Check scene is not completed
    if scene_doc["status"] == SceneStatus.COMPLETED.value:
        raise ValueError(f"Cannot append turn to completed scene {scene_id}")

    # Verify entity_id if speaker is entity
    if params.entity_id:
        entity_check_query = """
        MATCH (e {id: $entity_id})
        WHERE e:EntityArchetype OR e:EntityInstance
        RETURN e.id as id
        """
        result = neo4j_client.execute_read(
            entity_check_query, {"entity_id": str(params.entity_id)}
        )
        if not result:
            raise ValueError(f"Entity {params.entity_id} not found")

    # Create turn
    turn_id = uuid4()
    timestamp = datetime.now(timezone.utc)

    turn_doc = {
        "turn_id": str(turn_id),
        "speaker": params.speaker.value,
        "entity_id": str(params.entity_id) if params.entity_id else None,
        "text": params.text,
        "timestamp": timestamp,
        "resolution_ref": None,
    }

    # Append turn to scene
    scenes_collection.update_one(
        {"scene_id": str(scene_id)},
        {"$push": {"turns": turn_doc}, "$set": {"updated_at": timestamp}},
    )

    return TurnResponse(
        turn_id=turn_id,
        speaker=params.speaker,
        entity_id=params.entity_id,
        text=params.text,
        timestamp=timestamp,
        resolution_ref=None,
    )


# =============================================================================
# PROPOSED CHANGE OPERATIONS
# =============================================================================


def _convert_proposed_change_doc_to_response(
    doc: Dict[str, Any],
) -> ProposedChangeResponse:
    """
    Convert a proposed change document from MongoDB to a ProposedChangeResponse.

    Args:
        doc: ProposedChange data from MongoDB document

    Returns:
        ProposedChangeResponse object
    """
    # Convert evidence list
    evidence = [
        Evidence(type=e["type"], ref_id=UUID(e["ref_id"]))
        for e in doc.get("evidence", [])
    ]

    # Convert decision metadata if present
    decision_metadata = None
    if doc.get("decision_metadata"):
        dm = doc["decision_metadata"]
        decision_metadata = DecisionMetadata(
            decided_by=dm["decided_by"],
            decided_at=dm["decided_at"],
            reason=dm["reason"],
            canonical_ref=(
                UUID(dm["canonical_ref"]) if dm.get("canonical_ref") else None
            ),
        )

    return ProposedChangeResponse(
        proposal_id=UUID(doc["proposal_id"]),
        scene_id=UUID(doc["scene_id"]) if doc.get("scene_id") else None,
        story_id=UUID(doc["story_id"]) if doc.get("story_id") else None,
        turn_id=UUID(doc["turn_id"]) if doc.get("turn_id") else None,
        change_type=doc["change_type"],
        content=doc["content"],
        evidence=evidence,
        confidence=doc["confidence"],
        authority=doc["authority"],
        proposer=doc["proposer"],
        status=ProposalStatus(doc["status"]),
        decision_metadata=decision_metadata,
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
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
        result = neo4j_client.execute_read(
            story_query, {"story_id": str(params.story_id)}
        )
        if not result:
            raise ValueError(f"Story {params.story_id} not found")

    # Create proposal
    proposal_id = uuid4()
    created_at = datetime.now(timezone.utc)

    proposal_doc = {
        "proposal_id": str(proposal_id),
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "story_id": str(params.story_id) if params.story_id else None,
        "turn_id": str(params.turn_id) if params.turn_id else None,
        "change_type": params.change_type.value,
        "content": params.content,
        "evidence": [
            {"type": e.type, "ref_id": str(e.ref_id)} for e in params.evidence
        ],
        "confidence": params.confidence,
        "authority": params.authority.value,
        "proposer": params.proposer,
        "status": ProposalStatus.PENDING.value,
        "decision_metadata": None,
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
        created_at=created_at,
        updated_at=created_at,
    )


def mongodb_get_proposed_change(proposal_id: UUID) -> Optional[ProposedChangeResponse]:
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

    proposal_doc = proposed_changes_collection.find_one(
        {"proposal_id": str(proposal_id)}
    )
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
    filter_query: Dict[str, Any] = {}

    if params.scene_id is not None:
        filter_query["scene_id"] = str(params.scene_id)

    if params.story_id is not None:
        filter_query["story_id"] = str(params.story_id)

    if params.status is not None:
        filter_query["status"] = params.status.value

    if params.change_type is not None:
        filter_query["change_type"] = params.change_type.value

    # Count total matching documents
    total = proposed_changes_collection.count_documents(filter_query)

    # Build sort
    sort_field = (
        params.sort_by
        if params.sort_by in ["created_at", "confidence"]
        else "created_at"
    )
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


def mongodb_update_proposed_change(
    proposal_id: UUID, params: ProposedChangeUpdate
) -> ProposedChangeResponse:
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
    proposal_doc = proposed_changes_collection.find_one(
        {"proposal_id": str(proposal_id)}
    )
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
    updated_at = datetime.now(timezone.utc)
    decision_metadata_doc = {
        "decided_by": params.decision_metadata.decided_by,
        "decided_at": params.decision_metadata.decided_at,
        "reason": params.decision_metadata.reason,
        "canonical_ref": (
            str(params.decision_metadata.canonical_ref)
            if params.decision_metadata.canonical_ref
            else None
        ),
    }

    update_doc = {
        "status": new_status.value,
        "decision_metadata": decision_metadata_doc,
        "updated_at": updated_at,
    }

    # Update proposal
    proposed_changes_collection.update_one(
        {"proposal_id": str(proposal_id)}, {"$set": update_doc}
    )

    # Return updated proposal
    updated_proposal = mongodb_get_proposed_change(proposal_id)
    if updated_proposal is None:
        raise ValueError(f"Proposal {proposal_id} not found after update")

    return updated_proposal
