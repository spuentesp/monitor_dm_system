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
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class ActionType(StrEnum):
    """Type of action being resolved."""

    COMBAT = "combat"
    SKILL = "skill"
    SOCIAL = "social"
    EXPLORATION = "exploration"
    MAGIC = "magic"
    OTHER = "other"


class ResolutionType(StrEnum):
    """Mechanism used for resolution."""

    DICE = "dice"
    CARD = "card"
    NARRATIVE = "narrative"
    DETERMINISTIC = "deterministic"
    CONTESTED = "contested"
    FORCED_NARRATIVE = "forced_narrative"  # Player declared outcome in a dice session


class SuccessLevel(StrEnum):
    """Outcome level of the resolution."""

    CRITICAL_SUCCESS = "critical_success"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CRITICAL_FAILURE = "critical_failure"


class EffectType(StrEnum):
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
    reason: str = Field(max_length=500, description="Why this modifier applies (for audit trail)")


class RollResult(BaseModel):
    """Result of a dice roll."""

    raw_rolls: list[int] = Field(description="All dice rolled (before keep/drop logic)")
    kept_rolls: list[int] = Field(
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
    opponent_modifiers: list[Modifier] = Field(default_factory=list)
    margin_of_victory: int = Field(description="Difference between winner and loser totals")


class CardDraw(BaseModel):
    """Data for card-based resolution."""

    cards_drawn: list[str] = Field(description="Cards drawn (suit and rank, e.g. 'Hearts-King')")
    total_value: int = Field(description="Numeric value of the draw")
    special: str | None = Field(None, max_length=200, description="Special result (e.g., 'Red Joker')")


class Mechanics(BaseModel):
    """Mechanical details of the resolution."""

    game_system_id: UUID | None = Field(None, description="Reference to game system rules (DL-20)")
    formula: str = Field(max_length=200, description="Formula used (e.g., '2d20kh1+5 vs DC 15')")
    modifiers: list[Modifier] = Field(default_factory=list, description="All modifiers applied")
    target: int | None = Field(None, description="Target number or DC if applicable")
    roll: RollResult | None = Field(None, description="Roll result for dice-based resolutions")
    contested: ContestedRoll | None = Field(None, description="Opposed roll data for contested resolutions")
    card_draw: CardDraw | None = Field(None, description="Card draw data for card-based resolutions")


# =============================================================================
# EFFECT SCHEMAS
# =============================================================================


class Effect(BaseModel):
    """An effect applied as a result of the resolution."""

    effect_type: EffectType
    target_id: UUID = Field(description="Entity affected by this effect")
    magnitude: int = Field(default=0, description="Numeric magnitude (damage, healing, etc.)")
    damage_type: str | None = Field(None, max_length=100, description="Type of damage (fire, cold, etc.)")
    condition: str | None = Field(None, max_length=100, description="Condition applied (stunned, prone, etc.)")
    duration: int | None = Field(None, ge=0, description="Duration in rounds/turns if applicable")
    description: str = Field(max_length=500, description="Human-readable description of the effect")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional effect-specific data")


# =============================================================================
# RESOLUTION CRUD SCHEMAS
# =============================================================================


class ResolutionCreate(BaseModel):
    """Request to create a resolution record."""

    turn_id: UUID
    scene_id: UUID
    story_id: UUID
    actor_id: UUID = Field(description="Entity performing the action")
    action: str = Field(max_length=500, description="Description of the action attempted")
    action_type: ActionType
    resolution_type: ResolutionType
    mechanics: Mechanics
    success_level: SuccessLevel
    margin: int | None = Field(None, description="Margin of success/failure if applicable")
    effects: list[Effect] = Field(default_factory=list, description="Effects applied by this resolution")
    description: str | None = Field(None, max_length=1000, description="Narrative description of the outcome")
    gm_notes: str | None = Field(None, max_length=1000, description="GM-only notes about the resolution")
    forced_narrative: bool = Field(
        default=False,
        description=(
            "True when the player declared the outcome directly in a dice session "
            "(bypassed the roll). The scene is flagged so GMs can review later."
        ),
    )


class ResolutionUpdate(BaseModel):
    """Request to update a resolution record."""

    effects: list[Effect] | None = None
    description: str | None = Field(None, max_length=1000)
    gm_notes: str | None = Field(None, max_length=1000)


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
    margin: int | None
    effects: list[Effect]
    description: str | None
    gm_notes: str | None
    forced_narrative: bool = False
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class ResolutionFilter(BaseModel):
    """Filter parameters for listing resolutions."""

    scene_id: UUID | None = None
    turn_id: UUID | None = None
    actor_id: UUID | None = None
    action_type: ActionType | None = None
    success_level: SuccessLevel | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ResolutionListResponse(BaseModel):
    """Response for list operations."""

    resolutions: list[ResolutionResponse]
    total: int
    limit: int
    offset: int
