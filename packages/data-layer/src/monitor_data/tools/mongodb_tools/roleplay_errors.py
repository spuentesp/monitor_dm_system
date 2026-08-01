"""MongoDB tools for structured roleplay error tracking.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: monitor_agents.services.roleplay_error_recorder (Layer 2), CLI (read-only)

See monitor_data.schemas.roleplay_errors for the record shape and why a
dedicated append-only collection was chosen over a field on Scene/Story/Turn.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.roleplay_errors import (
    RoleplayError,
    RoleplayErrorCategory,
    RoleplayErrorFilter,
    RoleplayErrorListResponse,
    RoleplayErrorResponse,
    RoleplayErrorSource,
)

# =============================================================================
# ROLEPLAY ERROR TOOLS
# =============================================================================


def _convert_roleplay_error_doc(doc: dict[str, Any]) -> RoleplayErrorResponse:
    """Convert a MongoDB roleplay_errors document into the response schema.

    Raises explicitly on a malformed doc rather than silently coercing —
    there is no legacy data in this collection to accommodate, so any
    shape mismatch is a real bug worth surfacing immediately.
    """
    return RoleplayErrorResponse(
        error_id=UUID(doc["error_id"]),
        occurred_at=doc["occurred_at"],
        source=RoleplayErrorSource(doc["source"]),
        category=RoleplayErrorCategory(doc["category"]),
        llm_error_class=doc.get("llm_error_class"),
        message=doc["message"],
        detail=doc.get("detail"),
        fatal=doc.get("fatal", False),
        universe_id=UUID(doc["universe_id"]) if doc.get("universe_id") else None,
        story_id=UUID(doc["story_id"]) if doc.get("story_id") else None,
        scene_id=UUID(doc["scene_id"]) if doc.get("scene_id") else None,
        conversation_id=doc.get("conversation_id"),
        turn_id=UUID(doc["turn_id"]) if doc.get("turn_id") else None,
        entity_id=UUID(doc["entity_id"]) if doc.get("entity_id") else None,
    )


def mongodb_record_roleplay_error(params: RoleplayError) -> RoleplayErrorResponse:
    """
    Record a single roleplay error event.

    Append-only: one document per error, never updated afterward. Callers
    (RoleplayErrorRecorder in monitor_agents) must treat this as best-effort
    and never let a failure here propagate — recording an error must not
    itself break the play loop.

    Args:
        params: The error record to persist

    Returns:
        RoleplayErrorResponse for the inserted record
    """
    mongodb = get_mongodb_client()
    collection = mongodb.get_collection("roleplay_errors")

    doc = {
        "error_id": str(params.error_id),
        "occurred_at": params.occurred_at,
        "source": params.source.value,
        "category": params.category.value,
        "llm_error_class": params.llm_error_class,
        "message": params.message,
        "detail": params.detail,
        "fatal": params.fatal,
        "universe_id": str(params.universe_id) if params.universe_id else None,
        "story_id": str(params.story_id) if params.story_id else None,
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "conversation_id": params.conversation_id,
        "turn_id": str(params.turn_id) if params.turn_id else None,
        "entity_id": str(params.entity_id) if params.entity_id else None,
    }

    collection.insert_one(doc)

    return _convert_roleplay_error_doc(doc)


def mongodb_list_roleplay_errors(params: RoleplayErrorFilter) -> RoleplayErrorListResponse:
    """
    List roleplay errors with optional filtering.

    Args:
        params: Filter options (source, category, correlation ids, time range, pagination)

    Returns:
        RoleplayErrorListResponse with matching errors
    """
    mongodb = get_mongodb_client()
    collection = mongodb.get_collection("roleplay_errors")

    query: dict[str, Any] = {}
    if params.source:
        query["source"] = params.source.value
    if params.category:
        query["category"] = params.category.value
    if params.fatal is not None:
        query["fatal"] = params.fatal
    if params.universe_id:
        query["universe_id"] = str(params.universe_id)
    if params.story_id:
        query["story_id"] = str(params.story_id)
    if params.scene_id:
        query["scene_id"] = str(params.scene_id)
    if params.conversation_id:
        query["conversation_id"] = params.conversation_id
    if params.since or params.until:
        occurred_range: dict[str, datetime] = {}
        if params.since:
            occurred_range["$gte"] = params.since
        if params.until:
            occurred_range["$lte"] = params.until
        query["occurred_at"] = occurred_range

    sort_dir = -1 if params.sort_order == "desc" else 1
    total = collection.count_documents(query)
    cursor = collection.find(query).sort("occurred_at", sort_dir).skip(params.offset).limit(params.limit)

    errors = [_convert_roleplay_error_doc(doc) for doc in cursor]

    return RoleplayErrorListResponse(
        errors=errors,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
