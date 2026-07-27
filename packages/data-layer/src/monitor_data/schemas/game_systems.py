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
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from monitor_data.schemas.base import ProfileEvidenceRef

# =============================================================================
# ENUMS
# =============================================================================


class CoreMechanicType(StrEnum):
    """Core mechanic type used by the game system."""

    D20 = "d20"
    DICE_POOL = "dice_pool"
    PERCENTILE = "percentile"
    CARD = "card"
    NARRATIVE = "narrative"


class SuccessType(StrEnum):
    """Method for determining success."""

    MEET_OR_BEAT = "meet_or_beat"
    COUNT_SUCCESSES = "count_successes"
    HIGHEST_WINS = "highest_wins"
    DEGREES_OF_SUCCESS = "degrees_of_success"


class GameRuleType(StrEnum):
    """Classification for individual rules."""

    CORE = "core"
    COMBAT = "combat"
    SOCIAL = "social"
    POWER = "power"
    LORE = "lore"
    MECHANIC = "mechanic"
    CONDITION = "condition"
    CUSTOM = "custom"


# Aliases emitted by LLM extraction (esp. cheap local models like qwen2.5)
# that don't match the canonical enum. We normalize at the schema boundary
# instead of letting Pydantic reject the whole section's rules list — see
# INGESTION_PIPELINE_AUDIT and follow-up notes. Mapping is explicit; anything
# not listed falls back to CUSTOM at validation time.
GAME_RULE_TYPE_ALIASES: dict[str, GameRuleType] = {
    # Combat-flavored terms
    "ranged_combat": GameRuleType.COMBAT,
    "ranged": GameRuleType.COMBAT,
    "melee": GameRuleType.COMBAT,
    "attack": GameRuleType.COMBAT,
    "damage": GameRuleType.COMBAT,
    # Power / magic
    "magic": GameRuleType.POWER,
    "spell": GameRuleType.POWER,
    "healing": GameRuleType.POWER,
    "ritual": GameRuleType.POWER,
    "ceremony": GameRuleType.POWER,
    "discipline": GameRuleType.POWER,
    "power": GameRuleType.POWER,
    # Core mechanics
    "saving_throw": GameRuleType.CORE,
    "save": GameRuleType.CORE,
    "movement": GameRuleType.CORE,
    # D&D-flavored generic → CUSTOM (no canonical analog)
    "class": GameRuleType.CUSTOM,
    "background": GameRuleType.CUSTOM,
    "feat": GameRuleType.CUSTOM,
    "merit": GameRuleType.CUSTOM,
    "background_dot": GameRuleType.CUSTOM,
    "merit_dot": GameRuleType.CUSTOM,
    # LLM catch-alls
    "ability": GameRuleType.CUSTOM,
    "skill": GameRuleType.CUSTOM,
    "trait": GameRuleType.CUSTOM,
    "feature": GameRuleType.CUSTOM,
}


class AbilityScoreMethod(StrEnum):
    """How ability scores are generated."""

    RANDOM_ROLL = "random_roll"
    POINT_BUY = "point_buy"
    STANDARD_ARRAY = "standard_array"
    FIXED = "fixed"
    FREE_ASSIGN = "free_assign"


class CreationStepType(StrEnum):
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
    # Legacy aliases — older bundles (and the character_creation_loop default
    # injector) used these names before the enum was tightened. Keep them
    # accepted so ingestion + forge paths don't reject pre-existing data.
    CHOOSE_NAME = "choose_name"
    CHOOSE_ATTRIBUTES = "choose_attributes"
    CHOOSE_DISCIPLINES = "choose_disciplines"
    CHOOSE_ADVANTAGES = "choose_advantages"
    CUSTOM = "custom"


class LogicStepType(StrEnum):
    """The technical implementation of a creation logic step."""

    CHOICE = "choice"  # User picks from a list
    ROLL = "roll"  # System rolls dice
    CALCULATION = "calculation"  # System derives value from others
    TEXT = "text"  # User provides free-text
    NARRATIVE = "narrative"  # LLM generates based on profile


class NPCTier(StrEnum):
    """Power level category for an NPC."""

    MINION = "minion"
    STANDARD = "standard"
    ELITE = "elite"
    BOSS = "boss"
    BRUTE = "brute"
    VILLAIN = "villain"


