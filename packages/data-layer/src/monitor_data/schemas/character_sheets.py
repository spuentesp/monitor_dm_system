"""
Pydantic schemas for CharacterSheet operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

KEY DESIGN: A character (EntityInstance) can have MULTIPLE sheets, one per
game system. The active sheet for a given story is selected by matching
game_system_id to the story's game_system_id.

This means a character who played D&D 5e, then converted to Pathfinder 2e,
keeps both sheets. The GM can run either system with the same character.

Canonical identity (name, relationships, memories) lives in Neo4j.
Mechanical stats (HP, spell slots, skill ranks) live here in MongoDB.
Working state during a scene (current HP, temp effects) lives in working_state.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# HISTORY LOG ENTRY
# =============================================================================


class SheetHistoryEntry(BaseModel):
    """A single entry in the character sheet change history."""

    timestamp: datetime
    change: str = Field(max_length=500, description="Human-readable description of change")
    scene_id: UUID | None = Field(None, description="Scene where change occurred")
    old_value: Any | None = Field(None, description="Previous value (for audit trail)")
    new_value: Any | None = Field(None, description="New value")
    field: str | None = Field(None, max_length=200, description="Field that changed")


# =============================================================================
# CHARACTER SHEET CRUD SCHEMAS
# =============================================================================


class CharacterSheetCreate(BaseModel):
    """Request to create a CharacterSheet.

    A character can have multiple sheets (one per game system or per pack-bound
    embedded system snapshot). `game_system_id` remains the preferred reference
    for reusable library systems, while `system_source_type` /
    `system_source_id` allow sheets to stay attached to pack-integrated rules
    without copying them into the global library.
    """

    entity_id: UUID = Field(description="References Neo4j EntityInstance")
    game_system_id: UUID | None = Field(
        default=None,
        description="References MongoDB game_system when the sheet uses a generic library system",
    )
    system_source_type: str | None = Field(
        default=None,
        description="generic_library | pack_embedded | narrative_only",
    )
    system_source_id: str | None = Field(
        default=None,
        description="ID of the authoritative system source (game system id or pack id)",
    )
    system_name: str | None = Field(
        default=None,
        max_length=200,
        description="Human-readable system name snapshot for this sheet",
    )
    source_persona_id: str | None = Field(
        default=None,
        description=(
            "id of the standalone-character persona (see entities router "
            "CharacterCreate) this sheet was instantiated from via Session "
            "Zero pre-seeding, if any. Lets a returning player re-instantiate "
            "the same persona into a different world instead of re-interviewing."
        ),
    )
    # Core mechanical data (system-specific)
    stats: dict[str, Any] = Field(
        default_factory=dict,
        description="System attributes (e.g., {'STR': 16, 'DEX': 12, 'CON': 14})",
    )
    resources: dict[str, Any] = Field(
        default_factory=dict,
        description="Resources that fluctuate (e.g., {'HP': 45, 'max_HP': 45, 'spell_slots': {}})",
    )
    skills: dict[str, Any] = Field(
        default_factory=dict,
        description="Skill ranks/bonuses (e.g., {'Stealth': 5, 'Arcana': 8})",
    )
    # Class and advancement
    class_levels: dict[str, int] = Field(
        default_factory=dict,
        description="Class-to-level map (e.g., {'Fighter': 3, 'Rogue': 2})",
    )
    total_level: int = Field(default=1, ge=1, description="Total character level (sum of class_levels)")
    experience_points: int = Field(default=0, ge=0)
    # Character background
    background: str | None = Field(
        default=None,
        max_length=200,
        description="Character background (e.g., 'Soldier', 'Criminal')",
    )
    alignment: str | None = Field(
        default=None,
        max_length=100,
        description="Alignment string (e.g., 'Chaotic Good', 'Lawful Neutral')",
    )
    # Equipment on person
    equipment: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Items on the character (not party inventory)",
    )
    # Feats, abilities, spells
    special_abilities: list[str] = Field(default_factory=list, description="Class features, racial traits, feats")
    spells_known: list[str] = Field(default_factory=list, description="Known/prepared spells")
    # Notes
    notes: str | None = Field(None, max_length=5000, description="Character build notes")


class CharacterSheetUpdate(BaseModel):
    """Request to update a CharacterSheet.

    All fields optional — only provided fields are updated.
    History log is updated automatically by the tool.
    """

    stats: dict[str, Any] | None = None
    resources: dict[str, Any] | None = None
    skills: dict[str, Any] | None = None
    class_levels: dict[str, int] | None = None
    total_level: int | None = Field(None, ge=1)
    experience_points: int | None = Field(None, ge=0)
    background: str | None = Field(None, max_length=200)
    alignment: str | None = Field(None, max_length=100)
    equipment: list[dict[str, Any]] | None = None
    special_abilities: list[str] | None = None
    spells_known: list[str] | None = None
    notes: str | None = Field(None, max_length=5000)
    change_description: str | None = Field(
        None,
        max_length=500,
        description="Reason for update (written to history_log)",
    )


class CharacterSheetResponse(BaseModel):
    """Response with CharacterSheet data."""

    sheet_id: UUID
    entity_id: UUID
    game_system_id: UUID | None = None
    system_source_type: str | None = None
    system_source_id: str | None = None
    system_name: str | None = None
    source_persona_id: str | None = None
    stats: dict[str, Any]
    resources: dict[str, Any]
    skills: dict[str, Any]
    class_levels: dict[str, int]
    total_level: int
    experience_points: int
    background: str | None = None
    alignment: str | None = None
    equipment: list[dict[str, Any]]
    special_abilities: list[str]
    spells_known: list[str]
    notes: str | None = None
    is_active: bool = Field(description="Active sheet for the character's current story")
    history_log: list[SheetHistoryEntry] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class CharacterSheetFilter(BaseModel):
    """Filter for listing character sheets."""

    entity_id: UUID | None = Field(None, description="Get all sheets for a character")
    game_system_id: UUID | None = Field(None, description="Get sheets for a specific generic library system")
    system_source_type: str | None = None
    system_source_id: str | None = None
    is_active: bool | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class CharacterSheetListResponse(BaseModel):
    """Response for list operations."""

    sheets: list[CharacterSheetResponse]
    total: int
    limit: int
    offset: int


class SetActiveSheetRequest(BaseModel):
    """Request to set which sheet is active for a game system."""

    entity_id: UUID
    sheet_id: UUID = Field(description="Sheet to make active")


class ApplyXPRequest(BaseModel):
    """Request to add XP to a character sheet."""

    sheet_id: UUID
    xp_amount: int = Field(ge=1)
    source: str = Field(max_length=200, description="What the XP was awarded for")
    scene_id: UUID | None = None
