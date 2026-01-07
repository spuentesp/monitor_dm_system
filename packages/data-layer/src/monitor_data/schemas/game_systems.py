"""
Pydantic schemas for Game Systems & Rules operations (DL-20).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for storing game system definitions and
rule overrides. Pure data storage - rule execution logic (dice rolling, success
evaluation) lives in the agents layer.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class CoreMechanicType(str, Enum):
    """Core mechanic type used by the game system."""

    D20 = "d20"
    DICE_POOL = "dice_pool"
    PERCENTILE = "percentile"
    CARD = "card"
    NARRATIVE = "narrative"


class SuccessType(str, Enum):
    """Method for determining success."""

    MEET_OR_BEAT = "meet_or_beat"
    COUNT_SUCCESSES = "count_successes"
    HIGHEST_WINS = "highest_wins"


class RuleOverrideScope(str, Enum):
    """Scope of a rule override."""

    ONE_TIME = "one_time"
    SCENE = "scene"
    STORY = "story"
    UNIVERSE = "universe"


# =============================================================================
# CORE MECHANIC SCHEMAS
# =============================================================================


class CoreMechanic(BaseModel):
    """Core mechanic definition for a game system."""

    type: CoreMechanicType
    formula: str = Field(
        max_length=200,
        description="Base formula for resolution (e.g., '1d20+MOD vs DC')",
    )
    success_type: SuccessType
    success_threshold: Optional[str] = Field(
        None, max_length=200, description="How success is determined"
    )
    critical_success: Optional[str] = Field(
        None, max_length=200, description="Conditions for critical success"
    )
    critical_failure: Optional[str] = Field(
        None, max_length=200, description="Conditions for critical failure"
    )


# =============================================================================
# ATTRIBUTE/SKILL/RESOURCE SCHEMAS
# =============================================================================


class AttributeDefinition(BaseModel):
    """Definition of a character attribute."""

    name: str = Field(max_length=100, description="Attribute name (e.g., 'Strength')")
    abbreviation: str = Field(max_length=10, description="Short form (e.g., 'STR')")
    min_value: int = Field(description="Minimum value for this attribute")
    max_value: int = Field(description="Maximum value for this attribute")
    default_value: int = Field(description="Default starting value")
    modifier_formula: Optional[str] = Field(
        None,
        max_length=200,
        description="Formula for calculating modifier (e.g., '(VALUE-10)/2')",
    )


class SkillDefinition(BaseModel):
    """Definition of a character skill."""

    name: str = Field(max_length=100, description="Skill name (e.g., 'Stealth')")
    abbreviation: Optional[str] = Field(
        None, max_length=10, description="Short form if applicable"
    )
    linked_attribute: Optional[str] = Field(
        None,
        max_length=100,
        description="Attribute this skill is based on (e.g., 'Dexterity')",
    )
    description: Optional[str] = Field(
        None, max_length=500, description="What this skill represents"
    )


class ResourceDefinition(BaseModel):
    """Definition of a character resource (HP, mana, etc.)."""

    name: str = Field(max_length=100, description="Resource name (e.g., 'Hit Points')")
    abbreviation: str = Field(max_length=10, description="Short form (e.g., 'HP')")
    calculation: Optional[str] = Field(
        None,
        max_length=200,
        description="Formula for calculating max value (e.g., 'CON*10')",
    )
    min_value: int = Field(default=0, description="Minimum value (usually 0)")
    recovers_on: Optional[str] = Field(
        None,
        max_length=100,
        description="When this resource recovers (e.g., 'long rest')",
    )


# =============================================================================
# GAME SYSTEM CRUD SCHEMAS
# =============================================================================


class GameSystemCreate(BaseModel):
    """Request to create a game system."""

    name: str = Field(max_length=200, description="System name (e.g., 'D&D 5e')")
    description: str = Field(
        max_length=1000, description="Brief description of the system"
    )
    version: Optional[str] = Field(
        None, max_length=50, description="Version of the system (e.g., '5th Edition')"
    )
    core_mechanic: CoreMechanic
    attributes: List[AttributeDefinition] = Field(
        default_factory=list, description="Core attributes for this system"
    )
    skills: List[SkillDefinition] = Field(
        default_factory=list, description="Available skills"
    )
    resources: List[ResourceDefinition] = Field(
        default_factory=list, description="Character resources (HP, mana, etc.)"
    )
    custom_dice: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom dice definitions (e.g., Fate dice, Genesys symbols)",
    )
    is_builtin: bool = Field(
        default=False, description="Whether this is a built-in system"
    )


class GameSystemUpdate(BaseModel):
    """Request to update a game system."""

    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    version: Optional[str] = Field(None, max_length=50)
    core_mechanic: Optional[CoreMechanic] = None
    attributes: Optional[List[AttributeDefinition]] = None
    skills: Optional[List[SkillDefinition]] = None
    resources: Optional[List[ResourceDefinition]] = None
    custom_dice: Optional[Dict[str, Any]] = None


class GameSystemResponse(BaseModel):
    """Response with game system data."""

    id: UUID
    name: str
    description: str
    version: Optional[str]
    core_mechanic: CoreMechanic
    attributes: List[AttributeDefinition]
    skills: List[SkillDefinition]
    resources: List[ResourceDefinition]
    custom_dice: Dict[str, Any]
    is_builtin: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class GameSystemListResponse(BaseModel):
    """Response for list operations."""

    systems: List[GameSystemResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# RULE OVERRIDE CRUD SCHEMAS
# =============================================================================


class RuleOverrideCreate(BaseModel):
    """Request to create a rule override."""

    scope: RuleOverrideScope
    scope_id: UUID = Field(
        description="ID of the story/scene/universe this override applies to"
    )
    target: str = Field(
        max_length=200, description="What rule is being overridden (e.g., 'flanking')"
    )
    original: str = Field(max_length=500, description="Original rule text or behavior")
    override: str = Field(max_length=500, description="New rule text or behavior")
    reason: Optional[str] = Field(
        None, max_length=500, description="Why this override was created"
    )


class RuleOverrideUpdate(BaseModel):
    """Request to update a rule override."""

    active: Optional[bool] = None
    times_used: Optional[int] = Field(None, ge=0)
    reason: Optional[str] = Field(None, max_length=500)


class RuleOverrideResponse(BaseModel):
    """Response with rule override data."""

    id: UUID
    scope: RuleOverrideScope
    scope_id: UUID
    target: str
    original: str
    override: str
    reason: Optional[str]
    times_used: int
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleOverrideListResponse(BaseModel):
    """Response for list operations."""

    overrides: List[RuleOverrideResponse]
    total: int
