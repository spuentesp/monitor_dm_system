"""
Pydantic schemas for Turn Resolution operations (DL-24).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for storing mechanical resolution records
for player/NPC actions during gameplay. Pure data storage - resolution logic (dice
rolling, success evaluation) lives in the agents layer.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class ActionType(str, Enum):
    """Type of action being resolved."""

    COMBAT = "combat"
    SKILL = "skill"
    SOCIAL = "social"
    EXPLORATION = "exploration"
    MAGIC = "magic"
    OTHER = "other"


class ResolutionType(str, Enum):
    """Mechanism used for resolution."""

    DICE = "dice"
    CARD = "card"
    NARRATIVE = "narrative"
    DETERMINISTIC = "deterministic"
    CONTESTED = "contested"


class SuccessLevel(str, Enum):
    """Outcome level of the resolution."""

    CRITICAL_SUCCESS = "critical_success"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CRITICAL_FAILURE = "critical_failure"


class EffectType(str, Enum):
    """Type of effect applied by a resolution."""

    DAMAGE = "damage"
    HEALING = "healing"
    CONDITION = "condition"
    BUFF = "buff"
    DEBUFF = "debuff"
    RESOURCE_CHANGE = "resource_change"
    STAT_CHANGE = "stat_change"
    POSITION_CHANGE = "position_change"
    OTHER = "other"


# =============================================================================
# MECHANICS SCHEMAS
# =============================================================================


class Modifier(BaseModel):
    """A modifier applied to a roll or check."""

    source: str = Field(max_length=200, description="What provides this modifier")
    value: int = Field(description="Numeric modifier value")
    reason: str = Field(
        max_length=500, description="Why this modifier applies (for audit trail)"
    )


class RollResult(BaseModel):
    """Result of a dice roll."""

    raw_rolls: List[int] = Field(description="All dice rolled (before keep/drop logic)")
    kept_rolls: List[int] = Field(
        default_factory=list,
        description="Dice kept after keep/drop logic (may equal raw_rolls)",
    )
    total: int = Field(description="Final total after modifiers")
    natural: int = Field(
        default=0,
        description="Total of dice only, before modifiers (for critical detection)",
    )
    critical: bool = Field(default=False, description="Whether this was a critical")
    fumble: bool = Field(default=False, description="Whether this was a fumble/botch")


class ContestedRoll(BaseModel):
    """Data for a contested resolution (opposed rolls)."""

    opponent_id: UUID = Field(description="Entity ID of the opponent")
    opponent_roll: RollResult
    opponent_modifiers: List[Modifier] = Field(default_factory=list)
    margin_of_victory: int = Field(
        description="Difference between winner and loser totals"
    )


class CardDraw(BaseModel):
    """Data for card-based resolution."""

    cards_drawn: List[str] = Field(
        description="Cards drawn (suit and rank, e.g. 'Hearts-King')"
    )
    total_value: int = Field(description="Numeric value of the draw")
    special: Optional[str] = Field(
        None, max_length=200, description="Special result (e.g., 'Red Joker')"
    )


class Mechanics(BaseModel):
    """Mechanical details of the resolution."""

    game_system_id: Optional[UUID] = Field(
        None, description="Reference to game system rules (DL-20)"
    )
    formula: str = Field(
        max_length=200, description="Formula used (e.g., '2d20kh1+5 vs DC 15')"
    )
    modifiers: List[Modifier] = Field(
        default_factory=list, description="All modifiers applied"
    )
    target: Optional[int] = Field(None, description="Target number or DC if applicable")
    roll: Optional[RollResult] = Field(
        None, description="Roll result for dice-based resolutions"
    )
    contested: Optional[ContestedRoll] = Field(
        None, description="Opposed roll data for contested resolutions"
    )
    card_draw: Optional[CardDraw] = Field(
        None, description="Card draw data for card-based resolutions"
    )


# =============================================================================
# EFFECT SCHEMAS
# =============================================================================


class Effect(BaseModel):
    """An effect applied as a result of the resolution."""

    effect_type: EffectType
    target_id: UUID = Field(description="Entity affected by this effect")
    magnitude: int = Field(
        default=0, description="Numeric magnitude (damage, healing, etc.)"
    )
    damage_type: Optional[str] = Field(
        None, max_length=100, description="Type of damage (fire, cold, etc.)"
    )
    condition: Optional[str] = Field(
        None, max_length=100, description="Condition applied (stunned, prone, etc.)"
    )
    duration: Optional[int] = Field(
        None, ge=0, description="Duration in rounds/turns if applicable"
    )
    description: str = Field(
        max_length=500, description="Human-readable description of the effect"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional effect-specific data"
    )


# =============================================================================
# RESOLUTION CRUD SCHEMAS
# =============================================================================


class ResolutionCreate(BaseModel):
    """Request to create a resolution record."""

    turn_id: UUID
    scene_id: UUID
    story_id: UUID
    actor_id: UUID = Field(description="Entity performing the action")
    action: str = Field(
        max_length=500, description="Description of the action attempted"
    )
    action_type: ActionType
    resolution_type: ResolutionType
    mechanics: Mechanics
    success_level: SuccessLevel
    margin: Optional[int] = Field(
        None, description="Margin of success/failure if applicable"
    )
    effects: List[Effect] = Field(
        default_factory=list, description="Effects applied by this resolution"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Narrative description of the outcome"
    )
    gm_notes: Optional[str] = Field(
        None, max_length=1000, description="GM-only notes about the resolution"
    )


class ResolutionUpdate(BaseModel):
    """Request to update a resolution record."""

    effects: Optional[List[Effect]] = None
    description: Optional[str] = Field(None, max_length=1000)
    gm_notes: Optional[str] = Field(None, max_length=1000)


class ResolutionResponse(BaseModel):
    """Response with resolution data."""

    id: UUID
    turn_id: UUID
    scene_id: UUID
    story_id: UUID
    actor_id: UUID
    action: str
    action_type: ActionType
    resolution_type: ResolutionType
    mechanics: Mechanics
    success_level: SuccessLevel
    margin: Optional[int]
    effects: List[Effect]
    description: Optional[str]
    gm_notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class ResolutionFilter(BaseModel):
    """Filter parameters for listing resolutions."""

    scene_id: Optional[UUID] = None
    turn_id: Optional[UUID] = None
    actor_id: Optional[UUID] = None
    action_type: Optional[ActionType] = None
    success_level: Optional[SuccessLevel] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ResolutionListResponse(BaseModel):
    """Response for list operations."""

    resolutions: List[ResolutionResponse]
    total: int
    limit: int
    offset: int
