"""
Pydantic schemas for Scene and Turn operations (MongoDB).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for Scene and Turn CRUD operations.
Scenes are narrative episodes stored in MongoDB for flexibility.
Turns are individual exchanges within scenes.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from monitor_data.schemas.base import SceneStatus, Speaker


# =============================================================================
# TURN SCHEMAS
# =============================================================================


class TurnCreate(BaseModel):
    """Request to create a Turn (append to scene)."""

    speaker: Speaker
    entity_id: Optional[UUID] = Field(
        None, description="Entity ID if speaker is entity"
    )
    text: str = Field(min_length=1, max_length=10000)

    @field_validator("entity_id")
    @classmethod
    def validate_entity_speaker(cls, v: Optional[UUID], info) -> Optional[UUID]:
        """Validate that entity_id is provided when speaker is entity."""
        if info.data.get("speaker") == Speaker.ENTITY and v is None:
            raise ValueError("entity_id required when speaker is entity")
        return v


class TurnResponse(BaseModel):
    """Response with Turn data."""

    turn_id: UUID
    speaker: Speaker
    entity_id: Optional[UUID] = None
    text: str
    timestamp: datetime
    resolution_ref: Optional[UUID] = Field(
        None, description="Reference to resolution document"
    )

    model_config = {"from_attributes": True}


# =============================================================================
# SCENE SCHEMAS
# =============================================================================


class SceneCreate(BaseModel):
    """Request to create a Scene."""

    story_id: UUID
    universe_id: UUID
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(
        default="", max_length=1000, description="Scene purpose or goal"
    )
    order: Optional[int] = Field(None, ge=0, description="Scene order in story")
    location_ref: Optional[UUID] = Field(
        None, description="EntityInstance ID for location"
    )
    participating_entities: List[UUID] = Field(
        default_factory=list, description="EntityInstance IDs of participants"
    )
    status: SceneStatus = Field(default=SceneStatus.ACTIVE)


class SceneUpdate(BaseModel):
    """Request to update a Scene.

    Enforces valid status transitions.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    purpose: Optional[str] = Field(None, max_length=1000)
    status: Optional[SceneStatus] = None
    summary: Optional[str] = Field(None, max_length=5000, description="Scene summary")


class SceneResponse(BaseModel):
    """Response with Scene data."""

    scene_id: UUID
    story_id: UUID
    universe_id: UUID
    title: str
    purpose: str
    status: SceneStatus
    order: Optional[int] = None
    location_ref: Optional[UUID] = None
    participating_entities: List[UUID] = Field(default_factory=list)
    turns: List[TurnResponse] = Field(default_factory=list)
    proposed_changes: List[UUID] = Field(default_factory=list)
    canonical_outcomes: List[UUID] = Field(default_factory=list)
    summary: str = Field(default="")
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SceneFilter(BaseModel):
    """Filter parameters for listing scenes."""

    story_id: Optional[UUID] = None
    universe_id: Optional[UUID] = None
    status: Optional[SceneStatus] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at", description="Field to sort by: created_at, order"
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class SceneListResponse(BaseModel):
    """Response with list of scenes and pagination info."""

    scenes: List[SceneResponse]
    total: int
    limit: int
    offset: int
