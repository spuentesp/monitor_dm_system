"""
Pydantic schemas for Game Systems & Rules operations (DL-20).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for storing game system definitions and
rule overrides. Pure data storage - rule execution logic (dice rolling, success
evaluation) lives in the agents layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import ProfileEvidenceRef


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
    DEGREES_OF_SUCCESS = "degrees_of_success"


class GameRuleType(str, Enum):
    """Classification for individual rules."""

    CORE = "core"
    COMBAT = "combat"
    SOCIAL = "social"
    POWER = "power"
    LORE = "lore"
    MECHANIC = "mechanic"
    CONDITION = "condition"
    CUSTOM = "custom"


class AbilityScoreMethod(str, Enum):
    """How ability scores are generated."""

    RANDOM_ROLL = "random_roll"
    POINT_BUY = "point_buy"
    STANDARD_ARRAY = "standard_array"
    FIXED = "fixed"
    FREE_ASSIGN = "free_assign"


class CreationStepType(str, Enum):
    """Type of step in the character creation procedure."""

    CHOOSE_ARCHETYPE = "choose_archetype"
    CHOOSE_SPECIES = "choose_species"
    CHOOSE_CLASS = "choose_class"
    GENERATE_STATS = "generate_stats"
    GENERATE_ATTRIBUTES = "generate_attributes"
    ASSIGN_STATS = "assign_stats"
    CHOOSE_BACKGROUND = "choose_background"
    CHOOSE_POWERS = "choose_powers"
    CHOOSE_SKILLS = "choose_skills"
    CHOOSE_EQUIPMENT = "choose_equipment"
    CALCULATE_DERIVED = "calculate_derived"
    WRITE_BACKSTORY = "write_backstory"
    CUSTOM = "custom"


class LogicStepType(str, Enum):
    """The technical implementation of a creation logic step."""

    CHOICE = "choice"  # User picks from a list
    ROLL = "roll"  # System rolls dice
    CALCULATION = "calculation"  # System derives value from others
    TEXT = "text"  # User provides free-text
    NARRATIVE = "narrative"  # LLM generates based on profile


class NPCTier(str, Enum):
    """Power level category for an NPC."""

    MINION = "minion"
    STANDARD = "standard"
    ELITE = "elite"
    BOSS = "boss"
    BRUTE = "brute"
    VILLAIN = "villain"


class RuleOverrideScope(str, Enum):
    """Scope at which a rule override applies."""

    STORY = "story"  # Applies to an entire story/campaign
    SCENE = "scene"  # Applies to a specific scene only


# =============================================================================
# BASE COMPONENTS
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
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this attribute",
    )


class SkillDefinition(BaseModel):
    """Definition of a character skill."""

    name: str = Field(max_length=100, description="Skill name (e.g., 'Stealth')")
    abbreviation: Optional[str] = Field(None, max_length=10, description="Short form if applicable")
    linked_attribute: Optional[str] = Field(
        None,
        max_length=100,
        description="Attribute this skill is based on (e.g., 'Dexterity')",
    )
    description: Optional[str] = Field(
        None, max_length=500, description="What this skill represents"
    )
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this skill",
    )


class ThresholdEffect(BaseModel):
    """A threshold-triggered effect applied when a track reaches a given value."""

    value: int = Field(description="The track value that triggers the effect")
    direction: str = Field(default="at_or_below", description="at_or_below | at_or_above | exactly")
    effect: str = Field(max_length=500, description="Description of the effect that occurs")
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this threshold effect",
    )


class TrackDefinition(BaseModel):
    """Definition of a tracked numerical value (resource, stress, humanity, etc.)."""

    name: str = Field(max_length=200)
    abbreviation: Optional[str] = Field(None, max_length=20)
    min_value: int = Field(default=0)
    max_value: Optional[int] = Field(None)
    max_formula: Optional[str] = Field(None, max_length=200)
    default_value: Union[int, str] = Field(
        default=0, description="Default value (int or formula string like 'full')"
    )
    track_type: str = Field(default="custom", description="hp | stress | pool | points | custom")
    gain_conditions: List[str] = Field(default_factory=list)
    loss_conditions: List[str] = Field(default_factory=list)
    spend_conditions: List[str] = Field(default_factory=list)
    recovery_rules: List[str] = Field(default_factory=list)
    threshold_effects: List[ThresholdEffect] = Field(default_factory=list)
    depleted_effect: Optional[str] = Field(None, max_length=500)
    maxed_effect: Optional[str] = Field(None, max_length=500)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this track",
    )


class AbilityTier(BaseModel):
    """One power tier within a named ability system (Discipline level, spell rank, etc.)."""

    tier: int = Field(ge=1)
    name: str = Field(max_length=200)
    cost: Optional[str] = Field(None, max_length=100)
    effect: str = Field(max_length=2000)
    prerequisites: List[str] = Field(default_factory=list)
    duration: Optional[str] = Field(None, max_length=100)
    roll: Optional[str] = Field(None, max_length=300)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this ability tier",
    )


class TieredAbilitySystem(BaseModel):
    """Named ability group where each tier unlocks a distinct power (Disciplines, Spell Schools, etc.)."""

    name: str = Field(max_length=200)
    parent_category: Optional[str] = Field(None, max_length=200)
    tiers: List[AbilityTier] = Field(default_factory=list)
    max_tier: int = Field(default=1)
    acquisition_rule: Optional[str] = Field(None, max_length=500)
    linked_track: Optional[str] = Field(None, max_length=200)
    access_restriction: Optional[str] = Field(None, max_length=300)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this ability system",
    )


class AdvantageDefinition(BaseModel):
    """Character-sheet pick with a point cost and discrete effect (Merits, Flaws, Feats, Advantages)."""

    name: str = Field(max_length=200)
    cost: Optional[Union[int, str]] = None
    category: str = Field(default="advantage")
    effect: str = Field(max_length=1000)
    prerequisites: List[str] = Field(default_factory=list)
    mutually_exclusive: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this advantage",
    )


class SuccessDegree(BaseModel):
    """Describes what a given success threshold means in a resolution system."""

    threshold: str = Field(max_length=200)
    label: str = Field(max_length=100)
    effect: str = Field(max_length=500)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this success degree",
    )


class ResolutionMechanic(BaseModel):
    """How the core dice mechanic resolves actions."""

    dice_formula: str = Field(max_length=200)
    mechanic_type: CoreMechanicType
    difficulty_model: str = Field(max_length=50)
    difficulty_range: Optional[str] = Field(None, max_length=100)
    success_degrees: List[SuccessDegree] = Field(default_factory=list)
    success_type: SuccessType
    critical_success: Optional[str] = Field(None, max_length=300)
    critical_failure: Optional[str] = Field(None, max_length=300)
    consequence_on_failure: Optional[str] = Field(None, max_length=300)
    complication_mechanic: Optional[str] = Field(None, max_length=300)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this mechanic",
    )


class DamageType(BaseModel):
    """A named category of damage with distinct healing rules and lethality."""

    name: str = Field(max_length=100)
    healing_rate: str = Field(max_length=200)
    healing_requires: Optional[str] = Field(None, max_length=200)
    resisted_by: Optional[str] = Field(None, max_length=200)
    lethality: str = Field(max_length=50)
    bypasses: List[str] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this damage type",
    )


class DamageModel(BaseModel):
    """Complete damage and wound system definition."""

    damage_types: List[DamageType] = Field(default_factory=list)
    damage_track: str = Field(max_length=200)
    incapacitated_at: str = Field(max_length=200)
    death_condition: str = Field(max_length=500)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this damage model",
    )


class ConditionDefinition(BaseModel):
    """A status effect or state that can be applied to an entity."""

    name: str = Field(max_length=100)
    trigger: Optional[str] = Field(None, max_length=500)
    mechanical_effects: List[str] = Field(default_factory=list)
    roll_modifier: Optional[int] = Field(None, description="Flat bonus/penalty to rolls (e.g. -2)")
    roll_mode_override: Optional[str] = Field(None, description="advantage | disadvantage | normal")
    ends_when: Optional[str] = Field(None, max_length=500)
    stackable: bool = Field(default=False)
    source_ref: Optional[str] = Field(None, max_length=200)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this condition",
    )


class SceneryRule(BaseModel):
    """Rule defining how a location tag or description keyword affects action rolls."""

    keyword: str = Field(max_length=100)
    trigger_verbs: List[str] = Field(
        default_factory=list, description="Verbs that trigger this effect"
    )
    roll_modifier: Optional[int] = Field(None, description="Flat bonus/penalty (e.g. -2)")
    roll_mode_override: Optional[str] = Field(None, description="advantage | disadvantage | normal")
    reason_text: str = Field(max_length=200, description="Player-facing reason for the modifier")
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this rule",
    )


class ActionTypeDef(BaseModel):
    """A named action bucket within the game's action economy."""

    name: str = Field(max_length=100)
    count_per_turn: Union[int, str] = Field(default=1)
    can_be_used_for: List[str] = Field(default_factory=list)
    triggers_on: Optional[str] = Field(None, max_length=300)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this action type",
    )


