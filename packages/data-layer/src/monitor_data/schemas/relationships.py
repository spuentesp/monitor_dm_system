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
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import EmotionalRelationType

# =============================================================================
# ENUMS
# =============================================================================


class RelationshipType(StrEnum):
    """Structural relationship types between entities."""

    MEMBER_OF = "MEMBER_OF"  # Entity belongs to organization/group
    PART_OF = "PART_OF"  # Entity is a structural part/subgroup of a larger whole
    SUBGROUP_OF = "SUBGROUP_OF"  # Organization/faction nested inside another organization
    AFFILIATED_WITH = "AFFILIATED_WITH"  # Loose or non-exclusive affiliation
    OWNS = "OWNS"  # Entity owns another entity/object
    KNOWS = "KNOWS"  # Social relationship - acquaintance
    ALLIED_WITH = "ALLIED_WITH"  # Formal alliance relationship
    HOSTILE_TO = "HOSTILE_TO"  # Antagonistic relationship
    LOCATED_IN = "LOCATED_IN"  # Spatial containment
    CONTAINS = "CONTAINS"  # Spatial or structural containment
    PARTICIPATES_IN = "PARTICIPATES_IN"  # Event/activity participation
    DERIVES_FROM = "DERIVES_FROM"  # EntityInstance derives from Archetype
    SUBTYPE_OF = "SUBTYPE_OF"  # Taxonomy/category relationship
    INSTANCE_OF = "INSTANCE_OF"  # Named instance to archetype relationship
    CONTROLLED_BY = "CONTROLLED_BY"  # Political or supernatural domination (incoming)
    CONTROLS = "CONTROLS"  # Political or supernatural domination (outgoing)
    RELATED_TO = "RELATED_TO"  # Generic fallback relationship
    REVERES = "REVERES"  # Worship/reverence relation
    LEADS = "LEADS"  # Character leads a faction/group
    WORKS_FOR = "WORKS_FOR"  # Employment/service relationship

    # === Sub-plan 1: Game-system-agnostic group/place/power types ===
    # A "group" is any collective (clan, sect, organization, race, species,
    # faction, party). A "place" is any location. "Power" covers anything
    # that gives, costs, or conditions an entity's capability.
    # Every TTRPG has groups, places, and powers — just called by
    # different names. These are intentional generic terms.
    MEMBER_OF_GROUP = "MEMBER_OF_GROUP"             # entity belongs to a group
    SUBGROUP_OF_GROUP = "SUBGROUP_OF_GROUP"         # group is a sub-group of another
    LEADS_GROUP = "LEADS_GROUP"                     # entity leads a group
    FOUNDED_GROUP = "FOUNDED_GROUP"                 # entity founded a group
    CONTROLS_GROUP = "CONTROLS_GROUP"               # entity controls a group
    ALLIED_WITH_GROUP = "ALLIED_WITH_GROUP"         # group is allied with another
    HOSTILE_TO_GROUP = "HOSTILE_TO_GROUP"           # group is hostile to another
    AFFECTED_BY = "AFFECTED_BY"                     # entity affected by a power/condition
    GRANTS_POWER = "GRANTS_POWER"                   # group/role grants a power
    PRACTICES_DISCIPLINE = "PRACTICES_DISCIPLINE"   # entity practices a power
    LOCATED_IN_PLACE = "LOCATED_IN_PLACE"           # entity/group in a place
    CONTAINS_PLACE = "CONTAINS_PLACE"               # place contains a sub-place
    IS_BACKGROUND = "IS_BACKGROUND"                 # background/edge/hindrance
    IS_TOUCHSTONE = "IS_TOUCHSTONE"                 # touchstone/conviction/tenet
    IS_RESOURCE = "IS_RESOURCE"                     # tracked resource


