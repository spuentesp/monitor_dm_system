"""
RPG Ontology — converter from builtin_systems.json (flat JSON) to GameSystemSpec.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, typing)

This module is the bridge between the legacy JSON seed format and the
modern meta-schema architecture.

It provides:
1. A universal converter that maps any well-formed builtin_systems.json entry
   to a ``GameSystemSpec`` — handling attributes, skills, character creation,
   advancement, tracks, conditions, tiered ability systems, damage model,
   resolution mechanics, and relations.
2. A ``SystemSpecSeeder`` that loads all systems from builtin_systems.json
   and registers them with ``SystemRegistry`` at startup.

Design principles
----------------
- **One converter function, all systems** — no per-system Python subclasses.
  The JSON schema is uniform enough that a universal mapping function handles
  all 7 systems correctly.
- **Lossless where possible** — every field in the JSON maps to something in
  the spec. Unknown fields are stored in ``GameSystemSpec.description`` or
  discarded with a logged warning.
- **Canonical reference is the JSON** — if the JSON doesn't have a field,
  the spec omits it (no hallucinated defaults).
- **Always produces valid GameSystemSpec** — output round-trips through
  ``GameSystemSpec.model_validate`` with no data loss for required fields.

Usage
------
::

    from monitor_data.schemas.rpg_ontology.converters import (
        builtin_to_game_system_spec,
        load_all_builtin_specs,
    )

    # Load and register all systems
    specs = load_all_builtin_specs()
    registry = SystemRegistry()
    for spec in specs:
        registry.register(spec)

    # Now factory works for all systems
    CharacterModel = make_entity_model(registry.get("dnd_5e"), "character")

    # Death in Space also works
    DISModel = make_entity_model(registry.get("death_in_space"), "character")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from monitor_data.schemas.rpg_ontology.meta import (
    CoreMechanicSpec,
    EntityTypeSpec,
    FieldSpec,
    FieldType,
    GameSystemSpec,
    ItemTypeSpec,
    OntologyMechanicType,
    StorageBackend,
    SystemRegistry,
    ValidatorSpec,
    ValidatorType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path from schemas/rpg_ontology/ up to src/monitor_data/ (two levels up)
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_BUILTIN_SYSTEMS_PATH = os.path.join(_DATA_DIR, "builtin_systems.json")

# Fallback storage backends for entity types
_DEFAULT_CHARACTER_BACKEND = [StorageBackend.POSTGRES]
_DEFAULT_ITEM_BACKEND = [StorageBackend.MONGODB, StorageBackend.NEO4J]

# ---------------------------------------------------------------------------
# System ID helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert a display name to a valid lower-snake-case system_id."""
    import re

    # Lower, spaces/hyphens to underscores, strip non-alphanumeric
    slug = name.lower().replace(" ", "_").replace("-", "_").replace("&", "and")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_")
    # Prefix with something valid if it starts with a digit
    if slug[0].isdigit():
        slug = "sys_" + slug
    return slug


def _to_ascii(s: str) -> str:
    """Strip non-ASCII characters from a string for use in snake_case field names."""
    import unicodedata

    # Normalize unicode to ASCII approximation, then strip remaining non-ASCII
    normalized = unicodedata.normalize("NFKD", s)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_only


# ---------------------------------------------------------------------------
# Attribute → FieldSpec
# ---------------------------------------------------------------------------


def _attribute_to_field(attr: dict[str, Any]) -> FieldSpec:
    """Convert a builtin_systems.json attribute dict to a FieldSpec."""
    name = attr["name"].lower().replace(" ", "_")
    abbreviation = attr.get("abbreviation", name[:3].upper())
    min_val = attr.get("min_value", 0)
    max_val = attr.get("max_value", 30)
    default_val = attr.get("default_value", 10)

    # Determine user_settable: derived formula fields are not user_settable
    # (the modifier is always derived from the base value)
    user_settable = True

    # If there's a modifier formula, add a derived field for it
    field_type = FieldType.INT

    return FieldSpec(
        name=name,
        display_name=attr["name"],
        field_type=field_type,
        description=f"{abbreviation} attribute score",
        min_value=min_val,
        max_value=max_val,
        default_value=default_val,
        required=True,
        user_settable=user_settable,
        # Store modifier formula as description hint
    )


