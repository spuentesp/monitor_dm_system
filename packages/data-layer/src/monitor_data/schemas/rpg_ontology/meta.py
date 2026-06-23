"""
RPG Ontology — general meta-schema engine.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, uuid, enum, typing, re)

Why this exists
---------------
The previous ``base.py`` approach required a *Python class per game system*
(DISCharacterSheet, DND5ECharacterSheet, …).  This module replaces that with
a **data-driven** system: a game system is fully described by a
``GameSystemSpec`` object that contains field specs, validator specs, relation
specs, and entity type specs.  No Python subclassing is needed to add a new
game system — only data.

The companion ``factory.py`` uses Pydantic's ``create_model()`` to generate
validated model classes *at runtime* from a ``GameSystemSpec``.

Design principles
-----------------
1. **Pure data** — every class here is JSON-serialisable.  No Python code
   lives inside a spec; formulas are stored as strings and evaluated by the
   factory layer.
2. **System-agnostic** — the same spec format covers D20 (D&D 5e), attribute
   systems (DIS, Year Zero Engine), dice-pool systems (World of Darkness), and
   narrative / card-based systems.
3. **Relational integrity** — ``RelationSpec`` records cross-entity links
   (character → ship, character → faction) that the factory can use to build
   FK-style references.
4. **Data topology** — ``DataTopologySpec`` describes which storage backend
   each entity type lives in, enabling gap analysis at runtime.

Ontology hierarchy (all systems, abstract)
-------------------------------------------
::

    GameSystemSpec
    ├── entity_types: Dict[str, EntityTypeSpec]
    │   ├── fields: List[FieldSpec]
    │   ├── validators: List[ValidatorSpec]
    │   ├── item_types: Dict[str, ItemTypeSpec]   (for equipment)
    │   └── storage_backends: List[StorageBackend]
    ├── relations: List[RelationSpec]
    ├── core_mechanic: CoreMechanicSpec
    └── data_edges: List[DataEdgeSpec]
        (cross-store references used for topology mapping)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FieldType(str, Enum):
    """Primitive type for a field in an entity type."""

    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"
    ENUM = "enum"  # values come from ``enum_values``
    LIST_STR = "list_str"  # List[str]
    LIST_ENUM = "list_enum"  # List[str] restricted to enum_values
    UUID_REF = "uuid_ref"  # UUID that references another entity
    DICT = "dict"  # free-form JSON blob (last resort)


class ValidatorType(str, Enum):
    """Type of cross-field validator rule."""

    RANGE = "range"  # field value within [min, max]
    MIN = "min"  # field >= min
    MAX = "max"  # field <= max
    FORMULA = "formula"  # field == eval(expr)
    DERIVED = "derived"  # field is computed, cannot be set directly
    REQUIRES_IF = "requires_if"  # field B is required if field A matches condition
    ONE_OF = "one_of"  # field must be one of a static list
    COUNT_GATE = "count_gate"  # len(list_field) <= fn(other_field)


class OntologyMechanicType(str, Enum):
    """Fundamental resolution mechanic of the system."""

    D20_UNDER = "d20_under"  # roll d20 ≤ attribute (DIS, MÖRK BORG)
    D20_OVER = "d20_over"  # roll d20 ≥ DC (D&D 5e)
    DICE_POOL = "dice_pool"  # count successes in pool (WoD, Shadowrun)
    PERCENTILE = "percentile"  # roll d100 ≤ skill (Call of Cthulhu)
    D6_POOL = "d6_pool"  # Year Zero Engine
    STEP_DIE = "step_die"  # Savage Worlds
    NARRATIVE = "narrative"  # no dice, collaborative (Belonging Outside)
    CARD = "card"  # card-draw resolution (Doomtown)
    CUSTOM = "custom"  # described in ``core_mechanic.description``


class StorageBackend(str, Enum):
    """Storage backends used by MONITOR."""

    NEO4J = "neo4j"
    MONGODB = "mongodb"
    QDRANT = "qdrant"
    MINIO = "minio"
    POSTGRES = "postgres"
    OPENSEARCH = "opensearch"


class RelationCardinality(str, Enum):
    """Cardinality of a relation between entity types."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"


# ---------------------------------------------------------------------------
# Field-level specs
# ---------------------------------------------------------------------------