# === Sub-plan 1: Canonical category map for every relationship type ===
# Lets the canonkeeper pick the right Neo4j edge category without
# per-system branching. Categories match RelationshipCategory enum
# values (social / membership / ownership / spatial / temporal /
# taxonomic / power / generic).
RELATIONSHIP_CATEGORIES: dict[RelationshipType, str] = {
    # Group membership (universal across TTRPGs)
    RelationshipType.MEMBER_OF_GROUP: "membership",
    RelationshipType.SUBGROUP_OF_GROUP: "membership",
    RelationshipType.LEADS_GROUP: "membership",
    RelationshipType.FOUNDED_GROUP: "membership",
    RelationshipType.CONTROLS_GROUP: "membership",
    RelationshipType.ALLIED_WITH_GROUP: "membership",
    RelationshipType.HOSTILE_TO_GROUP: "membership",
    # Place containment (universal)
    RelationshipType.LOCATED_IN_PLACE: "spatial",
    RelationshipType.CONTAINS_PLACE: "spatial",
    # Power / cost / condition (universal)
    RelationshipType.AFFECTED_BY: "taxonomic",
    RelationshipType.GRANTS_POWER: "taxonomic",
    RelationshipType.PRACTICES_DISCIPLINE: "taxonomic",
    RelationshipType.IS_BACKGROUND: "taxonomic",
    RelationshipType.IS_TOUCHSTONE: "taxonomic",
    RelationshipType.IS_RESOURCE: "taxonomic",
    # Legacy types — keep their existing categories.
    RelationshipType.MEMBER_OF: "membership",
    RelationshipType.PART_OF: "membership",
    RelationshipType.SUBGROUP_OF: "membership",
    RelationshipType.AFFILIATED_WITH: "membership",
    RelationshipType.SUBTYPE_OF: "taxonomic",
    RelationshipType.INSTANCE_OF: "taxonomic",
    RelationshipType.DERIVES_FROM: "taxonomic",
    RelationshipType.RELATED_TO: "generic",
    RelationshipType.KNOWS: "social",
    RelationshipType.ALLIED_WITH: "social",
    RelationshipType.HOSTILE_TO: "social",
    RelationshipType.REVERES: "social",
    RelationshipType.LEADS: "social",
    RelationshipType.WORKS_FOR: "social",
    RelationshipType.OWNS: "ownership",
    RelationshipType.CONTROLLED_BY: "ownership",
    RelationshipType.CONTROLS: "ownership",
    RelationshipType.LOCATED_IN: "spatial",
    RelationshipType.CONTAINS: "spatial",
    RelationshipType.PARTICIPATES_IN: "temporal",
}


class RelationshipCategory(StrEnum):
    """High-level categories for contextual filtering.

    These categories enable hierarchical queries like "all social relationships"
    without listing every relationship type.
    """

    SOCIAL = "social"  # Personal connections (KNOWS, ALLIED_WITH, HOSTILE_TO, etc.)
    MEMBERSHIP = "membership"  # Group/organization relationships (MEMBER_OF, SUBGROUP_OF, etc.)
    OWNERSHIP = "ownership"  # Possession and control (OWNS, CONTROLLED_BY, CONTROLS)
    SPATIAL = "spatial"  # Location and containment (LOCATED_IN, CONTAINS)
    TEMPORAL = "temporal"  # Time-based participation (PARTICIPATES_IN)
    TAXONOMIC = "taxonomic"  # Classification and hierarchy (SUBTYPE_OF, INSTANCE_OF, DERIVES_FROM)
    POWER = "power"  # Authority and domination (LEADS, CONTROLLED_BY, CONTROLS)
    GENERIC = "generic"  # Fallback relationships (RELATED_TO, AFFILIATED_WITH)