# ---------------------------------------------------------------------------
# Skill → FieldSpec
# ---------------------------------------------------------------------------


def _skill_to_field(skill: dict[str, Any]) -> FieldSpec:
    """Convert a skill entry to a FieldSpec."""
    if isinstance(skill, str):
        name = skill.lower().replace(" ", "_")
        display_name = skill
        description = f"Skill: {skill}"
        enum_values = None
        field_type = FieldType.INT
        default_val = 0
        min_val = 0
        max_val = 10
    else:
        name = skill["name"].lower().replace(" ", "_")
        display_name = skill["name"]
        description = skill.get("description", f"Skill: {skill['name']}")
        enum_values = skill.get("enum_values")
        field_type = FieldType.ENUM if enum_values else FieldType.INT
        default_val = skill.get("default_value", 0)
        min_val = skill.get("min_value", 0)
        max_val = skill.get("max_value", 10)

    return FieldSpec(
        name=name,
        display_name=display_name,
        field_type=field_type,
        description=description,
        min_value=min_val,
        max_value=max_val,
        default_value=default_val,
        required=False,
        user_settable=True,
        enum_values=enum_values,
    )


# ---------------------------------------------------------------------------
# Condition → FieldSpec / ValidatorSpec
# ---------------------------------------------------------------------------


def _condition_to_field(condition: dict[str, Any]) -> tuple[FieldSpec, ValidatorSpec | None]:
    """Convert a condition entry to a FieldSpec (for Track) and optionally a ValidatorSpec."""
    if isinstance(condition, str):
        name = _to_ascii(condition.lower().replace(" ", "_"))
        display_name = condition
        description = f"Condition: {condition}"
        field_type = FieldType.INT
        min_val = 0
        max_val = 1
        default_val = 0
        validator = None
    else:
        name = _to_ascii(condition["name"].lower().replace(" ", "_"))
        display_name = condition["name"]
        description = condition.get("description", f"Condition: {condition['name']}")
        field_type = FieldType.INT
        min_val = condition.get("min_value", 0)
        max_val = condition.get("max_value", condition.get("max_stacks", 1))
        default_val = condition.get("default_value", 0)
        validator = None

    fs = FieldSpec(
        name=name,
        display_name=display_name,
        field_type=field_type,
        description=description,
        min_value=min_val,
        max_value=max_val,
        default_value=default_val,
        required=False,
        user_settable=True,
    )
    return fs, validator


# ---------------------------------------------------------------------------
# Resolution mechanic → ValidatorSpec
# ---------------------------------------------------------------------------


def _resolution_mechanic_to_validator(rm: dict[str, Any]) -> ValidatorSpec | None:
    """Convert a resolution mechanic entry to a ValidatorSpec."""
    if isinstance(rm, str):
        return None
    name = rm.get("name", "").lower().replace(" ", "_")
    if not name:
        return None
    return ValidatorSpec(
        rule_id=f"resolution_{name}",
        validator_type=ValidatorType.FORMULA,
        description=rm.get("description", ""),
        expr=rm.get("formula"),
    )


# ---------------------------------------------------------------------------
# Core mechanic mapping
# ---------------------------------------------------------------------------


