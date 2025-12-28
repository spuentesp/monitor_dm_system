"""
Pydantic schemas for Scene and Turn operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for Scene and Turn operations.
Scenes are narrative episodes stored in MongoDB for flexibility.
Turns are individual exchanges within scenes.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from monitor_data.schemas.base import SceneStatus, Speaker


# =============================================================================
# TURN SCHEMAS
# =============================================================================


class TurnCreate(BaseModel):
    """Request to create a Turn within a Scene."""

    speaker: Speaker
    entity_id: Optional[UUID] = Field(
        None, description="Entity ID if speaker is ENTITY"
    )
    text: str = Field(min_length=1)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata (dice rolls, resolution refs, etc.)",
    )

    @field_validator("entity_id")
    @classmethod
    def validate_entity_for_entity_speaker(
        cls, v: Optional[UUID], info
    ) -> Optional[UUID]:
        """Validate that entity_id is provided when speaker is ENTITY."""
        if info.data.get("speaker") == Speaker.ENTITY and v is None:
            raise ValueError("entity_id is required when speaker is ENTITY")
        return v


class TurnResponse(BaseModel):
    """Response with Turn data."""

    turn_id: UUID
    speaker: Speaker
    entity_id: Optional[UUID] = None
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# SCENE SCHEMAS
# =============================================================================


class SceneCreate(BaseModel):
    """Request to create a Scene."""

    story_id: UUID
    title: str = Field(min_length=1, max_length=500)
    purpose: Optional[str] = Field(
        None, max_length=2000, description="Scene objective or purpose"
    )
    order: Optional[int] = Field(
        None, ge=0, description="Optional ordering within the story"
    )
    location_id: Optional[UUID] = Field(
        None, description="Entity ID of location (if applicable)"
    )
    participant_ids: List[UUID] = Field(
        default_factory=list,
        description="Entity IDs of participants in this scene",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata for the scene",
    )


class SceneUpdate(BaseModel):
    """Request to update a Scene.

    Only status, summary, and metadata can be updated.
    """

    status: Optional[SceneStatus] = None
    summary: Optional[str] = Field(
        None, max_length=5000, description="Scene summary for retrieval"
    )
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("status")
    @classmethod
    def validate_status_transition(
        cls, v: Optional[SceneStatus]
    ) -> Optional[SceneStatus]:
        """Validate status transitions."""
        # Valid transitions:
        # active -> finalizing
        # finalizing -> completed
        # Any status can be set on creation, but updates must follow the flow
        # This will be enforced in the tool function with context of current status
        return v


class SceneResponse(BaseModel):
    """Response with Scene data."""

    scene_id: UUID
    story_id: UUID
    universe_id: UUID
    title: str
    purpose: Optional[str] = None
    status: SceneStatus
    order: Optional[int] = None
    location_id: Optional[UUID] = None
    participant_ids: List[UUID] = Field(default_factory=list)
    turns: List[TurnResponse] = Field(default_factory=list)
    proposed_changes: List[UUID] = Field(
        default_factory=list,
        description="IDs of proposed changes from this scene",
    )
    canonical_outcomes: List[UUID] = Field(
        default_factory=list,
        description="IDs of Facts/Events written to Neo4j",
    )
    summary: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SceneFilter(BaseModel):
    """Filter parameters for listing scenes."""

    story_id: Optional[UUID] = None
    status: Optional[SceneStatus] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at",
        description="Field to sort by: created_at, order",
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