class RelationshipSubcategory(StrEnum):
    """Fine-grained subcategories for precise filtering.

    These provide an intermediate level between category and specific type.
    """

    # Social subcategories
    PERSONAL = "personal"  # Individual relationships (KNOWS)
    ALLIANCE = "alliance"  # Formal alliances (ALLIED_WITH)
    ANTAGONISM = "antagonism"  # Hostile relationships (HOSTILE_TO)
    EMOTIONAL = "emotional"  # Emotional bonds (LOVES, HATES - via emotional relationships)

    # Membership subcategories
    ORGANIZATIONAL = "organizational"  # Organization membership (MEMBER_OF)
    FACTION = "faction"  # Faction relationships (SUBGROUP_OF)
    AFFILIATION = "affiliation"  # Loose affiliations (AFFILIATED_WITH)

    # Ownership subcategories
    POSSESSION = "possession"  # Direct ownership (OWNS)
    POLITICAL = "political"  # Political control (CONTROLLED_BY, CONTROLS)
    SUPERNATURAL = "supernatural"  # Supernatural domination (CONTROLLED_BY with magical bonds)

    # Spatial subcategories
    LOCATION = "location"  # Being located somewhere (LOCATED_IN)
    CONTAINMENT = "containment"  # Containing other things (CONTAINS)

    # Taxonomic subcategories
    CLASSIFICATION = "classification"  # Type hierarchies (SUBTYPE_OF)
    INSTANTIATION = "instantiation"  # Instance creation (INSTANCE_OF)
    DERIVATION = "derivation"  # Origin relationships (DERIVES_FROM)

    # Power subcategories
    LEADERSHIP = "leadership"  # Leading groups (LEADS)
    DOMINATION = "domination"  # Controlling entities (CONTROLS)
    SUBMISSION = "submission"  # Being controlled (CONTROLLED_BY)

    # Generic subcategories
    GENERAL = "general"  # General connections (RELATED_TO)
    LOOSE = "loose"  # Loose associations (AFFILIATED_WITH)


class Direction(StrEnum):
    """Direction for relationship queries."""

    OUTGOING = "outgoing"  # Relationships from entity to others
    INCOMING = "incoming"  # Relationships from others to entity
    BOTH = "both"  # Relationships in both directions


class StateTag(StrEnum):
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
    category: RelationshipCategory = Field(description="High-level category for contextual filtering")
    subcategory: RelationshipSubcategory | None = Field(
        None,
        description="Fine-grained subcategory for precise filtering",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional properties (since, strength, notes, etc.)",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags for flexible querying (e.g., 'familial', 'romantic', 'military')",
    )


class RelationshipUpdate(BaseModel):
    """Request to update a relationship's properties."""

    category: RelationshipCategory | None = Field(None, description="Update relationship category")
    subcategory: RelationshipSubcategory | None = Field(
        None,
        description="Update relationship subcategory",
    )
    properties: dict[str, Any] | None = Field(
        None,
        description="Updated properties (replaces existing if provided)",
    )
    tags: list[str] | None = Field(
        None,
        description="Update tags (replaces existing if provided)",
    )


class RelationshipResponse(BaseModel):
    """Response with relationship data."""

    relationship_id: str = Field(description="Neo4j internal relationship ID")
    from_entity_id: UUID
    to_entity_id: UUID
    rel_type: RelationshipType
    category: RelationshipCategory = Field(description="High-level category")
    subcategory: RelationshipSubcategory | None = Field(
        None,
        description="Fine-grained subcategory",
    )
    properties: dict[str, Any]
    tags: list[str] = Field(default_factory=list, description="Relationship tags")
    created_at: datetime | None = Field(None, description="When relationship was created")

    model_config = {"from_attributes": True}


# =============================================================================
# RELATIONSHIP QUERY SCHEMAS
# =============================================================================