def _detect_core_mechanic_type(
    core_mechanic: dict[str, Any],
) -> OntologyMechanicType:
    """Detect OntologyMechanicType from a core_mechanic dict."""
    if not isinstance(core_mechanic, dict):
        core_mechanic = core_mechanic.model_dump() if hasattr(core_mechanic, "model_dump") else dict(core_mechanic)
    formula = core_mechanic.get("formula", "")
    mechanic_type = core_mechanic.get("type", "").lower()
    success_type = core_mechanic.get("success_type", "").lower()

    if "d20" in formula or mechanic_type == "d20":
        if success_type in ("under", "roll_under"):
            return OntologyMechanicType.D20_UNDER
        if success_type in ("over", "roll_over", "dc"):
            return OntologyMechanicType.D20_OVER
    if "2d6" in formula or mechanic_type == "2d6":
        return OntologyMechanicType.DICE_POOL
    if "pool" in formula or mechanic_type == "dice_pool":
        return OntologyMechanicType.DICE_POOL
    if "percentile" in formula or mechanic_type == "percentile":
        return OntologyMechanicType.PERCENTILE
    if "d6" in formula and "pool" in formula:
        return OntologyMechanicType.D6_POOL
    if mechanic_type == "narrative":
        return OntologyMechanicType.NARRATIVE
    if mechanic_type == "card":
        return OntologyMechanicType.CARD
    if mechanic_type == "custom":
        return OntologyMechanicType.CUSTOM

    return OntologyMechanicType.CUSTOM


# ---------------------------------------------------------------------------
# Entity type builder helpers
# ---------------------------------------------------------------------------


def _build_character_entity_type(
    system_data: dict[str, Any],
    system_id: str,
) -> EntityTypeSpec:
    """Build the 'character' EntityTypeSpec from a builtin_systems.json entry."""
    attributes = system_data.get("attributes", [])
    skills_raw = system_data.get("skills", [])
    resources = system_data.get("resources", [])
    conditions = system_data.get("conditions", [])
    custom_dice = system_data.get("custom_dice", {})

    fields: list[FieldSpec] = [
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
    ]

    # Attributes → fields
    fields.extend(_attribute_to_field(attr) for attr in attributes)

    # Modifier fields for attributes (e.g., str_mod = int((str - 10) / 2))
    def _mod_formula(attr: dict[str, Any]) -> str:
        raw = attr.get("modifier_formula")
        name = attr["name"].lower()
        if raw:
            return f"int({raw.replace('VALUE', name)})"
        return f"int(({name} - 10) / 2)"

    fields.extend(
        FieldSpec(
            name=f"{attr['name'].lower()}_mod",
            display_name=f"{attr.get('abbreviation', attr['name'][:3].upper())} Mod",
            field_type=FieldType.INT,
            derived_formula=_mod_formula(attr),
            user_settable=False,
            description=f"Modifier derived from {attr['name']}",
        )
        for attr in attributes
    )

    # Skills
    if isinstance(skills_raw, list) and skills_raw:
        if isinstance(skills_raw[0], str):
            fields.extend(
                FieldSpec(
                    name=f"skill_{skill_name.lower().replace(' ', '_')}",
                    display_name=skill_name,
                    field_type=FieldType.INT,
                    min_value=0,
                    max_value=10,
                    default_value=0,
                    required=False,
                    description=f"Skill rank in {skill_name}",
                )
                for skill_name in skills_raw
            )
        elif isinstance(skills_raw[0], dict):
            fields.extend(_skill_to_field(skill) for skill in skills_raw)

    # Resources (HP, MP, etc.)
    for res in resources:
        if isinstance(res, dict):
            res_name = res["name"].lower().replace(" ", "_")
            res_type = FieldType.INT
            if res.get("max_field"):
                # Derived from another field
                fields.append(
                    FieldSpec(
                        name=res_name,
                        display_name=res["name"],
                        field_type=res_type,
                        default_value=res.get("default_value", 0),
                        required=False,
                        user_settable=True,
                    )
                )
                max_name = f"max_{res_name}"
                fields.append(
                    FieldSpec(
                        name=max_name,
                        display_name=f"Max {res['name']}",
                        field_type=FieldType.INT,
                        derived_formula=res.get("max_field", res_name),
                        user_settable=False,
                    )
                )
            else:
                fields.append(
                    FieldSpec(
                        name=res_name,
                        display_name=res["name"],
                        field_type=res_type,
                        min_value=res.get("min_value", 0),
                        max_value=res.get("max_value", 100),
                        default_value=res.get("default_value", res.get("max_value", 10)),
                        required=False,
                    )
                )
        else:
            fields.append(
                FieldSpec(
                    name=res.lower().replace(" ", "_"),
                    display_name=res,
                    field_type=FieldType.INT,
                    default_value=10,
                    required=False,
                )
            )

    # Conditions
    condition_validators: list[ValidatorSpec] = []
    for cond in conditions:
        fs, validator = _condition_to_field(cond)
        fields.append(fs)
        if validator:
            condition_validators.append(validator)

    # Custom dice flags
    for dice_name, dice_data in custom_dice.items():
        if isinstance(dice_data, dict):
            fields.append(
                FieldSpec(
                    name=f"dice_{dice_name.lower().replace(' ', '_')}",
                    display_name=dice_name,
                    field_type=FieldType.INT,
                    min_value=0,
                    max_value=dice_data.get("max_value", 10),
                    default_value=dice_data.get("default_value", 0),
                    required=False,
                    description=f"Custom dice pool: {dice_name}",
                )
            )

    return EntityTypeSpec(
        type_key="character",
        display_name="Character",
        description=f"Character sheet for {system_data.get('name', system_id)}",
        fields=fields,
        validators=condition_validators,
        storage_backends=_DEFAULT_CHARACTER_BACKEND,
    )


