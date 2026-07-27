"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.resolutions import (
    ResolutionCreate,
    ResolutionFilter,
    ResolutionListResponse,
    ResolutionResponse,
    ResolutionUpdate,
)

# =============================================================================
# RESOLUTION TOOLS (DL-24)
# =============================================================================


def _convert_resolution_doc_to_response(
    resolution_doc: dict[str, Any],
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
        Effect,
        Mechanics,
        ResolutionType,
        SuccessLevel,
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

    now = datetime.now(UTC)
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


def mongodb_get_resolution(resolution_id: UUID) -> ResolutionResponse | None:
    """
    Get a resolution by ID.

    Args:
        resolution_id: Resolution UUID

    Returns:
        ResolutionResponse or None if not found
    """
    mongodb = get_mongodb_client()
    resolutions_collection = mongodb.get_collection("resolutions")

    resolution_doc = resolutions_collection.find_one({"resolution_id": str(resolution_id)})
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
    query: dict[str, Any] = {}
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
    cursor = resolutions_collection.find(query).sort("created_at", -1).skip(params.offset).limit(params.limit)

    resolutions = [_convert_resolution_doc_to_response(doc) for doc in cursor]

    return ResolutionListResponse(
        resolutions=resolutions,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_update_resolution(resolution_id: UUID, params: ResolutionUpdate) -> ResolutionResponse:
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
    update_dict: dict[str, Any] = {}
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

    now = datetime.now(UTC)
    update_dict["updated_at"] = now

    result = resolutions_collection.update_one({"resolution_id": str(resolution_id)}, {"$set": update_dict})

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
