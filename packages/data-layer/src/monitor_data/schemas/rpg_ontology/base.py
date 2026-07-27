"""
RPG Ontology — abstract base classes and infrastructure.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, uuid, datetime, enum, typing)

Design principles
-----------------
1. Every game system registers an ``AttributeSpec`` list that describes its
   attributes (name, abbreviation, min/max range, derived formula).
2. Characters store their stats as a *validated JSON blob* in PostgreSQL —
   validated by the system-specific Pydantic model on read/write.
3. Equipment is stored relationally: a catalog row carries a validated JSON
   blob plus indexed columns (type, system_id) for fast queries.
4. The ``GameSystemRegistry`` is a singleton that maps ``system_id`` strings
   to their definition objects.  It never imports from monitor_agents or CLI.

Formal ontology hierarchy
--------------------------
::

    GameEntity (abstract)
    ├── Character
    │   ├── PlayerCharacter
    │   └── NonPlayerCharacter
    ├── Ship (for space/sci-fi systems)
    ├── Creature (for fantasy systems)
    └── (extensible via game system registration)

    Item (abstract)
    ├── Weapon
    ├── Armor
    ├── Consumable
    └── Miscellaneous

    GameSystem
    ├── attributes: List[AttributeSpec]
    ├── resources:  List[ResourceSpec]
    └── entity_types: Dict[str, Type[BaseCharacterSheet]]
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Primitive spec types — describe a game system's building blocks
# ---------------------------------------------------------------------------


class AttributeSpec(BaseModel):
    """
    Formal specification of a character attribute.

    An attribute is a scored stat that directly appears on a character sheet
    (e.g. BODY, STR, Agility).  This is the *schema* for the attribute —
    not a value on a specific character.
    """

    name: str = Field(max_length=80, description="Full name, e.g. 'Body'")
    abbreviation: str = Field(max_length=10, description="Short form, e.g. 'BODY'")
    min_value: int = Field(description="Minimum legal value")
    max_value: int = Field(description="Maximum legal value")
    default_value: int = Field(description="Starting/default value")
    modifier_formula: str | None = Field(
        None,
        max_length=200,
        description="Optional formula, e.g. '(VALUE - 10) // 2' for D&D modifier",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="What this attribute represents in the fiction",
    )

    @field_validator("abbreviation")
    @classmethod
    def upper_abbreviation(cls, v: str) -> str:
        return v.upper()


class ResourceSpec(BaseModel):
    """
    Formal specification of a tracked resource (HP, Cosmic Rot, MP, etc.).

    Resources differ from attributes: they have a *current* value that changes
    during play AND a *maximum* that may be derived from attributes.
    """

    name: str = Field(max_length=80)
    abbreviation: str = Field(max_length=10)
    min_value: int = Field(default=0)
    max_formula: str | None = Field(
        None,
        max_length=200,
        description="Formula for max value, e.g. 'BODY + 6'",
    )
    depleted_effect: str | None = Field(
        None,
        max_length=200,
        description="What happens at min_value (e.g. 'incapacitated')",
    )
    recovers_on: str | None = Field(
        None,
        max_length=100,
        description="When resource recovers (e.g. 'long rest', 'medical bay')",
    )

    @field_validator("abbreviation")
    @classmethod
    def upper_abbreviation(cls, v: str) -> str:
        return v.upper()


class ItemType(StrEnum):
    """Ontological classification for equipment items."""

    WEAPON = "weapon"
    ARMOR = "armor"
    TOOL = "tool"
    CONSUMABLE = "consumable"
    VEHICLE = "vehicle"
    MISC = "misc"


# ---------------------------------------------------------------------------
# Abstract entity schemas — subclassed per game system
# ---------------------------------------------------------------------------


class BaseCharacterSheet(BaseModel):
    """
    Abstract base for all game-system character sheets.

    Concrete subclasses (e.g. DISCharacterSheet) define typed attributes as
    proper fields instead of Dict[str, Any].  They also carry cross-field
    validators to enforce game rules (e.g. HP = BODY + 6).

    The ``system_id`` field is used as a discriminator: the registry looks up
    the correct Pydantic class based on this value.
    """

    system_id: ClassVar[str]  # Must be set in each concrete subclass

    entity_id: UUID = Field(
        default_factory=uuid4,
        description="Links to Neo4j EntityInstance UUID",
    )
    character_name: str = Field(min_length=1, max_length=200)
    is_player_character: bool = Field(
        default=True,
        description="PC vs NPC distinction",
    )
    notes: str = Field(
        default="",
        max_length=2000,
        description="Free-text notes not captured by typed fields",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: datetime | None = None


class BaseEquipmentItem(BaseModel):
    """
    Abstract base for all equipment items.

    The ontological hierarchy:
      Item
      ├── Weapon (damage_die required)
      ├── Armor  (protection required)
      ├── Tool / Consumable / Misc
      └── Vehicle (move_speed required)
    """

    item_type: ItemType
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    weight_kg: float | None = Field(None, ge=0.0)
    value: str | None = Field(
        None,
        max_length=50,
        description="Monetary value in system currency, e.g. '50 credits'",
    )
    source_ref: str | None = Field(
        None,
        max_length=200,
        description="Book/page citation, e.g. 'DIS Core p.42'",
    )
    tags: list[str] = Field(default_factory=list)


class BaseWeapon(BaseEquipmentItem):
    """Abstract weapon — adds damage mechanics."""

    item_type: ItemType = Field(default=ItemType.WEAPON)
    damage_formula: str = Field(
        max_length=50,
        description="Dice notation, e.g. 'd6', '2d8+2', 'd10+STR'",
    )
    is_ranged: bool = Field(default=False)
    range_m: int | None = Field(
        None,
        ge=0,
        description="Effective range in metres (None for melee-only)",
    )
    properties: Sequence[str | Enum] = Field(
        default_factory=list,
        description="Special properties, e.g. ['heavy', 'two-handed', 'energy']",
    )


class BaseArmor(BaseEquipmentItem):
    """Abstract armor — adds protection value."""

    item_type: ItemType = Field(default=ItemType.ARMOR)
    protection: int = Field(
        ge=0,
        description="Damage reduction / armor class bonus",
    )
    is_shield: bool = Field(default=False)
    max_dex_bonus: int | None = Field(
        None,
        description="Maximum DEX modifier allowed (None = no cap)",
    )


# ---------------------------------------------------------------------------
# Game system definition — registered by each concrete system
# ---------------------------------------------------------------------------


class BaseGameSystem(BaseModel):
    """
    Formal description of a tabletop RPG system.

    This is stored in PostgreSQL (``game_system_schemas`` table) and is the
    authoritative source for attribute ranges, resource formulas, and valid
    entity types for a given system.
    """

    system_id: str = Field(
        min_length=2,
        max_length=50,
        description="Machine-readable slug, e.g. 'death_in_space', 'dnd5e'",
    )
    system_name: str = Field(
        min_length=1,
        max_length=200,
        description="Human-readable name, e.g. 'Death in Space'",
    )
    version: str = Field(default="1.0", max_length=50)
    description: str = Field(default="", max_length=2000)
    publisher: str | None = Field(None, max_length=200)
    core_mechanic_formula: str = Field(
        max_length=200,
        description="Base resolution formula, e.g. 'd20 + bonus vs DC'",
    )
    attributes: list[AttributeSpec] = Field(
        description="Ordered list of character attributes",
    )
    resources: list[ResourceSpec] = Field(
        description="Tracked resources (HP, Cosmic Rot, etc.)",
    )
    schema_class: str = Field(
        max_length=200,
        description="Python import path for the concrete CharacterSheet subclass",
    )

    @field_validator("system_id")
    @classmethod
    def valid_slug(cls, v: str) -> str:
        import re

        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"system_id must be a lower-snake-case slug, got '{v}'")
        return v

    def attribute_by_abbr(self, abbreviation: str) -> AttributeSpec | None:
        """Look up an attribute spec by abbreviation."""
        abbr_upper = abbreviation.upper()
        return next((a for a in self.attributes if a.abbreviation == abbr_upper), None)

    def validate_attribute_value(self, abbreviation: str, value: int) -> bool:
        """Return True if the value is within the spec range."""
        spec = self.attribute_by_abbr(abbreviation)
        if spec is None:
            return False
        return spec.min_value <= value <= spec.max_value


# ---------------------------------------------------------------------------
# Game System Registry — singleton, no I/O
# ---------------------------------------------------------------------------


class GameSystemRegistry:
    """
    In-memory registry mapping system_id → (GameSystemDefinition, SheetClass).

    Populated at module import time by each concrete system module.
    Does NOT perform any I/O — the PostgreSQL client persists the definitions.
    """

    _instance: ClassVar[GameSystemRegistry | None] = None
    _systems: dict[str, tuple[BaseGameSystem, type[BaseCharacterSheet]]]

    def __new__(cls) -> GameSystemRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._systems = {}
        return cls._instance

    def register(
        self,
        definition: BaseGameSystem,
        sheet_class: type[BaseCharacterSheet],
    ) -> None:
        """Register a game system definition with its character sheet class."""
        self._systems[definition.system_id] = (definition, sheet_class)

    def get_definition(self, system_id: str) -> BaseGameSystem | None:
        """Get the system definition by ID."""
        entry = self._systems.get(system_id)
        return entry[0] if entry else None

    def get_sheet_class(self, system_id: str) -> type[BaseCharacterSheet] | None:
        """Get the character sheet Pydantic class for a system."""
        entry = self._systems.get(system_id)
        return entry[1] if entry else None

    def list_systems(self) -> list[str]:
        """Return all registered system IDs."""
        return list(self._systems.keys())

    def parse_sheet(self, system_id: str, data: dict[str, Any]) -> BaseCharacterSheet:
        """
        Deserialize + validate a character sheet from a JSON dict.

        Raises ValueError if system_id is unknown.
        Raises pydantic.ValidationError if data doesn't match the schema.
        """
        sheet_class = self.get_sheet_class(system_id)
        if sheet_class is None:
            raise ValueError(f"Unknown game system: '{system_id}'")
        return sheet_class.model_validate(data)


# ---------------------------------------------------------------------------
# Request/Response schemas for the MCP tool layer
# ---------------------------------------------------------------------------


class TypedCharacterSheetCreate(BaseModel):
    """Request to create a typed character sheet in PostgreSQL."""

    world_id: str = Field(description="PostgreSQL worlds.id value")
    entity_id: UUID = Field(
        description="Neo4j EntityInstance UUID — must already exist in Neo4j",
    )
    system_id: str = Field(description="Registered game system slug")
    sheet_data: dict[str, Any] = Field(
        description="Character sheet data — validated against the system's schema",
    )


class TypedCharacterSheetUpdate(BaseModel):
    """Request to update specific fields on a character sheet."""

    sheet_data: dict[str, Any] = Field(
        description="Partial sheet data — merged with existing record",
    )


class TypedCharacterSheetResponse(BaseModel):
    """Response containing a character sheet."""

    id: UUID
    world_id: str
    entity_id: UUID
    system_id: str
    character_name: str
    sheet_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime | None


class EquipmentItemCreate(BaseModel):
    """Request to add an item to the equipment catalog."""

    world_id: str
    system_id: str
    item_name: str = Field(min_length=1, max_length=200)
    item_type: ItemType
    item_data: dict[str, Any] = Field(
        description="Typed item data — validated against the system's item schema",
    )
    source_ref: str | None = Field(None, max_length=200)


class EquipmentItemResponse(BaseModel):
    """Response containing an equipment catalog entry."""

    id: UUID
    world_id: str
    system_id: str
    item_name: str
    item_type: ItemType
    item_data: dict[str, Any]
    source_ref: str | None
    created_at: datetime
