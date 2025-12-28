"""
MongoDB MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose MongoDB operations via the MCP server.
Scenes and turns are stored in MongoDB for narrative flexibility.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
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

    Authority: CanonKeeper, Narrator
    Use Case: DL-4

    Args:
        params: Scene creation parameters

    Returns:
        SceneResponse with created scene data

    Raises:
        ValueError: If story_id doesn't exist in Neo4j
    """
    # Verify story exists in Neo4j
    neo4j_client = get_neo4j_client()
    verify_query = """
    MATCH (s:Story {id: $story_id})
    RETURN s.id as id, s.universe_id as universe_id
    """
    result = neo4j_client.execute_read(
        verify_query, {"story_id": str(params.story_id)}
    )
    if not result:
        raise ValueError(f"Story {params.story_id} not found")
    
    universe_id = result[0]["universe_id"]

    # Create scene in MongoDB
    mongo_client = get_mongodb_client()
    scenes_collection = mongo_client.get_collection("scenes")

    scene_id = uuid4()
    created_at = datetime.now(timezone.utc)

    scene_doc = {
        "scene_id": str(scene_id),
        "story_id": str(params.story_id),
        "universe_id": universe_id,
        "title": params.title,
        "purpose": params.purpose,
        "status": SceneStatus.ACTIVE.value,
        "order": params.order,
        "location_id": str(params.location_id) if params.location_id else None,
        "participant_ids": [str(pid) for pid in params.participant_ids],
        "turns": [],
        "proposed_changes": [],
        "canonical_outcomes": [],
        "summary": None,
        "metadata": params.metadata,
        "created_at": created_at,
        "updated_at": created_at,
        "completed_at": None,
    }

    scenes_collection.insert_one(scene_doc)

    return SceneResponse(
        scene_id=scene_id,
        story_id=params.story_id,
        universe_id=UUID(universe_id),
        title=params.title,
        purpose=params.purpose,
        status=SceneStatus.ACTIVE,
        order=params.order,
        location_id=params.location_id,
        participant_ids=params.participant_ids,
        turns=[],
        proposed_changes=[],
        canonical_outcomes=[],
        summary=None,
        metadata=params.metadata,
        created_at=created_at,
        updated_at=created_at,
        completed_at=None,
    )


def mongodb_get_scene(scene_id: UUID) -> Optional[SceneResponse]:
    """
    Get a Scene by ID with all turns.

    Authority: Any agent (read-only)
    Use Case: DL-4

    Args:
        scene_id: UUID of the scene

    Returns:
        SceneResponse if found, None otherwise
    """
    mongo_client = get_mongodb_client()
    scenes_collection = mongo_client.get_collection("scenes")

    scene_doc = scenes_collection.find_one({"scene_id": str(scene_id)})

    if not scene_doc:
        return None

    # Convert turns to TurnResponse objects
    turns = []
    for turn_data in scene_doc.get("turns", []):
        turns.append(
            TurnResponse(
                turn_id=UUID(turn_data["turn_id"]),
                speaker=turn_data["speaker"],
                entity_id=UUID(turn_data["entity_id"]) if turn_data.get("entity_id") else None,
                text=turn_data["text"],
                metadata=turn_data.get("metadata", {}),
                timestamp=turn_data["timestamp"],
            )
        )

    return SceneResponse(
        scene_id=UUID(scene_doc["scene_id"]),
        story_id=UUID(scene_doc["story_id"]),
        universe_id=UUID(scene_doc["universe_id"]),
        title=scene_doc["title"],
        purpose=scene_doc.get("purpose"),
        status=scene_doc["status"],
        order=scene_doc.get("order"),
        location_id=UUID(scene_doc["location_id"]) if scene_doc.get("location_id") else None,
        participant_ids=[UUID(pid) for pid in scene_doc.get("participant_ids", [])],
        turns=turns,
        proposed_changes=[UUID(pc) for pc in scene_doc.get("proposed_changes", [])],
        canonical_outcomes=[UUID(co) for co in scene_doc.get("canonical_outcomes", [])],
        summary=scene_doc.get("summary"),
        metadata=scene_doc.get("metadata", {}),
        created_at=scene_doc["created_at"],
        updated_at=scene_doc["updated_at"],
        completed_at=scene_doc.get("completed_at"),
    )


