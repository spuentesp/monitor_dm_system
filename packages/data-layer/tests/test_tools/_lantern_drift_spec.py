"""An invented game system for tests: no real game is written into the platform.

It has the shape of a rules-light d20 roll-under game, so the spec factory's ranges,
derived formulas, gated lists, item subtypes and data edges all get exercised.
"""

from monitor_data.schemas.rpg_ontology.meta import (
    CoreMechanicSpec,
    DataEdgeSpec,
    EntityTypeSpec,
    FieldSpec,
    FieldType,
    GameSystemSpec,
    ItemTypeSpec,
    OntologyMechanicType,
    RelationCardinality,
    RelationSpec,
    StorageBackend,
    ValidatorSpec,
    ValidatorType,
)

# ---------------------------------------------------------------------------
# Shared enum values
# ---------------------------------------------------------------------------

_DAMAGE_DICE = ["d2", "d4", "d6", "d8", "d10", "d12"]

_ORIGINS = ["lamplighter", "ferryman", "archivist", "smuggler", "tinker", "pilgrim"]

_SKILLS = ["Climb", "Haggle", "Mend", "Steer", "Hide", "Bargain", "Read", "Brawl"]

_GIFTS = ["Glow Sight", "Quiet Step", "Warm Hands", "Far Call", "Still Mind"]

_WEAPON_PROPERTIES = ["loud", "hooked", "two_handed", "thrown", "fragile"]

_SHIP_CLASSES = ["skiff", "barge", "lantern_boat", "houseboat"]
_DRIVE_TYPES = ["standard", "oared", "steam", "broken"]
_SHIP_MODULES = ["hold", "galley", "lamp_room", "bunks", "winch"]

# ---------------------------------------------------------------------------
# Character entity type
# ---------------------------------------------------------------------------

_CHARACTER_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="character_name",
        display_name="Character Name",
        field_type=FieldType.STR,
        description="Full name of the character",
        required=True,
    ),
    FieldSpec(
        name="is_player_character",
        display_name="Player Character",
        field_type=FieldType.BOOL,
        default_value=True,
        required=False,
        description="True for PCs, False for NPCs",
    ),
    FieldSpec(
        name="grit",
        display_name="GRIT",
        field_type=FieldType.INT,
        min_value=-3,
        max_value=3,
        default_value=0,
        description="Physical power and durability",
    ),
    FieldSpec(
        name="nerve",
        display_name="NERVE",
        field_type=FieldType.INT,
        min_value=-3,
        max_value=3,
        default_value=0,
        description="Agility and reflexes",
    ),
    FieldSpec(
        name="wits",
        display_name="WITS",
        field_type=FieldType.INT,
        min_value=-3,
        max_value=3,
        default_value=0,
        description="Intuition, wits, and persuasion",
    ),
    FieldSpec(
        name="craft",
        display_name="CRAFT",
        field_type=FieldType.INT,
        min_value=-3,
        max_value=3,
        default_value=0,
        description="Technical skill and repair",
    ),
    # Derived: max_hp = max(1, grit + 6)
    FieldSpec(
        name="max_hp",
        display_name="Max HP",
        field_type=FieldType.INT,
        min_value=1,
        derived_formula="max(1, grit + 6)",
        user_settable=False,
        description="Maximum HP — derived from GRIT: max(1, GRIT + 6)",
    ),
    FieldSpec(
        name="hp",
        display_name="HP",
        field_type=FieldType.INT,
        min_value=0,
        default_value=7,
        description="Current HP (0 = incapacitated)",
    ),
    FieldSpec(
        name="strain",
        display_name="Strain",
        field_type=FieldType.INT,
        min_value=0,
        max_value=10,
        default_value=0,
        description="Corruption level 0-10. Powers unlock at 3, 6, 9.",
    ),
    FieldSpec(
        name="gifts",
        display_name="Gifts",
        field_type=FieldType.LIST_ENUM,
        enum_values=_GIFTS,
        default_value=[],
        required=False,
        description="Powers gained from Strain",
    ),
    FieldSpec(
        name="marks",
        display_name="Marks",
        field_type=FieldType.LIST_STR,
        default_value=[],
        required=False,
        description="Physical corruption marks (free text)",
    ),
    FieldSpec(
        name="origin",
        display_name="Origin",
        field_type=FieldType.ENUM,
        enum_values=_ORIGINS,
        required=False,
        description="Character background before the campaign",
    ),
    FieldSpec(
        name="drive",
        display_name="Drive",
        field_type=FieldType.STR,
        required=False,
        description="Personal motivation",
    ),
    FieldSpec(
        name="skills",
        display_name="Skills",
        field_type=FieldType.LIST_ENUM,
        enum_values=_SKILLS,
        default_value=[],
        required=False,
        description="Known skills — each gives +2 to relevant rolls",
    ),
    FieldSpec(
        name="credits",
        display_name="Credits",
        field_type=FieldType.INT,
        min_value=0,
        default_value=0,
        description="Cash credits carried",
    ),
    FieldSpec(
        name="debt",
        display_name="Debt",
        field_type=FieldType.INT,
        min_value=0,
        default_value=0,
        description="Total debt owed",
    ),
    FieldSpec(
        name="conditions",
        display_name="Conditions",
        field_type=FieldType.LIST_STR,
        default_value=[],
        required=False,
        description="Active conditions, e.g. ['Bleeding']",
    ),
    FieldSpec(
        name="gear_names",
        display_name="Gear",
        field_type=FieldType.LIST_STR,
        default_value=[],
        required=False,
        description="Names of carried items (links to equipment catalog)",
    ),
    FieldSpec(
        name="notes",
        display_name="Notes",
        field_type=FieldType.STR,
        default_value="",
        required=False,
    ),
]

