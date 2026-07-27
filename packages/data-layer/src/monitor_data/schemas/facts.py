"""
Pydantic schemas for Fact and Event operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Fact and Event CRUD operations.
Facts represent canonical truth about the world; Events are temporal facts with timestamps.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import (
    Authority,
    AxiomAuthority,
    CanonLevel,
    KnowledgeScope,
    SimulationScope,
)

# =============================================================================
# ENUMS
# =============================================================================


class FactType(StrEnum):
    """Type classification for facts."""

    STATE = "state"  # "Door is broken", "NPC is hostile"
    RELATIONSHIP = "relationship"  # "PC is allied with NPC"
    ATTRIBUTE = "attribute"  # "PC has 5 HP"
    OCCURRENCE = "occurrence"  # "PC took 5 damage" (distinct from Event entity)


class FactStatus(StrEnum):
    """Lifecycle status for a fact."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    TOMBSTONED = "tombstoned"


# =============================================================================
# FACT SCHEMAS
# =============================================================================


class FactCreate(BaseModel):
    """Request to create a Fact."""

    universe_id: UUID
    id: UUID | None = Field(None, description="Optional explicit Fact ID")
    statement: str = Field(min_length=1, max_length=2000, description="The fact statement")
    fact_type: FactType = Field(default=FactType.STATE)

    # Impact assessment
    magnitude: int = Field(default=1, ge=1, le=10, description="Impact severity 1-10")
    scope: SimulationScope = Field(default=SimulationScope.LOCAL)

    # Optional temporal properties
    time_ref: datetime | None = Field(None, description="When it became true")
    duration: int | None = Field(None, description="How long it was true (seconds)")

    # Custom properties
    properties: dict[str, Any] | None = None

    # Entity references
    entity_ids: list[UUID] | None = Field(default=None, description="Entity IDs this fact involves")

    # Provenance references
    source_ids: list[UUID] | None = Field(default=None, description="Source IDs supporting this fact")
    snippet_ids: list[str] | None = Field(
        default=None,
        description="Snippet IDs supporting this fact (stored for reference, not as Neo4j edges)",
    )
    scene_ids: list[UUID] | None = Field(default=None, description="Scene IDs supporting this fact")

    # Canonization metadata
    canon_level: CanonLevel = Field(default=CanonLevel.PROPOSED)
    knowledge_scope: KnowledgeScope = Field(
        default=KnowledgeScope.WORLD,
        description="Who holds this knowledge: world, character, player, rumor",
    )
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    authority: Authority = Field(default=Authority.SYSTEM)
    status: FactStatus = Field(default=FactStatus.ACTIVE)

    # Optional retcon tracking
    replaces: UUID | None = Field(None, description="Fact ID this retcons")


class FactUpdate(BaseModel):
    """Request to update a Fact.

    Only mutable fields can be updated: statement, canon_level, confidence, properties.
    Structural fields like universe_id and fact_type require creating a new fact.
    """

    statement: str | None = Field(None, min_length=1, max_length=2000)
    canon_level: CanonLevel | None = None
    knowledge_scope: KnowledgeScope | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    status: FactStatus | None = None
    properties: dict[str, Any] | None = None


class FactResponse(BaseModel):
    """Response with Fact data including relationships."""

    id: UUID
    universe_id: UUID
    statement: str
    fact_type: FactType
    magnitude: int = 1
    scope: SimulationScope = SimulationScope.LOCAL
    time_ref: datetime | None = None
    duration: int | None = None
    canon_level: CanonLevel
    knowledge_scope: KnowledgeScope = KnowledgeScope.WORLD
    confidence: float
    authority: Authority
    status: FactStatus = FactStatus.ACTIVE
    created_at: datetime
    replaces: UUID | None
    properties: dict[str, Any] | None

    # Relationship data (populated by get operations)
    entity_ids: list[UUID] = Field(default_factory=list)
    source_ids: list[UUID] = Field(default_factory=list)
    snippet_ids: list[str] = Field(default_factory=list)
    scene_ids: list[UUID] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FactFilter(BaseModel):
    """Filter parameters for listing facts."""

    universe_id: UUID | None = None
    entity_id: UUID | None = Field(default=None, description="Facts involving this entity")
    fact_type: FactType | None = None
    canon_level: CanonLevel | None = None
    status: FactStatus | None = Field(default=FactStatus.ACTIVE)
    min_magnitude: int = Field(default=1, ge=1, le=10)
    scope: SimulationScope | None = None
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# =============================================================================
# EVENT SCHEMAS
# =============================================================================


