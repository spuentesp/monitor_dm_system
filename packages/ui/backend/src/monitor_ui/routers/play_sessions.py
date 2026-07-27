"""Play Sessions router — the P-15 Play Home entry point.

Exposes CRUD for ``PlaySession`` (real-world game-night records) plus the
``/play/home`` aggregate that powers the Play Home "Continue Story /
Recent Recaps" widget.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from monitor_data.schemas.base import SessionStatus
from monitor_data.schemas.play_sessions import (
    PlaySessionCreate,
    PlaySessionFilter,
    PlaySessionListResponse,
    PlaySessionResponse,
    PlaySessionUpdate,
)
from monitor_data.tools.mongodb_tools.play_sessions import (
    mongodb_add_scene_to_play_session,
    mongodb_create_play_session,
    mongodb_get_latest_play_session,
    mongodb_get_play_session,
    mongodb_list_play_sessions,
    mongodb_list_recent_play_sessions,
    mongodb_update_play_session,
)
from pydantic import BaseModel

from .ingest_shared import db_op, validate_uuid

router = APIRouter()


# ---------------------------------------------------------------------------
# UI-layer request models
# ---------------------------------------------------------------------------


class PlayHomeResponse(BaseModel):
    """Aggregate payload for the Play Home screen (P-15)."""

    active_sessions: list[PlaySessionResponse]
    recent_recaps: list[PlaySessionResponse]


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("/play-sessions", response_model=PlaySessionResponse, status_code=201)
async def create_play_session(body: PlaySessionCreate) -> PlaySessionResponse:
    """Start a new PlaySession. Rejects duplicate session numbers per story."""
    with db_op():
        try:
            return mongodb_create_play_session(body)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/play-sessions/{session_id}", response_model=PlaySessionResponse)
async def get_play_session(session_id: str) -> PlaySessionResponse:
    """Fetch one session by id."""
    session_uuid = validate_uuid(session_id, "session_id")
    with db_op():
        result = mongodb_get_play_session(session_uuid)
    if not result:
        raise HTTPException(status_code=404, detail=f"PlaySession {session_id} not found")
    return result


@router.get("/play-sessions", response_model=PlaySessionListResponse)
async def list_play_sessions(
    story_id: str | None = Query(default=None),
    universe_id: str | None = Query(default=None),
    status: SessionStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> PlaySessionListResponse:
    """List sessions with optional filters + pagination."""
    filters = PlaySessionFilter(
        story_id=validate_uuid(story_id, "story_id") if story_id else None,
        universe_id=validate_uuid(universe_id, "universe_id") if universe_id else None,
        status=status,
        limit=limit,
        offset=offset,
        sort_order=sort_order,
    )
    with db_op():
        return mongodb_list_play_sessions(filters)


@router.patch("/play-sessions/{session_id}", response_model=PlaySessionResponse)
async def update_play_session(session_id: str, body: PlaySessionUpdate) -> PlaySessionResponse:
    """Apply a partial update (status, notes, summary, xp, scene_ids)."""
    session_uuid = validate_uuid(session_id, "session_id")
    with db_op():
        result = mongodb_update_play_session(session_uuid, body)
    if not result:
        raise HTTPException(status_code=404, detail=f"PlaySession {session_id} not found")
    return result


@router.post("/play-sessions/{session_id}/scenes/{scene_id}", response_model=PlaySessionResponse)
async def add_scene(session_id: str, scene_id: str) -> PlaySessionResponse:
    """Append a scene to a session's ordered scene list (idempotent)."""
    session_uuid = validate_uuid(session_id, "session_id")
    scene_uuid = validate_uuid(scene_id, "scene_id")
    with db_op():
        result = mongodb_add_scene_to_play_session(session_uuid, scene_uuid)
    if not result:
        raise HTTPException(status_code=404, detail=f"PlaySession {session_id} not found")
    return result


# ---------------------------------------------------------------------------
# Convenience / aggregate endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/stories/{story_id}/play-sessions/latest",
    response_model=PlaySessionResponse | None,
)
async def latest_session(story_id: str) -> PlaySessionResponse | None:
    """Return the most recent session for a story, or null."""
    story_uuid = validate_uuid(story_id, "story_id")
    with db_op():
        return mongodb_get_latest_play_session(story_uuid)


@router.get(
    "/universes/{universe_id}/play-sessions/recent",
    response_model=list[PlaySessionResponse],
)
async def recent_sessions(
    universe_id: str,
    limit: int = Query(default=10, ge=1, le=50),
) -> list[PlaySessionResponse]:
    """Return the N most recent sessions for a universe (any status)."""
    universe_uuid = validate_uuid(universe_id, "universe_id")
    with db_op():
        return mongodb_list_recent_play_sessions(universe_uuid, limit=limit)


@router.get("/universes/{universe_id}/play-home", response_model=PlayHomeResponse)
async def play_home(universe_id: str) -> PlayHomeResponse:
    """P-15 Play Home aggregate payload: active + recent sessions for a universe."""
    universe_uuid = validate_uuid(universe_id, "universe_id")
    with db_op():
        active = mongodb_list_play_sessions(
            PlaySessionFilter(
                universe_id=universe_uuid,
                status=SessionStatus.ACTIVE,
                limit=10,
            )
        ).sessions
        recent = mongodb_list_recent_play_sessions(universe_uuid, limit=10)
    return PlayHomeResponse(active_sessions=active, recent_recaps=recent)