_CHARACTER_VALIDATORS: list[ValidatorSpec] = [
    ValidatorSpec(
        rule_id="gifts_gated_by_strain",
        validator_type=ValidatorType.COUNT_GATE,
        field="gifts",
        other_field="strain",
        divisor=3,
        description="# of gifts ≤ floor(strain / 3)",
        error_message="Too many gifts for current strain",
    ),
]

CHARACTER_TYPE = EntityTypeSpec(
    type_key="character",
    display_name="Character",
    description="A player character or NPC in Lantern Drift",
    fields=_CHARACTER_FIELDS,
    validators=_CHARACTER_VALIDATORS,
    storage_backends=[StorageBackend.POSTGRES, StorageBackend.MONGODB],
)

# ---------------------------------------------------------------------------
# Item entity type
# ---------------------------------------------------------------------------

_ITEM_BASE_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="item_name",
        display_name="Item Name",
        field_type=FieldType.STR,
        description="Name of the item",
    ),
    FieldSpec(
        name="item_type",
        display_name="Item Type",
        field_type=FieldType.ENUM,
        enum_values=["weapon", "armor", "tool", "consumable", "vehicle", "misc", "boat"],
        description="Ontological classification",
    ),
    FieldSpec(
        name="description",
        display_name="Description",
        field_type=FieldType.STR,
        default_value="",
        required=False,
    ),
    FieldSpec(
        name="weight_kg",
        display_name="Weight (kg)",
        field_type=FieldType.FLOAT,
        min_value=0.0,
        required=False,
    ),
    FieldSpec(
        name="value",
        display_name="Value",
        field_type=FieldType.STR,
        required=False,
        description="E.g. '50 credits'",
    ),
    FieldSpec(
        name="source_ref",
        display_name="Source Reference",
        field_type=FieldType.STR,
        required=False,
        description="Book/page citation",
    ),
    FieldSpec(
        name="tags",
        display_name="Tags",
        field_type=FieldType.LIST_STR,
        default_value=[],
        required=False,
    ),
]

