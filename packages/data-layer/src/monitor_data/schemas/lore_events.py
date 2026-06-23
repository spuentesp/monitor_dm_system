"""
Pydantic schemas for LoreEvent operations (Neo4j).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

A LoreEvent is a CANONICAL SETTING EVENT in the universe timeline.
It is DISTINCT from:

  Event       (Scene-level causal moment during play — "Orc attacks PC")
  Story       (A playable narrative the player runs through)
  LoreEvent   ← THIS: Pre-existing setting events from manuals/lore
               e.g., "The Horus Heresy (M31)", "The Fall of Cadia",
                     "The signing of Magna Carta", "The War of 5 Kings"

LoreEvents populate the universe knowledge graph with closed and open
narrative threads that existed before any player session. They give the
GM historical context, timeline anchors, and NPC backstory hooks.

  CLOSED = Fully resolved in the setting (Horus Heresy: Horus is dead)
  OPEN   = Ongoing or future event in the setting timeline

LoreEvents can reference:
  - Source nodes (which book describes this event)
  - EntityInstance nodes (key figures involved)
  - Other LoreEvents via CAUSED_BY / LED_TO edges
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import (
    Authority,
    CanonLevel,
    HistoricalEventScope,
    LoreEventStatus,
)


# =============================================================================
# LORE EVENT CRUD SCHEMAS  (Neo4j)
# =============================================================================


class LoreEventCreate(BaseModel):
    """Request to create a LoreEvent node in Neo4j.

    LoreEvents are created primarily during document ingestion when
    the LLM identifies canonical historical events in the source text.
    They can also be created manually by the user while building the world.
    """

    universe_id: UUID
    title: str = Field(min_length=1, max_length=300, description="Event name")
    description: str = Field(default="", max_length=5000)
    # Timeline positioning
    era: Optional[str] = Field(
        None,
        max_length=200,
        description="In-universe era label (e.g., 'M31', 'Third Age', 'Year 432 AE')",
    )
    start_time_ref: Optional[datetime] = Field(
        None, description="In-universe start date (if mappable to real date)"
    )
    end_time_ref: Optional[datetime] = Field(None, description="In-universe end date")
    duration_description: Optional[str] = Field(
        None,
        max_length=200,
        description="Human-readable duration (e.g., '7 years', 'three decades')",
    )
    # Classification
    scope: HistoricalEventScope = Field(
        default=HistoricalEventScope.GLOBAL,
        description="COSMIC/GLOBAL/REGIONAL/LOCAL/PERSONAL",
    )
    event_status: LoreEventStatus = Field(
        default=LoreEventStatus.CLOSED,
        description="CLOSED=fully resolved; OPEN=ongoing or future in the setting",
    )
    # Provenance
    source_ids: List[UUID] = Field(
        default_factory=list,
        description="Neo4j Source node IDs that describe this event (SUPPORTED_BY edges)",
    )
    # Key participants
    entity_ids: List[UUID] = Field(
        default_factory=list,
        description="Key EntityInstance IDs involved in this event",
    )
    # Related events
    caused_by_ids: List[UUID] = Field(
        default_factory=list,
        description="LoreEvent IDs this event was caused by",
    )
    led_to_ids: List[UUID] = Field(
        default_factory=list,
        description="LoreEvent IDs this event directly caused",
    )
    # Canonization
    canon_level: CanonLevel = Field(default=CanonLevel.PROPOSED)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    authority: Authority = Field(default=Authority.SOURCE)


class LoreEventUpdate(BaseModel):
    """Request to update a LoreEvent node."""

    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = Field(None, max_length=5000)
    era: Optional[str] = Field(None, max_length=200)
    start_time_ref: Optional[datetime] = None
    end_time_ref: Optional[datetime] = None
    duration_description: Optional[str] = Field(None, max_length=200)
    scope: Optional[HistoricalEventScope] = None
    event_status: Optional[LoreEventStatus] = None
    canon_level: Optional[CanonLevel] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class LoreEventResponse(BaseModel):
    """Response with LoreEvent data."""

    id: UUID
    universe_id: UUID
    title: str
    description: str
    era: Optional[str] = None
    start_time_ref: Optional[datetime] = None
    end_time_ref: Optional[datetime] = None
    duration_description: Optional[str] = None
    scope: HistoricalEventScope
    event_status: LoreEventStatus
    source_ids: List[UUID] = Field(default_factory=list)
    entity_ids: List[UUID] = Field(default_factory=list)
    caused_by_ids: List[UUID] = Field(default_factory=list)
    led_to_ids: List[UUID] = Field(default_factory=list)
    canon_level: CanonLevel
    confidence: float
    authority: Authority
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class LoreEventFilter(BaseModel):
    """Filter parameters for listing lore events."""

    universe_id: Optional[UUID] = None
    scope: Optional[HistoricalEventScope] = None
    event_status: Optional[LoreEventStatus] = None
    era: Optional[str] = None
    canon_level: Optional[CanonLevel] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class LoreEventListResponse(BaseModel):
    """Response for list operations."""

    events: List[LoreEventResponse]
    total: int
    limit: int
    offset: int