class RuleOverrideScope(StrEnum):
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
    modifier_formula: str | None = Field(
        None,
        max_length=200,
        description="Formula for calculating modifier (e.g., '(VALUE-10)/2')",
    )
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this attribute",
    )


class SkillDefinition(BaseModel):
    """Definition of a character skill."""

    name: str = Field(max_length=100, description="Skill name (e.g., 'Stealth')")
    abbreviation: str | None = Field(None, max_length=10, description="Short form if applicable")
    linked_attribute: str | None = Field(
        None,
        max_length=100,
        description="Attribute this skill is based on (e.g., 'Dexterity')",
    )
    description: str | None = Field(None, max_length=500, description="What this skill represents")
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this skill",
    )


class ThresholdEffect(BaseModel):
    """A threshold-triggered effect applied when a track reaches a given value."""

    value: int = Field(description="The track value that triggers the effect")
    direction: str = Field(default="at_or_below", description="at_or_below | at_or_above | exactly")
    effect: str = Field(max_length=500, description="Description of the effect that occurs")
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this threshold effect",
    )


class TrackDefinition(BaseModel):
    """Definition of a tracked numerical value (resource, stress, humanity, etc.)."""

    name: str = Field(max_length=200)
    abbreviation: str | None = Field(None, max_length=20)
    min_value: int = Field(default=0)
    max_value: int | None = Field(None)
    max_formula: str | None = Field(None, max_length=200)
    default_value: int | str = Field(default=0, description="Default value (int or formula string like 'full')")
    track_type: str = Field(default="custom", description="hp | stress | pool | points | custom")
    gain_conditions: list[str] = Field(default_factory=list)
    loss_conditions: list[str] = Field(default_factory=list)
    spend_conditions: list[str] = Field(default_factory=list)
    recovery_rules: list[str] = Field(default_factory=list)
    threshold_effects: list[ThresholdEffect] = Field(default_factory=list)
    depleted_effect: str | None = Field(None, max_length=500)
    maxed_effect: str | None = Field(None, max_length=500)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this track",
    )


class AbilityTier(BaseModel):
    """One power tier within a named ability system (Discipline level, spell rank, etc.)."""

    tier: int = Field(ge=1)
    name: str = Field(max_length=200)
    cost: str | None = Field(None, max_length=100)
    effect: str = Field(max_length=2000)
    prerequisites: list[str] = Field(default_factory=list)
    duration: str | None = Field(None, max_length=100)
    roll: str | None = Field(None, max_length=300)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this ability tier",
    )


class TieredAbilitySystem(BaseModel):
    """Named ability group where each tier unlocks a distinct power (Disciplines, Spell Schools, etc.)."""

    name: str = Field(max_length=200)
    parent_category: str | None = Field(None, max_length=200)
    tiers: list[AbilityTier] = Field(default_factory=list)
    max_tier: int = Field(default=1)
    acquisition_rule: str | None = Field(None, max_length=500)
    linked_track: str | None = Field(None, max_length=200)
    access_restriction: str | None = Field(None, max_length=300)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this ability system",
    )


class AdvantageDefinition(BaseModel):
    """Character-sheet pick with a point cost and discrete effect (Merits, Flaws, Feats, Advantages)."""

    name: str = Field(max_length=200)
    cost: int | str | None = None
    category: str = Field(default="advantage")
    effect: str = Field(max_length=1000)
    prerequisites: list[str] = Field(default_factory=list)
    mutually_exclusive: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this advantage",
    )


class SuccessDegree(BaseModel):
    """Describes what a given success threshold means in a resolution system."""

    threshold: str = Field(max_length=200)
    label: str = Field(max_length=100)
    effect: str = Field(max_length=500)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this success degree",
    )


class ResolutionMechanic(BaseModel):
    """How the core dice mechanic resolves actions."""

    dice_formula: str = Field(max_length=200)
    mechanic_type: CoreMechanicType
    difficulty_model: str = Field(max_length=200)
    difficulty_range: str | None = Field(None, max_length=100)
    success_degrees: list[SuccessDegree] = Field(default_factory=list)
    success_type: SuccessType
    critical_success: str | None = Field(None, max_length=300)
    critical_failure: str | None = Field(None, max_length=300)
    consequence_on_failure: str | None = Field(None, max_length=300)
    complication_mechanic: str | None = Field(None, max_length=300)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this mechanic",
    )


