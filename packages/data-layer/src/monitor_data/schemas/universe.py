"""
Pydantic schemas for Omniverse, Multiverse, and Universe operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

Hierarchy: Omniverse → Multiverse → Universe

- Omniverse: root container for everything (1 per instance)
- Multiverse: a collection of related universes + an associated game system
  Can be is_template=True (ingested from a manual, reusable blueprint)
- Universe: a specific playable world
  Can be an alt-world (parent_universe_id != None)
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import (
    AltWorldType,
    Authority,
    CanonLevel,
    KnowledgeTreeType,
)

# =============================================================================
# OMNIVERSE SCHEMAS  (root — usually 1 per MONITOR instance)
# =============================================================================


class OmniverseCreate(BaseModel):
    """Request to create the root Omniverse."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class OmniverseUpdate(BaseModel):
    """Request to update an Omniverse."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=2000)


class OmniverseResponse(BaseModel):
    """Response with Omniverse data."""

    id: UUID
    name: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# MULTIVERSE SCHEMAS
# =============================================================================


class MultiverseCreate(BaseModel):
    """Request to create a Multiverse."""

    omniverse_id: UUID
    id: UUID | None = Field(None, description="Optional explicit Multiverse ID")
    name: str = Field(min_length=1, max_length=200)
    system_name: str = Field(
        min_length=1,
        max_length=200,
        description="e.g., 'D&D 5e', 'Warhammer 40k', 'Pathfinder 2e'",
    )
    description: str = Field(min_length=1, max_length=2000)
    is_template: bool = Field(
        default=False,
        description="Reusable world blueprint created from an ingested manual; not a live playable instance",
    )
    source_document_id: UUID | None = Field(
        None,
        description="MongoDB document ID of the ingested manual that created this template",
    )
    knowledge_tree_type: KnowledgeTreeType = Field(
        default=KnowledgeTreeType.DYNAMIC,
        description="STATIC=locked setting data; DYNAMIC=changes during play; TEMPLATE=blueprint",
    )
    parent_multiverse_id: UUID | None = Field(
        None, description="Source multiverse when this was forked/cloned from a template"
    )


class MultiverseUpdate(BaseModel):
    """Request to update a Multiverse."""

    name: str | None = Field(None, min_length=1, max_length=200)
    system_name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=2000)
    is_template: bool | None = None
    knowledge_tree_type: KnowledgeTreeType | None = None


class MultiverseResponse(BaseModel):
    """Response with Multiverse data."""

    id: UUID
    omniverse_id: UUID
    name: str
    system_name: str
    description: str
    is_template: bool = False
    knowledge_tree_type: KnowledgeTreeType = KnowledgeTreeType.DYNAMIC
    source_document_id: UUID | None = None
    parent_multiverse_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MultiverseFilter(BaseModel):
    """Filter parameters for listing multiverses."""

    omniverse_id: UUID | None = None
    is_template: bool | None = None
    knowledge_tree_type: KnowledgeTreeType | None = None
    limit: int = Field(default=30, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


# =============================================================================
# UNIVERSE SCHEMAS
# =============================================================================


class UniverseCreate(BaseModel):
    """Request to create a Universe."""

    multiverse_id: UUID
    id: UUID | None = Field(None, description="Optional explicit Universe ID")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    genre: str | None = Field(None, max_length=100, description="e.g., 'fantasy', 'sci-fi', 'horror'")
    tone: str | None = Field(None, max_length=100, description="e.g., 'dark', 'heroic', 'comedic'")
    tech_level: str | None = Field(None, max_length=100, description="e.g., 'medieval', 'modern', 'futuristic'")
    # Alt-world
    parent_universe_id: UUID | None = Field(None, description="Parent universe if this is an alt-world or fork")
    alt_world_type: AltWorldType = Field(
        default=AltWorldType.MAIN,
        description="MAIN for primary canon; VARIANT/WHAT_IF/FUTURE/PAST/MIRROR for alt-worlds",
    )
    # Template / locking
    is_template: bool = Field(
        default=False,
        description="Locked blueprint universe — clone to play inside it",
    )
    # Default game system / rules-source binding
    default_game_system_id: UUID | None = Field(
        None,
        description="Default game system for stories set in this universe when using the reusable generic library",
    )
    default_system_source_type: str | None = Field(
        None,
        description="generic_library | pack_embedded | narrative_only",
    )
    default_system_source_id: str | None = Field(
        None,
        description="Authoritative source object id for the bound ruleset (game system id or pack id)",
    )
    default_system_name: str | None = Field(
        None,
        max_length=200,
        description="Human-readable snapshot of the bound ruleset name",
    )
    authority: Authority = Field(default=Authority.SYSTEM)
    canon_level: CanonLevel = Field(default=CanonLevel.CANON)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class UniverseUpdate(BaseModel):
    """Request to update a Universe."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=2000)
    genre: str | None = Field(None, max_length=100)
    tone: str | None = Field(None, max_length=100)
    tech_level: str | None = Field(None, max_length=100)
    default_game_system_id: UUID | None = None
    default_system_source_type: str | None = None
    default_system_source_id: str | None = None
    default_system_name: str | None = Field(None, max_length=200)
    is_template: bool | None = None


class UniverseResponse(BaseModel):
    """Response with Universe data."""

    id: UUID
    multiverse_id: UUID | None = None
    name: str
    description: str
    genre: str | None = None
    tone: str | None = None
    tech_level: str | None = None
    parent_universe_id: UUID | None = None
    alt_world_type: AltWorldType = AltWorldType.MAIN
    is_template: bool = False
    default_game_system_id: UUID | None = None
    default_system_source_type: str | None = None
    default_system_source_id: str | None = None
    default_system_name: str | None = None
    canon_level: CanonLevel = CanonLevel.CANON
    confidence: float = 1.0
    authority: Authority = Authority.SYSTEM
    source_ids: list[UUID] = Field(
        default_factory=list,
        description="IDs of ingested Source nodes that contribute to this universe",
    )
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class UniverseFilter(BaseModel):
    """Filter parameters for listing universes."""

    multiverse_id: UUID | None = None
    canon_level: CanonLevel | None = None
    genre: str | None = None
    is_template: bool | None = None
    alt_world_type: AltWorldType | None = None
    limit: int = Field(default=30, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