class RelationshipFilter(BaseModel):
    """Filter parameters for listing relationships."""

    entity_id: UUID | None = Field(None, description="Filter by entity (as source or target)")
    rel_type: RelationshipType | None = Field(None, description="Filter by relationship type")
    category: RelationshipCategory | None = Field(None, description="Filter by category")
    subcategory: RelationshipSubcategory | None = Field(
        None,
        description="Filter by subcategory",
    )
    tags: list[str] | None = Field(
        None,
        description="Filter by tags (all must match)",
    )
    direction: Direction = Field(default=Direction.BOTH, description="Direction relative to entity_id")
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class RelationshipListResponse(BaseModel):
    """Response for list operations."""

    relationships: list[RelationshipResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# EMOTIONAL RELATIONSHIP SCHEMAS
# =============================================================================
# Emotional edges in Neo4j capture how a character FEELS about another.
# These are separate from structural relationships (OWNS, LOCATED_IN, etc.)
# and are directional: A LOVES B does not imply B LOVES A.
# =============================================================================


class EmotionalRelationshipCreate(BaseModel):
    """Request to create a directional emotional relationship edge.

    Example: entity A LOVES entity B with intensity 0.9, origin 'grew up together'.
    """

    from_entity_id: UUID = Field(description="Entity experiencing the emotion")
    to_entity_id: UUID = Field(description="Entity the emotion is directed at")
    rel_type: EmotionalRelationType
    category: RelationshipCategory = Field(
        default=RelationshipCategory.SOCIAL,
        description="High-level category (default: SOCIAL for emotional relationships)",
    )
    subcategory: RelationshipSubcategory = Field(
        default=RelationshipSubcategory.EMOTIONAL,
        description="Fine-grained subcategory (default: EMOTIONAL)",
    )
    intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Strength of the feeling (0=barely noticeable, 1=all-consuming)",
    )
    origin: str | None = Field(
        None,
        max_length=500,
        description="What caused this emotional bond (event, shared history, etc.)",
    )
    is_known_to_target: bool = Field(
        default=False,
        description="Whether the target knows about this feeling",
    )
    notes: str | None = Field(
        None,
        max_length=1000,
        description="GM-side notes about this relationship",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags (e.g., 'familial', 'romantic', 'unrequited')",
    )


class EmotionalRelationshipUpdate(BaseModel):
    """Request to update an emotional relationship."""

    category: RelationshipCategory | None = Field(None, description="Update category")
    subcategory: RelationshipSubcategory | None = Field(
        None,
        description="Update subcategory",
    )
    intensity: float | None = Field(None, ge=0.0, le=1.0)
    origin: str | None = Field(None, max_length=500)
    is_known_to_target: bool | None = None
    notes: str | None = Field(None, max_length=1000)
    tags: list[str] | None = Field(
        None,
        description="Update tags (replaces existing if provided)",
    )


class EmotionalRelationshipResponse(BaseModel):
    """Response with emotional relationship data."""

    relationship_id: str
    from_entity_id: UUID
    to_entity_id: UUID
    rel_type: EmotionalRelationType
    category: RelationshipCategory = Field(description="High-level category")
    subcategory: RelationshipSubcategory = Field(description="Fine-grained subcategory")
    intensity: float
    origin: str | None = None
    is_known_to_target: bool
    notes: str | None = None
    tags: list[str] = Field(default_factory=list, description="Relationship tags")
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class EmotionalRelationshipFilter(BaseModel):
    """Filter for querying emotional relationships."""

    entity_id: UUID | None = Field(None, description="Filter by entity (as source or target)")
    rel_type: EmotionalRelationType | None = None
    category: RelationshipCategory | None = Field(None, description="Filter by category")
    subcategory: RelationshipSubcategory | None = Field(
        None,
        description="Filter by subcategory",
    )
    tags: list[str] | None = Field(
        None,
        description="Filter by tags (all must match)",
    )
    direction: Direction = Field(default=Direction.BOTH)
    min_intensity: float | None = Field(None, ge=0.0, le=1.0)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class EmotionalRelationshipListResponse(BaseModel):
    """Response for list operations."""

    relationships: list[EmotionalRelationshipResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# STATE TAG SCHEMAS
# =============================================================================


class StateTagUpdate(BaseModel):
    """Request to update state tags on an entity instance."""

    entity_id: UUID
    add_tags: list[StateTag] = Field(default_factory=list, description="Tags to add to entity")
    remove_tags: list[StateTag] = Field(default_factory=list, description="Tags to remove from entity")


class StateTagResponse(BaseModel):
    """Response with entity's current state tags."""

    entity_id: UUID
    state_tags: list[StateTag] = Field(default_factory=list, description="Current state tags on entity")

    model_config = {"from_attributes": True}