class DamageType(BaseModel):
    """A named category of damage with distinct healing rules and lethality."""

    name: str = Field(max_length=100)
    healing_rate: str = Field(max_length=200)
    healing_requires: str | None = Field(None, max_length=200)
    resisted_by: str | None = Field(None, max_length=200)
    lethality: str = Field(max_length=50)
    bypasses: list[str] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this damage type",
    )


class DamageModel(BaseModel):
    """Complete damage and wound system definition."""

    damage_types: list[DamageType] = Field(default_factory=list)
    damage_track: str = Field(max_length=200)
    incapacitated_at: str = Field(max_length=200)
    death_condition: str = Field(max_length=500)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this damage model",
    )


class ConditionDefinition(BaseModel):
    """A status effect or state that can be applied to an entity."""

    name: str = Field(max_length=100)
    trigger: str | None = Field(None, max_length=500)
    mechanical_effects: list[str] = Field(default_factory=list)
    roll_modifier: int | None = Field(None, description="Flat bonus/penalty to rolls (e.g. -2)")
    roll_mode_override: str | None = Field(None, description="advantage | disadvantage | normal")
    ends_when: str | None = Field(None, max_length=500)
    stackable: bool = Field(default=False)
    source_ref: str | None = Field(None, max_length=200)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this condition",
    )


class SceneryRule(BaseModel):
    """Rule defining how a location tag or description keyword affects action rolls."""

    keyword: str = Field(max_length=100)
    trigger_verbs: list[str] = Field(default_factory=list, description="Verbs that trigger this effect")
    roll_modifier: int | None = Field(None, description="Flat bonus/penalty (e.g. -2)")
    roll_mode_override: str | None = Field(None, description="advantage | disadvantage | normal")
    reason_text: str = Field(max_length=200, description="Player-facing reason for the modifier")
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this rule",
    )


class ActionTypeDef(BaseModel):
    """A named action bucket within the game's action economy."""

    name: str = Field(max_length=100)
    count_per_turn: int | str = Field(default=1)
    can_be_used_for: list[str] = Field(default_factory=list)
    triggers_on: str | None = Field(None, max_length=300)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this action type",
    )


class ActionEconomy(BaseModel):
    """Definitions for turn structure and available action buckets."""

    action_types: list[ActionTypeDef] = Field(default_factory=list)
    turn_structure: str = Field(max_length=500)
    initiative_model: str = Field(max_length=300)
    surprise_rules: str | None = Field(None, max_length=500)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this action economy",
    )


class AdvancementCurrency(BaseModel):
    """A currency earned during play."""

    name: str = Field(max_length=100)
    earn_conditions: list[str] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this currency",
    )


class AdvancementTarget(BaseModel):
    """Something a character can purchase or improve."""

    target_type: str = Field(max_length=100)
    target_name: str | None = Field(None, max_length=100)
    cost_formula: str = Field(max_length=200)
    prerequisites: list[str] = Field(default_factory=list)
    max_purchases: int | None = None
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this target",
    )


class AdvancementModel(BaseModel):
    """The full character improvement system."""

    currencies: list[AdvancementCurrency] = Field(default_factory=list)
    targets: list[AdvancementTarget] = Field(default_factory=list)
    uses_levels: bool = Field(default=True)
    max_level: int | None = None
    progression_table: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this advancement model",
    )


class RecoveryEvent(BaseModel):
    """A rest or recovery action."""

    name: str = Field(max_length=100)
    duration: str = Field(max_length=200)
    restores: list[str] = Field(default_factory=list)
    requires: str | None = Field(None, max_length=300)
    available_when: str | None = Field(None, max_length=300)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this recovery event",
    )


class RecoveryModel(BaseModel):
    """The full rest and healing system."""

    events: list[RecoveryEvent] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this recovery model",
    )


class ResourceDefinition(BaseModel):
    """Definition of a character resource (HP, mana, etc.)."""

    name: str = Field(max_length=100)
    abbreviation: str = Field(max_length=10)
    calculation: str | None = Field(None, max_length=200)
    min_value: int = Field(default=0)
    recovers_on: str | None = Field(None, max_length=100)
    depleted_effect: str | None = Field(None, max_length=200)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this resource",
    )


