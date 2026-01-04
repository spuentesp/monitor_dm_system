"""
Pydantic schemas for Story Outlines and Plot Threads (DL-6).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py, neo4j_tools.py

These schemas define the data contracts for narrative structure tracking:
- Story Outlines (MongoDB): Planning, beats, pacing, mysteries
- Plot Threads (Neo4j): Cross-scene narrative threads with relationships

DL-6: Comprehensive implementation with narrative engine support
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from monitor_data.schemas.base import (
    PlotThreadType,
    PlotThreadStatus,
    BeatStatus,
    StoryStructureType,
    ArcTemplate,
    ThreadPriority,
    ThreadUrgency,
    ClueVisibility,
    PayoffStatus,
)


# =============================================================================
# STORY BEAT SCHEMAS (MongoDB - nested in story_outline)
# =============================================================================


class StoryBeat(BaseModel):
    """Individual story beat with progression tracking."""

    beat_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=2000)
    order: int = Field(ge=0, description="Display order in story")
    status: BeatStatus = Field(default=BeatStatus.PENDING)
    optional: bool = Field(
        default=False, description="Can be skipped without story incompleteness"
    )
    related_threads: List[UUID] = Field(
        default_factory=list,
        description="PlotThread IDs that advance during this beat",
    )
    required_for_threads: List[UUID] = Field(
        default_factory=list,
        description="PlotThreads that must be active for this beat to trigger",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(
        None, description="When status changed to in_progress"
    )
    completed_at: Optional[datetime] = Field(
        None, description="When status changed to completed"
    )
    completed_in_scene_id: Optional[UUID] = Field(
        None, description="Scene that completed this beat"
    )


class BranchingPoint(BaseModel):
    """Decision point for branching narratives."""

    beat_id: UUID = Field(description="Beat where branching occurs")
    decision: str = Field(max_length=500, description="What choice is made")
    branches: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Possible outcomes with conditions and next beats",
    )


# =============================================================================
# MYSTERY STRUCTURE SCHEMAS (MongoDB - nested in story_outline)
# =============================================================================


class MysteryClue(BaseModel):
    """Clue in a mystery structure."""

    clue_id: UUID = Field(
        default_factory=uuid4, description="References Neo4j Fact node"
    )
    content: str = Field(max_length=1000)
    discovery_methods: List[str] = Field(
        default_factory=list, description="How players can discover this clue"
    )
    is_discovered: bool = Field(default=False)
    discovered_in_scene_id: Optional[UUID] = None
    discovered_at: Optional[datetime] = None
    points_to: str = Field(default="", description="Which theory/suspect it supports")
    visibility: ClueVisibility = Field(
        default=ClueVisibility.HIDDEN,
        description="Current visibility status",
    )


class MysterySuspect(BaseModel):
    """Suspect/theory in a mystery."""

    entity_id: UUID = Field(description="Entity being suspected")
    theory: str = Field(max_length=500)
    evidence_for: List[UUID] = Field(
        default_factory=list, description="Clue IDs supporting this theory"
    )
    evidence_against: List[UUID] = Field(
        default_factory=list, description="Clue IDs contradicting this theory"
    )


class MysteryStructure(BaseModel):
    """Mystery-specific story structure."""

    truth: str = Field(max_length=2000, description="GM secret - actual solution")
    question: str = Field(max_length=500, description="What players are solving")
    core_clues: List[MysteryClue] = Field(
        default_factory=list, description="Essential clues for solving"
    )
    bonus_clues: List[MysteryClue] = Field(
        default_factory=list, description="Additional supporting clues"
    )
    red_herrings: List[MysteryClue] = Field(
        default_factory=list, description="Misleading clues"
    )
    suspects: List[MysterySuspect] = Field(default_factory=list)
    current_player_theories: List[str] = Field(
        default_factory=list, description="What players currently think"
    )


# =============================================================================
# PACING METRICS SCHEMAS (MongoDB - nested in story_outline)
# =============================================================================


class PacingMetrics(BaseModel):
    """Narrative pacing and tension tracking."""

    current_act: int = Field(default=1, ge=1, le=5, description="Current story act")
    tension_level: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Current narrative tension (0=calm, 1=climax)",
    )
    scenes_since_major_event: int = Field(
        default=0, ge=0, description="Scenes since last significant plot event"
    )
    scenes_in_current_act: int = Field(default=0, ge=0)
    estimated_completion: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Story completion percentage (completed_beats / total_beats)",
    )
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# STORY OUTLINE SCHEMAS (MongoDB)
# =============================================================================


class StoryOutlineCreate(BaseModel):
    """Create story outline with comprehensive narrative tracking."""

    story_id: UUID
    theme: str = Field(default="", max_length=500)
    premise: str = Field(default="", max_length=2000)
    constraints: List[str] = Field(
        default_factory=list, description="Story constraints or rules"
    )
    beats: List[StoryBeat] = Field(default_factory=list)
    structure_type: StoryStructureType = Field(default=StoryStructureType.LINEAR)
    template: ArcTemplate = Field(default=ArcTemplate.CUSTOM)
    branching_points: List[BranchingPoint] = Field(
        default_factory=list, description="Only for branching narratives"
    )
    mystery_structure: Optional[MysteryStructure] = Field(
        None, description="Only for mystery stories"
    )


class StoryOutlineUpdate(BaseModel):
    """Partial update to story outline with beat manipulation."""

    theme: Optional[str] = Field(None, max_length=500)
    premise: Optional[str] = Field(None, max_length=2000)
    constraints: Optional[List[str]] = None
    structure_type: Optional[StoryStructureType] = None
    template: Optional[ArcTemplate] = None
    # Beat operations (partial updates)
    add_beats: Optional[List[StoryBeat]] = Field(
        None, description="New beats to add to the end or insert"
    )
    remove_beat_ids: Optional[List[UUID]] = Field(
        None, description="Beat IDs to remove"
    )
    reorder_beats: Optional[List[UUID]] = Field(
        None, description="Reorder beats by providing full ordered list of beat_ids"
    )
    update_beats: Optional[List[StoryBeat]] = Field(
        None, description="Update existing beats (matched by beat_id)"
    )
    # Mystery operations
    update_mystery_structure: Optional[MysteryStructure] = None
    mark_clue_discovered: Optional[UUID] = Field(
        None, description="Clue ID to mark as discovered"
    )
    # Branching operations
    add_branching_points: Optional[List[BranchingPoint]] = None


class StoryOutlineResponse(BaseModel):
    """Story outline response with computed fields."""

    story_id: UUID
    theme: str
    premise: str
    constraints: List[str]
    beats: List[StoryBeat]
    structure_type: StoryStructureType
    template: ArcTemplate
    branching_points: List[BranchingPoint]
    mystery_structure: Optional[MysteryStructure] = None
    pacing_metrics: PacingMetrics
    open_threads: List[str] = Field(
        default_factory=list,
        description="List of unresolved thread titles (computed)",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# PLOT THREAD SCHEMAS (Neo4j)
# =============================================================================


class ThreadDeadline(BaseModel):
    """Time pressure for a plot thread."""

    world_time: datetime = Field(description="In-game deadline")
    description: str = Field(max_length=500)


class PlotThreadCreate(BaseModel):
    """Create plot thread with relationships and narrative tracking."""

    story_id: UUID
    title: str = Field(min_length=1, max_length=200)
    thread_type: PlotThreadType
    status: PlotThreadStatus = Field(default=PlotThreadStatus.OPEN)
    priority: ThreadPriority = Field(
        default=ThreadPriority.MINOR, description="Narrative importance"
    )
    urgency: ThreadUrgency = Field(default=ThreadUrgency.LOW)
    deadline: Optional[ThreadDeadline] = None
    # Relationships (created during thread creation)
    scene_ids: List[UUID] = Field(
        default_factory=list,
        description="Scenes that advanced this thread (ADVANCED_BY)",
    )
    entity_ids: List[UUID] = Field(
        default_factory=list, description="Entities involved in this thread (INVOLVES)"
    )
    # Foreshadowing/payoff tracking
    foreshadowing_events: List[UUID] = Field(
        default_factory=list,
        description="Event IDs that set up this thread (FORESHADOWS)",
    )
    revelation_events: List[UUID] = Field(
        default_factory=list, description="Event IDs that pay off this thread (REVEALS)"
    )
    payoff_status: PayoffStatus = Field(default=PayoffStatus.SETUP_ONLY)
    # Engagement tracking
    player_interest_level: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Tracked from player engagement",
    )
    gm_importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Set by GM")


class PlotThreadUpdate(BaseModel):
    """Update plot thread with relationship modifications."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    status: Optional[PlotThreadStatus] = None
    priority: Optional[ThreadPriority] = None
    urgency: Optional[ThreadUrgency] = None
    deadline: Optional[ThreadDeadline] = None
    payoff_status: Optional[PayoffStatus] = None
    player_interest_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    gm_importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    # Relationship operations (additive only - no removal to preserve history)
    add_scene_ids: Optional[List[UUID]] = Field(
        None, description="Add scenes that advanced this thread"
    )
    add_entity_ids: Optional[List[UUID]] = Field(
        None, description="Add entities involved in this thread"
    )
    add_foreshadowing_events: Optional[List[UUID]] = None
    add_revelation_events: Optional[List[UUID]] = None


