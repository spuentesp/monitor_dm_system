"""
Pydantic schemas for Combat operations (DL-25).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for Combat CRUD operations.
Combat encounters manage initiative, turn order, participants, and combat flow.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import CombatSide, CombatStatus

# =============================================================================
# CONDITION SCHEMAS
# =============================================================================


class Condition(BaseModel):
    """A temporary condition affecting a combatant."""

    name: str = Field(max_length=100, description="Condition name (e.g., 'Stunned', 'Blessed')")
    source: str = Field(max_length=200, description="What caused this condition")
    duration_type: str = Field(
        max_length=50,
        description="e.g., 'rounds', 'until_save', 'permanent', 'concentration'",
    )
    duration_remaining: int | None = Field(None, ge=0, description="Remaining rounds/turns")
    metadata: dict[str, Any] = Field(
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
    initiative_value: float | None = Field(None, description="Initiative score for turn order")
    is_active: bool = Field(default=True, description="Whether participant can act")
    conditions: list[Condition] = Field(default_factory=list)
    resources: dict[str, Any] = Field(default_factory=dict, description="Resource snapshot (HP, spell slots, etc.)")
    position: dict[str, Any] | None = Field(None, description="Position data (coordinates, zone, etc.)")


class AddCombatParticipant(BaseModel):
    """Request to add a participant to combat."""

    encounter_id: UUID
    entity_id: UUID
    name: str = Field(max_length=200)
    side: CombatSide
    initiative_value: float | None = None
    resources: dict[str, Any] | None = None


class UpdateCombatParticipant(BaseModel):
    """Request to update a combat participant."""

    encounter_id: UUID
    entity_id: UUID
    initiative_value: float | None = None
    is_active: bool | None = None
    conditions: list[Condition] | None = None
    resources: dict[str, Any] | None = None
    position: dict[str, Any] | None = None


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
    hazards: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Environmental hazards (fire, ice, traps, etc.)",
    )
    cover_positions: list[dict[str, Any]] = Field(default_factory=list, description="Available cover locations")
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# COMBAT LOG SCHEMAS
# =============================================================================


class CombatLogEntry(BaseModel):
    """A single entry in the combat log."""

    round: int = Field(ge=1)
    turn: int = Field(ge=1)
    actor_id: UUID
    action: str = Field(max_length=500, description="Action taken")
    resolution_id: UUID | None = Field(None, description="Link to resolution document")
    summary: str = Field(max_length=1000, description="Human-readable summary")
    timestamp: datetime


class AddCombatLogEntry(BaseModel):
    """Request to add a combat log entry."""

    encounter_id: UUID
    round: int = Field(ge=1)
    turn: int = Field(ge=1)
    actor_id: UUID
    action: str = Field(max_length=500)
    resolution_id: UUID | None = None
    summary: str = Field(max_length=1000)


# =============================================================================
# COMBAT OUTCOME SCHEMAS
# =============================================================================


class CombatOutcome(BaseModel):
    """Final outcome of a combat encounter."""

    result: str = Field(max_length=50, description="e.g., 'victory', 'defeat', 'retreat', 'negotiated'")
    winning_side: CombatSide | None = None
    survivors: list[UUID] = Field(default_factory=list)
    casualties: list[UUID] = Field(default_factory=list)
    loot: list[dict[str, Any]] = Field(default_factory=list)
    xp_awarded: int | None = Field(None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SetCombatOutcome(BaseModel):
    """Request to set combat outcome."""

    encounter_id: UUID
    result: str = Field(max_length=50)
    winning_side: CombatSide | None = None
    survivors: list[UUID] | None = None
    casualties: list[UUID] | None = None
    loot: list[dict[str, Any]] | None = None
    xp_awarded: int | None = Field(None, ge=0)


# =============================================================================
# COMBAT CRUD SCHEMAS
# =============================================================================


class CombatCreate(BaseModel):
    """Request to create a combat encounter."""

    scene_id: UUID
    story_id: UUID
    participants: list[CombatParticipant] = Field(default_factory=list, description="Initial participants")
    environment: CombatEnvironment | None = None


class CombatUpdate(BaseModel):
    """Request to update a combat encounter."""

    status: CombatStatus | None = None
    round: int | None = Field(None, ge=1)
    turn_order: list[UUID] | None = Field(None, description="Ordered list of entity_ids for initiative order")
    current_turn_index: int | None = Field(None, ge=0)


class CombatResponse(BaseModel):
    """Response with combat encounter data."""

    id: UUID
    scene_id: UUID
    story_id: UUID
    status: CombatStatus
    round: int = Field(default=0, ge=0)
    turn_order: list[UUID] = Field(default_factory=list)
    current_turn_index: int = Field(default=0, ge=0)
    participants: list[CombatParticipant]
    environment: CombatEnvironment
    combat_log: list[CombatLogEntry] = Field(default_factory=list)
    outcome: CombatOutcome | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class CombatFilter(BaseModel):
    """Filter parameters for listing combat encounters."""

    scene_id: UUID | None = None
    story_id: UUID | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class CombatListResponse(BaseModel):
    """Response for list operations."""

    combats: list[CombatResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# SESSION COMBAT TRACKER (CF-9 — ephemeral at-the-table state)
# =============================================================================
# Combat state for a live table encounter is ephemeral session state: it lives
# in MongoDB keyed by ``(universe_id, session_id)`` and is never written to
# Neo4j. Permanent world effects (deaths, faction shifts) leave the encounter
# only as ProposedChange items staged for CanonKeeper (CF-8 path).


class CombatantState(BaseModel):
    """One combatant in the session tracker."""

    id: UUID = Field(description="Combatant id within the encounter (not the canon entity id)")
    name: str = Field(max_length=200, description="Display name")
    side: CombatSide = Field(default=CombatSide.ENEMY, description="Which side the combatant fights for")
    hp: int = Field(ge=0, description="Current hit points")
    max_hp: int = Field(gt=0, description="Maximum hit points")
    temp_hp: int = Field(default=0, ge=0, description="Temporary hit points (absorbed first)")
    initiative: float | None = Field(None, description="Initiative score once rolled")
    conditions: list[str] = Field(
        default_factory=list,
        description="Active condition tags (free text in v1; structured per-system effects are a lookup, not state)",
    )
    dead: bool = Field(default=False, description="Death flag")
    unconscious: bool = Field(default=False, description="Unconscious / disabled flag")
    concentration: str | None = Field(
        None,
        max_length=500,
        description="Concentration or reminder note (e.g. 'bless: 3 allies')",
    )
    notes: str = Field(default="", max_length=2000, description="Free-form GM note")
    entity_id: UUID | None = Field(
        None,
        description="Canon entity backing this combatant, for read-only stat-block lookup",
    )


class CombatantCreate(BaseModel):
    """A combatant added when the encounter starts."""

    name: str = Field(min_length=1, max_length=200)
    side: CombatSide = CombatSide.ENEMY
    hp: int = Field(ge=0)
    max_hp: int = Field(gt=0)
    temp_hp: int = Field(default=0, ge=0)
    conditions: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)
    entity_id: UUID | None = None


class CombatStart(BaseModel):
    """Request to start (or restart) a session combat encounter."""

    universe_id: UUID
    session_id: str = Field(min_length=1, max_length=100, description="Owning play/chat session key")
    combatants: list[CombatantCreate] = Field(min_length=1, description="Initial combatants")
    story_id: UUID | None = Field(None, description="Story scope for end-of-encounter proposals (CF-8 queue)")
    scene_id: UUID | None = Field(None, description="Scene scope for end-of-encounter proposals (CF-8 queue)")


class CombatInitiativeEntry(BaseModel):
    """Initiative result for one combatant."""

    combatant_id: UUID
    initiative: float
    tiebreak: float = Field(
        default=0,
        description="Tie-break score (e.g. dex mod or a reroll); higher wins ties",
    )


class CombatSetInitiative(BaseModel):
    """Request to set initiative for the encounter."""

    universe_id: UUID
    session_id: str = Field(max_length=100)
    entries: list[CombatInitiativeEntry] = Field(min_length=1)


class CombatUpdateCombatant(BaseModel):
    """Request to adjust one combatant's tracked state.

    String fields follow a set/clear contract: ``None`` leaves the value
    unchanged, ``""`` clears it.
    """

    universe_id: UUID
    session_id: str = Field(max_length=100)
    combatant_id: UUID
    hp: int | None = Field(None, ge=0, description="Absolute HP (clamped to max_hp); overrides hp_delta")
    hp_delta: int | None = Field(
        None,
        description="Negative = damage (temp HP absorbed first), positive = healing",
    )
    temp_hp: int | None = Field(None, ge=0, description="Absolute temp HP")
    conditions_add: list[str] = Field(default_factory=list)
    conditions_remove: list[str] = Field(default_factory=list)
    dead: bool | None = None
    unconscious: bool | None = None
    concentration: str | None = Field(None, max_length=500, description="None = unchanged, '' = clear")
    notes: str | None = Field(None, max_length=2000, description="None = unchanged, '' = clear")


class CombatNextRound(BaseModel):
    """Request to advance the encounter to the next round."""

    universe_id: UUID
    session_id: str = Field(max_length=100)


class CombatEnd(BaseModel):
    """Request to end the encounter."""

    universe_id: UUID
    session_id: str = Field(max_length=100)


class CombatSessionState(BaseModel):
    """Full tracker state for one session encounter."""

    universe_id: UUID
    session_id: str
    status: CombatStatus = Field(
        description="INITIATIVE after start, ACTIVE once initiative is set, RESOLVED after end",
    )
    round: int = Field(default=1, ge=1, description="Current round counter")
    turn_order: list[UUID] = Field(
        default_factory=list,
        description="Combatant ids in initiative order (set by combat_set_initiative)",
    )
    combatants: list[CombatantState] = Field(default_factory=list)
    story_id: UUID | None = None
    scene_id: UUID | None = None
    started_at: datetime
    ended_at: datetime | None = None
