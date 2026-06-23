"""
Pydantic schemas for PlaySession operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

A PlaySession is a REAL-WORLD game night — a specific block of time
in which a player and the GM ran one or more scenes.

  Story (campaign arc) → many PlaySessions
  PlaySession → many Scenes

This is distinct from Scene (in-universe narrative unit) and Story
(canonical story arc). One long campaign may have 40+ sessions.

PlaySession data enables:
- "Show me a recap of last session" (context window loading)
- Session-level narrative generation (generate a readable chapter)
- XP tracking per session
- Real-world timestamp for when events occurred
- Player notes vs GM notes
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import SessionStatus


# =============================================================================
# PLAY SESSION CRUD SCHEMAS
# =============================================================================


class PlaySessionCreate(BaseModel):
    """Request to create/start a PlaySession."""

    story_id: UUID
    universe_id: UUID
    session_number: int = Field(
        ge=1, description="Session number within the story (session 1, 2, 3...)"
    )
    player_ids: List[UUID] = Field(
        default_factory=list,
        description="EntityInstance IDs of player characters who participated",
    )
    gm_notes: Optional[str] = Field(
        None,
        max_length=5000,
        description="GM prep notes / notes taken during session",
    )


class PlaySessionUpdate(BaseModel):
    """Request to update a PlaySession."""

    status: Optional[SessionStatus] = None
    ended_at: Optional[datetime] = None
    gm_notes: Optional[str] = Field(None, max_length=5000)
    player_notes: Optional[str] = Field(None, max_length=5000)
    summary: Optional[str] = Field(
        None,
        max_length=5000,
        description="Auto-generated or manually edited session summary",
    )
    xp_awarded: Optional[int] = Field(None, ge=0)
    # Updated as scenes are played during the session
    scene_ids: Optional[List[UUID]] = None


class PlaySessionAddScene(BaseModel):
    """Request to add a scene to the session's scene list."""

    session_id: UUID
    scene_id: UUID


class PlaySessionResponse(BaseModel):
    """Response with PlaySession data."""

    session_id: UUID
    story_id: UUID
    universe_id: UUID
    session_number: int
    status: SessionStatus
    player_ids: List[UUID]
    scene_ids: List[UUID] = Field(
        default_factory=list, description="Ordered list of scenes played this session"
    )
    gm_notes: Optional[str] = None
    player_notes: Optional[str] = None
    summary: Optional[str] = None
    xp_awarded: Optional[int] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(
        None, description="Session duration in minutes (computed from started/ended)"
    )
    narrative_id: Optional[UUID] = Field(
        None, description="ID of generated narrative for this session (if any)"
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class PlaySessionFilter(BaseModel):
    """Filter for listing play sessions."""

    story_id: Optional[UUID] = None
    universe_id: Optional[UUID] = None
    status: Optional[SessionStatus] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort_order: str = Field(
        default="asc",
        description="Sort by session_number: asc=oldest first, desc=newest first",
        pattern="^(asc|desc)$",
    )


class PlaySessionListResponse(BaseModel):
    """Response for list operations."""

    sessions: List[PlaySessionResponse]
    total: int
    limit: int
    offset: int
