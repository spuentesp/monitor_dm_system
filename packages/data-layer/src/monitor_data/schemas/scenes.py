"""
Pydantic schemas for Scene and Turn operations (MongoDB).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for Scene and Turn CRUD operations.
Scenes are narrative episodes stored in MongoDB for flexibility.
Turns are individual exchanges within scenes.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from monitor_data.schemas.base import SceneStatus, Speaker, TemporalMode

# =============================================================================
# TURN SCHEMAS
# =============================================================================


class TurnCreate(BaseModel):
    """Request to create a Turn (append to scene)."""

    speaker: Speaker
    entity_id: UUID | None = Field(None, description="Entity ID if speaker is entity")
    text: str = Field(min_length=1, max_length=10000)
    resolution_ref: UUID | None = Field(None, description="Reference to resolution document")

    @field_validator("entity_id")
    @classmethod
    def validate_entity_speaker(cls, v: UUID | None, info: ValidationInfo) -> UUID | None:
        """Validate that entity_id is provided when speaker is entity."""
        if info.data.get("speaker") == Speaker.ENTITY and v is None:
            raise ValueError("entity_id required when speaker is entity")
        return v


class TurnResponse(BaseModel):
    """Response with Turn data."""

    turn_id: UUID
    speaker: Speaker
    entity_id: UUID | None = None
    text: str
    timestamp: datetime
    resolution_ref: UUID | None = Field(None, description="Reference to resolution document")

    model_config = {"from_attributes": True}


# =============================================================================
# SCENE SCHEMAS
# =============================================================================


class SceneCreate(BaseModel):
    """Request to create a Scene."""

    story_id: UUID
    universe_id: UUID
    scene_id: UUID | None = Field(None, description="Optional explicit Scene ID")
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=1000, description="Scene purpose or goal")
    narrative_order: int | None = Field(
        None,
        ge=0,
        description="Order the scene is presented to the player (presentation sequence)",
    )
    # Temporal context
    temporal_mode: TemporalMode = Field(
        default=TemporalMode.PRESENT,
        description="PRESENT for normal scenes; FLASHBACK/FLASH_FORWARD/DREAM for non-linear scenes",
    )
    time_ref: datetime | None = Field(
        None,
        description="In-universe timestamp — used for chronological timeline ordering",
    )
    time_description: str | None = Field(
        None,
        max_length=200,
        description="Human-readable time context, e.g. '15 years ago', 'the eve of the battle'",
    )
    parent_scene_id: UUID | None = Field(
        None,
        description="For FLASHBACK/DREAM scenes: the scene to resume when this scene ends",
    )
    location_ref: UUID | None = Field(None, description="EntityInstance ID for location")
    participating_entities: list[UUID] = Field(default_factory=list, description="EntityInstance IDs of participants")
    status: SceneStatus = Field(default=SceneStatus.ACTIVE)


class SceneUpdate(BaseModel):
    """Request to update a Scene.

    Enforces valid status transitions.
    """

    title: str | None = Field(None, min_length=1, max_length=200)
    purpose: str | None = Field(None, max_length=1000)
    status: SceneStatus | None = None
    summary: str | None = Field(None, max_length=5000, description="Scene summary")


class SceneResponse(BaseModel):
    """Response with Scene data."""

    scene_id: UUID
    story_id: UUID
    universe_id: UUID
    title: str
    purpose: str
    status: SceneStatus
    narrative_order: int | None = None
    temporal_mode: TemporalMode = TemporalMode.PRESENT
    time_ref: datetime | None = None
    time_description: str | None = None
    parent_scene_id: UUID | None = None
    location_ref: UUID | None = None
    participating_entities: list[UUID] = Field(default_factory=list)
    turns: list[TurnResponse] = Field(default_factory=list)
    proposed_changes: list[UUID] = Field(default_factory=list)
    canonical_outcomes: list[UUID] = Field(default_factory=list)
    summary: str = Field(default="")
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class SceneFilter(BaseModel):
    """Filter parameters for listing scenes."""

    story_id: UUID | None = None
    universe_id: UUID | None = None
    status: SceneStatus | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="created_at", description="Field to sort by: created_at, order")
    sort_order: str = Field(default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$")


class SceneListResponse(BaseModel):
    """Response with list of scenes and pagination info."""

    scenes: list[SceneResponse]
    total: int
    limit: int
    offset: int