class ActionEconomy(BaseModel):
    """Definitions for turn structure and available action buckets."""

    action_types: List[ActionTypeDef] = Field(default_factory=list)
    turn_structure: str = Field(max_length=500)
    initiative_model: str = Field(max_length=300)
    surprise_rules: Optional[str] = Field(None, max_length=500)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this action economy",
    )


class AdvancementCurrency(BaseModel):
    """A currency earned during play."""

    name: str = Field(max_length=100)
    earn_conditions: List[str] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this currency",
    )


class AdvancementTarget(BaseModel):
    """Something a character can purchase or improve."""

    target_type: str = Field(max_length=100)
    target_name: Optional[str] = Field(None, max_length=100)
    cost_formula: str = Field(max_length=200)
    prerequisites: List[str] = Field(default_factory=list)
    max_purchases: Optional[int] = None
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this target",
    )


class AdvancementModel(BaseModel):
    """The full character improvement system."""

    currencies: List[AdvancementCurrency] = Field(default_factory=list)
    targets: List[AdvancementTarget] = Field(default_factory=list)
    uses_levels: bool = Field(default=True)
    max_level: Optional[int] = None
    progression_table: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this advancement model",
    )


class RecoveryEvent(BaseModel):
    """A rest or recovery action."""

    name: str = Field(max_length=100)
    duration: str = Field(max_length=200)
    restores: List[str] = Field(default_factory=list)
    requires: Optional[str] = Field(None, max_length=300)
    available_when: Optional[str] = Field(None, max_length=300)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this recovery event",
    )