class FieldSpec(BaseModel):
    """
    Specification for a single field in an entity type.

    All constraints expressed as data: range, enum values, default, formula.
    The factory layer converts these into Pydantic Field() parameters plus
    validators.
    """

    name: str = Field(
        min_length=1,
        max_length=80,
        description="Snake-case field name, e.g. 'body', 'cosmic_rot'",
    )
    display_name: str = Field(
        min_length=1,
        max_length=80,
        description="Human label, e.g. 'BODY', 'Cosmic Rot'",
    )
    field_type: FieldType
    description: str = Field(default="", max_length=500)

    # Numeric constraints (apply when field_type is INT or FLOAT)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default_value: Any = None

    # Enum / list constraints
    enum_values: Optional[List[str]] = Field(
        None,
        description="Legal values for ENUM / LIST_ENUM field types",
    )

    # Derived field formula (e.g. "max(1, body + 6)")
    # The factory evaluates this against the other fields at model validation.
    derived_formula: Optional[str] = Field(
        None,
        max_length=300,
        description=(
            "Python expression evaluated against the sibling fields. "
            "E.g. 'max(1, body + 6)'. Available names: all other field names."
        ),
    )

    # Whether this field is required (not optional) on creation
    required: bool = True

    # Whether this field can be set by the user or is always derived
    user_settable: bool = True

    @field_validator("name")
    @classmethod
    def snake_case(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"Field name must be snake_case, got '{v}'")
        return v

    @model_validator(mode="after")
    def enum_required_for_enum_types(self) -> "FieldSpec":
        if self.field_type in (FieldType.ENUM, FieldType.LIST_ENUM):
            if not self.enum_values:
                raise ValueError(
                    f"Field '{self.name}' has type {self.field_type} but no enum_values"
                )
        return self

    @model_validator(mode="after")
    def derived_not_user_settable(self) -> "FieldSpec":
        if self.derived_formula and self.user_settable:
            # Auto-correct: derived fields are implicitly not user-settable
            object.__setattr__(self, "user_settable", False)
        return self


# ---------------------------------------------------------------------------
# Validator specs — cross-field rules expressed as data
# ---------------------------------------------------------------------------


class ValidatorSpec(BaseModel):
    """
    A data-driven validation rule applied to an entity type.

    The factory generates an actual Pydantic ``model_validator`` from each spec.
    """

    rule_id: str = Field(
        min_length=1,
        max_length=100,
        description="Unique ID for this rule, e.g. 'hp_at_most_max_hp'",
    )
    validator_type: ValidatorType
    description: str = Field(default="", max_length=500)

    # The field(s) this rule operates on
    field: Optional[str] = None  # primary field
    other_field: Optional[str] = None  # secondary (for REQUIRES_IF, COUNT_GATE)

    # Numeric bounds (for RANGE, MIN, MAX)
    min_bound: Optional[float] = None
    max_bound: Optional[float] = None

    # Formula string (for FORMULA / DERIVED)
    expr: Optional[str] = Field(
        None,
        max_length=300,
        description="Python expression that should equal field value",
    )

    # Gate expression (for COUNT_GATE: len(field) ≤ floor(other_field / divisor))
    divisor: Optional[int] = None

    # List of legal values (for ONE_OF)
    allowed_values: Optional[List[str]] = None

    # Error message template (variables: {field}, {value}, {bound})
    error_message: str = Field(
        default="Validation failed for field '{field}'",
        max_length=300,
    )


# ---------------------------------------------------------------------------
# Item type spec (sub-category of entity types used for equipment)
# ---------------------------------------------------------------------------


class ItemTypeSpec(BaseModel):
    """
    Describes an item sub-type (weapon, armor, tool, vehicle, …).

    Extends the parent ``EntityTypeSpec`` with item-specific extra fields
    and a category enum.  Systems can define their own item taxonomy here.
    """

    type_key: str = Field(
        min_length=1,
        max_length=50,
        description="Machine key, e.g. 'weapon', 'armor', 'ship'",
    )
    display_name: str = Field(min_length=1, max_length=80)
    extra_fields: List[FieldSpec] = Field(
        default_factory=list,
        description="Fields specific to this item type (beyond the parent entity fields)",
    )
    validators: List[ValidatorSpec] = Field(default_factory=list)

    @field_validator("type_key")
    @classmethod
    def snake_case(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"type_key must be snake_case, got '{v}'")
        return v


# ---------------------------------------------------------------------------
# Entity type spec
# ---------------------------------------------------------------------------


