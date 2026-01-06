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
from monitor_data.schemas.base import (
    SceneStatus,
    ProposalStatus,
    CombatStatus,
    CombatSide,
)
from monitor_data.schemas.story_outlines import (
    StoryOutlineCreate,
    StoryOutlineUpdate,
    StoryOutlineResponse,
    StoryBeat,
    PacingMetrics,
    BranchingPoint,
    MysteryStructure,
    MysteryClue,
    BeatStatus,
)
from monitor_data.schemas.combat import (
    CombatCreate,
    CombatUpdate,
    CombatResponse,
    CombatFilter,
    CombatListResponse,
    CombatParticipant,
    AddCombatParticipant,
    UpdateCombatParticipant,
    RemoveCombatParticipant,
    CombatEnvironment,
    AddCombatLogEntry,
    CombatLogEntry,
    SetCombatOutcome,
    CombatOutcome,
    Condition,
)
from monitor_data.schemas.resolutions import (
    ResolutionCreate,
    ResolutionUpdate,
    ResolutionResponse,
    ResolutionFilter,
    ResolutionListResponse,
)
from monitor_data.schemas.memories import (
    MemoryCreate,
    MemoryUpdate,
    MemoryFilter,
    MemoryResponse,
    MemoryListResponse,
)
from monitor_data.schemas.party_inventory import (
    ItemCategory,
    SplitStatus,
    InventoryItem,
    PartyInventoryCreate,
    PartyInventoryResponse,
    AddInventoryItemRequest,
    RemoveInventoryItemRequest,
    TransferItemRequest,
    UpdateGoldRequest,
    SubParty,
    PartySplitCreate,
    PartySplitResponse,
    ResolvePartySplitRequest,
    ActiveSplitsResponse,
    SplitHistoryFilter,
    SplitHistoryResponse,
)


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


# =============================================================================
# STORY OUTLINE OPERATIONS (DL-6)
# =============================================================================