_WEAPON_ITEM_TYPE = ItemTypeSpec(
    type_key="weapon",
    display_name="Weapon",
    extra_fields=[
        FieldSpec(
            name="damage_die",
            display_name="Damage Die",
            field_type=FieldType.ENUM,
            enum_values=_DAMAGE_DICE,
            description="Damage die (d2, d4, d6, d8, d10, d12)",
        ),
        FieldSpec(
            name="is_ranged",
            display_name="Ranged",
            field_type=FieldType.BOOL,
            default_value=False,
        ),
        FieldSpec(
            name="range_m",
            display_name="Range (m)",
            field_type=FieldType.INT,
            min_value=0,
            required=False,
            description="Effective range — required for ranged weapons",
        ),
        FieldSpec(
            name="properties",
            display_name="Properties",
            field_type=FieldType.LIST_ENUM,
            enum_values=_WEAPON_PROPERTIES,
            default_value=[],
            required=False,
        ),
    ],
    validators=[
        ValidatorSpec(
            rule_id="ranged_needs_range_m",
            validator_type=ValidatorType.REQUIRES_IF,
            field="range_m",
            other_field="is_ranged",
            description="Ranged weapons must specify range_m",
            error_message="'range_m' is required when 'is_ranged' is True",
        ),
    ],
)

_ARMOR_ITEM_TYPE = ItemTypeSpec(
    type_key="armor",
    display_name="Armor",
    extra_fields=[
        FieldSpec(
            name="protection",
            display_name="Protection",
            field_type=FieldType.INT,
            min_value=0,
            max_value=3,
            description="Damage reduction (0=none, 1=light, 2=medium, 3=heavy)",
        ),
        FieldSpec(
            name="blocks_strain",
            display_name="Blocks Strain",
            field_type=FieldType.BOOL,
            default_value=False,
            description="Some env suits also block Strain exposure",
        ),
    ],
)

_SHIP_ITEM_TYPE = ItemTypeSpec(
    type_key="boat",
    display_name="Boat",
    extra_fields=[
        FieldSpec(
            name="boat_class",
            display_name="Boat Class",
            field_type=FieldType.ENUM,
            enum_values=_SHIP_CLASSES,
        ),
        FieldSpec(
            name="plank_points",
            display_name="Plank Points",
            field_type=FieldType.INT,
            min_value=0,
        ),
        FieldSpec(
            name="max_plank_points",
            display_name="Max Plank Points",
            field_type=FieldType.INT,
            min_value=1,
        ),
        FieldSpec(
            name="crew_capacity",
            display_name="Crew Capacity",
            field_type=FieldType.INT,
            min_value=1,
        ),
        FieldSpec(
            name="drive_type",
            display_name="Drive Type",
            field_type=FieldType.ENUM,
            enum_values=_DRIVE_TYPES,
            default_value="standard",
        ),
        FieldSpec(
            name="drive_condition",
            display_name="Drive Condition",
            field_type=FieldType.INT,
            min_value=0,
            max_value=6,
            default_value=6,
            description="Drive integrity 0-6 (6=fully functional, 0=destroyed)",
        ),
        FieldSpec(
            name="modules",
            display_name="Modules",
            field_type=FieldType.LIST_ENUM,
            enum_values=_SHIP_MODULES,
            default_value=[],
            required=False,
        ),
        FieldSpec(
            name="cargo_units",
            display_name="Cargo Units",
            field_type=FieldType.INT,
            min_value=0,
            default_value=0,
        ),
        FieldSpec(
            name="credits_debt",
            display_name="Credits Debt",
            field_type=FieldType.INT,
            min_value=0,
            default_value=0,
        ),
    ],
)

