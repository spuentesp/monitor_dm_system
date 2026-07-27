"""
RPG Ontology MCP tools — typed game-mechanical CRUD for MONITOR.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries + monitor_data (schemas, db.postgres)
CALLED BY: monitor_agents (via MCP tool dispatcher)

These tools replace the old pattern of:
  - Storing character stats as ``properties: Dict[str, Any]`` in MongoDB
  - Having no schema validation for game-specific entity data

The new pattern:
  - Game system schemas registered in PostgreSQL ``game_system_schemas``
  - Character sheets stored as validated JSONB in ``character_sheet_index``
  - Equipment stored as typed rows in ``equipment_catalog``
  - Pydantic validation enforced on every write (HP = BODY + 6, etc.)

Tool naming
-----------
All public coroutines in this module are registered as MCP tools.
Names follow the convention:  ``rpg_<entity>_<action>``

Exposed tools
-------------
  rpg_system_register      Register a game system schema
  rpg_system_get           Get a registered system definition
  rpg_system_list          List all registered systems
  rpg_character_create     Create a typed character sheet
  rpg_character_get        Retrieve a character sheet (parsed + validated)
  rpg_character_update     Update character sheet fields (validated)
  rpg_character_delete     Delete a character sheet
  rpg_character_list       List character sheets for a world/system
  rpg_equipment_add        Add item to catalog
  rpg_equipment_get        Get item by ID
  rpg_equipment_list       List catalog for a world/system/type
  rpg_sheet_equip          Link equipment item to a character
  rpg_sheet_unequip        Unlink equipment from a character
  rpg_validate_sheet       Validate raw dict against a system's schema
  rpg_schema_inspect       Inspect a game system's full schema definition
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.rpg_ontology import (
    BaseGameSystem,
    EquipmentItemCreate,
    EquipmentItemResponse,
    GameSystemRegistry,
    ItemType,
    SystemRegistry,
    TypedCharacterSheetCreate,
    TypedCharacterSheetResponse,
    TypedCharacterSheetUpdate,
)

# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _registry() -> GameSystemRegistry:
    """Return the global singleton registry (populated at import time)."""
    return GameSystemRegistry()


def _spec_registry() -> SystemRegistry:
    """Return the new meta-schema registry (GameSystemSpec objects)."""
    return SystemRegistry()


# ---------------------------------------------------------------------------
# Game system registration
# ---------------------------------------------------------------------------


async def rpg_system_register(
    client: PostgresClient,
    system: BaseGameSystem,
) -> dict[str, Any]:
    """
    Register a game system definition in PostgreSQL.

    If a system with the same ``system_id`` already exists the row is
    updated (upsert).  The in-memory registry should already have the system
    registered (done at module import by the system module).

    Returns the stored row as a dict.
    """
    pool = await client._get_pool()
    attrs_json = json.dumps([a.model_dump() for a in system.attributes])
    res_json = json.dumps([r.model_dump() for r in system.resources])

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO game_system_schemas
                (system_id, system_name, version, description, publisher,
                 core_mechanic, attributes, resources, schema_class, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9, now())
            ON CONFLICT (system_id) DO UPDATE SET
                system_name  = EXCLUDED.system_name,
                version      = EXCLUDED.version,
                description  = EXCLUDED.description,
                publisher    = EXCLUDED.publisher,
                core_mechanic = EXCLUDED.core_mechanic,
                attributes   = EXCLUDED.attributes,
                resources    = EXCLUDED.resources,
                schema_class = EXCLUDED.schema_class,
                updated_at   = now()
            RETURNING *
            """,
            system.system_id,
            system.system_name,
            system.version,
            system.description,
            system.publisher,
            system.core_mechanic_formula,
            attrs_json,
            res_json,
            system.schema_class,
        )
    return dict(row)


async def rpg_system_get(
    client: PostgresClient,
    system_id: str,
) -> dict[str, Any] | None:
    """Retrieve a registered game system definition by ID."""
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM game_system_schemas WHERE system_id = $1", system_id)
    return dict(row) if row else None