class PlotThreadResponse(BaseModel):
    """Plot thread response with all tracking data."""

    id: UUID
    story_id: UUID
    title: str
    thread_type: PlotThreadType
    status: PlotThreadStatus
    priority: ThreadPriority
    urgency: ThreadUrgency
    deadline: Optional[ThreadDeadline] = None
    payoff_status: PayoffStatus
    player_interest_level: float
    gm_importance: float
    # Relationships (lists of UUIDs)
    scene_ids: List[UUID] = Field(default_factory=list)
    entity_ids: List[UUID] = Field(default_factory=list)
    foreshadowing_events: List[UUID] = Field(default_factory=list)
    revelation_events: List[UUID] = Field(default_factory=list)
    # Timestamps
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = Field(
        None, description="When status changed to resolved"
    )

    model_config = {"from_attributes": True}


class PlotThreadFilter(BaseModel):
    """Filter for listing plot threads."""

    story_id: Optional[UUID] = None
    thread_type: Optional[PlotThreadType] = None
    status: Optional[PlotThreadStatus] = None
    priority: Optional[ThreadPriority] = None
    entity_id: Optional[UUID] = Field(
        None, description="Show threads involving this entity"
    )
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at",
        description="Sort field: created_at, updated_at, priority, urgency",
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class PlotThreadListResponse(BaseModel):
    """Response with list of plot threads and pagination."""

    threads: List[PlotThreadResponse]
    total: int
    limit: int
    offset: int