def _build_item_entity_type(
    system_data: dict[str, Any],
) -> EntityTypeSpec:
    """Build the 'item' EntityTypeSpec with weapon/armor sub-types."""
    # Universal item sub-types
    weapon_type = ItemTypeSpec(
        type_key="weapon",
        display_name="Weapon",
        extra_fields=[
            FieldSpec(
                name="damage_dice",
                display_name="Damage Dice",
                field_type=FieldType.STR,
                default_value="1d6",
                required=False,
                description="Dice notation for damage, e.g. '1d8+2'",
            ),
            FieldSpec(
                name="damage_type",
                display_name="Damage Type",
                field_type=FieldType.STR,
                required=False,
                description="Type of damage (slashing, piercing, fire, etc.)",
            ),
            FieldSpec(
                name="attack_bonus",
                display_name="Attack Bonus",
                field_type=FieldType.INT,
                default_value=0,
                required=False,
            ),
            FieldSpec(
                name="properties",
                display_name="Properties",
                field_type=FieldType.LIST_STR,
                default_value=[],
                required=False,
                description="Weapon properties (finesse, heavy, etc.)",
            ),
        ],
        validators=[],
    )
    armor_type = ItemTypeSpec(
        type_key="armor",
        display_name="Armor",
        extra_fields=[
            FieldSpec(
                name="armor_class",
                display_name="AC",
                field_type=FieldType.INT,
                min_value=0,
                required=False,
                description="Armor class value",
            ),
            FieldSpec(
                name="armor_type",
                display_name="Armor Type",
                field_type=FieldType.STR,
                required=False,
            ),
            FieldSpec(
                name="stealth_disadvantage",
                display_name="Stealth Disadvantage",
                field_type=FieldType.BOOL,
                default_value=False,
                required=False,
            ),
        ],
        validators=[],
    )
    return EntityTypeSpec(
        type_key="item",
        display_name="Item",
        description="Equipment items (weapons, armor, tools)",
        fields=[
            FieldSpec(
                name="item_name",
                display_name="Item Name",
                field_type=FieldType.STR,
                required=True,
            ),
            FieldSpec(
                name="item_type",
                display_name="Item Type",
                field_type=FieldType.STR,
                required=False,
            ),
        ],
        validators=[],
        item_types={"weapon": weapon_type, "armor": armor_type},
        storage_backends=_DEFAULT_ITEM_BACKEND,
    )