def _convert_story_outline_doc_to_response(doc: Dict[str, Any]) -> StoryOutlineResponse:
    """
    Convert a story_outline document from MongoDB to StoryOutlineResponse.

    Args:
        doc: Story outline document from MongoDB

    Returns:
        StoryOutlineResponse object
    """
    # Convert beats
    beats = []
    for beat_dict in doc.get("beats", []):
        beat = StoryBeat(
            beat_id=UUID(beat_dict["beat_id"]),
            title=beat_dict["title"],
            description=beat_dict["description"],
            order=beat_dict["order"],
            status=BeatStatus(beat_dict.get("status", "pending")),
            optional=beat_dict.get("optional", False),
            related_threads=[UUID(tid) for tid in beat_dict.get("related_threads", [])],
            required_for_threads=[
                UUID(tid) for tid in beat_dict.get("required_for_threads", [])
            ],
            created_at=beat_dict.get("created_at"),
            started_at=beat_dict.get("started_at"),
            completed_at=beat_dict.get("completed_at"),
            completed_in_scene_id=(
                UUID(beat_dict["completed_in_scene_id"])
                if beat_dict.get("completed_in_scene_id")
                else None
            ),
        )
        beats.append(beat)

    # Convert pacing metrics
    pacing_dict = doc.get("pacing_metrics", {})
    pacing = PacingMetrics(**pacing_dict) if pacing_dict else PacingMetrics()

    # Convert mystery structure if present
    mystery_structure = None
    if "mystery_structure" in doc and doc["mystery_structure"]:
        mystery_dict = doc["mystery_structure"]
        mystery_structure = MysteryStructure(
            truth=mystery_dict["truth"],
            question=mystery_dict["question"],
            core_clues=[
                MysteryClue(**clue) for clue in mystery_dict.get("core_clues", [])
            ],
            bonus_clues=[
                MysteryClue(**clue) for clue in mystery_dict.get("bonus_clues", [])
            ],
            red_herrings=[
                MysteryClue(**clue) for clue in mystery_dict.get("red_herrings", [])
            ],
            suspects=mystery_dict.get("suspects", []),
            current_player_theories=mystery_dict.get("current_player_theories", []),
        )

    # Convert branching points
    branching_points = [BranchingPoint(**bp) for bp in doc.get("branching_points", [])]

    return StoryOutlineResponse(
        story_id=UUID(doc["story_id"]),
        theme=doc.get("theme", ""),
        premise=doc.get("premise", ""),
        constraints=doc.get("constraints", []),
        beats=beats,
        structure_type=doc.get("structure_type", "linear"),
        template=doc.get("template", "custom"),
        branching_points=branching_points,
        mystery_structure=mystery_structure,
        pacing_metrics=pacing,
        open_threads=doc.get("open_threads", []),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _calculate_pacing_metrics(
    beats: list[StoryBeat], scenes_since_major_event: int = 0
) -> PacingMetrics:
    """
    Calculate pacing metrics from beats.

    Args:
        beats: List of story beats
        scenes_since_major_event: Counter for pacing

    Returns:
        Calculated pacing metrics
    """
    total_beats = len(beats)
    completed_beats = sum(1 for b in beats if b.status == BeatStatus.COMPLETED)
    in_progress_beats = sum(1 for b in beats if b.status == BeatStatus.IN_PROGRESS)

    # Calculate completion percentage
    estimated_completion = completed_beats / total_beats if total_beats > 0 else 0.0

    # Calculate tension based on active threads and progression
    # Simple heuristic: tension rises as we approach climax (80%+) or have many in-progress beats
    tension_level = 0.0
    if estimated_completion > 0.8:
        tension_level = min(1.0, 0.7 + (estimated_completion - 0.8) * 1.5)
    elif in_progress_beats > 0:
        tension_level = min(0.6, 0.3 + (in_progress_beats * 0.1))

    # Determine current act (simple three-act structure)
    if estimated_completion < 0.25:
        current_act = 1
    elif estimated_completion < 0.75:
        current_act = 2
    else:
        current_act = 3

    return PacingMetrics(
        current_act=current_act,
        tension_level=tension_level,
        scenes_since_major_event=scenes_since_major_event,
        scenes_in_current_act=0,  # Would need scene tracking
        estimated_completion=estimated_completion,
        last_updated=datetime.now(timezone.utc),
    )


def mongodb_create_story_outline(params: StoryOutlineCreate) -> StoryOutlineResponse:
    """
    Create a story outline for a story (DL-6).

    Authority: Orchestrator
    Use Case: P-1, ST-1

    Args:
        params: Story outline creation parameters

    Returns:
        Created story outline

    Raises:
        ValueError: If story doesn't exist in Neo4j
    """
    client = get_mongodb_client()
    neo4j_client = get_neo4j_client()
    outlines_collection = client.get_collection("story_outlines")

    # Verify story exists in Neo4j
    verify_query = "MATCH (s:Story {id: $story_id}) RETURN s.id as id"
    result = neo4j_client.execute_read(verify_query, {"story_id": str(params.story_id)})
    if not result:
        raise ValueError(f"Story {params.story_id} not found")

    # Check if outline already exists
    existing = outlines_collection.find_one({"story_id": str(params.story_id)})
    if existing:
        raise ValueError(f"Story outline for {params.story_id} already exists")

    # Calculate initial pacing metrics
    pacing = _calculate_pacing_metrics(params.beats)

    # Build document
    now = datetime.now(timezone.utc)
    doc = {
        "story_id": str(params.story_id),
        "theme": params.theme,
        "premise": params.premise,
        "constraints": params.constraints,
        "beats": [beat.model_dump(mode="json") for beat in params.beats],
        "structure_type": params.structure_type.value,
        "template": params.template.value,
        "branching_points": [
            bp.model_dump(mode="json") for bp in params.branching_points
        ],
        "mystery_structure": (
            params.mystery_structure.model_dump(mode="json")
            if params.mystery_structure
            else None
        ),
        "pacing_metrics": pacing.model_dump(mode="json"),
        "open_threads": [],  # Will be populated by plot threads
        "created_at": now,
        "updated_at": now,
    }

    # Insert
    outlines_collection.insert_one(doc)

    return _convert_story_outline_doc_to_response(doc)


def mongodb_get_story_outline(story_id: UUID) -> Optional[StoryOutlineResponse]:
    """
    Get story outline for a story (DL-6).

    Authority: All agents
    Use Case: P-2, ST-1

    Args:
        story_id: Story UUID

    Returns:
        Story outline or None if not found
    """
    client = get_mongodb_client()
    outlines_collection = client.get_collection("story_outlines")

    doc = outlines_collection.find_one({"story_id": str(story_id)})
    if not doc:
        return None

    return _convert_story_outline_doc_to_response(doc)


def mongodb_update_story_outline(
    story_id: UUID, params: StoryOutlineUpdate
) -> StoryOutlineResponse:
    """
    Update story outline with partial updates and beat manipulation (DL-6).

    Authority: Orchestrator
    Use Case: P-8, ST-1

    Supports:
    - Updating theme, premise, constraints, structure, template
    - Adding new beats
    - Removing beats by ID
    - Reordering beats
    - Updating existing beats
    - Updating mystery structure
    - Marking clues as discovered

    Beat operations are applied in this order:
    1. update_beats: Modify existing beats (preserves order)
    2. remove_beat_ids: Remove beats by ID
    3. add_beats: Append new beats to the end
    4. reorder_beats: Reorder all beats (must include ALL beat IDs)

    Note: reorder_beats requires all beat IDs to be included. Mixing
    reorder_beats with other beat operations in the same update may lead
    to unexpected results. It's recommended to either use reorder_beats
    alone or use other beat operations separately.

    Args:
        story_id: Story UUID
        params: Update parameters

    Returns:
        Updated story outline

    Raises:
        ValueError: If outline doesn't exist or beat operations invalid
    """
    client = get_mongodb_client()
    outlines_collection = client.get_collection("story_outlines")

    # Get existing document
    doc = outlines_collection.find_one({"story_id": str(story_id)})
    if not doc:
        raise ValueError(f"Story outline for {story_id} not found")

    # Build update document
    update_doc: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}

    # Update simple fields
    if params.theme is not None:
        update_doc["theme"] = params.theme
    if params.premise is not None:
        update_doc["premise"] = params.premise
    if params.constraints is not None:
        update_doc["constraints"] = params.constraints
    if params.structure_type is not None:
        update_doc["structure_type"] = params.structure_type.value
    if params.template is not None:
        update_doc["template"] = params.template.value

    # Handle beat operations
    current_beats = [StoryBeat(**b) for b in doc.get("beats", [])]

    # Update existing beats
    if params.update_beats:
        update_map = {str(b.beat_id): b for b in params.update_beats}
        for i, beat in enumerate(current_beats):
            beat_id_str = str(beat.beat_id)
            if beat_id_str in update_map:
                current_beats[i] = update_map[beat_id_str]

    # Remove beats
    if params.remove_beat_ids:
        remove_ids = {str(bid) for bid in params.remove_beat_ids}
        current_beats = [b for b in current_beats if str(b.beat_id) not in remove_ids]

    # Add beats
    if params.add_beats:
        current_beats.extend(params.add_beats)

    # Reorder beats
    if params.reorder_beats:
        beats_by_id = {str(b.beat_id): b for b in current_beats}
        if len(params.reorder_beats) != len(beats_by_id):
            raise ValueError(
                f"reorder_beats must include all {len(beats_by_id)} beat IDs. "
                f"Got {len(params.reorder_beats)} IDs instead."
            )
        reordered: list[StoryBeat] = []
        for beat_id in params.reorder_beats:
            beat_id_str = str(beat_id)
            if beat_id_str not in beats_by_id:
                raise ValueError(f"Beat ID {beat_id} not found in current beats")
            beat = beats_by_id[beat_id_str]
            beat.order = len(reordered)
            reordered.append(beat)
        current_beats = reordered

    update_doc["beats"] = [beat.model_dump(mode="json") for beat in current_beats]

    # Recalculate pacing metrics
    pacing = _calculate_pacing_metrics(
        current_beats, doc.get("pacing_metrics", {}).get("scenes_since_major_event", 0)
    )
    update_doc["pacing_metrics"] = pacing.model_dump(mode="json")

    # Update mystery structure
    if params.update_mystery_structure:
        update_doc["mystery_structure"] = params.update_mystery_structure.model_dump(
            mode="json"
        )

    # Mark clue as discovered
    if params.mark_clue_discovered and "mystery_structure" in doc:
        mystery = doc["mystery_structure"]
        if mystery is None:
            raise ValueError(
                "Cannot mark clue as discovered: story outline has no mystery structure"
            )
        clue_id_str = str(params.mark_clue_discovered)
        now = datetime.now(timezone.utc)

        # Search in all clue lists
        for clue_list_name in ["core_clues", "bonus_clues", "red_herrings"]:
            for clue in mystery.get(clue_list_name, []):
                if str(clue.get("clue_id")) == clue_id_str:
                    clue["is_discovered"] = True
                    clue["discovered_at"] = now
                    clue["visibility"] = "discovered"

        update_doc["mystery_structure"] = mystery

    # Branching points
    if params.add_branching_points:
        existing_bp = doc.get("branching_points", [])
        existing_bp.extend(
            [bp.model_dump(mode="json") for bp in params.add_branching_points]
        )
        update_doc["branching_points"] = existing_bp

    # Perform update
    outlines_collection.update_one({"story_id": str(story_id)}, {"$set": update_doc})

    # Return updated outline
    updated = mongodb_get_story_outline(story_id)
    if not updated:
        raise ValueError(f"Story outline {story_id} not found after update")

    return updated


# =============================================================================
# COMBAT OPERATIONS (DL-25)
# =============================================================================


