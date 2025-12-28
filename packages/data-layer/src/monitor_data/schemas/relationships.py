"""
Pydantic schemas for Relationship operations between entities.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Relationship CRUD operations.
Relationships are typed edges between EntityInstance nodes.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# RELATIONSHIP TYPE ENUM
# =============================================================================


class RelationshipType(str, Enum):
    """Types of relationships between entities.
    
    Based on ONTOLOGY.md section 2.4 - Entity relationships include:
    - Membership: MEMBER_OF (character in faction, object in container)
    - Ownership: OWNS (character owns object)
    - Social: ALLY_OF, ENEMY_OF (relationships between characters/factions)
    - Spatial: LOCATED_IN (entity physically located in location)
    - Participation: PARTICIPATED_IN (entity participated in scene/event)
    - Derivation: DERIVES_FROM (instance derives from archetype)
    """

    MEMBER_OF = "MEMBER_OF"
    OWNS = "OWNS"
    ALLY_OF = "ALLY_OF"
    ENEMY_OF = "ENEMY_OF"
    LOCATED_IN = "LOCATED_IN"
    PARTICIPATED_IN = "PARTICIPATED_IN"
    DERIVES_FROM = "DERIVES_FROM"


# =============================================================================
# RELATIONSHIP SCHEMAS
# =============================================================================


class RelationshipCreate(BaseModel):
    """Request to create a relationship (edge) between two entities."""

    from_entity_id: UUID = Field(description="Source entity ID")
    to_entity_id: UUID = Field(description="Target entity ID")
    rel_type: RelationshipType = Field(description="Type of relationship")
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional properties on the relationship (e.g., valid_from, valid_to, strength)",
    )

    @field_validator("from_entity_id", "to_entity_id")
    @classmethod
    def validate_entity_ids(cls, v: UUID) -> UUID:
        """Validate entity IDs are proper UUIDs."""
        # UUID validation is automatic with pydantic, this is for documentation
        return v

    def model_post_init(self, __context):
        """Validate that from_entity_id and to_entity_id are different."""
        if self.from_entity_id == self.to_entity_id:
            raise ValueError("from_entity_id and to_entity_id must be different")


class RelationshipUpdate(BaseModel):
    """Request to update a relationship's properties.
    
    Note: from_entity_id, to_entity_id, and rel_type are immutable.
    To change these, delete the relationship and create a new one.
    """

    properties: Dict[str, Any] = Field(
        description="Updated properties for the relationship"
    )


class RelationshipResponse(BaseModel):
    """Response with relationship data including related entities."""

    id: str = Field(description="Neo4j internal relationship ID")
    from_entity_id: UUID
    to_entity_id: UUID
    rel_type: RelationshipType
    properties: Dict[str, Any] = Field(default_factory=dict)
    
    # Optional: Include entity names for convenience
    from_entity_name: Optional[str] = None
    to_entity_name: Optional[str] = None

    model_config = {"from_attributes": True}


class RelationshipFilter(BaseModel):
    """Filter parameters for listing relationships."""

    entity_id: Optional[UUID] = Field(
        None,
        description="Filter relationships involving this entity (either from or to)",
    )
    from_entity_id: Optional[UUID] = Field(
        None, description="Filter relationships from this entity"
    )
    to_entity_id: Optional[UUID] = Field(
        None, description="Filter relationships to this entity"
    )
    rel_type: Optional[RelationshipType] = Field(
        None, description="Filter by relationship type"
    )
    direction: str = Field(
        default="both",
        description="Direction filter: 'outgoing', 'incoming', 'both'",
        pattern="^(outgoing|incoming|both)$",
    )
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class RelationshipListResponse(BaseModel):
    """Response with list of relationships and pagination info."""

    relationships: List[RelationshipResponse]
    total: int
    limit: int
    offset: int