class EntityTypeSpec(BaseModel):
    """
    Describes one entity type within a game system (character, ship, creature…).

    An entity type maps to a Pydantic model class generated by the factory.
    Multiple entity types can coexist in one system (e.g. DIS has 'character'
    and 'ship').
    """

    type_key: str = Field(
        min_length=1,
        max_length=50,
        description="Machine key, e.g. 'character', 'ship', 'creature'",
    )
    display_name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)

    fields: List[FieldSpec] = Field(
        description="All fields for this entity type",
    )
    validators: List[ValidatorSpec] = Field(
        default_factory=list,
        description="Cross-field validation rules for this entity type",
    )

    # For equipment entity types — sub-type taxonomy
    item_types: Dict[str, ItemTypeSpec] = Field(
        default_factory=dict,
        description="Sub-types (weapon, armor, etc.) — only for 'item' entity type",
    )

    # Which storage backends hold instances of this entity type
    storage_backends: List[StorageBackend] = Field(
        default_factory=list,
        description=(
            "Backends where instances live. E.g. character → [POSTGRES], scene → [MONGODB, QDRANT]"
        ),
    )

    @field_validator("type_key")
    @classmethod
    def snake_case(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"type_key must be snake_case, got '{v}'")
        return v

    def get_field(self, name: str) -> Optional[FieldSpec]:
        """Look up a field spec by name."""
        return next((f for f in self.fields if f.name == name), None)

    def get_user_settable_fields(self) -> List[FieldSpec]:
        """Return only fields the user can set (not derived)."""
        return [f for f in self.fields if f.user_settable]


# ---------------------------------------------------------------------------
# Relation spec — cross-entity links
# ---------------------------------------------------------------------------


class RelationSpec(BaseModel):
    """
    Describes a directed relationship between two entity types.

    E.g. character → ship (one-to-many crew), character → faction (many-to-many).
    Used by the factory to generate FK-style reference fields and by the topology
    mapper to document data edges between storage backends.
    """

    relation_id: str = Field(
        min_length=1,
        max_length=100,
        description="Unique key, e.g. 'character_crews_ship'",
    )
    display_name: str = Field(min_length=1, max_length=100)
    from_type: str = Field(description="Source entity_type key")
    to_type: str = Field(description="Target entity_type key")
    cardinality: RelationCardinality
    description: str = Field(default="", max_length=500)
    is_required: bool = Field(
        default=False,
        description="If True, from_type must always have at least one to_type link",
    )


# ---------------------------------------------------------------------------
# Core mechanic spec
# ---------------------------------------------------------------------------


class CoreMechanicSpec(BaseModel):
    """
    Describes how the game system resolves action outcomes.

    Stored as pure data so the agents layer (never the data layer) can use
    it as a prompt-injection seed when narrating dice rolls.
    """

    mechanic_type: OntologyMechanicType
    dice_notation: Optional[str] = Field(
        None,
        max_length=50,
        description="E.g. 'd20', '2d6', 'pool:d6'",
    )
    roll_vs: Optional[str] = Field(
        None,
        max_length=200,
        description="What the roll is compared against, e.g. 'attribute score'",
    )
    success_condition: str = Field(
        max_length=200,
        description="What constitutes success, e.g. 'roll ≤ attribute'",
    )
    critical_rule: Optional[str] = Field(
        None,
        max_length=200,
        description="Criticals/fumbles rule, e.g. '1 = crit success, 20 = fumble'",
    )
    description: str = Field(default="", max_length=1000)


# ---------------------------------------------------------------------------
# Data edge spec — cross-store references for topology mapping
# ---------------------------------------------------------------------------


class DataEdgeSpec(BaseModel):
    """
    Documents a cross-store reference between two pieces of data.

    Used by the DataTopology mapper to produce a complete graph of what
    references what across all six backends.

    Example:  MongoDB scene.universe_id → Neo4j Universe.id
    """

    edge_id: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)

    from_backend: StorageBackend
    from_collection: str  # e.g. "scenes", "character_sheet_index"
    from_field: str  # e.g. "universe_id"

    to_backend: StorageBackend
    to_collection: str  # e.g. "Universe" (Neo4j node label)
    to_field: str  # e.g. "id"

    is_enforced: bool = Field(
        default=False,
        description=(
            "True if referential integrity is enforced by the backend "
            "(e.g. PG FK), False if it is a soft/logical reference"
        ),
    )
    notes: Optional[str] = Field(None, max_length=300)


# ---------------------------------------------------------------------------
# Full game system spec — the top-level object
# ---------------------------------------------------------------------------