def _convert_combat_doc_to_response(combat_doc: Dict[str, Any]) -> CombatResponse:
    """
    Convert a combat document from MongoDB to a CombatResponse object.

    Args:
        combat_doc: Combat data from MongoDB document

    Returns:
        CombatResponse object
    """
    # Convert participants
    participants = [
        CombatParticipant(
            entity_id=UUID(p["entity_id"]),
            name=p["name"],
            side=CombatSide(p["side"]),
            initiative_value=p.get("initiative_value"),
            is_active=p.get("is_active", True),
            conditions=[Condition(**c) for c in p.get("conditions", [])],
            resources=p.get("resources", {}),
            position=p.get("position"),
        )
        for p in combat_doc.get("participants", [])
    ]

    # Convert environment
    env_data = combat_doc.get("environment", {})
    environment = CombatEnvironment(**env_data) if env_data else CombatEnvironment()

    # Convert combat log
    combat_log = [
        CombatLogEntry(
            round=entry["round"],
            turn=entry["turn"],
            actor_id=UUID(entry["actor_id"]),
            action=entry["action"],
            resolution_id=(
                UUID(entry["resolution_id"]) if entry.get("resolution_id") else None
            ),
            summary=entry["summary"],
            timestamp=entry["timestamp"],
        )
        for entry in combat_doc.get("combat_log", [])
    ]

    # Convert outcome
    outcome_data = combat_doc.get("outcome")
    outcome = None
    if outcome_data:
        outcome = CombatOutcome(
            result=outcome_data["result"],
            winning_side=(
                CombatSide(outcome_data["winning_side"])
                if outcome_data.get("winning_side")
                else None
            ),
            survivors=[UUID(sid) for sid in outcome_data.get("survivors", [])],
            casualties=[UUID(cid) for cid in outcome_data.get("casualties", [])],
            loot=outcome_data.get("loot", []),
            xp_awarded=outcome_data.get("xp_awarded"),
            metadata=outcome_data.get("metadata", {}),
        )

    return CombatResponse(
        id=UUID(combat_doc["encounter_id"]),
        scene_id=UUID(combat_doc["scene_id"]),
        story_id=UUID(combat_doc["story_id"]),
        status=CombatStatus(combat_doc.get("status", "initializing")),
        round=combat_doc.get("round", 0),
        turn_order=[UUID(tid) for tid in combat_doc.get("turn_order", [])],
        current_turn_index=combat_doc.get("current_turn_index", 0),
        participants=participants,
        environment=environment,
        combat_log=combat_log,
        outcome=outcome,
        created_at=combat_doc["created_at"],
        updated_at=combat_doc.get("updated_at"),
    )


def mongodb_create_combat(params: CombatCreate) -> CombatResponse:
    """
    Create a new combat encounter.

    Args:
        params: Combat creation parameters

    Returns:
        CombatResponse with created combat data

    Raises:
        ValueError: If scene_id or story_id doesn't exist
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Validate scene exists
    scenes_collection = mongodb.get_collection("scenes")
    scene = scenes_collection.find_one({"scene_id": str(params.scene_id)})
    if not scene:
        raise ValueError(f"Scene {params.scene_id} not found")

    # Validate story exists (via Neo4j)
    neo4j_client = get_neo4j_client()
    story_exists = neo4j_client.execute_read(
        "MATCH (s:Story {id: $story_id}) RETURN s.id AS story_id",
        {"story_id": str(params.story_id)},
    )
    if not story_exists:
        raise ValueError(f"Story {params.story_id} not found")

    now = datetime.now(timezone.utc)
    encounter_id = uuid4()

    # Prepare environment
    environment = params.environment if params.environment else CombatEnvironment()

    combat_doc = {
        "encounter_id": str(encounter_id),
        "scene_id": str(params.scene_id),
        "story_id": str(params.story_id),
        "status": "initializing",
        "round": 0,
        "turn_order": [],
        "current_turn_index": 0,
        "participants": [p.model_dump(mode="json") for p in params.participants],
        "environment": environment.model_dump(mode="json"),
        "combat_log": [],
        "outcome": None,
        "created_at": now,
        "updated_at": None,
    }

    combats_collection.insert_one(combat_doc)

    return _convert_combat_doc_to_response(combat_doc)


def mongodb_get_combat(encounter_id: UUID) -> Optional[CombatResponse]:
    """
    Get a combat encounter by ID.

    Args:
        encounter_id: Combat encounter UUID

    Returns:
        CombatResponse or None if not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    combat_doc = combats_collection.find_one({"encounter_id": str(encounter_id)})
    if not combat_doc:
        return None

    return _convert_combat_doc_to_response(combat_doc)


def mongodb_list_combats(params: CombatFilter) -> CombatListResponse:
    """
    List combat encounters with filtering.

    Args:
        params: Filter parameters

    Returns:
        CombatListResponse with matching combats
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Build query
    query: Dict[str, Any] = {}
    if params.scene_id:
        query["scene_id"] = str(params.scene_id)
    if params.story_id:
        query["story_id"] = str(params.story_id)
    if params.status:
        query["status"] = params.status

    # Count total
    total = combats_collection.count_documents(query)

    # Get page
    cursor = (
        combats_collection.find(query)
        .sort("created_at", -1)
        .skip(params.offset)
        .limit(params.limit)
    )

    combats = [_convert_combat_doc_to_response(doc) for doc in cursor]

    return CombatListResponse(
        combats=combats,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_update_combat(encounter_id: UUID, params: CombatUpdate) -> CombatResponse:
    """
    Update a combat encounter.

    Args:
        encounter_id: Combat encounter UUID
        params: Update parameters

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {encounter_id} not found")

    now = datetime.now(timezone.utc)
    update_doc: Dict[str, Any] = {"updated_at": now}

    if params.status is not None:
        update_doc["status"] = params.status.value
    if params.round is not None:
        update_doc["round"] = params.round
    if params.turn_order is not None:
        update_doc["turn_order"] = [str(tid) for tid in params.turn_order]
    if params.current_turn_index is not None:
        update_doc["current_turn_index"] = params.current_turn_index

    combats_collection.update_one(
        {"encounter_id": str(encounter_id)}, {"$set": update_doc}
    )

    updated = mongodb_get_combat(encounter_id)
    if not updated:
        raise ValueError(f"Combat encounter {encounter_id} not found after update")

    return updated


