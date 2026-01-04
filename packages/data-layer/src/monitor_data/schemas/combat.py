"""
Pydantic schemas for Combat operations (DL-25).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for Combat CRUD operations.
Combat encounters manage initiative, turn order, participants, and combat flow.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import CombatStatus, CombatSide


# =============================================================================
# CONDITION SCHEMAS
# =============================================================================


class Condition(BaseModel):
    """A temporary condition affecting a combatant."""

    name: str = Field(
        max_length=100, description="Condition name (e.g., 'Stunned', 'Blessed')"
    )
    source: str = Field(max_length=200, description="What caused this condition")
    duration_type: str = Field(
        max_length=50,
        description="e.g., 'rounds', 'until_save', 'permanent', 'concentration'",
    )
    duration_remaining: Optional[int] = Field(
        None, ge=0, description="Remaining rounds/turns"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional condition data (save DC, effect details, etc.)",
    )


# =============================================================================
# PARTICIPANT SCHEMAS
# =============================================================================


class CombatParticipant(BaseModel):
    """A participant in combat."""

    entity_id: UUID
    name: str = Field(max_length=200, description="Display name")
    side: CombatSide
    initiative_value: Optional[float] = Field(
        None, description="Initiative score for turn order"
    )
    is_active: bool = Field(default=True, description="Whether participant can act")
    conditions: List[Condition] = Field(default_factory=list)
    resources: Dict[str, Any] = Field(
        default_factory=dict, description="Resource snapshot (HP, spell slots, etc.)"
    )
    position: Optional[Dict[str, Any]] = Field(
        None, description="Position data (coordinates, zone, etc.)"
    )


class AddCombatParticipant(BaseModel):
    """Request to add a participant to combat."""

    encounter_id: UUID
    entity_id: UUID
    name: str = Field(max_length=200)
    side: CombatSide
    initiative_value: Optional[float] = None
    resources: Optional[Dict[str, Any]] = None


class UpdateCombatParticipant(BaseModel):
    """Request to update a combat participant."""

    encounter_id: UUID
    entity_id: UUID
    initiative_value: Optional[float] = None
    is_active: Optional[bool] = None
    conditions: Optional[List[Condition]] = None
    resources: Optional[Dict[str, Any]] = None
    position: Optional[Dict[str, Any]] = None


class RemoveCombatParticipant(BaseModel):
    """Request to remove a participant from combat."""

    encounter_id: UUID
    entity_id: UUID


# =============================================================================
# ENVIRONMENT SCHEMAS
# =============================================================================


class CombatEnvironment(BaseModel):
    """Environmental factors affecting combat."""

    terrain: str = Field(default="normal", max_length=100)
    lighting: str = Field(default="normal", max_length=100)
    hazards: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Environmental hazards (fire, ice, traps, etc.)",
    )
    cover_positions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Available cover locations"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# COMBAT LOG SCHEMAS
# =============================================================================


class CombatLogEntry(BaseModel):
    """A single entry in the combat log."""

    round: int = Field(ge=1)
    turn: int = Field(ge=1)
    actor_id: UUID
    action: str = Field(max_length=500, description="Action taken")
    resolution_id: Optional[UUID] = Field(
        None, description="Link to resolution document"
    )
    summary: str = Field(max_length=1000, description="Human-readable summary")
    timestamp: datetime


class AddCombatLogEntry(BaseModel):
    """Request to add a combat log entry."""

    encounter_id: UUID
    round: int = Field(ge=1)
    turn: int = Field(ge=1)
    actor_id: UUID
    action: str = Field(max_length=500)
    resolution_id: Optional[UUID] = None
    summary: str = Field(max_length=1000)


# =============================================================================
# COMBAT OUTCOME SCHEMAS
# =============================================================================


class CombatOutcome(BaseModel):
    """Final outcome of a combat encounter."""

    result: str = Field(
        max_length=50, description="e.g., 'victory', 'defeat', 'retreat', 'negotiated'"
    )
    winning_side: Optional[CombatSide] = None
    survivors: List[UUID] = Field(default_factory=list)
    casualties: List[UUID] = Field(default_factory=list)
    loot: List[Dict[str, Any]] = Field(default_factory=list)
    xp_awarded: Optional[int] = Field(None, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SetCombatOutcome(BaseModel):
    """Request to set combat outcome."""

    encounter_id: UUID
    result: str = Field(max_length=50)
    winning_side: Optional[CombatSide] = None
    survivors: Optional[List[UUID]] = None
    casualties: Optional[List[UUID]] = None
    loot: Optional[List[Dict[str, Any]]] = None
    xp_awarded: Optional[int] = Field(None, ge=0)


# =============================================================================
# COMBAT CRUD SCHEMAS
# =============================================================================


class CombatCreate(BaseModel):
    """Request to create a combat encounter."""

    scene_id: UUID
    story_id: UUID
    participants: List[CombatParticipant] = Field(
        default_factory=list, description="Initial participants"
    )
    environment: Optional[CombatEnvironment] = None


class CombatUpdate(BaseModel):
    """Request to update a combat encounter."""

    status: Optional[CombatStatus] = None
    round: Optional[int] = Field(None, ge=1)
    turn_order: Optional[List[UUID]] = Field(
        None, description="Ordered list of entity_ids for initiative order"
    )
    current_turn_index: Optional[int] = Field(None, ge=0)


class CombatResponse(BaseModel):
    """Response with combat encounter data."""

    id: UUID
    scene_id: UUID
    story_id: UUID
    status: CombatStatus
    round: int = Field(default=0, ge=0)
    turn_order: List[UUID] = Field(default_factory=list)
    current_turn_index: int = Field(default=0, ge=0)
    participants: List[CombatParticipant]
    environment: CombatEnvironment
    combat_log: List[CombatLogEntry] = Field(default_factory=list)
    outcome: Optional[CombatOutcome] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class CombatFilter(BaseModel):
    """Filter parameters for listing combat encounters."""

    scene_id: Optional[UUID] = None
    story_id: Optional[UUID] = None
    status: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class CombatListResponse(BaseModel):
    """Response for list operations."""

    combats: List[CombatResponse]
    total: int
    limit: int
    offset: int