class CoreMechanic(BaseModel):
    """Primary dice/card resolution mechanic definition."""

    type: CoreMechanicType
    formula: str = Field(max_length=200)
    success_type: SuccessType
    success_threshold: int | str | None = None
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this core mechanic",
    )


class GameRule(BaseModel):
    """An individual mechanical rule extracted from a source."""

    name: str = Field(max_length=200)
    # Default to CUSTOM so LLM emissions that omit the field entirely (common
    # with qwen2.5) don't reject the whole section. The validator below also
    # maps unknown string values to CUSTOM.
    rule_type: GameRuleType = Field(default=GameRuleType.CUSTOM)
    description: str = Field(max_length=2000)
    formula: str | None = Field(None, max_length=300)
    source_ref: str | None = Field(None, max_length=200)
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this rule",
    )

    @field_validator("rule_type", mode="before")
    @classmethod
    def _normalize_rule_type(cls, value: Any) -> Any:
        """Normalize LLM-emitted aliases to canonical GameRuleType.

        DSPy signature output runs Pydantic validation; an unknown enum
        value (e.g. ``"class"`` from qwen2.5) would reject the whole
        ``rules`` list for that section, silently zeroing extraction.
        Map known aliases via ``GAME_RULE_TYPE_ALIASES``; anything unknown
        becomes ``CUSTOM`` instead of raising.
        """
        if value is None:
            return GameRuleType.CUSTOM.value
        if isinstance(value, GameRuleType):
            return value
        if not isinstance(value, str):
            return GameRuleType.CUSTOM.value
        normalized = value.strip().lower()
        if not normalized:
            return GameRuleType.CUSTOM.value
        if normalized in {e.value for e in GameRuleType}:
            return normalized
        if normalized in GAME_RULE_TYPE_ALIASES:
            return GAME_RULE_TYPE_ALIASES[normalized].value
        return GameRuleType.CUSTOM.value


# =============================================================================
# CHARACTER CREATION SCHEMAS
# =============================================================================


class AbilityScoreGeneration(BaseModel):
    """Rules for generating core attributes."""

    method: AbilityScoreMethod
    roll_formula: str | None = Field(None, max_length=100)
    roll_count: int | None = Field(None, ge=1)
    reroll_ones: bool = Field(default=False)
    point_budget: int | None = Field(None, ge=0)
    point_cost_table: dict[str, int] = Field(default_factory=dict)
    standard_array: list[int] = Field(default_factory=list)
    fixed_value: int | None = None
    min_score: int | None = None
    max_score: int | None = None
    evidence_refs: list[ProfileEvidenceRef] = Field(
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
    options: list[str] = Field(default_factory=list)
    derived_stats: list[str] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this creation step",
    )


class CreationLogicStep(BaseModel):
    """Actionable logic for a single step."""

    step_number: int = Field(ge=1)
    logic_type: LogicStepType
    data_source: str | None = Field(None, max_length=100)
    target_field: str | None = Field(None, max_length=100)
    prompt_template: str | None = Field(None, max_length=1000)
    is_automated: bool = Field(default=False)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this logic step",
    )


class Background(BaseModel):
    """A character background option."""

    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    skill_proficiencies: list[str] = Field(default_factory=list)
    tool_proficiencies: list[str] = Field(default_factory=list)
    languages: int = Field(default=0, ge=0)
    equipment: list[str] = Field(default_factory=list)
    feature_name: str | None = Field(None, max_length=200)
    feature_description: str | None = Field(None, max_length=1000)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this background",
    )


class AdvancementEntry(BaseModel):
    """A single progression entry."""

    level: int = Field(ge=1)
    xp_required: int | None = None
    proficiency_bonus: int | None = None
    features_gained: list[str] = Field(default_factory=list)
    resource_increases: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(None, max_length=500)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this advancement entry",
    )


class AdvancementSystem(BaseModel):
    """Rules for character advancement."""

    method: str = Field(max_length=100)
    max_level: int | None = None
    xp_per_session: int | None = None
    milestone_description: str | None = Field(None, max_length=500)
    progression_table: list[AdvancementEntry] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this advancement system",
    )


