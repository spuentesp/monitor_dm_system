"""
Pydantic schemas for Fact and Event operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Fact and Event CRUD operations.
Facts represent canonical truth about the world; Events are temporal facts with timestamps.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import Authority, CanonLevel


# =============================================================================
# ENUMS
# =============================================================================


class FactType(str, Enum):
    """Type classification for facts."""

    STATE = "state"  # "Door is broken", "NPC is hostile"
    RELATIONSHIP = "relationship"  # "PC is allied with NPC"
    ATTRIBUTE = "attribute"  # "PC has 5 HP"
    OCCURRENCE = "occurrence"  # "PC took 5 damage" (distinct from Event entity)


# =============================================================================
# FACT SCHEMAS
# =============================================================================


class FactCreate(BaseModel):
    """Request to create a Fact."""

    universe_id: UUID
    statement: str = Field(min_length=1, max_length=2000, description="The fact statement")
    fact_type: FactType = Field(default=FactType.STATE)
    
    # Optional temporal properties
    time_ref: Optional[datetime] = Field(None, description="When it became true")
    duration: Optional[int] = Field(None, description="How long it was true (seconds)")
    
    # Entity references
    entity_ids: Optional[List[UUID]] = Field(
        default=None, description="Entity IDs this fact involves"
    )
    
    # Provenance references
    source_ids: Optional[List[UUID]] = Field(
        default=None, description="Source IDs supporting this fact"
    )
    snippet_ids: Optional[List[str]] = Field(
        default=None, 
        description="Snippet IDs supporting this fact (stored for reference, not as Neo4j edges)"
    )
    scene_ids: Optional[List[UUID]] = Field(
        default=None, description="Scene IDs supporting this fact"
    )
    
    # Canonization metadata
    canon_level: CanonLevel = Field(default=CanonLevel.PROPOSED)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    authority: Authority = Field(default=Authority.SYSTEM)
    
    # Optional retcon tracking
    replaces: Optional[UUID] = Field(None, description="Fact ID this retcons")
    
    # Custom properties
    properties: Optional[dict] = Field(
        default=None, description="Additional custom properties"
    )


class FactUpdate(BaseModel):
    """Request to update a Fact.

    Only mutable fields can be updated: statement, canon_level, confidence, properties.
    Structural fields like universe_id and fact_type require creating a new fact.
    """

    statement: Optional[str] = Field(None, min_length=1, max_length=2000)
    canon_level: Optional[CanonLevel] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    properties: Optional[dict] = None


class FactResponse(BaseModel):
    """Response with Fact data including relationships."""

    id: UUID
    universe_id: UUID
    statement: str
    fact_type: FactType
    time_ref: Optional[datetime]
    duration: Optional[int]
    canon_level: CanonLevel
    confidence: float
    authority: Authority
    created_at: datetime
    replaces: Optional[UUID]
    properties: Optional[dict]
    
    # Relationship data (populated by get operations)
    entity_ids: List[UUID] = Field(default_factory=list)
    source_ids: List[UUID] = Field(default_factory=list)
    snippet_ids: List[str] = Field(default_factory=list)
    scene_ids: List[UUID] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FactFilter(BaseModel):
    """Filter parameters for listing facts."""

    universe_id: Optional[UUID] = None
    entity_id: Optional[UUID] = Field(None, description="Facts involving this entity")
    fact_type: Optional[FactType] = None
    canon_level: Optional[CanonLevel] = None
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# =============================================================================
# EVENT SCHEMAS
# =============================================================================


class EventCreate(BaseModel):
    """Request to create an Event."""

    universe_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    
    # Temporal properties (required for events)
    start_time: datetime = Field(description="When the event started")
    end_time: Optional[datetime] = Field(None, description="When the event ended")
    
    # Optional scene reference
    scene_id: Optional[UUID] = None
    
    # Severity/importance
    severity: int = Field(default=5, ge=0, le=10, description="Event severity 0-10")
    
    # Entity references
    entity_ids: Optional[List[UUID]] = Field(
        default=None, description="Entity IDs involved in this event"
    )
    
    # Provenance references
    source_ids: Optional[List[UUID]] = Field(
        default=None, description="Source IDs supporting this event"
    )
    
    # Timeline ordering (for establishing BEFORE and AFTER edges)
    timeline_after: Optional[List[UUID]] = Field(
        default=None, description="Event IDs this event comes after"
    )
    timeline_before: Optional[List[UUID]] = Field(
        default=None, description="Event IDs this event comes before"
    )
    
    # Causal relationships
    causes: Optional[List[UUID]] = Field(
        default=None, description="Event IDs this event causes"
    )
    
    # Canonization metadata
    canon_level: CanonLevel = Field(default=CanonLevel.PROPOSED)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    authority: Authority = Field(default=Authority.SYSTEM)
    
    # Custom properties
    properties: Optional[dict] = Field(
        default=None, description="Additional custom properties"
    )


class EventResponse(BaseModel):
    """Response with Event data including relationships."""

    id: UUID
    universe_id: UUID
    scene_id: Optional[UUID]
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    severity: int
    canon_level: CanonLevel
    confidence: float
    authority: Authority
    created_at: datetime
    properties: Optional[dict]
    
    # Relationship data (populated by get operations)
    entity_ids: List[UUID] = Field(default_factory=list)
    source_ids: List[UUID] = Field(default_factory=list)
    timeline_after: List[UUID] = Field(default_factory=list)
    timeline_before: List[UUID] = Field(default_factory=list)
    causes: List[UUID] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EventFilter(BaseModel):
    """Filter parameters for listing events."""

    universe_id: Optional[UUID] = None
    scene_id: Optional[UUID] = None
    entity_id: Optional[UUID] = Field(None, description="Events involving this entity")
    canon_level: Optional[CanonLevel] = None
    start_after: Optional[datetime] = Field(None, description="Events starting after this time")
    start_before: Optional[datetime] = Field(None, description="Events starting before this time")
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