async def rpg_system_list(
    client: PostgresClient,
) -> list[dict[str, Any]]:
    """List all registered game systems."""
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM game_system_schemas ORDER BY system_name")
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Character sheet CRUD
# ---------------------------------------------------------------------------


async def rpg_character_create(
    client: PostgresClient,
    request: TypedCharacterSheetCreate,
) -> TypedCharacterSheetResponse:
    """
    Create a typed character sheet in PostgreSQL.

    Validates ``sheet_data`` against the system's Pydantic schema BEFORE
    writing to the database.  Raises ``ValidationError`` on schema violation.

    The caller must ensure:
    - ``world_id`` exists in the ``worlds`` table
    - ``system_id`` is registered in ``game_system_schemas``
    - ``entity_id`` is an existing Neo4j EntityInstance UUID
    """
    # Validate against the registered Pydantic schema
    registry = _registry()
    parsed_sheet = registry.parse_sheet(request.system_id, request.sheet_data)
    validated_data = parsed_sheet.model_dump(mode="json")

    pool = await client._get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO character_sheet_index
                (world_id, entity_id, system_id, character_name,
                 is_player_character, sheet_data, created_at)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb, now())
            RETURNING *
            """,
            request.world_id,
            str(request.entity_id),
            request.system_id,
            validated_data["character_name"],
            validated_data.get("is_player_character", True),
            json.dumps(validated_data),
        )

    return TypedCharacterSheetResponse(
        id=row["id"],
        world_id=row["world_id"],
        entity_id=UUID(row["entity_id"]),
        system_id=row["system_id"],
        character_name=row["character_name"],
        sheet_data=dict(row["sheet_data"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def rpg_character_get(
    client: PostgresClient,
    sheet_id: UUID,
) -> TypedCharacterSheetResponse | None:
    """Retrieve a character sheet by its UUID."""
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM character_sheet_index WHERE id = $1", sheet_id)
    if row is None:
        return None
    return TypedCharacterSheetResponse(
        id=row["id"],
        world_id=row["world_id"],
        entity_id=UUID(row["entity_id"]),
        system_id=row["system_id"],
        character_name=row["character_name"],
        sheet_data=dict(row["sheet_data"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def rpg_character_get_by_entity(
    client: PostgresClient,
    entity_id: UUID,
    world_id: str,
) -> TypedCharacterSheetResponse | None:
    """Retrieve a character sheet by Neo4j entity_id + world_id pair."""
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM character_sheet_index
            WHERE entity_id = $1 AND world_id = $2
            """,
            str(entity_id),
            world_id,
        )
    if row is None:
        return None
    return TypedCharacterSheetResponse(
        id=row["id"],
        world_id=row["world_id"],
        entity_id=UUID(row["entity_id"]),
        system_id=row["system_id"],
        character_name=row["character_name"],
        sheet_data=dict(row["sheet_data"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def rpg_character_update(
    client: PostgresClient,
    sheet_id: UUID,
    update: TypedCharacterSheetUpdate,
) -> TypedCharacterSheetResponse | None:
    """
    Update a character sheet with validated partial data.

    The existing sheet_data is merged with the incoming dict, then the
    merged result is re-validated against the schema.  This ensures the
    sheet remains internally consistent after every update (e.g. HP ≤ max_hp).
    """
    # Fetch current sheet
    current = await rpg_character_get(client, sheet_id)
    if current is None:
        return None

    # Merge and revalidate
    merged = {**current.sheet_data, **update.sheet_data}
    registry = _registry()
    parsed = registry.parse_sheet(current.system_id, merged)
    validated = parsed.model_dump(mode="json")

    pool = await client._get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE character_sheet_index
            SET sheet_data    = $1::jsonb,
                character_name = $2,
                updated_at    = now()
            WHERE id = $3
            RETURNING *
            """,
            json.dumps(validated),
            validated["character_name"],
            sheet_id,
        )

    if row is None:
        return None
    return TypedCharacterSheetResponse(
        id=row["id"],
        world_id=row["world_id"],
        entity_id=UUID(row["entity_id"]),
        system_id=row["system_id"],
        character_name=row["character_name"],
        sheet_data=dict(row["sheet_data"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def rpg_character_delete(
    client: PostgresClient,
    sheet_id: UUID,
) -> bool:
    """Delete a character sheet. Returns True if a row was deleted."""
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM character_sheet_index WHERE id = $1", sheet_id)
    return bool(result.split()[-1] != "0")


async def rpg_character_list(
    client: PostgresClient,
    world_id: str | None = None,
    system_id: str | None = None,
    is_player_character: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TypedCharacterSheetResponse]:
    """List character sheets with optional filters."""
    conditions = []
    params: list[Any] = []
    idx = 1

    if world_id is not None:
        conditions.append(f"world_id = ${idx}")
        params.append(world_id)
        idx += 1
    if system_id is not None:
        conditions.append(f"system_id = ${idx}")
        params.append(system_id)
        idx += 1
    if is_player_character is not None:
        conditions.append(f"is_player_character = ${idx}")
        params.append(is_player_character)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.extend([limit, offset])

    pool = await client._get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT * FROM character_sheet_index
            {where}
            ORDER BY character_name
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
        )

    return [
        TypedCharacterSheetResponse(
            id=r["id"],
            world_id=r["world_id"],
            entity_id=UUID(r["entity_id"]),
            system_id=r["system_id"],
            character_name=r["character_name"],
            sheet_data=dict(r["sheet_data"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Equipment catalog
# ---------------------------------------------------------------------------


async def rpg_equipment_add(
    client: PostgresClient,
    request: EquipmentItemCreate,
) -> EquipmentItemResponse:
    """
    Add an item to the equipment catalog.

    ``item_data`` is stored as-is (JSONB).  Callers should pre-validate with
    the appropriate system item model (e.g. DISWeapon) before calling this.
    """
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO equipment_catalog
                (world_id, system_id, item_name, item_type, item_data, source_ref, created_at)
            VALUES ($1,$2,$3,$4,$5::jsonb,$6, now())
            ON CONFLICT (system_id, item_name, world_id) DO UPDATE SET
                item_type  = EXCLUDED.item_type,
                item_data  = EXCLUDED.item_data,
                source_ref = EXCLUDED.source_ref
            RETURNING *
            """,
            request.world_id,
            request.system_id,
            request.item_name,
            request.item_type.value,
            json.dumps(request.item_data),
            request.source_ref,
        )
    return EquipmentItemResponse(
        id=row["id"],
        world_id=row["world_id"],
        system_id=row["system_id"],
        item_name=row["item_name"],
        item_type=ItemType(row["item_type"]),
        item_data=dict(row["item_data"]),
        source_ref=row["source_ref"],
        created_at=row["created_at"],
    )


async def rpg_equipment_get(
    client: PostgresClient,
    item_id: UUID,
) -> EquipmentItemResponse | None:
    """Retrieve an equipment catalog entry by UUID."""
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM equipment_catalog WHERE id = $1", item_id)
    if row is None:
        return None
    return EquipmentItemResponse(
        id=row["id"],
        world_id=row["world_id"],
        system_id=row["system_id"],
        item_name=row["item_name"],
        item_type=ItemType(row["item_type"]),
        item_data=dict(row["item_data"]),
        source_ref=row["source_ref"],
        created_at=row["created_at"],
    )


async def rpg_equipment_list(
    client: PostgresClient,
    world_id: str | None = None,
    system_id: str | None = None,
    item_type: ItemType | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[EquipmentItemResponse]:
    """List equipment catalog entries with optional filters."""
    conditions = []
    params: list[Any] = []
    idx = 1

    if world_id is not None:
        conditions.append(f"world_id = ${idx}")
        params.append(world_id)
        idx += 1
    if system_id is not None:
        conditions.append(f"system_id = ${idx}")
        params.append(system_id)
        idx += 1
    if item_type is not None:
        conditions.append(f"item_type = ${idx}")
        params.append(item_type.value)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.extend([limit, offset])

    pool = await client._get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT * FROM equipment_catalog
            {where}
            ORDER BY item_name
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
        )
    return [
        EquipmentItemResponse(
            id=r["id"],
            world_id=r["world_id"],
            system_id=r["system_id"],
            item_name=r["item_name"],
            item_type=ItemType(r["item_type"]),
            item_data=dict(r["item_data"]),
            source_ref=r["source_ref"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Character ↔ Equipment linking
# ---------------------------------------------------------------------------


async def rpg_sheet_equip(
    client: PostgresClient,
    sheet_id: UUID,
    item_id: UUID,
    quantity: int = 1,
    is_equipped: bool = False,
    slot: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Link an equipment catalog item to a character sheet."""
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO character_equipment
                (character_sheet_id, item_id, quantity, is_equipped, slot, notes)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (character_sheet_id, item_id) DO UPDATE SET
                quantity    = EXCLUDED.quantity,
                is_equipped = EXCLUDED.is_equipped,
                slot        = EXCLUDED.slot,
                notes       = EXCLUDED.notes
            RETURNING *
            """,
            sheet_id,
            item_id,
            quantity,
            is_equipped,
            slot,
            notes,
        )
    return dict(row)


async def rpg_sheet_unequip(
    client: PostgresClient,
    sheet_id: UUID,
    item_id: UUID,
) -> bool:
    """Remove an equipment link from a character sheet."""
    pool = await client._get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM character_equipment
            WHERE character_sheet_id = $1 AND item_id = $2
            """,
            sheet_id,
            item_id,
        )
    return bool(result.split()[-1] != "0")


# ---------------------------------------------------------------------------
# Validation helper (no I/O — pure Pydantic)
# ---------------------------------------------------------------------------


def rpg_validate_sheet(
    system_id: str,
    sheet_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate a raw dict against the registered system schema.

    Returns ``{"valid": True, "errors": []}`` on success.
    Returns ``{"valid": False, "errors": [...]}`` on validation failure.
    Never raises — safe to call from untrusted input paths.
    """
    registry = _registry()
    sheet_class = registry.get_sheet_class(system_id)
    if sheet_class is None:
        return {
            "valid": False,
            "errors": [f"Unknown game system: '{system_id}'"],
        }
    try:
        sheet_class.model_validate(sheet_data)
        return {"valid": True, "errors": []}
    except ValidationError as exc:
        return {
            "valid": False,
            "errors": [str(e) for e in exc.errors()],
        }


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------


async def rpg_schema_inspect(
    client: PostgresClient,
    system_id: str,
) -> dict[str, Any] | None:
    """
    Return a structured summary of a registered game system's schema.

    Checks the in-memory ``SystemRegistry`` first (populated at import from
    built-in spec modules).  If not found, falls back to the ``spec`` JSONB
    column in ``game_system_schemas``.

    Returns ``None`` if the system is not found in either source.

    The returned dict is self-contained and safe to pass to an LLM as a
    context document — no code, no lambdas, only plain data.

    Return shape::

        {
            "system_id": str,
            "system_name": str,
            "version": str,
            "publisher": str | None,
            "tags": list[str],
            "core_mechanic": {
                "mechanic_type": str,
                "dice_notation": str | None,
                "success_condition": str,
                "critical_rule": str | None,
                "description": str,
            },
            "entity_types": {
                "<type_key>": {
                    "display_name": str,
                    "description": str,
                    "storage_backends": list[str],
                    "fields": [
                        {
                            "name": str,
                            "display_name": str,
                            "field_type": str,
                            "required": bool,
                            "user_settable": bool,
                            "derived_formula": str | None,
                            "default_value": Any,
                            "min_value": float | None,
                            "max_value": float | None,
                            "enum_values": list[str] | None,
                        }, ...
                    ],
                    "validators": [
                        {"validator_type": str, "target_field": str, ...}, ...
                    ],
                    "item_types": {"weapon": {...}, ...}   # if sub-typed
                }
            },
            "relations": [
                {
                    "relation_id": str,
                    "display_name": str,
                    "from_type": str,
                    "to_type": str,
                    "cardinality": str,
                    "is_required": bool,
                    "description": str,
                }, ...
            ],
            "data_edges": [
                {
                    "edge_id": str,
                    "from_backend": str,
                    "from_collection": str,
                    "to_backend": str,
                    "to_collection": str,
                    "is_enforced": bool,
                    "description": str,
                }, ...
            ],
        }
    """
    spec_reg = _spec_registry()
    spec = spec_reg.get(system_id)

    if spec is None:
        # Fall back to PostgreSQL JSONB column
        pool = await client._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT spec FROM game_system_schemas WHERE system_id = $1",
                system_id,
            )
        if row is None or row["spec"] is None:
            return None
        spec = spec_reg.load_from_dict(dict(row["spec"]))

    # --- core mechanic ---
    cm = spec.core_mechanic
    core_mechanic_summary: dict[str, Any] = {
        "mechanic_type": cm.mechanic_type.value,
        "dice_notation": cm.dice_notation,
        "success_condition": cm.success_condition,
        "critical_rule": cm.critical_rule,
        "description": cm.description,
    }

    # --- entity types ---
    entity_types_summary: dict[str, Any] = {}
    for type_key, et in spec.entity_types.items():
        fields_summary = [
            {
                "name": f.name,
                "display_name": f.display_name,
                "field_type": f.field_type.value,
                "required": f.required,
                "user_settable": f.user_settable,
                "derived_formula": f.derived_formula,
                "default_value": f.default_value,
                "min_value": f.min_value,
                "max_value": f.max_value,
                "enum_values": list(f.enum_values) if f.enum_values else None,
            }
            for f in et.fields
        ]

        validators_summary = [
            {
                "validator_type": v.validator_type.value,
                "field": v.field,
                "other_field": v.other_field,
                "min_bound": v.min_bound,
                "max_bound": v.max_bound,
                "expr": v.expr,
                "divisor": v.divisor,
                "allowed_values": list(v.allowed_values) if v.allowed_values else None,
                "error_message": v.error_message,
            }
            for v in et.validators
        ]

        item_types_summary: dict[str, Any] = {}
        for it_key, it in et.item_types.items():
            item_types_summary[it_key] = {
                "display_name": it.display_name,
                "extra_fields": [
                    {
                        "name": f.name,
                        "display_name": f.display_name,
                        "field_type": f.field_type.value,
                        "required": f.required,
                        "min_value": f.min_value,
                        "max_value": f.max_value,
                        "enum_values": list(f.enum_values) if f.enum_values else None,
                    }
                    for f in it.extra_fields
                ],
            }

        entity_types_summary[type_key] = {
            "display_name": et.display_name,
            "description": et.description,
            "storage_backends": [b.value for b in et.storage_backends],
            "fields": fields_summary,
            "validators": validators_summary,
            "item_types": item_types_summary,
        }

    # --- relations ---
    relations_summary = [
        {
            "relation_id": r.relation_id,
            "display_name": r.display_name,
            "from_type": r.from_type,
            "to_type": r.to_type,
            "cardinality": r.cardinality.value,
            "is_required": r.is_required,
            "description": r.description,
        }
        for r in spec.relations
    ]

    # --- data edges ---
    data_edges_summary = [
        {
            "edge_id": e.edge_id,
            "from_backend": e.from_backend.value,
            "from_collection": e.from_collection,
            "to_backend": e.to_backend.value,
            "to_collection": e.to_collection,
            "is_enforced": e.is_enforced,
            "description": e.description,
        }
        for e in spec.data_edges
    ]

    return {
        "system_id": spec.system_id,
        "system_name": spec.system_name,
        "version": spec.version,
        "publisher": spec.publisher,
        "tags": list(spec.tags),
        "core_mechanic": core_mechanic_summary,
        "entity_types": entity_types_summary,
        "relations": relations_summary,
        "data_edges": data_edges_summary,
    }
