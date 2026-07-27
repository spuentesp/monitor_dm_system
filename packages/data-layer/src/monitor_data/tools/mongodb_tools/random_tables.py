"""
MongoDB tools for Random Table operations.

LAYER: 1 (data-layer)
Authority: MongoDB
Use Case: DL-21
"""

import logging
import random
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.random_tables import (
    RandomTableCreate,
    RandomTableFilter,
    RandomTableListResponse,
    RandomTableResponse,
    RandomTableUpdate,
)
from monitor_data.utils.dice import roll_dice

logger = logging.getLogger(__name__)

# =============================================================================
# RANDOM TABLE OPERATIONS (DL-21)
# =============================================================================


def mongodb_create_random_table(params: RandomTableCreate) -> RandomTableResponse:
    """Create a new random table in MongoDB."""
    client = get_mongodb_client()
    collection = client.get_collection("random_tables")

    table_id = uuid4()
    now = datetime.now(UTC)

    table_doc = params.model_dump()
    table_doc["table_id"] = str(table_id)
    table_doc["universe_id"] = str(params.universe_id) if params.universe_id else None
    table_doc["source_id"] = str(params.source_id) if params.source_id else None
    table_doc["game_system_id"] = str(params.game_system_id) if params.game_system_id else None
    table_doc["created_at"] = now
    table_doc["updated_at"] = now

    # Convert entries UUIDs to strings
    for entry in table_doc["entries"]:
        if entry.get("subtable_id"):
            entry["subtable_id"] = str(entry["subtable_id"])

    collection.insert_one(table_doc)

    res = mongodb_get_random_table(table_id)
    assert res
    return res


def mongodb_get_random_table(table_id: UUID) -> RandomTableResponse | None:
    """Retrieve a random table by ID."""
    client = get_mongodb_client()
    collection = client.get_collection("random_tables")

    doc = collection.find_one({"table_id": str(table_id)})
    if not doc:
        return None

    return RandomTableResponse(**doc)


def mongodb_list_random_tables(filters: RandomTableFilter) -> RandomTableListResponse:
    """List random tables with filtering."""
    client = get_mongodb_client()
    collection = client.get_collection("random_tables")

    query = {}
    if filters.universe_id:
        query["universe_id"] = str(filters.universe_id)
    if filters.table_type:
        query["table_type"] = filters.table_type.value
    if filters.game_system_id:
        query["game_system_id"] = str(filters.game_system_id)

    total = collection.count_documents(query)
    cursor = collection.find(query).skip(filters.offset).limit(filters.limit)

    tables = [RandomTableResponse(**doc) for doc in cursor]

    return RandomTableListResponse(tables=tables, total=total, limit=filters.limit, offset=filters.offset)


def mongodb_update_random_table(table_id: UUID, params: RandomTableUpdate) -> RandomTableResponse:
    """Update an existing random table."""
    client = get_mongodb_client()
    collection = client.get_collection("random_tables")

    update_data = params.model_dump(exclude_unset=True)
    if not update_data:
        res = mongodb_get_random_table(table_id)
    assert res
    return res

    update_data["updated_at"] = datetime.now(UTC)

    # Handle UUID stringification in entries if updated
    if "entries" in update_data:
        for entry in update_data["entries"]:
            if entry.get("subtable_id"):
                entry["subtable_id"] = str(entry["subtable_id"])

    result = collection.update_one({"table_id": str(table_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise ValueError(f"Random table {table_id} not found")

    return mongodb_get_random_table(table_id)


def mongodb_delete_random_table(table_id: UUID) -> bool:
    """Delete a random table."""
    client = get_mongodb_client()
    collection = client.get_collection("random_tables")

    result = collection.delete_one({"table_id": str(table_id)})
    return result.deleted_count > 0


def mongodb_roll_on_table(table_id: UUID, actor_id: UUID | None = None) -> dict[str, Any]:
    """
    Roll on a random table and return the result.
    If subtable_id is present in result, it recursively rolls on it.
    """
    table = mongodb_get_random_table(table_id)
    if not table:
        raise ValueError(f"Random table {table_id} not found")

    # 1. Roll the dice
    roll_result = roll_dice(table.dice_formula)
    total = roll_result.total

    # 2. Find matching entry
    selected_entry = None
    if table.weighted:
        # Weighted roll logic
        total_weight = sum(e.weight or 1.0 for e in table.entries)
        r = random.uniform(0, total_weight)
        cumulative = 0.0
        for e in table.entries:
            cumulative += e.weight or 1.0
            if r <= cumulative:
                selected_entry = e
                break
    else:
        # Range-based roll logic
        for e in table.entries:
            if e.min_roll <= total <= e.max_roll:
                selected_entry = e
                break

    if not selected_entry:
        return {
            "table_id": str(table_id),
            "roll": total,
            "formula": table.dice_formula,
            "value": "No result found for this roll.",
        }

    # 3. Handle subtable recursion
    sub_results = []
    if selected_entry.subtable_id:
        sub_res = mongodb_roll_on_table(selected_entry.subtable_id, actor_id)
        sub_results.append(sub_res)

    return {
        "table_id": str(table_id),
        "table_name": table.name,
        "roll": total,
        "formula": table.dice_formula,
        "value": selected_entry.value,
        "sub_results": sub_results,
    }
