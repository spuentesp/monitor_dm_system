"""
Pydantic schemas for Story operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Story CRUD operations.
Stories are canonical containers in Neo4j linking narratives to universes.
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
    title: str = Field(min_length=1, max_length=500)
    story_type: StoryType = Field(default=StoryType.CAMPAIGN)
    theme: Optional[str] = Field(None, max_length=1000)
    premise: Optional[str] = Field(None, max_length=2000)
    pc_ids: List[UUID] = Field(
        default_factory=list,
        description="Player character entity IDs (creates PARTICIPATES edges)",
    )
    start_time_ref: Optional[datetime] = Field(
        None, description="In-universe time when story starts"
    )


class StoryUpdate(BaseModel):
    """Request to update a Story.

    Only mutable fields can be updated: title, status, theme, premise.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    status: Optional[StoryStatus] = None
    theme: Optional[str] = Field(None, max_length=1000)
    premise: Optional[str] = Field(None, max_length=2000)
    end_time_ref: Optional[datetime] = Field(
        None, description="In-universe time when story ends"
    )


class StoryResponse(BaseModel):
    """Response with Story data."""

    id: UUID
    universe_id: UUID
    title: str
    story_type: StoryType
    theme: Optional[str] = None
    premise: Optional[str] = None
    status: StoryStatus
    start_time_ref: Optional[datetime] = None
    end_time_ref: Optional[datetime] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    scene_count: int = Field(default=0, description="Number of scenes in this story")
    participant_ids: List[UUID] = Field(
        default_factory=list, description="Entity IDs of story participants"
    )

    model_config = {"from_attributes": True}


class StoryFilter(BaseModel):
    """Filter parameters for listing stories."""

    universe_id: Optional[UUID] = None
    status: Optional[StoryStatus] = None
    story_type: Optional[StoryType] = None
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
