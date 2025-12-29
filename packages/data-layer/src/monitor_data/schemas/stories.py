"""
Pydantic schemas for Story operations (Neo4j).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Story CRUD operations.
Stories are canonical containers for narrative campaigns/arcs/episodes.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import StoryType, StoryStatus


# =============================================================================
# STORY SCHEMAS
# =============================================================================


class StoryCreate(BaseModel):
    """Request to create a Story."""

    universe_id: UUID
    title: str = Field(min_length=1, max_length=200)
    story_type: StoryType = Field(default=StoryType.CAMPAIGN)
    theme: str = Field(default="", max_length=500, description="Main theme or tone")
    premise: str = Field(
        default="", max_length=2000, description="Story premise or summary"
    )
    status: StoryStatus = Field(default=StoryStatus.PLANNED)
    start_time_ref: Optional[datetime] = Field(
        None, description="In-universe start time"
    )
    pc_ids: List[UUID] = Field(
        default_factory=list,
        description="Player character entity IDs (creates PARTICIPATES edges)",
    )


class StoryUpdate(BaseModel):
    """Request to update a Story.

    Only mutable fields can be updated: title, theme, premise, status.
    Structural fields require special operations.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    theme: Optional[str] = Field(None, max_length=500)
    premise: Optional[str] = Field(None, max_length=2000)
    status: Optional[StoryStatus] = None


class StoryResponse(BaseModel):
    """Response with Story data."""

    id: UUID
    universe_id: UUID
    title: str
    story_type: StoryType
    theme: str
    premise: str
    status: StoryStatus
    start_time_ref: Optional[datetime] = None
    end_time_ref: Optional[datetime] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    scene_count: int = Field(default=0, description="Number of scenes in this story")
    pc_ids: List[UUID] = Field(
        default_factory=list, description="Player character entity IDs"
    )

    model_config = {"from_attributes": True}


class StoryFilter(BaseModel):
    """Filter parameters for listing stories."""

    universe_id: Optional[UUID] = None
    story_type: Optional[StoryType] = None
    status: Optional[StoryStatus] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at", description="Field to sort by: created_at, title"
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class StoryListResponse(BaseModel):
    """Response with list of stories and pagination info."""

    stories: List[StoryResponse]
    total: int
    limit: int
    offset: int