class RecoveryModel(BaseModel):
    """The full rest and healing system."""

    events: List[RecoveryEvent] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this recovery model",
    )


class ResourceDefinition(BaseModel):
    """Definition of a character resource (HP, mana, etc.)."""

    name: str = Field(max_length=100)
    abbreviation: str = Field(max_length=10)
    calculation: Optional[str] = Field(None, max_length=200)
    min_value: int = Field(default=0)
    recovers_on: Optional[str] = Field(None, max_length=100)
    depleted_effect: Optional[str] = Field(None, max_length=200)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this resource",
    )


class CoreMechanic(BaseModel):
    """Primary dice/card resolution mechanic definition."""

    type: CoreMechanicType
    formula: str = Field(max_length=200)
    success_type: SuccessType
    success_threshold: Optional[Union[int, str]] = None
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this core mechanic",
    )


class GameRule(BaseModel):
    """An individual mechanical rule extracted from a source."""

    name: str = Field(max_length=200)
    rule_type: GameRuleType
    description: str = Field(max_length=2000)
    formula: Optional[str] = Field(None, max_length=300)
    source_ref: Optional[str] = Field(None, max_length=200)
    tags: List[str] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this rule",
    )


# =============================================================================
# CHARACTER CREATION SCHEMAS
# =============================================================================


class AbilityScoreGeneration(BaseModel):
    """Rules for generating core attributes."""

    method: AbilityScoreMethod
    roll_formula: Optional[str] = Field(None, max_length=100)
    roll_count: Optional[int] = Field(None, ge=1)
    reroll_ones: bool = Field(default=False)
    point_budget: Optional[int] = Field(None, ge=0)
    point_cost_table: Dict[str, int] = Field(default_factory=dict)
    standard_array: List[int] = Field(default_factory=list)
    fixed_value: Optional[int] = None
    min_score: Optional[int] = None
    max_score: Optional[int] = None
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this generation method",
    )


class CreationStep(BaseModel):
    """A single step in the character creation procedure."""

    step_number: int = Field(ge=1)
    step_type: CreationStepType
    title: str = Field(max_length=200)
    instructions: str = Field(max_length=2000)
    is_optional: bool = Field(default=False)
    options: List[str] = Field(default_factory=list)
    derived_stats: List[str] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this creation step",
    )


class CreationLogicStep(BaseModel):
    """Actionable logic for a single step."""

    step_number: int = Field(ge=1)
    logic_type: LogicStepType
    data_source: Optional[str] = Field(None, max_length=100)
    target_field: Optional[str] = Field(None, max_length=100)
    prompt_template: Optional[str] = Field(None, max_length=1000)
    is_automated: bool = Field(default=False)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this logic step",
    )


class Background(BaseModel):
    """A character background option."""

    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    skill_proficiencies: List[str] = Field(default_factory=list)
    tool_proficiencies: List[str] = Field(default_factory=list)
    languages: int = Field(default=0, ge=0)
    equipment: List[str] = Field(default_factory=list)
    feature_name: Optional[str] = Field(None, max_length=200)
    feature_description: Optional[str] = Field(None, max_length=1000)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this background",
    )