def mongodb_update_scene(scene_id: UUID, params: SceneUpdate) -> SceneResponse:
    """
    Update a Scene.

    Authority: CanonKeeper, Narrator
    Use Case: DL-4

    Args:
        scene_id: UUID of the scene to update
        params: Fields to update

    Returns:
        SceneResponse with updated scene data

    Raises:
        ValueError: If scene not found or invalid status transition
    """
    mongo_client = get_mongodb_client()
    scenes_collection = mongo_client.get_collection("scenes")

    # Get current scene
    scene_doc = scenes_collection.find_one({"scene_id": str(scene_id)})
    if not scene_doc:
        raise ValueError(f"Scene {scene_id} not found")

    # Build update document
    update_doc: Dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc)
    }

    # Validate and apply status transition if provided
    if params.status is not None:
        current_status = SceneStatus(scene_doc["status"])
        new_status = params.status

        # Valid transitions: active -> finalizing -> completed
        valid_transitions = {
            SceneStatus.ACTIVE: [SceneStatus.FINALIZING],
            SceneStatus.FINALIZING: [SceneStatus.COMPLETED],
        }

        if current_status != new_status:
            if new_status not in valid_transitions.get(current_status, []):
                raise ValueError(
                    f"Invalid status transition from {current_status.value} to {new_status.value}"
                )

        update_doc["status"] = new_status.value

        # Set completed_at when status becomes completed
        if new_status == SceneStatus.COMPLETED:
            update_doc["completed_at"] = update_doc["updated_at"]

    if params.summary is not None:
        update_doc["summary"] = params.summary

    if params.metadata is not None:
        update_doc["metadata"] = params.metadata

    # Update the scene
    scenes_collection.update_one(
        {"scene_id": str(scene_id)},
        {"$set": update_doc}
    )

    # Return updated scene
    result = mongodb_get_scene(scene_id)
    if result is None:
        raise ValueError(f"Scene {scene_id} not found after update")
    return result


def mongodb_list_scenes(filters: SceneFilter) -> SceneListResponse:
    """
    List scenes with optional filtering.

    Authority: Any agent (read-only)
    Use Case: DL-4

    Args:
        filters: Filter and pagination parameters

    Returns:
        SceneListResponse with list of scenes and pagination info
    """
    mongo_client = get_mongodb_client()
    scenes_collection = mongo_client.get_collection("scenes")

    # Build query filter
    query_filter: Dict[str, Any] = {}

    if filters.story_id is not None:
        query_filter["story_id"] = str(filters.story_id)

    if filters.status is not None:
        query_filter["status"] = filters.status.value

    # Count total
    total = scenes_collection.count_documents(query_filter)

    # Determine sort order
    sort_field = "created_at" if filters.sort_by == "created_at" else "order"
    sort_order = 1 if filters.sort_order == "asc" else -1

    # Get scenes with pagination
    cursor = scenes_collection.find(query_filter).sort(
        sort_field, sort_order
    ).skip(filters.offset).limit(filters.limit)

    scenes = []
    for scene_doc in cursor:
        # Convert turns to TurnResponse objects
        turns = []
        for turn_data in scene_doc.get("turns", []):
            turns.append(
                TurnResponse(
                    turn_id=UUID(turn_data["turn_id"]),
                    speaker=turn_data["speaker"],
                    entity_id=UUID(turn_data["entity_id"]) if turn_data.get("entity_id") else None,
                    text=turn_data["text"],
                    metadata=turn_data.get("metadata", {}),
                    timestamp=turn_data["timestamp"],
                )
            )

        scenes.append(
            SceneResponse(
                scene_id=UUID(scene_doc["scene_id"]),
                story_id=UUID(scene_doc["story_id"]),
                universe_id=UUID(scene_doc["universe_id"]),
                title=scene_doc["title"],
                purpose=scene_doc.get("purpose"),
                status=scene_doc["status"],
                order=scene_doc.get("order"),
                location_id=UUID(scene_doc["location_id"]) if scene_doc.get("location_id") else None,
                participant_ids=[UUID(pid) for pid in scene_doc.get("participant_ids", [])],
                turns=turns,
                proposed_changes=[UUID(pc) for pc in scene_doc.get("proposed_changes", [])],
                canonical_outcomes=[UUID(co) for co in scene_doc.get("canonical_outcomes", [])],
                summary=scene_doc.get("summary"),
                metadata=scene_doc.get("metadata", {}),
                created_at=scene_doc["created_at"],
                updated_at=scene_doc["updated_at"],
                completed_at=scene_doc.get("completed_at"),
            )
        )

    return SceneListResponse(
        scenes=scenes,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


# =============================================================================
# TURN OPERATIONS
# =============================================================================


def mongodb_append_turn(scene_id: UUID, params: TurnCreate) -> TurnResponse:
    """
    Append a Turn to a Scene.

    Authority: Any agent (turns can be added by anyone)
    Use Case: DL-4

    Args:
        scene_id: UUID of the scene
        params: Turn creation parameters

    Returns:
        TurnResponse with created turn data

    Raises:
        ValueError: If scene not found
    """
    mongo_client = get_mongodb_client()
    scenes_collection = mongo_client.get_collection("scenes")

    # Verify scene exists
    scene_doc = scenes_collection.find_one({"scene_id": str(scene_id)})
    if not scene_doc:
        raise ValueError(f"Scene {scene_id} not found")

    # Create turn
    turn_id = uuid4()
    timestamp = datetime.now(timezone.utc)

    turn_doc = {
        "turn_id": str(turn_id),
        "speaker": params.speaker.value,
        "entity_id": str(params.entity_id) if params.entity_id else None,
        "text": params.text,
        "metadata": params.metadata,
        "timestamp": timestamp,
    }

    # Append turn to scene
    scenes_collection.update_one(
        {"scene_id": str(scene_id)},
        {
            "$push": {"turns": turn_doc},
            "$set": {"updated_at": timestamp}
        }
    )

    return TurnResponse(
        turn_id=turn_id,
        speaker=params.speaker,
        entity_id=params.entity_id,
        text=params.text,
        metadata=params.metadata,
        timestamp=timestamp,
    )
