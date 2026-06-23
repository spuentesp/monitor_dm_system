"""
Pydantic schemas for Entity operations (EntityArchetype and EntityInstance).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Entity CRUD operations.
EntityArchetype represents templates/concepts, EntityInstance represents concrete entities.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from monitor_data.schemas.base import (
    AuditMixin,
    Authority,
    CanonLevel,
    DetailLevel,
    EntityType,
)


# =============================================================================
# ENTITY SCHEMAS
# =============================================================================


class EntityCreate(BaseModel):
    """Request to create an Entity (Archetype or Instance)."""

    universe_id: UUID
    id: Optional[UUID] = Field(None, description="Optional explicit Entity ID")
    name: str = Field(min_length=1, max_length=200)
    entity_type: EntityType
    sub_type: Optional[str] = Field(
        None,
        max_length=100,
        description="Free-text sub-classification within entity_type (e.g. clan, discipline, deity, species)",
    )
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
    detail_level: DetailLevel = Field(
        default=DetailLevel.STUB,
        description="NPC elaboration level — advances as player interacts with the character",
    )

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

    def model_post_init(self, __context: Any) -> None:
        """Validate that add_tags and remove_tags don't overlap."""
        add_set = set(self.add_tags)
        remove_set = set(self.remove_tags)
        overlap = add_set & remove_set
        if overlap:
            raise ValueError(
                f"Tags cannot appear in both add_tags and remove_tags: {sorted(overlap)}"
            )


class EntityResponse(AuditMixin):
    """Response with Entity data."""

    universe_id: UUID
    name: str
    entity_type: EntityType
    sub_type: Optional[str] = None
    is_archetype: bool
    description: str
    properties: Dict[str, Any]
    state_tags: List[str] = Field(default_factory=list)
    archetype_id: Optional[UUID] = None
    canon_level: CanonLevel
    confidence: float
    authority: Authority
    detail_level: DetailLevel = DetailLevel.STUB

    model_config = {"from_attributes": True}


class EntityFilter(BaseModel):
    """Filter parameters for listing entities."""

    universe_id: Optional[UUID] = None
    entity_type: Optional[EntityType] = None
    is_archetype: Optional[bool] = None
    name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Filter by entity name (case-insensitive contains)",
    )
    state_tags: Optional[List[str]] = Field(
        default=None, description="Filter by state tags (AND logic)"
    )
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="created_at", description="Field to sort by: created_at, name")
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class EntityListResponse(BaseModel):
    """Response with list of entities and pagination info."""

    entities: List[EntityResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# Batch operation schemas
# =============================================================================


class BatchError(BaseModel):
    """Error from a batch operation on a single item."""

    index: int
    entity_id: Optional[UUID] = None
    message: str
    code: Optional[str] = None


class EntityBatchCreateRequest(BaseModel):
    """Request to create multiple entities in a single operation."""

    universe_id: UUID
    entities: List[EntityCreate] = Field(min_length=1, max_length=100)
    continue_on_error: bool = Field(
        default=False,
        description="If True, continue processing remaining items after an error",
    )


class EntityBatchCreateResponse(BaseModel):
    """Response from a batch entity creation operation."""

    entities: List[EntityResponse]
    total: int
    succeeded: int
    failed: int
    errors: List[BatchError] = Field(default_factory=list)


class EntityBatchUpdateRequest(BaseModel):
    """Request to update multiple entities in a single operation."""

    updates: List[dict] = Field(
        min_length=1,
        max_length=100,
        description="List of {entity_id: UUID, update: EntityUpdate dict} items",
    )
    continue_on_error: bool = Field(default=False)


class EntityBatchUpdateResponse(BaseModel):
    """Response from a batch entity update operation."""

    entities: List[EntityResponse]
    total: int
    succeeded: int
    failed: int
    errors: List[BatchError] = Field(default_factory=list)


class EntityBatchDeleteRequest(BaseModel):
    """Request to delete multiple entities in a single operation."""

    entity_ids: List[UUID] = Field(min_length=1, max_length=100)
    force: bool = Field(default=False, description="Force delete even if entity has relationships")


class EntityBatchDeleteResponse(BaseModel):
    """Response from a batch entity delete operation."""

    deleted: List[UUID]
    total: int
    succeeded: int
    failed: int
    errors: List[BatchError] = Field(default_factory=list)


class EntityBatchCloneRequest(BaseModel):
    """Request to clone multiple entities with optional prefix/suffix."""

    entity_ids: List[UUID] = Field(min_length=1, max_length=50)
    name_prefix: Optional[str] = Field(default=None, max_length=50)
    name_suffix: Optional[str] = Field(default=None, max_length=50)
    keep_relationships: bool = Field(default=True)