class StartingPackage(BaseModel):
    """A starting equipment/resource package."""

    name: str = Field(max_length=200)
    class_or_archetype: str | None = Field(None, max_length=200)
    items: list[str] = Field(default_factory=list)
    gold: int = Field(default=0, ge=0)
    resources: dict[str, int] = Field(default_factory=dict)
    notes: str | None = Field(None, max_length=500)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this package",
    )


class CharacterCreationProcedure(BaseModel):
    """Complete character creation rules."""

    steps: list[CreationStep] = Field(default_factory=list)
    logic: list[CreationLogicStep] = Field(default_factory=list)
    ability_score_generation: AbilityScoreGeneration | None = None
    backgrounds: list[Background] = Field(default_factory=list)
    starting_packages: list[StartingPackage] = Field(default_factory=list)
    advancement: AdvancementSystem | None = None
    multiclass_rules: str | None = Field(None, max_length=1000)
    notes: str | None = Field(None, max_length=2000)
    evidence_refs: list[ProfileEvidenceRef] = Field(
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
    hp: int | None = None
    defense: str | None = Field(None, max_length=100)

    @field_validator("defense", mode="before")
    @classmethod
    def _coerce_defense(cls, v: Any) -> Any:
        # LLM sometimes emits defensive numeric values (e.g. "0" or 0);
        # coerce non-str to str so the optional[100-char] field validates.
        if v is None or isinstance(v, str):
            return v
        return str(v)

    attacks: list[NPCAttack] = Field(default_factory=list)
    special_abilities: list[str] = Field(default_factory=list)
    morale: str | None = Field(None, max_length=100)
    tags: list[str] = Field(default_factory=list)
    source_ref: str | None = Field(None, max_length=200)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this stat block",
    )


class NPCCreationRules(BaseModel):
    """Rules for creating or scaling NPCs."""

    types_available: list[str] = Field(default_factory=list)
    simplified_stat_method: str | None = Field(None, max_length=500)
    scaling_notes: str | None = Field(None, max_length=5000)
    evidence_refs: list[ProfileEvidenceRef] = Field(
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
    version: str | None = Field(None, max_length=50)
    core_mechanic: CoreMechanic
    attributes: list[AttributeDefinition] = Field(default_factory=list)
    skills: list[SkillDefinition] = Field(default_factory=list)
    resources: list[ResourceDefinition] = Field(default_factory=list)
    tracks: list[TrackDefinition] = Field(default_factory=list)
    tiered_ability_systems: list[TieredAbilitySystem] = Field(default_factory=list)
    advantages: list[AdvantageDefinition] = Field(default_factory=list)
    damage_model: DamageModel | None = None
    conditions: list[ConditionDefinition] = Field(default_factory=list)
    scenery_rules: list[SceneryRule] = Field(default_factory=list)
    action_economy: ActionEconomy | None = None
    resolution_mechanics: list[ResolutionMechanic] = Field(default_factory=list)
    advancement_model: AdvancementModel | None = None
    recovery_model: RecoveryModel | None = None
    custom_dice: dict[str, Any] | None = None
    rules: list[GameRule] = Field(default_factory=list)
    agendas: list[Any] = Field(default_factory=list)
    topologies: list[Any] = Field(default_factory=list)
    character_profiles: list[Any] = Field(default_factory=list)
    generation_templates: list[Any] = Field(default_factory=list)
    character_creation: CharacterCreationProcedure | None = None
    npc_stat_blocks: list[NPCStatBlock] = Field(default_factory=list)
    npc_creation_rules: NPCCreationRules | None = None
    random_tables: list[UUID] = Field(default_factory=list)
    source_document_id: UUID | None = None
    is_builtin: bool = Field(default=False, description="True for seed data only")
    hand_authored: bool = Field(
        default=False,
        description=(
            "True when this system was authored directly (no source PDF), "
            "e.g. via the hand-authoring endpoint. Distinguishes 'legitimately "
            "has no source_document_id' from 'looks real, isn't' — see "
            "INGESTION_PIPELINE_AUDIT.md Finding 3."
        ),
    )
    needs_review: bool = Field(
        default=False,
        description=(
            "True when extraction produced a degenerate result (e.g. zero "
            "populated schema fields, or a core_mechanic built entirely from "
            "placeholder defaults) rather than a genuine failure or a "
            "genuine success. See INGESTION_PIPELINE_AUDIT.md Finding 5."
        ),
    )
    degenerate_reason: str | None = Field(
        None,
        max_length=500,
        description="Human-readable explanation of why needs_review is set.",
    )


class GameSystemUpdate(BaseModel):
    """Request to update a game system."""

    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=1000)
    version: str | None = Field(None, max_length=50)
    core_mechanic: CoreMechanic | None = None
    attributes: list[AttributeDefinition] | None = None
    skills: list[SkillDefinition] | None = None
    resources: list[ResourceDefinition] | None = None
    tracks: list[TrackDefinition] | None = None
    tiered_ability_systems: list[TieredAbilitySystem] | None = None
    advantages: list[AdvantageDefinition] | None = None
    damage_model: DamageModel | None = None
    conditions: list[ConditionDefinition] | None = None
    scenery_rules: list[SceneryRule] | None = None
    action_economy: ActionEconomy | None = None
    resolution_mechanics: list[ResolutionMechanic] | None = None
    advancement_model: AdvancementModel | None = None
    recovery_model: RecoveryModel | None = None
    custom_dice: dict[str, Any] | None = None
    rules: list[GameRule] | None = None
    agendas: list[Any] | None = None
    topologies: list[Any] | None = None
    character_profiles: list[Any] | None = None
    generation_templates: list[Any] | None = None
    character_creation: CharacterCreationProcedure | None = None
    npc_stat_blocks: list[NPCStatBlock] | None = None
    npc_creation_rules: NPCCreationRules | None = None
    random_tables: list[UUID] | None = None
    needs_review: bool | None = None
    degenerate_reason: str | None = Field(None, max_length=500)


