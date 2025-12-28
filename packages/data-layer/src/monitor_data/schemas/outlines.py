"""
Pydantic schemas for Story Outline operations (MongoDB).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for Story Outline CRUD operations.
Story outlines contain narrative beats and planning for stories.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# OUTLINE SCHEMAS
# =============================================================================


class OutlineBeat(BaseModel):
    """A single narrative beat in a story outline."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    order: int = Field(ge=0, description="Display order in the outline")
    status: str = Field(
        default="pending",
        description="Beat status: pending, active, completed, skipped",
        pattern="^(pending|active|completed|skipped)$",
    )


class StoryOutlineCreate(BaseModel):
    """Request to create a story outline."""

    story_id: UUID = Field(description="Story this outline belongs to (must exist in Neo4j)")
    theme: str = Field(default="", max_length=500, description="Central theme of the story")
    premise: str = Field(default="", max_length=2000, description="Story premise or hook")
    constraints: List[str] = Field(
        default_factory=list, description="Narrative constraints or rules"
    )
    beats: List[OutlineBeat] = Field(
        default_factory=list, description="Ordered list of narrative beats"
    )
    open_threads: List[str] = Field(
        default_factory=list, description="Open plot threads or questions"
    )
    pc_ids: List[UUID] = Field(
        default_factory=list, description="Player character IDs involved in the story"
    )


class StoryOutlineUpdate(BaseModel):
    """Request to update a story outline."""

    theme: Optional[str] = Field(None, max_length=500)
    premise: Optional[str] = Field(None, max_length=2000)
    constraints: Optional[List[str]] = None
    beats: Optional[List[OutlineBeat]] = None
    open_threads: Optional[List[str]] = None
    status: Optional[str] = Field(
        None,
        description="Outline status: draft, active, completed, archived",
        pattern="^(draft|active|completed|archived)$",
    )


class StoryOutlineResponse(BaseModel):
    """Response with story outline data."""

    story_id: UUID
    theme: str
    premise: str
    constraints: List[str]
    beats: List[OutlineBeat]
    open_threads: List[str]
    pc_ids: List[UUID]
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