def mongodb_delete_combat(encounter_id: UUID) -> bool:
    """
    Delete a combat encounter.

    Args:
        encounter_id: Combat encounter UUID

    Returns:
        True if deleted, False if not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    result = combats_collection.delete_one({"encounter_id": str(encounter_id)})
    return result.deleted_count > 0


def mongodb_add_combat_participant(params: AddCombatParticipant) -> CombatResponse:
    """
    Add a participant to a combat encounter.

    Args:
        params: Participant data

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat not found or entity already participating
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    # Check if entity already participating
    for p in combat.get("participants", []):
        if p["entity_id"] == str(params.entity_id):
            raise ValueError(f"Entity {params.entity_id} is already in combat")

    # Create participant
    participant = CombatParticipant(
        entity_id=params.entity_id,
        name=params.name,
        side=params.side,
        initiative_value=params.initiative_value,
        is_active=True,
        conditions=[],
        resources=params.resources if params.resources else {},
        position=None,
    )

    now = datetime.now(timezone.utc)
    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)},
        {
            "$push": {"participants": participant.model_dump(mode="json")},
            "$set": {"updated_at": now},
        },
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(
            f"Combat encounter {params.encounter_id} not found after update"
        )

    return updated


def mongodb_update_combat_participant(
    params: UpdateCombatParticipant,
) -> CombatResponse:
    """
    Update a combat participant.

    Args:
        params: Participant update data

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat or participant not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    # Find participant index
    participants = combat.get("participants", [])
    participant_idx = None
    for i, p in enumerate(participants):
        if p["entity_id"] == str(params.entity_id):
            participant_idx = i
            break

    if participant_idx is None:
        raise ValueError(
            f"Participant {params.entity_id} not found in combat {params.encounter_id}"
        )

    # Build update
    now = datetime.now(timezone.utc)
    update_fields: Dict[str, Any] = {}

    if params.initiative_value is not None:
        update_fields[f"participants.{participant_idx}.initiative_value"] = (
            params.initiative_value
        )
    if params.is_active is not None:
        update_fields[f"participants.{participant_idx}.is_active"] = params.is_active
    if params.conditions is not None:
        update_fields[f"participants.{participant_idx}.conditions"] = [
            c.model_dump(mode="json") for c in params.conditions
        ]
    if params.resources is not None:
        update_fields[f"participants.{participant_idx}.resources"] = params.resources
    if params.position is not None:
        update_fields[f"participants.{participant_idx}.position"] = params.position

    update_fields["updated_at"] = now

    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)}, {"$set": update_fields}
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(
            f"Combat encounter {params.encounter_id} not found after update"
        )

    return updated


def mongodb_remove_combat_participant(
    params: RemoveCombatParticipant,
) -> CombatResponse:
    """
    Remove a participant from a combat encounter.

    Args:
        params: Removal parameters

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat or participant not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    # Verify participant exists
    participants = combat.get("participants", [])
    found = any(p["entity_id"] == str(params.entity_id) for p in participants)
    if not found:
        raise ValueError(
            f"Participant {params.entity_id} not found in combat {params.encounter_id}"
        )

    now = datetime.now(timezone.utc)
    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)},
        {
            "$pull": {"participants": {"entity_id": str(params.entity_id)}},
            "$set": {"updated_at": now},
        },
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(
            f"Combat encounter {params.encounter_id} not found after update"
        )

    return updated


def mongodb_add_combat_log_entry(params: AddCombatLogEntry) -> CombatResponse:
    """
    Add an entry to the combat log.

    Args:
        params: Log entry data

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    now = datetime.now(timezone.utc)
    log_entry = CombatLogEntry(
        round=params.round,
        turn=params.turn,
        actor_id=params.actor_id,
        action=params.action,
        resolution_id=params.resolution_id,
        summary=params.summary,
        timestamp=now,
    )

    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)},
        {
            "$push": {"combat_log": log_entry.model_dump(mode="json")},
            "$set": {"updated_at": now},
        },
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(
            f"Combat encounter {params.encounter_id} not found after update"
        )

    return updated


def mongodb_set_combat_outcome(params: SetCombatOutcome) -> CombatResponse:
    """
    Set the final outcome of a combat encounter.

    Args:
        params: Outcome data

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    outcome = CombatOutcome(
        result=params.result,
        winning_side=params.winning_side,
        survivors=params.survivors if params.survivors else [],
        casualties=params.casualties if params.casualties else [],
        loot=params.loot if params.loot else [],
        xp_awarded=params.xp_awarded,
        metadata={},
    )

    now = datetime.now(timezone.utc)
    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)},
        {
            "$set": {
                "outcome": outcome.model_dump(mode="json"),
                "status": "resolved",
                "updated_at": now,
            }
        },
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(
            f"Combat encounter {params.encounter_id} not found after update"
        )

    return updated


# =============================================================================
# RESOLUTION TOOLS (DL-24)
# =============================================================================


def _convert_resolution_doc_to_response(
    resolution_doc: Dict[str, Any],
) -> ResolutionResponse:
    """
    Convert a resolution document from MongoDB to a ResolutionResponse object.

    Args:
        resolution_doc: Resolution data from MongoDB

    Returns:
        ResolutionResponse object
    """
    from monitor_data.schemas.resolutions import (
        ActionType,
        ResolutionType,
        SuccessLevel,
        Mechanics,
        Effect,
    )

    return ResolutionResponse(
        id=UUID(resolution_doc["resolution_id"]),
        turn_id=UUID(resolution_doc["turn_id"]),
        scene_id=UUID(resolution_doc["scene_id"]),
        story_id=UUID(resolution_doc["story_id"]),
        actor_id=UUID(resolution_doc["actor_id"]),
        action=resolution_doc["action"],
        action_type=ActionType(resolution_doc["action_type"]),
        resolution_type=ResolutionType(resolution_doc["resolution_type"]),
        mechanics=Mechanics(**resolution_doc["mechanics"]),
        success_level=SuccessLevel(resolution_doc["success_level"]),
        margin=resolution_doc.get("margin"),
        effects=[Effect(**e) for e in resolution_doc.get("effects", [])],
        description=resolution_doc.get("description"),
        gm_notes=resolution_doc.get("gm_notes"),
        created_at=resolution_doc["created_at"],
        updated_at=resolution_doc.get("updated_at"),
    )