class GameSystemResponse(BaseModel):
    """Response with game system data."""

    id: UUID
    name: str
    description: str
    version: str | None
    core_mechanic: CoreMechanic
    attributes: list[AttributeDefinition]
    skills: list[SkillDefinition]
    resources: list[ResourceDefinition]
    tracks: list[TrackDefinition] = Field(default_factory=list)
    tiered_ability_systems: list[TieredAbilitySystem] = Field(default_factory=list)
    advantages: list[AdvantageDefinition] = Field(default_factory=list)
    damage_model: DamageModel | None = None
    conditions: list[ConditionDefinition] = Field(default_factory=list)
    scenery_rules: list[SceneryRule] = Field(default_factory=list)
    action_economy: ActionEconomy | None = None
    resolution_mechanics: list[ResolutionMechanic] = Field(default_factory=list)
    advancement_model: AdvancementModel | None = None
    recovery_model: RecoveryModel | None = None
    custom_dice: dict[str, Any] | None = None
    rules: list[GameRule] = Field(default_factory=list)
    agendas: list[Any] = Field(default_factory=list)
    topologies: list[Any] = Field(default_factory=list)
    character_profiles: list[Any] = Field(default_factory=list)
    generation_templates: list[Any] = Field(default_factory=list)
    character_creation: CharacterCreationProcedure | None = None
    npc_stat_blocks: list[NPCStatBlock] = Field(default_factory=list)
    npc_creation_rules: NPCCreationRules | None = None
    random_tables: list[UUID] = Field(default_factory=list)
    source_document_id: UUID | None = None
    is_builtin: bool
    hand_authored: bool = Field(default=False)
    needs_review: bool = Field(default=False)
    degenerate_reason: str | None = None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class GameSystemListResponse(BaseModel):
    """Response for listing game systems."""

    systems: list[GameSystemResponse]
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
    reason: str | None = Field(None, max_length=500, description="Why this override exists")


class RuleOverrideUpdate(BaseModel):
    """Request to update a rule override."""

    active: bool | None = None
    times_used: int | None = None
    reason: str | None = Field(None, max_length=500)


class RuleOverrideResponse(BaseModel):
    """Response with rule override data."""

    id: UUID
    scope: RuleOverrideScope
    scope_id: UUID
    target: str
    original: str
    override: str
    reason: str | None = None
    times_used: int
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleOverrideListResponse(BaseModel):
    """Response for listing rule overrides."""

    overrides: list[RuleOverrideResponse]
    total: int
