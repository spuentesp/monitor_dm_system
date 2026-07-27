"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client

# =============================================================================
# CONVERSATION SESSION OPERATIONS (DL-20)
# =============================================================================
from monitor_data.schemas.conversations import (
    AppendConversationTurn,
    ConversationMode,
    ConversationSessionCreate,
    ConversationSessionFilter,
    ConversationSessionListResponse,
    ConversationSessionResponse,
    ConversationSessionUpdate,
    ConversationStatus,
    ConversationTurn,
)


def _conversation_doc_to_response(doc: dict[str, Any]) -> ConversationSessionResponse:
    turns = [
        ConversationTurn(
            turn_index=t["turn_index"],
            speaker_role=t["speaker_role"],
            entity_id=UUID(t["entity_id"]) if t.get("entity_id") else None,
            entity_name=t.get("entity_name"),
            text=t["text"],
            emotional_state=t.get("emotional_state"),
            timestamp=t["timestamp"],
        )
        for t in doc.get("turns", [])
    ]
    return ConversationSessionResponse(
        conversation_id=UUID(doc["conversation_id"]),
        universe_id=UUID(doc["universe_id"]),
        mode=ConversationMode(doc["mode"]),
        status=ConversationStatus(doc["status"]),
        npc_ids=[UUID(nid) for nid in doc["npc_ids"]],
        scene_id=UUID(doc["scene_id"]) if doc.get("scene_id") else None,
        story_id=UUID(doc["story_id"]) if doc.get("story_id") else None,
        player_entity_id=UUID(doc["player_entity_id"]) if doc.get("player_entity_id") else None,
        turns=turns,
        metadata=doc.get("metadata", {}),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        completed_at=doc.get("completed_at"),
    )