def mongodb_create_resolution(params: ResolutionCreate) -> ResolutionResponse:
    """
    Create a new resolution record.

    Args:
        params: Resolution creation parameters

    Returns:
        ResolutionResponse with created resolution data

    Raises:
        ValueError: If turn_id, scene_id, or story_id doesn't exist
    """
    mongodb = get_mongodb_client()
    resolutions_collection = mongodb.get_collection("resolutions")

    # Validate turn exists
    scenes_collection = mongodb.get_collection("scenes")
    scene = scenes_collection.find_one({"scene_id": str(params.scene_id)})
    if not scene:
        raise ValueError(f"Scene {params.scene_id} not found")

    # Validate turn exists in the scene
    turn_found = False
    for turn in scene.get("turns", []):
        if turn.get("turn_id") == str(params.turn_id):
            turn_found = True
            break
    if not turn_found:
        raise ValueError(f"Turn {params.turn_id} not found in scene {params.scene_id}")

    # Validate story exists (via Neo4j)
    neo4j_client = get_neo4j_client()
    story_exists = neo4j_client.execute_read(
        "MATCH (s:Story {id: $story_id}) RETURN s.id AS story_id",
        {"story_id": str(params.story_id)},
    )
    if not story_exists:
        raise ValueError(f"Story {params.story_id} not found")

    now = datetime.now(timezone.utc)
    resolution_id = uuid4()

    resolution_doc = {
        "resolution_id": str(resolution_id),
        "turn_id": str(params.turn_id),
        "scene_id": str(params.scene_id),
        "story_id": str(params.story_id),
        "actor_id": str(params.actor_id),
        "action": params.action,
        "action_type": params.action_type.value,
        "resolution_type": params.resolution_type.value,
        "mechanics": params.mechanics.model_dump(mode="json"),
        "success_level": params.success_level.value,
        "margin": params.margin,
        "effects": [e.model_dump(mode="json") for e in params.effects],
        "description": params.description,
        "gm_notes": params.gm_notes,
        "created_at": now,
        "updated_at": None,
    }

    resolutions_collection.insert_one(resolution_doc)

    return _convert_resolution_doc_to_response(resolution_doc)


def mongodb_get_resolution(resolution_id: UUID) -> Optional[ResolutionResponse]:
    """
    Get a resolution by ID.

    Args:
        resolution_id: Resolution UUID

    Returns:
        ResolutionResponse or None if not found
    """
    mongodb = get_mongodb_client()
    resolutions_collection = mongodb.get_collection("resolutions")

    resolution_doc = resolutions_collection.find_one(
        {"resolution_id": str(resolution_id)}
    )
    if not resolution_doc:
        return None

    return _convert_resolution_doc_to_response(resolution_doc)


