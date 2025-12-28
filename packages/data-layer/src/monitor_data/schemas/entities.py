"""
Pydantic schemas for Entity operations (EntityArchetype and EntityInstance).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Entity CRUD operations.
EntityArchetype represents templates/concepts, EntityInstance represents concrete entities.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from monitor_data.schemas.base import Authority, CanonLevel, EntityType


# =============================================================================
# ENTITY SCHEMAS
# =============================================================================


class EntityCreate(BaseModel):
    """Request to create an Entity (Archetype or Instance)."""

    universe_id: UUID
    name: str = Field(min_length=1, max_length=200)
    entity_type: EntityType
    is_archetype: bool = Field(
        default=False,
        description="True for EntityArchetype (templates), False for EntityInstance (concrete)",
    )
    description: str = Field(default="", max_length=2000)
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific properties (see ENTITY_TAXONOMY.md)",
    )
    state_tags: List[str] = Field(
        default_factory=list,
        description="Dynamic state tags (EntityInstance only)",
    )
    archetype_id: Optional[UUID] = Field(
        None,
        description="If instance derives from archetype, link via DERIVES_FROM",
    )
    authority: Authority = Field(default=Authority.SYSTEM)
    canon_level: CanonLevel = Field(default=CanonLevel.CANON)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)

    @field_validator("state_tags")
    @classmethod
    def validate_state_tags(cls, v: List[str]) -> List[str]:
        """Validate state_tags are unique."""
        if len(v) != len(set(v)):
            raise ValueError("state_tags must not contain duplicates")
        return v


class EntityUpdate(BaseModel):
    """Request to update an Entity.

    Only mutable fields can be updated: name, description, properties.
    State tags are updated via neo4j_set_state_tags.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    properties: Optional[Dict[str, Any]] = None


class StateTagsUpdate(BaseModel):
    """Request to update state tags on an EntityInstance."""

    add_tags: List[str] = Field(default_factory=list, description="Tags to add")
    remove_tags: List[str] = Field(default_factory=list, description="Tags to remove")

    @field_validator("add_tags", "remove_tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Validate tags are unique within each list."""
        if len(v) != len(set(v)):
            raise ValueError("Tags must not contain duplicates")
        return v

    def model_post_init(self, __context):
        """Validate that add_tags and remove_tags don't overlap."""
        add_set = set(self.add_tags)
        remove_set = set(self.remove_tags)
        overlap = add_set & remove_set
        if overlap:
            raise ValueError(
                f"Tags cannot appear in both add_tags and remove_tags: {sorted(overlap)}"
            )


class EntityResponse(BaseModel):
    """Response with Entity data."""

    id: UUID
    universe_id: UUID
    name: str
    entity_type: EntityType
    is_archetype: bool
    description: str
    properties: Dict[str, Any]
    state_tags: List[str] = Field(default_factory=list)
    archetype_id: Optional[UUID] = None
    canon_level: CanonLevel
    confidence: float
    authority: Authority
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EntityFilter(BaseModel):
    """Filter parameters for listing entities."""

    universe_id: Optional[UUID] = None
    entity_type: Optional[EntityType] = None
    is_archetype: Optional[bool] = None
    state_tags: Optional[List[str]] = Field(
        None, description="Filter by state tags (AND logic)"
    )
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at", description="Field to sort by: created_at, name"
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class EntityListResponse(BaseModel):
    """Response with list of entities and pagination info."""

    entities: List[EntityResponse]
    total: int
    limit: int
    offset: int