def mongodb_create_conversation(params: ConversationSessionCreate) -> ConversationSessionResponse:
    """
    Open a new NPC ConversationSession document in MongoDB.

    Authority: NPCVoice, Narrator
    Use Case: DL-20, P-17, M-31

    Args:
        params: Session creation parameters.

    Returns:
        ConversationSessionResponse with the new session.
    """
    client = get_mongodb_client()
    conversation_id = uuid4()
    now = datetime.now(UTC)

    doc = {
        "conversation_id": str(conversation_id),
        "universe_id": str(params.universe_id),
        "mode": params.mode.value,
        "status": ConversationStatus.ACTIVE.value,
        "npc_ids": [str(nid) for nid in params.npc_ids],
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "story_id": str(params.story_id) if params.story_id else None,
        "player_entity_id": str(params.player_entity_id) if params.player_entity_id else None,
        "turns": [],
        "metadata": params.metadata,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    client["conversations"].insert_one(doc)
    return _conversation_doc_to_response(doc)


def mongodb_get_conversation(conversation_id: UUID) -> ConversationSessionResponse | None:
    """
    Retrieve a ConversationSession by ID.

    Authority: all agents (read)
    Use Case: DL-20

    Args:
        conversation_id: UUID of the session.

    Returns:
        ConversationSessionResponse or None if not found.
    """
    client = get_mongodb_client()
    doc = client["conversations"].find_one({"conversation_id": str(conversation_id)})
    if not doc:
        return None
    return _conversation_doc_to_response(doc)


def mongodb_get_recent_conversation_turns(
    scene_id: UUID,
    story_id: UUID | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return recent flattened conversation turns for a scene/story context.

    Authority: all agents (read)
    Use Case: DL-20, P-17, M-31
    """
    client = get_mongodb_client()
    query: dict[str, Any] = {"scene_id": str(scene_id)}
    if story_id is not None:
        query["story_id"] = str(story_id)

    docs = list(client["conversations"].find(query).sort("updated_at", -1).limit(max(1, min(int(limit), 100))))

    flattened: list[dict[str, Any]] = [
        {
            "conversation_id": doc.get("conversation_id"),
            "mode": doc.get("mode"),
            "turn_index": turn.get("turn_index"),
            "speaker_role": turn.get("speaker_role"),
            "entity_id": turn.get("entity_id"),
            "entity_name": turn.get("entity_name"),
            "text": turn.get("text"),
            "emotional_state": turn.get("emotional_state"),
            "timestamp": turn.get("timestamp"),
        }
        for doc in docs
        for turn in doc.get("turns", [])
    ]

    flattened.sort(key=lambda t: t.get("timestamp") or datetime.min, reverse=True)
    return flattened[: max(1, min(int(limit), 100))]


def mongodb_append_conversation_turn(
    conversation_id: UUID,
    params: AppendConversationTurn,
) -> ConversationSessionResponse:
    """
    Append a single turn to an active ConversationSession.

    Authority: NPCVoice, Narrator
    Use Case: DL-20, P-17, M-31

    Args:
        conversation_id: UUID of the active session.
        params:          Turn data to append.

    Returns:
        Updated ConversationSessionResponse.

    Raises:
        ValueError: If session not found or not active.
    """
    client = get_mongodb_client()
    doc = client["conversations"].find_one({"conversation_id": str(conversation_id)})
    if not doc:
        raise ValueError(f"ConversationSession {conversation_id} not found")
    if doc["status"] != ConversationStatus.ACTIVE.value:
        raise ValueError(f"Cannot append to conversation {conversation_id}: status={doc['status']}")

    turn_index = len(doc.get("turns", []))
    now = datetime.now(UTC)

    new_turn = {
        "turn_index": turn_index,
        "speaker_role": params.speaker_role,
        "entity_id": str(params.entity_id) if params.entity_id else None,
        "entity_name": params.entity_name,
        "text": params.text,
        "emotional_state": params.emotional_state,
        "timestamp": now,
    }

    client["conversations"].update_one(
        {"conversation_id": str(conversation_id)},
        {
            "$push": {"turns": new_turn},
            "$set": {"updated_at": now},
        },
    )

    updated_doc = client["conversations"].find_one({"conversation_id": str(conversation_id)})
    if updated_doc is None:
        raise ValueError(f"ConversationSession {conversation_id} not found after append")
    return _conversation_doc_to_response(updated_doc)


def mongodb_update_conversation(
    conversation_id: UUID,
    params: ConversationSessionUpdate,
) -> ConversationSessionResponse:
    """
    Update status or metadata of a ConversationSession (e.g., mark completed).

    Authority: NPCVoice, Orchestrator
    Use Case: DL-20

    Args:
        conversation_id: UUID of the session.
        params:          Fields to update.

    Returns:
        Updated ConversationSessionResponse.

    Raises:
        ValueError: If session not found.
    """
    client = get_mongodb_client()
    doc = client["conversations"].find_one({"conversation_id": str(conversation_id)})
    if not doc:
        raise ValueError(f"ConversationSession {conversation_id} not found")

    now = datetime.now(UTC)
    update_fields: dict[str, Any] = {"updated_at": now}

    if params.status is not None:
        update_fields["status"] = params.status.value
        if params.status in (ConversationStatus.COMPLETED, ConversationStatus.ABANDONED):
            update_fields["completed_at"] = now

    if params.metadata is not None:
        update_fields["metadata"] = params.metadata

    client["conversations"].update_one(
        {"conversation_id": str(conversation_id)},
        {"$set": update_fields},
    )

    updated_doc = client["conversations"].find_one({"conversation_id": str(conversation_id)})
    if updated_doc is None:
        raise ValueError(f"ConversationSession {conversation_id} not found after update")
    return _conversation_doc_to_response(updated_doc)


def mongodb_list_conversations(
    filter_params: ConversationSessionFilter,
) -> ConversationSessionListResponse:
    """
    List ConversationSessions with optional filtering.

    Authority: all agents (read)
    Use Case: DL-20

    Args:
        filter_params: Filter and pagination options.

    Returns:
        ConversationSessionListResponse with matching sessions.
    """
    client = get_mongodb_client()

    query: dict[str, Any] = {}
    if filter_params.universe_id:
        query["universe_id"] = str(filter_params.universe_id)
    if filter_params.scene_id:
        query["scene_id"] = str(filter_params.scene_id)
    if filter_params.story_id:
        query["story_id"] = str(filter_params.story_id)
    if filter_params.npc_id:
        query["npc_ids"] = str(filter_params.npc_id)
    if filter_params.mode:
        query["mode"] = filter_params.mode.value
    if filter_params.status:
        query["status"] = filter_params.status.value

    total = client["conversations"].count_documents(query)
    docs = list(
        client["conversations"].find(query).skip(filter_params.offset).limit(filter_params.limit).sort("created_at", -1)
    )

    return ConversationSessionListResponse(
        sessions=[_conversation_doc_to_response(d) for d in docs],
        total=total,
        limit=filter_params.limit,
        offset=filter_params.offset,
    )
