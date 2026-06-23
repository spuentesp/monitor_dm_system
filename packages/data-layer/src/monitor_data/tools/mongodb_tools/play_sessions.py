"""MongoDB tools for PlaySession (real-world game night) records.

LAYER: 1 (data-layer)

Implements the data-layer side of P-15 (Start Play Session).

A ``PlaySession`` is a real-world block of time during which the user played
one or more scenes. It is distinct from a ``Story`` (canonical narrative
arc) and a ``Scene`` (in-universe narrative unit). One campaign may have
40+ PlaySessions.

This module provides the CRUD surface that the agents and routers consume.
Tools are sync (matching the rest of ``mongodb_tools``) and delegate the
actual I/O to ``get_mongodb_client()``.

Use cases:
- P-15: Start Play Session
- Q-3:  Show last-session recap
- SYS-4: Session lifecycle persistence
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.base import SessionStatus
from monitor_data.schemas.play_sessions import (
    PlaySessionCreate,
    PlaySessionFilter,
    PlaySessionListResponse,
    PlaySessionResponse,
    PlaySessionUpdate,
)
from monitor_data.tools._shared import utcnow as _utcnow


COLLECTION = "play_sessions"


# =============================================================================
# HELPERS
# =============================================================================


def _convert_doc_to_response(doc: Dict[str, Any]) -> PlaySessionResponse:
    """Translate a raw MongoDB document into a ``PlaySessionResponse``."""
    started_at: datetime = doc["started_at"]
    ended_at: Optional[datetime] = doc.get("ended_at")
    duration_minutes: Optional[int] = None
    if ended_at and started_at:
        duration_minutes = max(0, int((ended_at - started_at).total_seconds() // 60))

    return PlaySessionResponse(
        session_id=UUID(doc["session_id"]),
        story_id=UUID(doc["story_id"]),
        universe_id=UUID(doc["universe_id"]),
        session_number=int(doc["session_number"]),
        status=SessionStatus(doc.get("status", SessionStatus.ACTIVE.value)),
        player_ids=[UUID(pid) for pid in doc.get("player_ids", [])],
        scene_ids=[UUID(sid) for sid in doc.get("scene_ids", [])],
        gm_notes=doc.get("gm_notes"),
        player_notes=doc.get("player_notes"),
        summary=doc.get("summary"),
        xp_awarded=doc.get("xp_awarded"),
        started_at=started_at,
        ended_at=ended_at,
        duration_minutes=duration_minutes,
        narrative_id=UUID(doc["narrative_id"]) if doc.get("narrative_id") else None,
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _ensure_indexes() -> None:
    """Create the indexes we rely on (idempotent)."""
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)
    coll.create_index([("session_id", 1)], unique=True)
    coll.create_index([("story_id", 1), ("session_number", 1)], unique=True)
    coll.create_index([("universe_id", 1), ("status", 1)])
    coll.create_index([("started_at", -1)])


# =============================================================================
# CRUD TOOLS
# =============================================================================


def mongodb_create_play_session(params: PlaySessionCreate) -> PlaySessionResponse:
    """Create a new PlaySession and return its response.

    Use case: P-15 (Start Play Session).
    Authority: anyone (the user owns their sessions).
    """
    client = get_mongodb_client()
    _ensure_indexes()
    coll = client.get_collection(COLLECTION)

    # Reject duplicate session numbers within the same story
    if coll.find_one(
        {
            "story_id": str(params.story_id),
            "session_number": params.session_number,
        }
    ):
        raise ValueError(
            f"Session #{params.session_number} already exists for story {params.story_id}"
        )

    now = _utcnow()
    doc: Dict[str, Any] = {
        "session_id": str(uuid4()),
        "story_id": str(params.story_id),
        "universe_id": str(params.universe_id),
        "session_number": params.session_number,
        "status": SessionStatus.ACTIVE.value,
        "player_ids": [str(pid) for pid in params.player_ids],
        "scene_ids": [],
        "gm_notes": params.gm_notes,
        "started_at": now,
        "created_at": now,
        "updated_at": now,
    }
    coll.insert_one(doc)
    return _convert_doc_to_response(doc)


def mongodb_get_play_session(session_id: UUID) -> Optional[PlaySessionResponse]:
    """Fetch a single PlaySession by id.

    Returns ``None`` if the session does not exist.
    """
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)
    doc = coll.find_one({"session_id": str(session_id)})
    if not doc:
        return None
    return _convert_doc_to_response(doc)


def mongodb_list_play_sessions(filters: PlaySessionFilter) -> PlaySessionListResponse:
    """List PlaySessions with optional filters and pagination.

    Sort order: ``asc`` = oldest session first (good for a recap feed),
    ``desc`` = newest first (good for "recent sessions" widgets).
    """
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)

    query: Dict[str, Any] = {}
    if filters.story_id is not None:
        query["story_id"] = str(filters.story_id)
    if filters.universe_id is not None:
        query["universe_id"] = str(filters.universe_id)
    if filters.status is not None:
        query["status"] = filters.status.value

    direction = -1 if filters.sort_order == "desc" else 1
    cursor = (
        coll.find(query).sort("session_number", direction).skip(filters.offset).limit(filters.limit)
    )
    sessions = [_convert_doc_to_response(doc) for doc in cursor]
    total = coll.count_documents(query)
    return PlaySessionListResponse(
        sessions=sessions,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


def mongodb_update_play_session(
    session_id: UUID, params: PlaySessionUpdate
) -> Optional[PlaySessionResponse]:
    """Apply a partial update to a PlaySession.

    Returns the updated session, or ``None`` if the session does not exist.
    """
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)

    update: Dict[str, Any] = {}
    if params.status is not None:
        update["status"] = params.status.value
        if params.status == SessionStatus.COMPLETED and params.ended_at is None:
            update["ended_at"] = _utcnow()
    if params.ended_at is not None:
        update["ended_at"] = params.ended_at
    if params.gm_notes is not None:
        update["gm_notes"] = params.gm_notes
    if params.player_notes is not None:
        update["player_notes"] = params.player_notes
    if params.summary is not None:
        update["summary"] = params.summary
    if params.xp_awarded is not None:
        update["xp_awarded"] = params.xp_awarded
    if params.scene_ids is not None:
        update["scene_ids"] = [str(sid) for sid in params.scene_ids]

    if not update:
        # Nothing to do — return current state
        return mongodb_get_play_session(session_id)

    update["updated_at"] = _utcnow()
    res = coll.find_one_and_update(
        {"session_id": str(session_id)},
        {"$set": update},
        return_document=True,  # ReturnDocument.AFTER equivalent
    )
    if not res:
        return None
    return _convert_doc_to_response(res)


def mongodb_add_scene_to_play_session(
    session_id: UUID, scene_id: UUID
) -> Optional[PlaySessionResponse]:
    """Append a scene to the session's ordered ``scene_ids`` list (idempotent)."""
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)
    res = coll.find_one_and_update(
        {"session_id": str(session_id)},
        {
            "$addToSet": {"scene_ids": str(scene_id)},
            "$set": {"updated_at": _utcnow()},
        },
        return_document=True,
    )
    if not res:
        return None
    return _convert_doc_to_response(res)


def mongodb_get_latest_play_session(story_id: UUID) -> Optional[PlaySessionResponse]:
    """Return the most recent PlaySession for a story, or ``None``."""
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)
    cursor = coll.find({"story_id": str(story_id)}).sort("session_number", -1).limit(1)
    docs = list(cursor)
    if not docs:
        return None
    return _convert_doc_to_response(docs[0])


def mongodb_list_recent_play_sessions(
    universe_id: UUID, limit: int = 10
) -> List[PlaySessionResponse]:
    """Return the N most recent sessions for a universe, regardless of status.

    Used by the Play Home "Recent Recaps" widget.
    """
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)
    cursor = coll.find({"universe_id": str(universe_id)}).sort("started_at", -1).limit(limit)
    return [_convert_doc_to_response(doc) for doc in cursor]