class AdvancementEntry(BaseModel):
    """A single progression entry."""

    level: int = Field(ge=1)
    xp_required: Optional[int] = None
    proficiency_bonus: Optional[int] = None
    features_gained: List[str] = Field(default_factory=list)
    resource_increases: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = Field(None, max_length=500)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this advancement entry",
    )


class AdvancementSystem(BaseModel):
    """Rules for character advancement."""

    method: str = Field(max_length=100)
    max_level: Optional[int] = None
    xp_per_session: Optional[int] = None
    milestone_description: Optional[str] = Field(None, max_length=500)
    progression_table: List[AdvancementEntry] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this advancement system",
    )


class StartingPackage(BaseModel):
    """A starting equipment/resource package."""

    name: str = Field(max_length=200)
    class_or_archetype: Optional[str] = Field(None, max_length=200)
    items: List[str] = Field(default_factory=list)
    gold: int = Field(default=0, ge=0)
    resources: Dict[str, int] = Field(default_factory=dict)
    notes: Optional[str] = Field(None, max_length=500)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this package",
    )


class CharacterCreationProcedure(BaseModel):
    """Complete character creation rules."""

    steps: List[CreationStep] = Field(default_factory=list)
    logic: List[CreationLogicStep] = Field(default_factory=list)
    ability_score_generation: Optional[AbilityScoreGeneration] = None
    backgrounds: List[Background] = Field(default_factory=list)
    starting_packages: List[StartingPackage] = Field(default_factory=list)
    advancement: Optional[AdvancementSystem] = None
    multiclass_rules: Optional[str] = Field(None, max_length=1000)
    notes: Optional[str] = Field(None, max_length=2000)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this creation procedure",
    )


# =============================================================================
# NPC STAT BLOCK SCHEMAS
# =============================================================================


class NPCAttack(BaseModel):
    """A single attack or combat action for an NPC."""

    name: str = Field(max_length=200)
    damage: str = Field(max_length=100)


class NPCStatBlock(BaseModel):
    """Example NPC/creature stat block."""

    name: str = Field(max_length=200)
    tier: NPCTier
    hp: Optional[int] = None
    defense: Optional[str] = Field(None, max_length=100)
    attacks: List[NPCAttack] = Field(default_factory=list)
    special_abilities: List[str] = Field(default_factory=list)
    morale: Optional[str] = Field(None, max_length=100)
    tags: List[str] = Field(default_factory=list)
    source_ref: Optional[str] = Field(None, max_length=200)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this stat block",
    )


class NPCCreationRules(BaseModel):
    """Rules for creating or scaling NPCs."""

    types_available: List[str] = Field(default_factory=list)
    simplified_stat_method: Optional[str] = Field(None, max_length=500)
    scaling_notes: Optional[str] = Field(None, max_length=5000)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing these NPC rules",
    )


# =============================================================================
# GAME SYSTEM CRUD SCHEMAS
# =============================================================================


class GameSystemCreate(BaseModel):
    """Request to create a game system."""

    name: str = Field(max_length=200)
    description: str = Field(max_length=1000)
    version: Optional[str] = Field(None, max_length=50)
    core_mechanic: CoreMechanic
    attributes: List[AttributeDefinition] = Field(default_factory=list)
    skills: List[SkillDefinition] = Field(default_factory=list)
    resources: List[ResourceDefinition] = Field(default_factory=list)
    tracks: List[TrackDefinition] = Field(default_factory=list)
    tiered_ability_systems: List[TieredAbilitySystem] = Field(default_factory=list)
    advantages: List[AdvantageDefinition] = Field(default_factory=list)
    damage_model: Optional[DamageModel] = None
    conditions: List[ConditionDefinition] = Field(default_factory=list)
    scenery_rules: List[SceneryRule] = Field(default_factory=list)
    action_economy: Optional[ActionEconomy] = None
    resolution_mechanics: List[ResolutionMechanic] = Field(default_factory=list)
    advancement_model: Optional[AdvancementModel] = None
    recovery_model: Optional[RecoveryModel] = None
    custom_dice: Optional[Dict[str, Any]] = None
    rules: List[GameRule] = Field(default_factory=list)
    agendas: List[Any] = Field(default_factory=list)
    topologies: List[Any] = Field(default_factory=list)
    character_profiles: List[Any] = Field(default_factory=list)
    generation_templates: List[Any] = Field(default_factory=list)
    character_creation: Optional[CharacterCreationProcedure] = None
    npc_stat_blocks: List[NPCStatBlock] = Field(default_factory=list)
    npc_creation_rules: Optional[NPCCreationRules] = None
    random_tables: List[UUID] = Field(default_factory=list)
    source_document_id: Optional[UUID] = None
    is_builtin: bool = Field(default=False, description="True for seed data only")


