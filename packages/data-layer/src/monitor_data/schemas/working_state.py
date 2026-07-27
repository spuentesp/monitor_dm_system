"""
Pydantic schemas for Character Working State (DL-26).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the temporary/working state of characters during a scene.
This includes HP, resources, temporary buffs/debuffs, and modified stats.
Canonical stats live in Neo4j (EntityInstance); working state lives in MongoDB.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class DurationType(StrEnum):
    """Type of duration for effects."""

    ROUNDS = "rounds"
    MINUTES = "minutes"
    HOURS = "hours"
    SCENE = "scene"
    UNTIL_REST = "until_rest"
    PERMANENT = "permanent"
    CONCENTRATION = "concentration"


class InventoryChangeType(StrEnum):
    """Type of inventory change."""

    ADD = "add"
    REMOVE = "remove"
    USE = "use"
    EQUIP = "equip"
    UNEQUIP = "unequip"


# =============================================================================
# SUB-MODELS
# =============================================================================


class StatModification(BaseModel):
    """A modification to a base stat or resource."""

    mod_id: UUID
    stat_or_resource: str = Field(description="Name of stat/resource modified")
    change: int = Field(description="Numeric change amount")
    source: str = Field(description="Source of change (e.g. 'Fireball', 'Potion')")
    source_id: UUID | None = Field(None, description="ID of source entity/effect")
    timestamp: datetime


class TemporaryEffect(BaseModel):
    """A temporary effect applied to the character."""

    effect_id: UUID
    name: str = Field(description="Name of effect")
    source: str = Field(description="Source of effect")
    stat_modifiers: dict[str, int] = Field(default_factory=dict, description="Map of stat names to modifier values")
    duration_type: DurationType
    duration_remaining: int | None = Field(None, description="Rounds/minutes remaining")
    applied_at: datetime
    expires_at: datetime | None = None
    conditions: list[str] = Field(default_factory=list, description="Conditions applied")


class InventoryChange(BaseModel):
    """A tracked inventory change in working state."""

    change_type: InventoryChangeType
    item: str
    quantity: int
    timestamp: datetime


# =============================================================================
# MAIN SCHEMAS
# =============================================================================


class CharacterWorkingState(BaseModel):
    """
    Working state document for a character in a specific scene.
    Stores temporary values (HP, resources) and modifications.
    """

    id: UUID
    state_id: UUID
    entity_id: UUID
    scene_id: UUID
    story_id: UUID

    # Base stats (snapshot from Neo4j at start of scene)
    base_stats: dict[str, Any] = Field(default_factory=dict)

    # Current stats (derived from base + mods)
    current_stats: dict[str, Any] = Field(default_factory=dict)

    # Resources (HP, MP, Slots - things that fluctuate)
    resources: dict[str, Any] = Field(default_factory=dict, description="Dynamic resources like HP, MP, Spell Slots")

    # Progression (XP, level — grow permanently from play, P-21)
    xp: int = Field(default=0, ge=0, description="Experience points accumulated")
    level: int = Field(default=1, ge=1, description="Current character level")

    # Tracking log
    modifications: list[StatModification] = Field(default_factory=list)
    temporary_effects: list[TemporaryEffect] = Field(default_factory=list)
    inventory_changes: list[InventoryChange] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime
    canonized: bool = False
    canonized_at: datetime | None = None


# =============================================================================
# CRUD REQUEST SCHEMAS
# =============================================================================


class WorkingStateCreate(BaseModel):
    """Request to create a working state record."""

    entity_id: UUID
    scene_id: UUID
    story_id: UUID
    base_stats: dict[str, Any]
    current_stats: dict[str, Any] | None = None
    resources: dict[str, Any]


class WorkingStateUpdate(BaseModel):
    """Request to update working state."""

    current_stats: dict[str, Any] | None = None
    resources: dict[str, Any] | None = None


class AddStatModification(BaseModel):
    """Request to add a stat modification."""

    state_id: UUID
    stat_or_resource: str
    change: int
    source: str
    source_id: UUID | None = None


class AddTemporaryEffect(BaseModel):
    """Request to add a temporary effect."""

    state_id: UUID
    name: str
    source: str
    stat_modifiers: dict[str, int] = Field(default_factory=dict)
    duration_type: DurationType
    duration_remaining: int | None = None
    conditions: list[str] = Field(default_factory=list)


class WorkingStateFilter(BaseModel):
    """Filter for listing working states."""

    scene_id: UUID | None = None
    story_id: UUID | None = None
    entity_id: UUID | None = None
    canonized: bool | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class WorkingStateResponse(BaseModel):
    """Response wrapper."""

    state: CharacterWorkingState

    model_config = {"from_attributes": True}


class WorkingStateListResponse(BaseModel):
    """List response."""

    states: list[CharacterWorkingState]
    total: int
    limit: int
    offset: int
