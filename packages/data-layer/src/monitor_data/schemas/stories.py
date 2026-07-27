"""
Pydantic schemas for Story operations (Neo4j).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Story CRUD operations.
Stories are canonical containers for narrative campaigns/arcs/episodes.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import StoryStatus, StoryType

# =============================================================================
# STORY SCHEMAS
# =============================================================================


class StoryCreate(BaseModel):
    """Request to create a Story."""

    universe_id: UUID
    id: UUID | None = Field(None, description="Optional explicit Story ID")
    title: str = Field(min_length=1, max_length=200)
    story_type: StoryType = Field(default=StoryType.CAMPAIGN)
    theme: str = Field(default="", max_length=500, description="Main theme or tone")
    premise: str = Field(default="", max_length=2000, description="Story premise or summary")
    status: StoryStatus = Field(default=StoryStatus.PLANNED)
    start_time_ref: datetime | None = Field(None, description="In-universe start time")
    pc_ids: list[UUID] = Field(
        default_factory=list,
        description="Player character entity IDs (creates PARTICIPATES edges)",
    )
    # Game system binding
    game_system_id: UUID | None = Field(
        None,
        description="Game system (rules/dice) to use for this story. Falls back to Universe.default_game_system_id.",
    )
    # Setting lore
    is_setting_lore: bool = Field(
        default=False,
        description="True for canonical setting events (Horus Heresy, etc.); False for playable stories",
    )
    lore_era: str | None = Field(
        None,
        max_length=200,
        description="In-universe era label, e.g. 'M31', 'Third Age', '500 years before present'",
    )


class StoryUpdate(BaseModel):
    """Request to update a Story.

    Only mutable fields can be updated: title, theme, premise, status.
    Structural fields require special operations.
    """

    title: str | None = Field(None, min_length=1, max_length=200)
    theme: str | None = Field(None, max_length=500)
    premise: str | None = Field(None, max_length=2000)
    status: StoryStatus | None = None


class StoryResponse(BaseModel):
    """Response with Story data."""

    id: UUID
    universe_id: UUID
    title: str
    story_type: StoryType
    theme: str
    premise: str
    status: StoryStatus
    start_time_ref: datetime | None = None
    end_time_ref: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None
    scene_count: int = Field(default=0, description="Number of scenes in this story")
    pc_ids: list[UUID] = Field(default_factory=list, description="Player character entity IDs")
    game_system_id: UUID | None = None
    is_setting_lore: bool = False
    lore_era: str | None = None

    model_config = {"from_attributes": True}


class StoryFilter(BaseModel):
    """Filter parameters for listing stories."""

    universe_id: UUID | None = None
    story_type: StoryType | None = None
    status: StoryStatus | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="created_at", description="Field to sort by: created_at, title")
    sort_order: str = Field(default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$")


class StoryListResponse(BaseModel):
    """Response with list of stories and pagination info."""

    stories: list[StoryResponse]
    total: int
    limit: int
    offset: int


# Re-export base schemas for convenience
__all__ = [
    "StoryCreate",
    "StoryFilter",
    "StoryListResponse",
    "StoryResponse",
    "StoryStatus",
    "StoryType",
    "StoryUpdate",
]
