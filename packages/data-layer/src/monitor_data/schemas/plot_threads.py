"""
Pydantic schemas for Plot Thread operations (Neo4j).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for PlotThread CRUD operations.
Plot threads are canonical tracking of narrative arcs that advance through
scenes and link to facts/events.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field

from monitor_data.schemas.base import CanonLevel, Authority


# =============================================================================
# ENUMS
# =============================================================================


class ThreadType(str, Enum):
    """Plot thread classification."""

    MAIN = "main"
    SUBPLOT = "subplot"
    CHARACTER_ARC = "character_arc"
    MYSTERY = "mystery"
    CONFLICT = "conflict"


class ThreadStatus(str, Enum):
    """Plot thread status."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


# =============================================================================
# PLOT THREAD SCHEMAS
# =============================================================================


class PlotThreadCreate(BaseModel):
    """Request to create a plot thread."""

    story_id: UUID = Field(description="Story this thread belongs to (must exist)")
    title: str = Field(min_length=1, max_length=200, description="Thread title")
    thread_type: ThreadType = Field(description="Type of narrative thread")
    description: str = Field(default="", max_length=2000, description="Thread description")
    status: ThreadStatus = Field(
        default=ThreadStatus.ACTIVE, description="Current thread status"
    )
    canon_level: CanonLevel = Field(default=CanonLevel.CANON)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    authority: Authority = Field(default=Authority.GM)


class PlotThreadUpdate(BaseModel):
    """Request to update a plot thread."""

    status: Optional[ThreadStatus] = None
    description: Optional[str] = Field(None, max_length=2000)


class PlotThreadResponse(BaseModel):
    """Response with plot thread data."""

    id: UUID
    story_id: UUID
    title: str
    thread_type: ThreadType
    description: str
    status: ThreadStatus
    canon_level: CanonLevel
    confidence: float
    authority: Authority
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PlotThreadFilter(BaseModel):
    """Filter parameters for listing plot threads."""

    story_id: Optional[UUID] = None
    status: Optional[ThreadStatus] = None
    thread_type: Optional[ThreadType] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class PlotThreadListResponse(BaseModel):
    """Response with list of plot threads and pagination info."""

    threads: List[PlotThreadResponse]
    total: int
    limit: int
    offset: int


class PlotThreadAdvancement(BaseModel):
    """Request to advance a plot thread with a scene."""

    scene_id: UUID = Field(description="Scene that advances this thread")
    advancement_note: str = Field(
        default="", max_length=500, description="Note about how thread was advanced"
    )


class PlotThreadFactLink(BaseModel):
    """Request to link a plot thread to a fact/event."""

    fact_id: UUID = Field(description="Fact or Event node to link")
    link_type: str = Field(
        default="relates_to",
        max_length=50,
        description="Type of relationship: relates_to, resolves, complicates, etc.",
    )
