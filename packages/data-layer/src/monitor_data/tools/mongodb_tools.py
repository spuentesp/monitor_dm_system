"""
MongoDB MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose MongoDB operations via the MCP server.
MongoDB stores narrative artifacts (scenes, turns) and proposals.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
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
from monitor_data.schemas.base import SceneStatus


# =============================================================================
# SCENE OPERATIONS
# =============================================================================


def mongodb_create_scene(params: SceneCreate) -> SceneResponse:
    """
    Create a new Scene document in MongoDB.

    Authority: Orchestrator only
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

    # Convert turns from dict to TurnResponse
    turns = []
    for turn_dict in scene_doc.get("turns", []):
        turns.append(
            TurnResponse(
                turn_id=UUID(turn_dict["turn_id"]),
                speaker=turn_dict["speaker"],
                entity_id=UUID(turn_dict["entity_id"]) if turn_dict.get("entity_id") else None,
                text=turn_dict["text"],
                timestamp=turn_dict["timestamp"],
                resolution_ref=UUID(turn_dict["resolution_ref"])
                if turn_dict.get("resolution_ref")
                else None,
            )
        )

    return SceneResponse(
        scene_id=UUID(scene_doc["scene_id"]),
        story_id=UUID(scene_doc["story_id"]),
        universe_id=UUID(scene_doc["universe_id"]),
        title=scene_doc["title"],
        purpose=scene_doc["purpose"],
        status=SceneStatus(scene_doc["status"]),
        order=scene_doc.get("order"),
        location_ref=UUID(scene_doc["location_ref"]) if scene_doc.get("location_ref") else None,
        participating_entities=[UUID(eid) for eid in scene_doc.get("participating_entities", [])],
        turns=turns,
        proposed_changes=[UUID(pid) for pid in scene_doc.get("proposed_changes", [])],
        canonical_outcomes=[UUID(cid) for cid in scene_doc.get("canonical_outcomes", [])],
        summary=scene_doc.get("summary", ""),
        created_at=scene_doc["created_at"],
        updated_at=scene_doc["updated_at"],
        completed_at=scene_doc.get("completed_at"),
    )


def mongodb_update_scene(scene_id: UUID, params: SceneUpdate) -> SceneResponse:
    """
    Update a Scene's mutable fields with status transition enforcement.

    Authority: Orchestrator only
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
    sort_field = params.sort_by if params.sort_by in ["created_at", "order"] else "created_at"
    sort_order = -1 if params.sort_order == "desc" else 1

    # Query with pagination
    cursor = (
        scenes_collection.find(filter_query)
        .sort(sort_field, sort_order)
        .skip(params.offset)
        .limit(params.limit)
    )

    scenes = []
    for scene_doc in cursor:
        # Convert turns from dict to TurnResponse
        turns = []
        for turn_dict in scene_doc.get("turns", []):
            turns.append(
                TurnResponse(
                    turn_id=UUID(turn_dict["turn_id"]),
                    speaker=turn_dict["speaker"],
                    entity_id=UUID(turn_dict["entity_id"])
                    if turn_dict.get("entity_id")
                    else None,
                    text=turn_dict["text"],
                    timestamp=turn_dict["timestamp"],
                    resolution_ref=UUID(turn_dict["resolution_ref"])
                    if turn_dict.get("resolution_ref")
                    else None,
                )
            )

        scenes.append(
            SceneResponse(
                scene_id=UUID(scene_doc["scene_id"]),
                story_id=UUID(scene_doc["story_id"]),
                universe_id=UUID(scene_doc["universe_id"]),
                title=scene_doc["title"],
                purpose=scene_doc["purpose"],
                status=SceneStatus(scene_doc["status"]),
                order=scene_doc.get("order"),
                location_ref=UUID(scene_doc["location_ref"])
                if scene_doc.get("location_ref")
                else None,
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
        )

    return SceneListResponse(scenes=scenes, total=total, limit=params.limit, offset=params.offset)


def mongodb_append_turn(scene_id: UUID, params: TurnCreate) -> TurnResponse:
    """
    Append a turn to a scene with proper ordering.

    Authority: All agents (primarily Narrator and Orchestrator)
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
