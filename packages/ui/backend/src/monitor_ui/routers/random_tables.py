"""
Random Tables router — CRUD + roll operations for the GM toolkit.

Exposes the full lifecycle of random tables (encounters, loot, names, weather,
rumors, etc.) to the UI. Tables can be system-wide (universe_id=null) or
universe-specific overrides. Backed by MongoDB.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from monitor_data.schemas.random_tables import (
    RandomTableCreate,
    RandomTableFilter,
    RandomTableListResponse,
    RandomTableResponse,
    RandomTableType,
    RandomTableUpdate,
)
from monitor_data.tools.mongodb_tools.random_tables import (
    mongodb_create_random_table,
    mongodb_delete_random_table,
    mongodb_get_random_table,
    mongodb_list_random_tables,
    mongodb_roll_on_table,
    mongodb_update_random_table,
)
from pydantic import BaseModel

from .ingest_shared import db_op, validate_uuid

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas (UI layer — mirrors data-layer shapes)
# ---------------------------------------------------------------------------


class TableEntryRequest:
    """Body for a single random table entry on create/update."""

    def __init__(
        self,
        min_roll: int,
        max_roll: int,
        value: str,
        weight: float | None = None,
        subtable_id: str | None = None,
        conditions: dict[str, Any] | None = None,
    ):
        self.min_roll = min_roll
        self.max_roll = max_roll
        self.weight = weight
        self.value = value
        self.subtable_id = subtable_id
        self.conditions = conditions


# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------


@router.get("/random-tables", response_model=RandomTableListResponse)
async def list_random_tables(
    universe_id: str | None = Query(default=None, description="Filter by universe"),
    table_type: RandomTableType | None = Query(default=None, description="Filter by table type category"),
    game_system_id: str | None = Query(default=None, description="Filter by game system"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RandomTableListResponse:
    """
    Return random tables with optional filters.

    - universe_id=null returns system-wide (global) tables.
    - universe_id=<uuid> returns tables scoped to that universe.
    - Combine both to see all tables available in a given universe context.
    """
    filters = RandomTableFilter(
        universe_id=validate_uuid(universe_id) if universe_id else None,
        table_type=table_type,
        game_system_id=validate_uuid(game_system_id) if game_system_id else None,
        limit=limit,
        offset=offset,
    )
    with db_op("Database unavailable"):
        return mongodb_list_random_tables(filters)


@router.get("/random-tables/{table_id}", response_model=RandomTableResponse)
async def get_random_table(table_id: str) -> RandomTableResponse:
    """Retrieve a single random table by ID."""
    uid = validate_uuid(table_id, "table_id")
    with db_op("Database unavailable"):
        table = mongodb_get_random_table(uid)
    if not table:
        raise HTTPException(404, "Random table not found")
    return table


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class _CreateEntry(BaseModel):
    """Validated entry for table creation / update payloads."""

    min_roll: int
    max_roll: int
    value: str
    weight: float | None = None
    subtable_id: str | None = None
    conditions: dict[str, Any] | None = None

    # reason: bare adapter method with no return annotation; mypy can't narrow the RandomTableEntry construction against the untyped self / optional weight / subtable fields
    def to_entry(self):  # type: ignore
        from monitor_data.schemas.random_tables import RandomTableEntry

        return RandomTableEntry(
            min_roll=self.min_roll,
            max_roll=self.max_roll,
            value=self.value,
            weight=self.weight,
            subtable_id=UUID(self.subtable_id) if self.subtable_id else None,
            conditions=self.conditions,
        )


class RandomTableCreateRequest(BaseModel):
    name: str
    description: str = ""
    table_type: RandomTableType = RandomTableType.CUSTOM
    dice_formula: str = "1d20"
    weighted: bool = False
    entries: list[_CreateEntry]
    universe_id: str | None = None
    source_id: str | None = None
    game_system_id: str | None = None


@router.post("/random-tables", status_code=201, response_model=RandomTableResponse)
async def create_random_table(body: RandomTableCreateRequest) -> RandomTableResponse:
    """
    Create a new random table.

    - universe_id=null → system-wide global table (available to all universes).
    - universe_id=<uuid> → universe-specific override / extension.
    - At least one entry is required.
    """
    try:
        params = RandomTableCreate(
            name=body.name,
            description=body.description,
            table_type=body.table_type,
            dice_formula=body.dice_formula,
            weighted=body.weighted,
            # reason: to_entry() has no return annotation; the comprehension yields a list[Any] that the surrounding RandomTableCreate.entries: list[RandomTableEntry] rejects
            entries=[e.to_entry() for e in body.entries],  # type: ignore
            universe_id=UUID(body.universe_id) if body.universe_id else None,
            source_id=UUID(body.source_id) if body.source_id else None,
            game_system_id=UUID(body.game_system_id) if body.game_system_id else None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    with db_op("Database unavailable"):
        return mongodb_create_random_table(params)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class RandomTableUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    table_type: RandomTableType | None = None
    dice_formula: str | None = None
    weighted: bool | None = None
    entries: list[_CreateEntry] | None = None


@router.put("/random-tables/{table_id}", response_model=RandomTableResponse)
async def update_random_table(table_id: str, body: RandomTableUpdateRequest) -> RandomTableResponse:
    """Update an existing random table (partial update — only provided fields are changed)."""
    uid = validate_uuid(table_id, "table_id")

    update_kwargs: dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}

    if "entries" in update_kwargs and update_kwargs["entries"] is not None:
        update_kwargs["entries"] = [e.to_entry() for e in update_kwargs["entries"]]

    if not update_kwargs:
        raise HTTPException(400, "No fields to update")

    try:
        params = RandomTableUpdate(**update_kwargs)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

    with db_op("Database unavailable"):
        try:
            return mongodb_update_random_table(uid, params)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/random-tables/{table_id}", status_code=204)
async def delete_random_table(table_id: str) -> None:
    """Permanently delete a random table."""
    uid = validate_uuid(table_id, "table_id")
    with db_op("Database unavailable"):
        deleted = mongodb_delete_random_table(uid)
    if not deleted:
        raise HTTPException(404, "Random table not found")


# ---------------------------------------------------------------------------
# Roll
# ---------------------------------------------------------------------------


@router.post("/random-tables/{table_id}/roll")
async def roll_random_table(
    table_id: str,
    actor_id: str | None = Query(default=None, description="Actor rolling the dice"),
) -> dict[str, Any]:
    """
    Roll on a random table and return the result.

    - Resolves weighted vs. range-based selection automatically.
    - If the selected entry has a subtable_id, the result recursively rolls on it.
    - Returns the raw roll value, the selected entry text, and any sub-results.
    """
    uid = validate_uuid(table_id, "table_id")
    actor_uid = validate_uuid(actor_id) if actor_id else None

    with db_op("Database unavailable"):
        try:
            return mongodb_roll_on_table(uid, actor_uid)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