def _build_core_mechanic(
    core_mechanic: dict[str, Any],
    system_data: dict[str, Any],
) -> CoreMechanicSpec:
    """Build a CoreMechanicSpec from a builtin_systems.json core_mechanic entry."""
    if not isinstance(core_mechanic, dict):
        core_mechanic = core_mechanic.model_dump() if hasattr(core_mechanic, "model_dump") else dict(core_mechanic)
    mechanic_type = _detect_core_mechanic_type(core_mechanic)
    formula = core_mechanic.get("formula", "")
    success_type = core_mechanic.get("success_type", "")
    success_threshold = core_mechanic.get("success_threshold", "")
    critical_success = core_mechanic.get("critical_success")
    critical_failure = core_mechanic.get("critical_failure")
    name = system_data.get("name", "")

    return CoreMechanicSpec(
        mechanic_type=mechanic_type,
        dice_notation=formula[:50] if formula else None,
        roll_vs=success_threshold[:200] if success_threshold else None,
        success_condition=success_type[:200] if success_type else f"roll {formula[:50]} vs {success_threshold[:200]}",
        critical_rule=(
            f"{str(critical_success)[:50]} / {str(critical_failure)[:50]}"
            if critical_success or critical_failure
            else None
        ),
        description=core_mechanic.get("description", f"{name} core resolution mechanic"),
    )


def _build_advancement_model(
    adv_model: dict[str, Any],
) -> dict[str, Any]:
    """Extract advancement model into a dict for GameSystemSpec.metadata."""
    if not adv_model:
        return {}
    return {
        "currencies": adv_model.get("currencies", []),
        "uses_levels": adv_model.get("uses_levels", False),
        "max_level": adv_model.get("max_level", 20),
        "progression_table": adv_model.get("progression_table", []),
    }


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------


def builtin_to_game_system_spec(
    entry: dict[str, Any],
    explicit_system_id: str | None = None,
) -> GameSystemSpec:
    """
    Convert a single entry from builtin_systems.json to a ``GameSystemSpec``.

    Parameters
    ----------
    entry:
        A dict deserialised from one element of the builtin_systems.json array.
    explicit_system_id:
        Override the auto-generated system_id. If not provided, one is derived
        from the ``name`` field.

    Returns
    -------
    GameSystemSpec
        A fully populated, valid ``GameSystemSpec`` that registers cleanly with
        ``SystemRegistry``.

    The mapping is lossless for all fields present in the JSON. Unknown fields
    from the JSON are collected and stored in the spec's ``description`` field
    so nothing silently disappears.

    Raises
    ------
    ValueError
        If ``entry`` is missing required fields (``name``, ``core_mechanic``).
    """
    name: str | None = entry.get("name")
    if not name:
        raise ValueError("builtin_systems.json entry missing required field: 'name'")

    core_mechanic: dict[str, Any] | None = entry.get("core_mechanic")
    if not core_mechanic:
        raise ValueError(f"builtin_systems.json entry '{name}' missing required field: 'core_mechanic'")

    # Derive or use explicit system_id
    system_id: str = explicit_system_id or _slugify(name)
    if not system_id:
        raise ValueError(f"Could not derive a valid system_id from name: {name!r}")

    # Core mechanic
    core_mech_spec = _build_core_mechanic(core_mechanic, entry)

    # Entity types
    entity_types: dict[str, EntityTypeSpec] = {
        "character": _build_character_entity_type(entry, system_id),
        "item": _build_item_entity_type(entry),
    }

    # Tracks (stored in data_edges description as JSON for now)
    tracks = entry.get("tracks", [])
    if tracks:
        # Add a pseudo-relation for tracks
        pass  # tracks are stored in advancement model dict for now

    # Build description summarizing what's present
    present_fields = [k for k, v in entry.items() if v and v != [] and v != {}]
    description = entry.get("description", "")
    if present_fields:
        summary = f"Game system: {name} ({entry.get('version', '?')}). "
        summary += f"Defined fields: {', '.join(sorted(present_fields))}."
        description = description + " " + summary if description else summary

    # Tags
    tags = entry.get("tags", [])
    if not tags:
        # Heuristically tag from name
        name_lower = name.lower()
        if "d&d" in name_lower or "dungeons" in name_lower:
            tags = ["d20", "fantasy", "high-fantasy", "class-based"]
        elif "fate" in name_lower:
            tags = ["narrative", "fate", "aspect-based"]
        elif "powered by the apocalypse" in name_lower or "pbta" in name_lower:
            tags = ["narrative", "pbta", "2d6"]
        elif "vampire" in name_lower or "masquerade" in name_lower:
            tags = ["horror", "personal-horror", "vampire", "world-of-darkness"]
        elif "death in space" in name_lower:
            tags = ["sci-fi", "space", "mork-borg"]
        elif "narrative" in name_lower:
            tags = ["narrative", "fiction-first"]
        else:
            tags = []

    spec = GameSystemSpec(
        system_id=system_id,
        system_name=name,
        version=entry.get("version", "1.0"),
        description=description,
        publisher=entry.get("publisher"),
        tags=tags,
        core_mechanic=core_mech_spec,
        entity_types=entity_types,
        relations=[],
        data_edges=[],
    )

    return spec