class EventCreate(BaseModel):
    """Request to create an Event."""

    universe_id: UUID
    id: UUID | None = Field(None, description="Optional explicit Event ID")
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)

    # Temporal properties (required for events)
    start_time: datetime = Field(description="When the event started")
    end_time: datetime | None = Field(None, description="When the event ended")

    # Optional scene reference
    scene_id: UUID | None = None

    # Impact assessment
    magnitude: int = Field(default=5, ge=0, le=10, description="Event magnitude 0-10")
    scope: SimulationScope = Field(default=SimulationScope.LOCAL)

    # Custom properties
    properties: dict[str, Any] | None = None

    # Entity references
    entity_ids: list[UUID] | None = Field(default=None, description="Entity IDs involved in this event")

    # Provenance references
    source_ids: list[UUID] | None = Field(default=None, description="Source IDs supporting this event")

    # Timeline ordering (for establishing BEFORE and AFTER edges)
    timeline_after: list[UUID] | None = Field(default=None, description="Event IDs this event comes after")
    timeline_before: list[UUID] | None = Field(default=None, description="Event IDs this event comes before")

    # Causal relationships
    causes: list[UUID] | None = Field(default=None, description="Event IDs this event causes")

    # Canonization metadata
    canon_level: CanonLevel = Field(default=CanonLevel.PROPOSED)
    knowledge_scope: KnowledgeScope = Field(
        default=KnowledgeScope.WORLD,
        description="Who holds this knowledge: world, character, player, rumor",
    )
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    authority: Authority = Field(default=Authority.SYSTEM)


class EventUpdate(BaseModel):
    """Request to update mutable Event fields.

    Structural fields (universe_id, timeline/causal edges) require creating a
    new event; only descriptive and canonization fields are mutable.
    """

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    start_time: datetime | None = None
    end_time: datetime | None = None
    magnitude: int | None = Field(None, ge=0, le=10)
    scope: SimulationScope | None = None
    canon_level: CanonLevel | None = None
    knowledge_scope: KnowledgeScope | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    properties: dict[str, Any] | None = None


class EventResponse(BaseModel):
    """Response with Event data including relationships."""

    id: UUID
    universe_id: UUID
    scene_id: UUID | None = None
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    magnitude: int = 1
    scope: SimulationScope = SimulationScope.LOCAL
    canon_level: CanonLevel
    knowledge_scope: KnowledgeScope = KnowledgeScope.WORLD
    confidence: float
    authority: Authority
    created_at: datetime
    properties: dict[str, Any] | None = None

    # Relationship data (populated by get operations)
    entity_ids: list[UUID] = Field(default_factory=list)
    source_ids: list[UUID] = Field(default_factory=list)
    timeline_after: list[UUID] = Field(default_factory=list)
    timeline_before: list[UUID] = Field(default_factory=list)
    causes: list[UUID] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EventFilter(BaseModel):
    """Filter parameters for listing events."""

    universe_id: UUID | None = None
    scene_id: UUID | None = None
    entity_id: UUID | None = Field(None, description="Events involving this entity")
    canon_level: CanonLevel | None = None
    min_magnitude: int = Field(default=1, ge=1, le=10)
    scope: SimulationScope | None = None
    start_after: datetime | None = Field(None, description="Events starting after this time")
    start_before: datetime | None = Field(None, description="Events starting before this time")
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# =============================================================================
# AXIOM SCHEMAS
# =============================================================================


class AxiomCreate(BaseModel):
    """
    Request to create an Axiom node in Neo4j.

    Axioms are ontological world truths — they describe what the world IS,
    not what happens in it.  They are the strongest form of canon.

    Examples:
        "Magic exists and is woven into the fabric of reality"
        "The gods are real and can intervene in mortal affairs"
        "Interstellar travel requires FTL drives"
    """

    universe_id: UUID
    id: UUID | None = Field(None, description="Optional explicit Axiom ID")
    statement: str = Field(min_length=1, max_length=500, description="The axiom statement")
    domain: str = Field(
        min_length=1,
        max_length=100,
        description="Category: 'magic', 'physics', 'society', 'religion', 'technology', etc.",
    )

    # Impact assessment
    magnitude: int = Field(default=8, ge=1, le=10, description="Impact severity 1-10")
    scope: SimulationScope = Field(default=SimulationScope.GLOBAL)

    # Provenance
    source_ids: list[UUID] | None = Field(default=None, description="Source IDs that assert this axiom")
    source_ref: str | None = Field(None, max_length=200, description="Page/section citation from source document")

    # Canonization metadata
    canon_level: CanonLevel = Field(default=CanonLevel.PROPOSED)
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    authority: AxiomAuthority = Field(default=AxiomAuthority.METAPHYSICS)

    # Custom properties / tags
    tags: list[str] | None = Field(default_factory=list)
    properties: dict[str, Any] | None = None


class AxiomUpdate(BaseModel):
    """Request to update mutable Axiom fields."""

    statement: str | None = Field(None, min_length=1, max_length=500)
    domain: str | None = Field(None, min_length=1, max_length=100)
    magnitude: int | None = Field(None, ge=1, le=10)
    scope: SimulationScope | None = None
    canon_level: CanonLevel | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    tags: list[str] | None = None
    properties: dict[str, Any] | None = None


class AxiomResponse(BaseModel):
    """Response with Axiom data."""

    id: UUID
    universe_id: UUID
    statement: str
    domain: str
    magnitude: int
    scope: SimulationScope
    canon_level: CanonLevel
    confidence: float
    authority: AxiomAuthority
    source_ref: str | None
    tags: list[str] = Field(default_factory=list)
    properties: dict[str, Any] | None
    created_at: datetime

    # Provenance
    source_ids: list[UUID] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AxiomFilter(BaseModel):
    """Filter parameters for listing axioms."""

    universe_id: UUID | None = None
    domain: str | None = None
    min_magnitude: int = Field(default=1, ge=1, le=10)
    scope: SimulationScope | None = None
    canon_level: CanonLevel | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