class GameSystemSpec(BaseModel):
    """
    Complete specification of a tabletop RPG system.

    This is the single source of truth for a game system in MONITOR.  It is:
    - JSON-serialisable (no Python lambda / code inside)
    - Stored in PostgreSQL as a JSONB blob (``game_system_specs`` table)
    - Used by the factory to generate Pydantic model classes at runtime
    - Used by agents to understand the game's mechanics during narration

    To add a new game system, create a ``GameSystemSpec`` instance and call
    ``SystemRegistry.register(spec)``.  No Python subclassing needed.
    """

    system_id: str = Field(
        min_length=2,
        max_length=50,
        description="Lower-snake-case slug, e.g. 'death_in_space', 'dnd_5e'",
    )
    system_name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1.0", max_length=50)
    description: str = Field(default="", max_length=2000)
    publisher: Optional[str] = Field(None, max_length=200)
    tags: List[str] = Field(
        default_factory=list,
        description="Classification tags, e.g. ['sci-fi', 'horror', 'space']",
    )

    core_mechanic: CoreMechanicSpec

    entity_types: Dict[str, EntityTypeSpec] = Field(
        description=(
            "All entity types keyed by type_key. "
            "Standard keys: 'character', 'item', 'vehicle', 'creature'."
        ),
    )
    relations: List[RelationSpec] = Field(
        default_factory=list,
        description="All relations between entity types",
    )
    data_edges: List[DataEdgeSpec] = Field(
        default_factory=list,
        description="Cross-store data references for topology mapping",
    )

    @field_validator("system_id")
    @classmethod
    def valid_slug(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"system_id must be lower-snake-case, got '{v}'")
        return v

    @model_validator(mode="after")
    def validate_relations(self) -> "GameSystemSpec":
        """Check that all relation from/to types exist in entity_types."""
        for rel in self.relations:
            if rel.from_type not in self.entity_types:
                raise ValueError(
                    f"Relation '{rel.relation_id}' references unknown from_type '{rel.from_type}'"
                )
            if rel.to_type not in self.entity_types:
                raise ValueError(
                    f"Relation '{rel.relation_id}' references unknown to_type '{rel.to_type}'"
                )
        return self

    def get_entity_type(self, type_key: str) -> Optional[EntityTypeSpec]:
        return self.entity_types.get(type_key)

    def get_fields_for(self, type_key: str) -> List[FieldSpec]:
        et = self.entity_types.get(type_key)
        return et.fields if et else []

    def list_storage_backends(self) -> List[StorageBackend]:
        """Return all distinct backends used by any entity type."""
        backends: set[StorageBackend] = set()
        for et in self.entity_types.values():
            backends.update(et.storage_backends)
        return sorted(backends, key=lambda b: b.value)


# ---------------------------------------------------------------------------
# System registry — singleton, no I/O
# ---------------------------------------------------------------------------


class SystemRegistry:
    """
    In-memory registry mapping system_id → GameSystemSpec.

    Populated at module import time by each system spec module, or by loading
    JSONB blobs from PostgreSQL at startup.  Provides factory helpers to
    generate Pydantic model classes on demand.

    This replaces the old ``GameSystemRegistry`` in base.py — it no longer
    stores or requires Pydantic subclasses; those are generated at runtime.
    """

    _instance: ClassVar[Optional["SystemRegistry"]] = None
    _specs: Dict[str, "GameSystemSpec"]

    def __new__(cls) -> "SystemRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._specs = {}
        return cls._instance

    def register(self, spec: "GameSystemSpec") -> None:
        """Register a game system spec.  Idempotent."""
        self._specs[spec.system_id] = spec

    def get(self, system_id: str) -> Optional["GameSystemSpec"]:
        return self._specs.get(system_id)

    def list_systems(self) -> List[str]:
        return list(self._specs.keys())

    def all_specs(self) -> List["GameSystemSpec"]:
        return list(self._specs.values())

    def unregister(self, system_id: str) -> None:
        """Remove a system from the registry (useful in tests)."""
        self._specs.pop(system_id, None)

    def load_from_dict(self, data: Dict[str, Any]) -> "GameSystemSpec":
        """
        Deserialise a ``GameSystemSpec`` from a raw dict (e.g. from PostgreSQL
        JSONB) and register it.  Returns the parsed spec.
        """
        spec = GameSystemSpec.model_validate(data)
        self.register(spec)
        return spec
