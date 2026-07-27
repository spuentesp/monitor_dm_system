"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.working_state import (
    AddStatModification,
    CharacterWorkingState,
    InventoryChange,
    StatModification,
    TemporaryEffect,
    WorkingStateCreate,
    WorkingStateFilter,
    WorkingStateListResponse,
    WorkingStateResponse,
    WorkingStateUpdate,
)

# =============================================================================
# CHARACTER WORKING STATE (DL-26)
# =============================================================================


def _convert_working_state_doc_to_response(state_doc: dict[str, Any]) -> WorkingStateResponse:
    """
    Convert a working state document from MongoDB to a WorkingStateResponse object.

    Args:
        state_doc: Working state data from MongoDB

    Returns:
        WorkingStateResponse object
    """
    # Use "state_id" if creating the object requires an "id" field alias
    # But schema defines "id" and "state_id".

    return WorkingStateResponse(
        state=CharacterWorkingState(
            id=UUID(state_doc["state_id"]),
            state_id=UUID(state_doc["state_id"]),
            entity_id=UUID(state_doc["entity_id"]),
            scene_id=UUID(state_doc["scene_id"]),
            story_id=UUID(state_doc["story_id"]),
            base_stats=state_doc["base_stats"],
            current_stats=state_doc["current_stats"],
            resources=state_doc["resources"],
            modifications=[StatModification(**m) for m in state_doc.get("modifications", [])],
            temporary_effects=[TemporaryEffect(**e) for e in state_doc.get("temporary_effects", [])],
            inventory_changes=[InventoryChange(**i) for i in state_doc.get("inventory_changes", [])],
            created_at=state_doc.get("created_at", datetime.now(UTC)),
            updated_at=state_doc.get("updated_at", datetime.now(UTC)),
            canonized=state_doc.get("canonized", False),
            canonized_at=state_doc.get("canonized_at"),
        )
    )


def mongodb_create_working_state(
    params: WorkingStateCreate,
) -> WorkingStateResponse:
    """
    Create a new character working state record.

    Args:
        params: Creation parameters

    Returns:
        WorkingStateResponse
    """
    mongodb = get_mongodb_client()
    state_collection = mongodb.get_collection("character_working_state")

    # Check existence
    existing = state_collection.find_one(
        {
            "entity_id": str(params.entity_id),
            "scene_id": str(params.scene_id),
        }
    )
    if existing:
        return _convert_working_state_doc_to_response(existing)

    state_id = uuid4()
    now = datetime.now(UTC)

    # Initialize current stats as base if not provided
    current_stats = params.current_stats or params.base_stats.copy()

    state_doc = {
        "state_id": str(state_id),
        "entity_id": str(params.entity_id),
        "scene_id": str(params.scene_id),
        "story_id": str(params.story_id),
        "base_stats": params.base_stats,
        "current_stats": current_stats,
        "resources": params.resources,
        "modifications": [],
        "temporary_effects": [],
        "inventory_changes": [],
        "created_at": now,
        "updated_at": now,
        "canonized": False,
        "canonized_at": None,
    }

    state_collection.insert_one(state_doc)
    return _convert_working_state_doc_to_response(state_doc)


def mongodb_get_working_state(entity_id: UUID, scene_id: UUID) -> WorkingStateResponse | None:
    """Get working state by entity and scene."""
    mongodb = get_mongodb_client()
    state_collection = mongodb.get_collection("character_working_state")

    doc = state_collection.find_one({"entity_id": str(entity_id), "scene_id": str(scene_id)})
    if not doc:
        return None
    return _convert_working_state_doc_to_response(doc)


def mongodb_update_working_state(state_id: UUID, params: WorkingStateUpdate) -> WorkingStateResponse:
    """Update working state stats or resources."""
    mongodb = get_mongodb_client()
    state_collection = mongodb.get_collection("character_working_state")

    update_dict: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if params.current_stats is not None:
        update_dict["current_stats"] = params.current_stats
    if params.resources is not None:
        update_dict["resources"] = params.resources

    result = state_collection.find_one_and_update(
        {"state_id": str(state_id)},
        {"$set": update_dict},
        return_document=True,
    )

    if not result:
        raise ValueError(f"Working state {state_id} not found")

    return _convert_working_state_doc_to_response(result)


def mongodb_add_modification(params: AddStatModification) -> WorkingStateResponse:
    """Log a stat modification."""
    mongodb = get_mongodb_client()
    state_collection = mongodb.get_collection("character_working_state")

    mod = StatModification(
        mod_id=uuid4(),
        stat_or_resource=params.stat_or_resource,
        change=params.change,
        source=params.source,
        source_id=params.source_id,
        timestamp=datetime.now(UTC),
    )

    result = state_collection.find_one_and_update(
        {"state_id": str(params.state_id)},
        {
            "$push": {"modifications": mod.model_dump(mode="json")},
            "$set": {"updated_at": datetime.now(UTC)},
        },
        return_document=True,
    )

    if not result:
        raise ValueError(f"Working state {params.state_id} not found")

    return _convert_working_state_doc_to_response(result)


def mongodb_list_working_states(params: WorkingStateFilter) -> WorkingStateListResponse:
    """List working states with filtering."""
    mongodb = get_mongodb_client()
    state_collection = mongodb.get_collection("character_working_state")

    query: dict[str, Any] = {}
    if params.scene_id:
        query["scene_id"] = str(params.scene_id)
    if params.story_id:
        query["story_id"] = str(params.story_id)
    if params.entity_id:
        query["entity_id"] = str(params.entity_id)
    if params.canonized is not None:
        query["canonized"] = params.canonized

    total = state_collection.count_documents(query)
    cursor = state_collection.find(query).skip(params.offset).limit(params.limit)

    states = [_convert_working_state_doc_to_response(doc).state for doc in cursor]

    return WorkingStateListResponse(
        states=states,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