class GameSystemUpdate(BaseModel):
    """Request to update a game system."""

    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    version: Optional[str] = Field(None, max_length=50)
    core_mechanic: Optional[CoreMechanic] = None
    attributes: Optional[List[AttributeDefinition]] = None
    skills: Optional[List[SkillDefinition]] = None
    resources: Optional[List[ResourceDefinition]] = None
    tracks: Optional[List[TrackDefinition]] = None
    tiered_ability_systems: Optional[List[TieredAbilitySystem]] = None
    advantages: Optional[List[AdvantageDefinition]] = None
    damage_model: Optional[DamageModel] = None
    conditions: Optional[List[ConditionDefinition]] = None
    scenery_rules: Optional[List[SceneryRule]] = None
    action_economy: Optional[ActionEconomy] = None
    resolution_mechanics: Optional[List[ResolutionMechanic]] = None
    advancement_model: Optional[AdvancementModel] = None
    recovery_model: Optional[RecoveryModel] = None
    custom_dice: Optional[Dict[str, Any]] = None
    rules: Optional[List[GameRule]] = None
    agendas: Optional[List[Any]] = None
    topologies: Optional[List[Any]] = None
    character_profiles: Optional[List[Any]] = None
    generation_templates: Optional[List[Any]] = None
    character_creation: Optional[CharacterCreationProcedure] = None
    npc_stat_blocks: Optional[List[NPCStatBlock]] = None
    npc_creation_rules: Optional[NPCCreationRules] = None
    random_tables: Optional[List[UUID]] = None


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
    tracks: List[TrackDefinition] = Field(default_factory=list)
    tiered_ability_systems: List[TieredAbilitySystem] = Field(default_factory=list)
    advantages: List[AdvantageDefinition] = Field(default_factory=list)
    damage_model: Optional[DamageModel] = None
    conditions: List[ConditionDefinition] = Field(default_factory=list)
    scenery_rules: List[SceneryRule] = Field(default_factory=list)
    action_economy: Optional[ActionEconomy] = None
    resolution_mechanics: List[ResolutionMechanic] = Field(default_factory=list)
    advancement_model: Optional[AdvancementModel] = None
    recovery_model: Optional[RecoveryModel] = None
    custom_dice: Optional[Dict[str, Any]] = None
    rules: List[GameRule] = Field(default_factory=list)
    agendas: List[Any] = Field(default_factory=list)
    topologies: List[Any] = Field(default_factory=list)
    character_profiles: List[Any] = Field(default_factory=list)
    generation_templates: List[Any] = Field(default_factory=list)
    character_creation: Optional[CharacterCreationProcedure] = None
    npc_stat_blocks: List[NPCStatBlock] = Field(default_factory=list)
    npc_creation_rules: Optional[NPCCreationRules] = None
    random_tables: List[UUID] = Field(default_factory=list)
    source_document_id: Optional[UUID] = None
    is_builtin: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class GameSystemListResponse(BaseModel):
    """Response for listing game systems."""

    systems: List[GameSystemResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# RULE OVERRIDE SCHEMAS
# =============================================================================


class RuleOverrideCreate(BaseModel):
    """Request to create a rule override."""

    scope: RuleOverrideScope = Field(default=RuleOverrideScope.STORY)
    scope_id: UUID
    target: str = Field(max_length=200, description="Target rule/mechanic being overridden")
    original: str = Field(max_length=500, description="Original rule text or formula")
    override: str = Field(max_length=500, description="Replacement rule text or formula")
    reason: Optional[str] = Field(None, max_length=500, description="Why this override exists")


class RuleOverrideUpdate(BaseModel):
    """Request to update a rule override."""

    active: Optional[bool] = None
    times_used: Optional[int] = None
    reason: Optional[str] = Field(None, max_length=500)


class RuleOverrideResponse(BaseModel):
    """Response with rule override data."""

    id: UUID
    scope: RuleOverrideScope
    scope_id: UUID
    target: str
    original: str
    override: str
    reason: Optional[str] = None
    times_used: int
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleOverrideListResponse(BaseModel):
    """Response for listing rule overrides."""

    overrides: List[RuleOverrideResponse]
    total: int
