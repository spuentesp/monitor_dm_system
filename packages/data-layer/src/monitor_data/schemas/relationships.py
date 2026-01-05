"""
Pydantic schemas for Relationship and State Tag operations (DL-14).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for managing relationships between entities
and dynamic state tags on entity instances. Relationships are Neo4j edges with
typed connections and metadata. State tags track dynamic entity status.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class RelationshipType(str, Enum):
    """Type of relationship between entities."""

    MEMBER_OF = "MEMBER_OF"  # Entity belongs to organization/group
    OWNS = "OWNS"  # Entity owns another entity/object
    KNOWS = "KNOWS"  # Social relationship - acquaintance
    ALLIED_WITH = "ALLIED_WITH"  # Formal alliance relationship
    HOSTILE_TO = "HOSTILE_TO"  # Antagonistic relationship
    LOCATED_IN = "LOCATED_IN"  # Spatial containment
    PARTICIPATES_IN = "PARTICIPATES_IN"  # Event/activity participation


class Direction(str, Enum):
    """Direction for relationship queries."""

    OUTGOING = "outgoing"  # Relationships from entity to others
    INCOMING = "incoming"  # Relationships from others to entity
    BOTH = "both"  # Relationships in both directions


class StateTag(str, Enum):
    """Dynamic state tags for entity instances."""

    # Vital status
    ALIVE = "alive"
    DEAD = "dead"
    UNCONSCIOUS = "unconscious"
    WOUNDED = "wounded"

    # Visibility
    HIDDEN = "hidden"
    REVEALED = "revealed"

    # Disposition
    HOSTILE = "hostile"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"

    # Combat states
    PRONE = "prone"
    GRAPPLED = "grappled"
    RESTRAINED = "restrained"
    INCAPACITATED = "incapacitated"

    # Mental states
    CHARMED = "charmed"
    FRIGHTENED = "frightened"
    STUNNED = "stunned"
    CONFUSED = "confused"


# =============================================================================
# RELATIONSHIP CRUD SCHEMAS
# =============================================================================


class RelationshipCreate(BaseModel):
    """Request to create a relationship between entities."""

    from_entity_id: UUID = Field(description="Source entity ID")
    to_entity_id: UUID = Field(description="Target entity ID")
    rel_type: RelationshipType
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional properties (since, strength, notes, etc.)",
    )


class RelationshipUpdate(BaseModel):
    """Request to update a relationship's properties."""

    properties: Dict[str, Any] = Field(
        description="Updated properties (replaces existing)"
    )


class RelationshipResponse(BaseModel):
    """Response with relationship data."""

    relationship_id: str = Field(description="Neo4j internal relationship ID")
    from_entity_id: UUID
    to_entity_id: UUID
    rel_type: RelationshipType
    properties: Dict[str, Any]
    created_at: Optional[datetime] = Field(
        None, description="When relationship was created"
    )

    model_config = {"from_attributes": True}


# =============================================================================
# RELATIONSHIP QUERY SCHEMAS
# =============================================================================


class RelationshipFilter(BaseModel):
    """Filter parameters for listing relationships."""

    entity_id: Optional[UUID] = Field(
        None, description="Filter by entity (as source or target)"
    )
    rel_type: Optional[RelationshipType] = Field(
        None, description="Filter by relationship type"
    )
    direction: Direction = Field(
        default=Direction.BOTH, description="Direction relative to entity_id"
    )
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class RelationshipListResponse(BaseModel):
    """Response for list operations."""

    relationships: List[RelationshipResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# STATE TAG SCHEMAS
# =============================================================================


class StateTagUpdate(BaseModel):
    """Request to update state tags on an entity instance."""

    entity_id: UUID
    add_tags: List[StateTag] = Field(
        default_factory=list, description="Tags to add to entity"
    )
    remove_tags: List[StateTag] = Field(
        default_factory=list, description="Tags to remove from entity"
    )


class StateTagResponse(BaseModel):
    """Response with entity's current state tags."""

    entity_id: UUID
    state_tags: List[StateTag] = Field(
        default_factory=list, description="Current state tags on entity"
    )

    model_config = {"from_attributes": True}