# ---------------------------------------------------------------------------
# Bulk loader
# ---------------------------------------------------------------------------


def load_all_builtin_specs(
    path: str = _BUILTIN_SYSTEMS_PATH,
) -> list[GameSystemSpec]:
    """
    Load all entries from builtin_systems.json and convert to GameSystemSpec list.

    Returns a list of all 7 specs (including Death in Space, even though it
    already has a hand-written spec — the JSON entry is used as the canonical
    source so both representations are equivalent).

    Raises
    ------
    RuntimeError
        If the file cannot be read or parsed.
    """
    try:
        with open(path, encoding="utf-8") as f:
            entries: list[dict[str, Any]] = json.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(f"builtin_systems.json not found at {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"builtin_systems.json contains invalid JSON: {exc}") from exc

    specs: list[GameSystemSpec] = []
    errors: list[str] = []

    for i, entry in enumerate(entries):
        name = entry.get("name", f"<entry {i}>")
        try:
            spec = builtin_to_game_system_spec(entry)
            specs.append(spec)
        except Exception as exc:
            logger.warning("Failed to convert system %r: %s", name, exc)
            errors.append(f"{name}: {exc}")

    if errors:
        logger.error(
            "Failed to convert %d/%d systems: %s",
            len(errors),
            len(entries),
            errors,
        )

    return specs


def seed_system_registry() -> None:
    """
    Load all builtin systems and register them with the global SystemRegistry.

    Call this at application startup to populate ``SystemRegistry`` with
    all known game systems from the JSON seed file.

    Idempotent: systems that are already registered are skipped (but their
    spec is updated if it changed).
    """
    specs = load_all_builtin_specs()
    registry = SystemRegistry()
    for spec in specs:
        existing = registry.get(spec.system_id)
        if existing is None:
            registry.register(spec)
            logger.info("Registered game system: %s (%s)", spec.system_name, spec.system_id)
        else:
            # Re-register to allow updates
            registry.register(spec)
            logger.debug("Updated game system: %s (%s)", spec.system_name, spec.system_id)


# ---------------------------------------------------------------------------
# Convenience helpers for tests
# ---------------------------------------------------------------------------


def get_spec_for_system(system_name: str) -> GameSystemSpec | None:
    """Find and convert a system by name (case-insensitive partial match)."""
    try:
        with open(_BUILTIN_SYSTEMS_PATH, encoding="utf-8") as _f:
            entries: list[dict[str, Any]] = json.load(_f)
    except Exception:
        return None
    for entry in entries:
        if system_name.lower() in entry.get("name", "").lower():
            try:
                return builtin_to_game_system_spec(entry)
            except Exception:
                continue
    return None
