"""Character persistence helpers — MongoDB-only storage for standalone characters."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

log = structlog.get_logger()


def _coll() -> Any:
    """Lazy access to the 'characters' MongoDB collection."""
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client().get_collection("characters")


def create_character(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new character document. Returns the created doc."""
    now = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid4()),
        "name": data["name"],
        "description": data.get("description", ""),
        "avatar_url": data.get("avatar_url"),
        "personality": data.get("personality", ""),
        "gm_notes": data.get("gm_notes", ""),
        "first_message": data.get("first_message", ""),
        "is_ooc_persona": data.get("is_ooc_persona", False),
        "entity_id": data.get("entity_id"),  # may be None
        "source_universe_id": data.get("source_universe_id"),
        "memory_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    _coll().insert_one(doc)
    log.info("character_created", character_id=doc["id"], name=doc["name"])
    return doc


def get_character(character_id: str) -> dict[str, Any] | None:
    """Fetch a single character by ID."""
    return _coll().find_one({"id": character_id})


def update_character(
    character_id: str, updates: dict[str, Any]
) -> dict[str, Any] | None:
    """Update fields on a character. Returns the updated doc or None."""
    updates["updated_at"] = datetime.now(timezone.utc)
    result = _coll().find_one_and_update(
        {"id": character_id},
        {"$set": updates},
        return_document=True,
    )
    if result:
        log.info("character_updated", character_id=character_id)
    return result


def delete_character(character_id: str) -> bool:
    """Delete a character by ID. Returns True if deleted."""
    result = _coll().delete_one({"id": character_id})
    deleted = result.deleted_count > 0
    if deleted:
        log.info("character_deleted", character_id=character_id)
    return deleted


def list_characters(
    limit: int = 50, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """List characters sorted by updated_at descending. Returns (docs, total)."""
    total = _coll().count_documents({})
    cursor = _coll().find({}).sort("updated_at", -1).skip(offset).limit(limit)
    return list(cursor), total


def increment_memory_count(character_id: str, delta: int = 1) -> None:
    """Increment the memory_count field on a character."""
    _coll().update_one(
        {"id": character_id},
        {
            "$inc": {"memory_count": delta},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