ITEM_TYPE = EntityTypeSpec(
    type_key="item",
    display_name="Item",
    description="Equipment, weapons, armor, boats, and other items",
    fields=_ITEM_BASE_FIELDS,
    validators=[],
    item_types={
        "weapon": _WEAPON_ITEM_TYPE,
        "armor": _ARMOR_ITEM_TYPE,
        "boat": _SHIP_ITEM_TYPE,
    },
    storage_backends=[StorageBackend.POSTGRES],
)

# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------

_RELATIONS: list[RelationSpec] = [
    RelationSpec(
        relation_id="character_crews_boat",
        display_name="Crews Boat",
        from_type="character",
        to_type="item",
        cardinality=RelationCardinality.MANY_TO_MANY,
        description="Characters can crew boats (via party_inventories join)",
    ),
]

# ---------------------------------------------------------------------------
# Data edges — cross-store references
# ---------------------------------------------------------------------------

_DATA_EDGES: list[DataEdgeSpec] = [
    DataEdgeSpec(
        edge_id="ld_char_sheet_to_neo4j_entity",
        description="Character sheet (PostgreSQL) links to canonical entity in Neo4j",
        from_backend=StorageBackend.POSTGRES,
        from_collection="character_sheet_index",
        from_field="entity_id",
        to_backend=StorageBackend.NEO4J,
        to_collection="EntityInstance",
        to_field="id",
        is_enforced=False,
        notes="Soft reference — no FK across backends",
    ),
    DataEdgeSpec(
        edge_id="ld_char_working_state_to_sheet",
        description="In-scene working state (MongoDB) references the character entity",
        from_backend=StorageBackend.MONGODB,
        from_collection="character_working_state",
        from_field="entity_id",
        to_backend=StorageBackend.POSTGRES,
        to_collection="character_sheet_index",
        to_field="entity_id",
        is_enforced=False,
        notes="Ephemeral in-scene state; not canonical",
    ),
    DataEdgeSpec(
        edge_id="ld_memory_to_entity",
        description="Character memory (MongoDB) references entity in Neo4j",
        from_backend=StorageBackend.MONGODB,
        from_collection="memories",
        from_field="entity_id",
        to_backend=StorageBackend.NEO4J,
        to_collection="EntityInstance",
        to_field="id",
        is_enforced=False,
    ),
    DataEdgeSpec(
        edge_id="ld_game_system_to_source_doc",
        description="Game system record in MongoDB points to the source PDF in MinIO",
        from_backend=StorageBackend.MONGODB,
        from_collection="game_systems",
        from_field="source_document_id",
        to_backend=StorageBackend.MINIO,
        to_collection="monitor/uploads",
        to_field="doc_id",
        is_enforced=False,
    ),
]

# ---------------------------------------------------------------------------
# Core mechanic
# ---------------------------------------------------------------------------

_CORE_MECHANIC = CoreMechanicSpec(
    mechanic_type=OntologyMechanicType.D20_UNDER,
    dice_notation="d20",
    roll_vs="attribute score",
    success_condition="roll ≤ attribute (lower roll = better outcome)",
    critical_rule="1 = critical success; 20 = critical failure (fumble)",
    description=(
        "Roll a d20. If the result is equal to or less than the relevant attribute "
        "(-3 to +3), the action succeeds. A natural 1 is always critical success. "
        "A natural 20 is always a fumble."
    ),
)

# ---------------------------------------------------------------------------
# The spec
# ---------------------------------------------------------------------------

LANTERN_DRIFT: GameSystemSpec = GameSystemSpec(
    system_id="lantern_drift",
    system_name="Lantern Drift",
    version="1.0",
    description="An invented game for tests: lamp-boat crews on a flooded city's canals.",
    publisher=None,
    tags=["invented", "test-fixture"],
    core_mechanic=_CORE_MECHANIC,
    entity_types={
        "character": CHARACTER_TYPE,
        "item": ITEM_TYPE,
    },
    relations=_RELATIONS,
    data_edges=_DATA_EDGES,
)
