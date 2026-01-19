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
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class DurationType(str, Enum):
    """Type of duration for effects."""

    ROUNDS = "rounds"
    MINUTES = "minutes"
    HOURS = "hours"
    SCENE = "scene"
    UNTIL_REST = "until_rest"
    PERMANENT = "permanent"
    CONCENTRATION = "concentration"


class InventoryChangeType(str, Enum):
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
    source_id: Optional[UUID] = Field(None, description="ID of source entity/effect")
    timestamp: datetime


class TemporaryEffect(BaseModel):
    """A temporary effect applied to the character."""

    effect_id: UUID
    name: str = Field(description="Name of effect")
    source: str = Field(description="Source of effect")
    stat_modifiers: Dict[str, int] = Field(
        default_factory=dict, description="Map of stat names to modifier values"
    )
    duration_type: DurationType
    duration_remaining: Optional[int] = Field(
        None, description="Rounds/minutes remaining"
    )
    applied_at: datetime
    expires_at: Optional[datetime] = None
    conditions: List[str] = Field(
        default_factory=list, description="Conditions applied"
    )


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
    base_stats: Dict[str, Any] = Field(default_factory=dict)

    # Current stats (derived from base + mods)
    current_stats: Dict[str, Any] = Field(default_factory=dict)

    # Resources (HP, MP, Slots - things that fluctuate)
    resources: Dict[str, Any] = Field(
        default_factory=dict, description="Dynamic resources like HP, MP, Spell Slots"
    )

    # Tracking log
    modifications: List[StatModification] = Field(default_factory=list)
    temporary_effects: List[TemporaryEffect] = Field(default_factory=list)
    inventory_changes: List[InventoryChange] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime
    canonized: bool = False
    canonized_at: Optional[datetime] = None


# =============================================================================
# CRUD REQUEST SCHEMAS
# =============================================================================


class WorkingStateCreate(BaseModel):
    """Request to create a working state record."""

    entity_id: UUID
    scene_id: UUID
    story_id: UUID
    base_stats: Dict[str, Any]
    current_stats: Optional[Dict[str, Any]] = None
    resources: Dict[str, Any]


class WorkingStateUpdate(BaseModel):
    """Request to update working state."""

    current_stats: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None


class AddStatModification(BaseModel):
    """Request to add a stat modification."""

    state_id: UUID
    stat_or_resource: str
    change: int
    source: str
    source_id: Optional[UUID] = None


class AddTemporaryEffect(BaseModel):
    """Request to add a temporary effect."""

    state_id: UUID
    name: str
    source: str
    stat_modifiers: Dict[str, int] = Field(default_factory=dict)
    duration_type: DurationType
    duration_remaining: Optional[int] = None
    conditions: List[str] = Field(default_factory=list)


class WorkingStateFilter(BaseModel):
    """Filter for listing working states."""

    scene_id: Optional[UUID] = None
    story_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    canonized: Optional[bool] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class WorkingStateResponse(BaseModel):
    """Response wrapper."""

    state: CharacterWorkingState

    model_config = {"from_attributes": True}


class WorkingStateListResponse(BaseModel):
    """List response."""

    states: List[CharacterWorkingState]
    total: int
    limit: int
    offset: int