def mongodb_list_resolutions(params: ResolutionFilter) -> ResolutionListResponse:
    """
    List resolutions with filtering.

    Args:
        params: Filter parameters

    Returns:
        ResolutionListResponse with matching resolutions
    """
    mongodb = get_mongodb_client()
    resolutions_collection = mongodb.get_collection("resolutions")

    # Build query
    query: Dict[str, Any] = {}
    if params.scene_id:
        query["scene_id"] = str(params.scene_id)
    if params.turn_id:
        query["turn_id"] = str(params.turn_id)
    if params.actor_id:
        query["actor_id"] = str(params.actor_id)
    if params.action_type:
        query["action_type"] = params.action_type.value
    if params.success_level:
        query["success_level"] = params.success_level.value

    # Count total
    total = resolutions_collection.count_documents(query)

    # Get page
    cursor = (
        resolutions_collection.find(query)
        .sort("created_at", -1)
        .skip(params.offset)
        .limit(params.limit)
    )

    resolutions = [_convert_resolution_doc_to_response(doc) for doc in cursor]

    return ResolutionListResponse(
        resolutions=resolutions,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_update_resolution(
    resolution_id: UUID, params: ResolutionUpdate
) -> ResolutionResponse:
    """
    Update a resolution record.

    Args:
        resolution_id: Resolution UUID
        params: Fields to update

    Returns:
        Updated ResolutionResponse

    Raises:
        ValueError: If resolution not found
    """
    mongodb = get_mongodb_client()
    resolutions_collection = mongodb.get_collection("resolutions")

    # Build update dict
    update_dict: Dict[str, Any] = {}
    if params.effects is not None:
        update_dict["effects"] = [e.model_dump(mode="json") for e in params.effects]
    if params.description is not None:
        update_dict["description"] = params.description
    if params.gm_notes is not None:
        update_dict["gm_notes"] = params.gm_notes

    if not update_dict:
        # No updates provided, just return current state
        resolution = mongodb_get_resolution(resolution_id)
        if not resolution:
            raise ValueError(f"Resolution {resolution_id} not found")
        return resolution

    now = datetime.now(timezone.utc)
    update_dict["updated_at"] = now

    result = resolutions_collection.update_one(
        {"resolution_id": str(resolution_id)}, {"$set": update_dict}
    )

    if result.matched_count == 0:
        raise ValueError(f"Resolution {resolution_id} not found")

    updated = mongodb_get_resolution(resolution_id)
    if not updated:
        raise ValueError(f"Resolution {resolution_id} not found after update")

    return updated


def mongodb_delete_resolution(resolution_id: UUID) -> bool:
    """
    Delete a resolution record.

    Args:
        resolution_id: Resolution UUID

    Returns:
        True if deleted, False if not found
    """
    mongodb = get_mongodb_client()
    resolutions_collection = mongodb.get_collection("resolutions")

    result = resolutions_collection.delete_one({"resolution_id": str(resolution_id)})

    return result.deleted_count > 0


# =============================================================================
# CHARACTER MEMORY OPERATIONS
# =============================================================================


def mongodb_create_memory(params: MemoryCreate) -> MemoryResponse:
    """
    Create a new CharacterMemory document in MongoDB.

    Authority: All agents
    Use Case: DL-7

    Args:
        params: Memory creation parameters

    Returns:
        MemoryResponse with created memory data

    Raises:
        ValueError: If entity_id doesn't exist in Neo4j
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify entity exists in Neo4j
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

    # Verify scene exists if provided
    if params.scene_id:
        scenes_collection = mongo_client.get_collection("scenes")
        scene = scenes_collection.find_one({"scene_id": str(params.scene_id)})
        if not scene:
            raise ValueError(f"Scene {params.scene_id} not found")

    # Verify linked fact exists if provided
    if params.linked_fact_id:
        fact_check_query = """
        MATCH (f:Fact {id: $fact_id})
        RETURN f.id as id
        """
        result = neo4j_client.execute_read(
            fact_check_query, {"fact_id": str(params.linked_fact_id)}
        )
        if not result:
            raise ValueError(f"Fact {params.linked_fact_id} not found")

    # Create memory document
    now = datetime.now(timezone.utc)
    memory_id = uuid4()

    memory_doc = {
        "memory_id": str(memory_id),
        "entity_id": str(params.entity_id),
        "text": params.text,
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "linked_fact_id": str(params.linked_fact_id) if params.linked_fact_id else None,
        "emotional_valence": params.emotional_valence,
        "importance": params.importance,
        "certainty": params.certainty,
        "metadata": params.metadata,
        "created_at": now,
        "last_accessed": now,
        "access_count": 0,
    }

    memories_collection = mongo_client.get_collection("character_memories")
    memories_collection.insert_one(memory_doc)

    return MemoryResponse(
        memory_id=memory_id,
        entity_id=params.entity_id,
        text=params.text,
        scene_id=params.scene_id,
        linked_fact_id=params.linked_fact_id,
        emotional_valence=params.emotional_valence,
        importance=params.importance,
        certainty=params.certainty,
        metadata=params.metadata,
        created_at=now,
        last_accessed=now,
        access_count=0,
    )


def mongodb_get_memory(memory_id: UUID) -> MemoryResponse:
    """
    Get a memory by ID and update access tracking.

    Authority: All agents
    Use Case: DL-7

    Args:
        memory_id: Memory UUID

    Returns:
        MemoryResponse with memory data

    Raises:
        ValueError: If memory not found
    """
    mongo_client = get_mongodb_client()
    memories_collection = mongo_client.get_collection("character_memories")

    # Update access tracking
    now = datetime.now(timezone.utc)
    result = memories_collection.find_one_and_update(
        {"memory_id": str(memory_id)},
        {"$set": {"last_accessed": now}, "$inc": {"access_count": 1}},
        return_document=True,
    )

    if not result:
        raise ValueError(f"Memory {memory_id} not found")

    return MemoryResponse(
        memory_id=UUID(result["memory_id"]),
        entity_id=UUID(result["entity_id"]),
        text=result["text"],
        scene_id=UUID(result["scene_id"]) if result.get("scene_id") else None,
        linked_fact_id=(
            UUID(result["linked_fact_id"]) if result.get("linked_fact_id") else None
        ),
        emotional_valence=result["emotional_valence"],
        importance=result["importance"],
        certainty=result["certainty"],
        metadata=result["metadata"],
        created_at=result["created_at"],
        last_accessed=result["last_accessed"],
        access_count=result["access_count"],
    )


def mongodb_list_memories(params: MemoryFilter) -> MemoryListResponse:
    """
    List memories with optional filters.

    Authority: All agents
    Use Case: DL-7

    Args:
        params: Filter parameters

    Returns:
        MemoryListResponse with filtered memories and pagination
    """
    mongo_client = get_mongodb_client()
    memories_collection = mongo_client.get_collection("character_memories")

    # Build filter
    filter_dict: Dict[str, Any] = {}
    if params.entity_id:
        filter_dict["entity_id"] = str(params.entity_id)
    if params.scene_id:
        filter_dict["scene_id"] = str(params.scene_id)
    if params.min_importance is not None or params.max_importance is not None:
        filter_dict["importance"] = {}
        if params.min_importance is not None:
            filter_dict["importance"]["$gte"] = params.min_importance
        if params.max_importance is not None:
            filter_dict["importance"]["$lte"] = params.max_importance
    if (
        params.min_emotional_valence is not None
        or params.max_emotional_valence is not None
    ):
        filter_dict["emotional_valence"] = {}
        if params.min_emotional_valence is not None:
            filter_dict["emotional_valence"]["$gte"] = params.min_emotional_valence
        if params.max_emotional_valence is not None:
            filter_dict["emotional_valence"]["$lte"] = params.max_emotional_valence

    # Get total count
    total = memories_collection.count_documents(filter_dict)

    # Get paginated results, ordered by importance descending
    cursor = (
        memories_collection.find(filter_dict)
        .sort("importance", -1)
        .skip(params.offset)
        .limit(params.limit)
    )

    memories = []
    for mem_doc in cursor:
        memories.append(
            MemoryResponse(
                memory_id=UUID(mem_doc["memory_id"]),
                entity_id=UUID(mem_doc["entity_id"]),
                text=mem_doc["text"],
                scene_id=UUID(mem_doc["scene_id"]) if mem_doc.get("scene_id") else None,
                linked_fact_id=(
                    UUID(mem_doc["linked_fact_id"])
                    if mem_doc.get("linked_fact_id")
                    else None
                ),
                emotional_valence=mem_doc["emotional_valence"],
                importance=mem_doc["importance"],
                certainty=mem_doc["certainty"],
                metadata=mem_doc["metadata"],
                created_at=mem_doc["created_at"],
                last_accessed=mem_doc["last_accessed"],
                access_count=mem_doc["access_count"],
            )
        )

    return MemoryListResponse(
        memories=memories, total=total, limit=params.limit, offset=params.offset
    )


def mongodb_update_memory(memory_id: UUID, params: MemoryUpdate) -> MemoryResponse:
    """
    Update a memory document.

    Authority: All agents
    Use Case: DL-7

    Args:
        memory_id: Memory UUID
        params: Fields to update

    Returns:
        Updated MemoryResponse

    Raises:
        ValueError: If memory not found
    """
    mongo_client = get_mongodb_client()
    memories_collection = mongo_client.get_collection("character_memories")

    # Build update dict
    update_dict: Dict[str, Any] = {}
    if params.importance is not None:
        update_dict["importance"] = params.importance
    if params.certainty is not None:
        update_dict["certainty"] = params.certainty
    if params.emotional_valence is not None:
        update_dict["emotional_valence"] = params.emotional_valence
    if params.metadata is not None:
        update_dict["metadata"] = params.metadata

    if not update_dict:
        # No updates provided, just return current state
        return mongodb_get_memory(memory_id)

    result = memories_collection.update_one(
        {"memory_id": str(memory_id)}, {"$set": update_dict}
    )

    if result.matched_count == 0:
        raise ValueError(f"Memory {memory_id} not found")

    return mongodb_get_memory(memory_id)


def mongodb_delete_memory(memory_id: UUID) -> bool:
    """
    Delete a memory document.

    Note: Caller is responsible for deleting corresponding Qdrant vector.

    Authority: All agents
    Use Case: DL-7

    Args:
        memory_id: Memory UUID

    Returns:
        True if deleted, False if not found
    """
    mongo_client = get_mongodb_client()
    memories_collection = mongo_client.get_collection("character_memories")

    result = memories_collection.delete_one({"memory_id": str(memory_id)})

    return result.deleted_count > 0


# =============================================================================
# PARTY INVENTORY OPERATIONS (DL-16)
# =============================================================================


def mongodb_create_party_inventory(
    params: PartyInventoryCreate,
) -> PartyInventoryResponse:
    """
    Create a new party inventory document in MongoDB.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Party inventory creation parameters

    Returns:
        PartyInventoryResponse with created inventory data

    Raises:
        ValueError: If party_id doesn't exist in Neo4j or inventory already exists
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify party exists in Neo4j
    party_check_query = """
    MATCH (p:Party {id: $party_id})
    RETURN p.id as id
    """
    result = neo4j_client.execute_read(
        party_check_query, {"party_id": str(params.party_id)}
    )
    if not result:
        raise ValueError(f"Party {params.party_id} not found")

    # Check if inventory already exists
    inventories_collection = mongo_client.get_collection("party_inventories")
    existing = inventories_collection.find_one({"party_id": str(params.party_id)})
    if existing:
        raise ValueError(f"Inventory for party {params.party_id} already exists")

    # Create inventory document
    now = datetime.now(timezone.utc)
    inventory_id = uuid4()

    # Process initial items
    items = []
    if params.initial_items:
        for item_data in params.initial_items:
            item = InventoryItem(
                name=item_data["name"],
                quantity=item_data.get("quantity", 1),
                category=ItemCategory(item_data.get("category", ItemCategory.MISC)),
                value=item_data.get("value"),
                notes=item_data.get("notes"),
                added_at=now,
            )
            items.append(item.model_dump(mode="json"))

    inventory_doc = {
        "inventory_id": str(inventory_id),
        "party_id": str(params.party_id),
        "gold": params.initial_gold,
        "items": items,
        "created_at": now,
        "updated_at": now,
    }

    inventories_collection.insert_one(inventory_doc)

    return PartyInventoryResponse(
        inventory_id=inventory_id,
        party_id=params.party_id,
        gold=params.initial_gold,
        items=[InventoryItem(**item) for item in items],
        created_at=now,
        updated_at=now,
    )


def mongodb_get_party_inventory(party_id: UUID) -> PartyInventoryResponse:
    """
    Get party inventory by party_id.

    Authority: All agents
    Use Case: DL-16

    Args:
        party_id: Party UUID

    Returns:
        PartyInventoryResponse with inventory data

    Raises:
        ValueError: If inventory not found
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("party_inventories")

    inventory_doc = inventories_collection.find_one({"party_id": str(party_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for party {party_id} not found")

    return PartyInventoryResponse(
        inventory_id=UUID(inventory_doc["inventory_id"]),
        party_id=UUID(inventory_doc["party_id"]),
        gold=inventory_doc["gold"],
        items=[InventoryItem(**item) for item in inventory_doc.get("items", [])],
        created_at=inventory_doc["created_at"],
        updated_at=inventory_doc.get("updated_at"),
    )


def mongodb_add_inventory_item(
    params: AddInventoryItemRequest,
) -> PartyInventoryResponse:
    """
    Add an item to party inventory or increment quantity if it exists.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Add item parameters

    Returns:
        PartyInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory not found
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("party_inventories")

    # Get current inventory
    inventory_doc = inventories_collection.find_one({"party_id": str(params.party_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for party {params.party_id} not found")

    now = datetime.now(timezone.utc)
    items = inventory_doc.get("items", [])

    # Normalize item name for case-insensitive comparison
    normalized_name = params.item_name.strip().casefold()

    # Check if item already exists (case-insensitive)
    existing_item = None
    for item in items:
        item_name = item.get("name", "")
        if item_name.strip().casefold() == normalized_name:
            existing_item = item
            break

    if existing_item:
        # Increment quantity
        existing_item["quantity"] += params.quantity
    else:
        # Add new item (store with stripped whitespace but preserve case)
        new_item = InventoryItem(
            name=params.item_name.strip(),
            quantity=params.quantity,
            category=params.category or ItemCategory.MISC,
            value=params.value,
            notes=params.notes,
            added_at=now,
        )
        items.append(new_item.model_dump(mode="json"))

    # Update inventory
    inventories_collection.update_one(
        {"party_id": str(params.party_id)},
        {"$set": {"items": items, "updated_at": now}},
    )

    return mongodb_get_party_inventory(params.party_id)


def mongodb_remove_inventory_item(
    params: RemoveInventoryItemRequest,
) -> PartyInventoryResponse:
    """
    Remove an item from party inventory or decrement quantity.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Remove item parameters

    Returns:
        PartyInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory or item not found, or insufficient quantity
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("party_inventories")

    # Get current inventory
    inventory_doc = inventories_collection.find_one({"party_id": str(params.party_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for party {params.party_id} not found")

    now = datetime.now(timezone.utc)
    items = inventory_doc.get("items", [])

    # Find the item
    item_index = None
    for i, item in enumerate(items):
        if item["name"] == params.item_name:
            item_index = i
            break

    if item_index is None:
        raise ValueError(f"Item '{params.item_name}' not found in inventory")

    item = items[item_index]

    # Check for insufficient quantity
    if params.quantity is not None and params.quantity > item["quantity"]:
        raise ValueError(
            f"Insufficient quantity: have {item['quantity']}, trying to remove {params.quantity}"
        )

    if params.quantity is None or params.quantity >= item["quantity"]:
        # Remove item completely
        items.pop(item_index)
    else:
        # Decrement quantity
        item["quantity"] -= params.quantity

    # Update inventory
    inventories_collection.update_one(
        {"party_id": str(params.party_id)},
        {"$set": {"items": items, "updated_at": now}},
    )

    return mongodb_get_party_inventory(params.party_id)


def mongodb_update_party_gold(params: UpdateGoldRequest) -> PartyInventoryResponse:
    """
    Update party gold (add or subtract).

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Update gold parameters

    Returns:
        PartyInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory not found or gold would become negative
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("party_inventories")

    # Get current inventory
    inventory_doc = inventories_collection.find_one({"party_id": str(params.party_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for party {params.party_id} not found")

    current_gold = inventory_doc.get("gold", 0)
    new_gold = current_gold + params.amount

    if new_gold < 0:
        raise ValueError(
            f"Insufficient gold: have {current_gold}, trying to subtract {-params.amount}"
        )

    now = datetime.now(timezone.utc)

    # Update inventory
    inventories_collection.update_one(
        {"party_id": str(params.party_id)},
        {"$set": {"gold": new_gold, "updated_at": now}},
    )

    return mongodb_get_party_inventory(params.party_id)


def mongodb_transfer_item(params: TransferItemRequest) -> Dict[str, str]:
    """
    Transfer an item between party and character inventory.

    Note: This is a placeholder that validates the transfer but doesn't
    implement character inventory (not in scope for DL-16).

    Authority: Orchestrator
    Use Case: DL-16

    Args:
        params: Transfer item parameters

    Returns:
        Dict with transfer confirmation

    Raises:
        ValueError: If source inventory not found or insufficient quantity
        NotImplementedError: If character inventory is involved (not yet implemented)
    """
    mongo_client = get_mongodb_client()

    # Validate transfer type
    if params.from_type.value == "character" or params.to_type.value == "character":
        raise NotImplementedError(
            "Character inventory not yet implemented. "
            "This tool currently only supports party inventory operations."
        )

    # For party-to-party transfers, this would be for moving items between
    # different parties (e.g., splitting loot)
    # For now, just validate that the source party has the item

    inventories_collection = mongo_client.get_collection("party_inventories")
    source_inventory = inventories_collection.find_one(
        {"party_id": str(params.from_id)}
    )
    if not source_inventory:
        raise ValueError(f"Source inventory for party {params.from_id} not found")

    # Find the item
    items = source_inventory.get("items", [])
    item_found = False
    for item in items:
        if item["name"] == params.item_name:
            item_found = True
            if item["quantity"] < params.quantity:
                raise ValueError(
                    f"Insufficient quantity: have {item['quantity']}, trying to transfer {params.quantity}"
                )
            break

    if not item_found:
        raise ValueError(f"Item '{params.item_name}' not found in source inventory")

    # TODO: Implement actual transfer when character inventory is added
    return {
        "status": "validated",
        "message": f"Transfer of {params.quantity}x {params.item_name} validated but not executed (character inventory not implemented)",
    }


def mongodb_create_party_split(params: PartySplitCreate) -> PartySplitResponse:
    """
    Create a party split record.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Party split creation parameters

    Returns:
        PartySplitResponse with created split data

    Raises:
        ValueError: If party doesn't exist or validation fails
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify party exists
    party_check_query = """
    MATCH (p:Party {id: $party_id})
    RETURN p.id as id
    """
    result = neo4j_client.execute_read(
        party_check_query, {"party_id": str(params.party_id)}
    )
    if not result:
        raise ValueError(f"Party {params.party_id} not found")

    # Validate sub-parties (check that all members exist)
    all_member_ids = []
    for sub_party in params.sub_parties:
        all_member_ids.extend(sub_party.member_ids)

    # Check for duplicate member IDs across sub-parties
    if len(all_member_ids) != len(set(all_member_ids)):
        raise ValueError(
            "Duplicate member IDs found across sub-parties. "
            "Each character can only be assigned to one sub-party."
        )

    # Verify locations if provided
    for sub_party in params.sub_parties:
        # Verify location if provided
        if sub_party.location_id:
            location_check_query = """
            MATCH (l:EntityInstance {id: $location_id})
            WHERE l.entity_type = 'location'
            RETURN l.id as id
            """
            result = neo4j_client.execute_read(
                location_check_query, {"location_id": str(sub_party.location_id)}
            )
            if not result:
                raise ValueError(f"Location {sub_party.location_id} not found")

    # Verify all members exist
    for member_id in all_member_ids:
        member_check_query = """
        MATCH (e:EntityInstance {id: $entity_id})
        RETURN e.id as id
        """
        result = neo4j_client.execute_read(
            member_check_query, {"entity_id": str(member_id)}
        )
        if not result:
            raise ValueError(f"Entity {member_id} not found")

    # Create split document
    now = datetime.now(timezone.utc)
    split_id = uuid4()

    sub_parties_list = [
        sub_party.model_dump(mode="json") for sub_party in params.sub_parties
    ]

    split_doc = {
        "split_id": str(split_id),
        "party_id": str(params.party_id),
        "sub_parties": sub_parties_list,
        "status": SplitStatus.ACTIVE.value,
        "created_at": now,
        "resolved_at": None,
        "resolution_notes": None,
    }

    splits_collection = mongo_client.get_collection("party_splits")
    splits_collection.insert_one(split_doc)

    return PartySplitResponse(
        split_id=split_id,
        party_id=params.party_id,
        sub_parties=params.sub_parties,
        status=SplitStatus.ACTIVE,
        created_at=now,
        resolved_at=None,
        resolution_notes=None,
    )


def mongodb_get_active_splits(party_id: UUID) -> ActiveSplitsResponse:
    """
    Get all active splits for a party.

    Authority: All agents
    Use Case: DL-16

    Args:
        party_id: Party UUID

    Returns:
        ActiveSplitsResponse with active splits
    """
    mongo_client = get_mongodb_client()
    splits_collection = mongo_client.get_collection("party_splits")

    # Find all active splits for party
    splits_docs = splits_collection.find(
        {"party_id": str(party_id), "status": SplitStatus.ACTIVE.value}
    )

    splits = []
    for split_doc in splits_docs:
        splits.append(
            PartySplitResponse(
                split_id=UUID(split_doc["split_id"]),
                party_id=UUID(split_doc["party_id"]),
                sub_parties=[
                    SubParty(**sub_party) for sub_party in split_doc["sub_parties"]
                ],
                status=SplitStatus(split_doc["status"]),
                created_at=split_doc["created_at"],
                resolved_at=split_doc.get("resolved_at"),
                resolution_notes=split_doc.get("resolution_notes"),
            )
        )

    return ActiveSplitsResponse(party_id=party_id, splits=splits)


def mongodb_resolve_party_split(
    params: ResolvePartySplitRequest,
) -> PartySplitResponse:
    """
    Resolve a party split (mark as rejoined).

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Resolve split parameters

    Returns:
        PartySplitResponse with resolved split data

    Raises:
        ValueError: If split not found or already resolved
    """
    mongo_client = get_mongodb_client()
    splits_collection = mongo_client.get_collection("party_splits")

    # Get current split
    split_doc = splits_collection.find_one({"split_id": str(params.split_id)})
    if not split_doc:
        raise ValueError(f"Split {params.split_id} not found")

    if split_doc["status"] == SplitStatus.RESOLVED.value:
        raise ValueError(f"Split {params.split_id} is already resolved")

    now = datetime.now(timezone.utc)

    # Update split
    splits_collection.update_one(
        {"split_id": str(params.split_id)},
        {
            "$set": {
                "status": SplitStatus.RESOLVED.value,
                "resolved_at": now,
                "resolution_notes": params.resolution_notes,
            }
        },
    )

    # Return updated split
    updated_split_doc = splits_collection.find_one({"split_id": str(params.split_id)})
    if not updated_split_doc:
        raise ValueError(f"Split {params.split_id} not found after update")

    return PartySplitResponse(
        split_id=UUID(updated_split_doc["split_id"]),
        party_id=UUID(updated_split_doc["party_id"]),
        sub_parties=[
            SubParty(**sub_party) for sub_party in updated_split_doc["sub_parties"]
        ],
        status=SplitStatus(updated_split_doc["status"]),
        created_at=updated_split_doc["created_at"],
        resolved_at=updated_split_doc.get("resolved_at"),
        resolution_notes=updated_split_doc.get("resolution_notes"),
    )


def mongodb_get_split_history(params: SplitHistoryFilter) -> SplitHistoryResponse:
    """
    Get split history for a party (all splits, including resolved).

    Authority: All agents
    Use Case: DL-16

    Args:
        params: Split history filter parameters

    Returns:
        SplitHistoryResponse with split history
    """
    mongo_client = get_mongodb_client()
    splits_collection = mongo_client.get_collection("party_splits")

    # Count total splits
    total = splits_collection.count_documents({"party_id": str(params.party_id)})

    # Find splits with pagination
    splits_docs = (
        splits_collection.find({"party_id": str(params.party_id)})
        .sort("created_at", -1)  # Most recent first
        .skip(params.offset)
        .limit(params.limit)
    )

    splits = []
    for split_doc in splits_docs:
        splits.append(
            PartySplitResponse(
                split_id=UUID(split_doc["split_id"]),
                party_id=UUID(split_doc["party_id"]),
                sub_parties=[
                    SubParty(**sub_party) for sub_party in split_doc["sub_parties"]
                ],
                status=SplitStatus(split_doc["status"]),
                created_at=split_doc["created_at"],
                resolved_at=split_doc.get("resolved_at"),
                resolution_notes=split_doc.get("resolution_notes"),
            )
        )

    return SplitHistoryResponse(
        party_id=params.party_id,
        splits=splits,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
