"""Character persistence helpers — MongoDB-only storage for standalone characters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

log = structlog.get_logger()

# Reserved keys that callers must not set via update_character — mutations
# to these fields go through dedicated helpers (e.g. add_version) so the
# invariants stay intact.
_PROTECTED_KEYS = frozenset({"versions"})


def _coll() -> Any:
    """Lazy access to the 'characters' MongoDB collection."""
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client().get_collection("characters")


def create_character(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new character document. Returns the created doc."""
    now = datetime.now(UTC)
    doc = {
        "id": str(uuid4()),
        "name": data["name"],
        "description": data.get("description", ""),
        "avatar_url": data.get("avatar_url"),
        "personality": data.get("personality", ""),
        "gm_notes": data.get("gm_notes", ""),
        "first_message": data.get("first_message", ""),
        "is_ooc_persona": data.get("is_ooc_persona", False),
        "entity_id": data.get("entity_id"),  # may be None (legacy compat)
        "source_universe_id": data.get("source_universe_id"),
        "default_universe_id": data.get("source_universe_id"),
        "versions": [],
        "memory_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    _coll().insert_one(doc)
    log.info("character_created", character_id=doc["id"], name=doc["name"])
    return doc


def get_character(character_id: str) -> dict[str, Any] | None:
    """Fetch a single character by ID."""
    return _coll().find_one({"id": character_id})  # type: ignore


def update_character(character_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update fields on a character. Returns the updated doc or None.

    Refuses to set reserved keys (versions) — callers must use the dedicated
    version helpers so the array invariant is preserved.
    """
    if forbidden := _PROTECTED_KEYS & set(updates):
        raise ValueError(
            f"update_character refused to set reserved keys: {sorted(forbidden)}. "
            "Use the dedicated version helpers instead."
        )
    updates = dict(updates)
    updates["updated_at"] = datetime.now(UTC)
    result = _coll().find_one_and_update(
        {"id": character_id},
        {"$set": updates},
        return_document=True,
    )
    if result:
        log.info("character_updated", character_id=character_id)
    return result  # type: ignore


def set_character_avatar(character_id: str, minio_key: str) -> dict[str, Any] | None:
    """Point a character's avatar at a stored MinIO object key.

    Only the matching character document is touched — avatar mutations from
    the image approval flow (Task 6) always go through here so the stored
    value is the stable object key, never an expiring presigned URL.
    """
    result = update_character(character_id, {"avatar_url": minio_key})
    if result:
        log.info("character_avatar_updated", character_id=character_id)
    return result


def delete_character(character_id: str) -> bool:
    """Delete a character. Returns True if deleted."""
    result = _coll().delete_one({"id": character_id})
    deleted = result.deleted_count > 0
    if deleted:
        log.info("character_deleted", character_id=character_id)
    return deleted  # type: ignore


def list_characters(limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
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
            "$set": {"updated_at": datetime.now(UTC)},
        },
    )


# ---------------------------------------------------------------------------
# Versions — per-universe incarnations of a character
# ---------------------------------------------------------------------------


def _version_summary(version: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe summary of a stored version entry."""
    created = version.get("created_at")
    last_chat = version.get("last_chatted_at")
    return {
        "version_id": version["version_id"],
        "universe_id": version["universe_id"],
        "entity_id": version["entity_id"],
        "npc_profile_id": version.get("npc_profile_id"),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),  # type: ignore
        "last_chatted_at": last_chat.isoformat() if hasattr(last_chat, "isoformat") else last_chat,  # type: ignore
    }


def get_version(character_id: str, universe_id: str) -> dict[str, Any] | None:
    """Return the raw version entry for (character_id, universe_id), or None."""
    char = get_character(character_id)
    if not char:
        return None
    for v in char.get("versions", []) or []:
        if v.get("universe_id") == universe_id:
            return v  # type: ignore
    return None


def get_version_summary(character_id: str, universe_id: str) -> dict[str, Any] | None:
    """Return the JSON-safe summary for a (character, universe), or None."""
    raw = get_version(character_id, universe_id)
    return _version_summary(raw) if raw else None


def list_versions(character_id: str) -> list[dict[str, Any]]:
    """Return all version summaries for the character (newest first)."""
    char = get_character(character_id)
    if not char:
        return []
    versions = sorted(
        char.get("versions", []) or [],
        key=lambda v: v.get("created_at") or "",
        reverse=True,
    )
    return [_version_summary(v) for v in versions]


def add_version(
    character_id: str,
    universe_id: str,
    entity_id: str,
    npc_profile_id: str | None = None,
) -> dict[str, Any]:
    """Append a new incarnation entry; idempotent per (character, universe).

    If a version already exists for that universe, the existing entry is
    returned untouched (callers may update last_chatted_at via touch_version).
    On the first incarnation, the top-level default_universe_id /
    source_universe_id / entity_id are aligned for legacy callers.
    """
    existing = get_version(character_id, universe_id)
    if existing:
        return _version_summary(existing)

    now = datetime.now(UTC)
    version_id = str(uuid4())
    entry = {
        "version_id": version_id,
        "universe_id": universe_id,
        "entity_id": entity_id,
        "npc_profile_id": npc_profile_id,
        "created_at": now,
        "last_chatted_at": None,
    }
    _coll().update_one(
        {"id": character_id},
        {
            "$push": {"versions": entry},
            "$set": {
                "default_universe_id": universe_id,
                "entity_id": entity_id,
                "source_universe_id": universe_id,
                "updated_at": now,
            },
        },
    )
    log.info(
        "character_version_added",
        character_id=character_id,
        universe_id=universe_id,
        entity_id=entity_id,
        version_id=version_id,
    )
    return _version_summary(entry)


def touch_version(character_id: str, universe_id: str) -> None:
    """Bump last_chatted_at on the matching incarnation (best-effort)."""
    now = datetime.now(UTC)
    _coll().update_one(
        {"id": character_id, "versions.universe_id": universe_id},
        {
            "$set": {
                "versions.$.last_chatted_at": now,
                "updated_at": now,
            }
        },
    )


def delete_version(character_id: str, universe_id: str) -> dict[str, Any] | None:
    """Remove the incarnation entry; return the popped entry (raw).

    Does NOT touch Neo4j / Mongo NPCProfile — callers must do their own
    teardown (see character_conversation.delete_incarnation).
    """
    char = get_character(character_id)
    if not char:
        return None
    popped: dict[str, Any] | None = None
    remaining: list[dict[str, Any]] = []
    for v in char.get("versions", []) or []:
        if v.get("universe_id") == universe_id and popped is None:
            popped = v
        else:
            remaining.append(v)
    if popped is None:
        return None

    update_set: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    # If the popped incarnation was the default, promote the next-newest
    # surviving entry as the new default. If none remain, clear defaults.
    if char.get("default_universe_id") == universe_id:
        new_default = remaining[0] if remaining else None
        update_set["default_universe_id"] = new_default.get("universe_id") if new_default else None
        update_set["entity_id"] = new_default.get("entity_id") if new_default else None
        update_set["source_universe_id"] = new_default.get("universe_id") if new_default else None
    _coll().update_one(
        {"id": character_id},
        {"$set": {"versions": remaining, **update_set}},
    )
    log.info(
        "character_version_deleted",
        character_id=character_id,
        universe_id=universe_id,
    )
    return popped


def set_default_universe(character_id: str, universe_id: str | None) -> dict[str, Any] | None:
    """Pin which incarnation the card opens by default. Must match an existing version."""
    char = get_character(character_id)
    if not char:
        return None
    if universe_id is not None:
        match = next(
            (v for v in char.get("versions", []) or [] if v.get("universe_id") == universe_id),
            None,
        )
        if match is None:
            raise ValueError(f"No version for universe {universe_id!r} on character {character_id!r}")
    new_entity_id = match.get("entity_id") if "match" in locals() and match else None
    return update_character(
        character_id,
        {
            "default_universe_id": universe_id,
            "entity_id": new_entity_id,
            "source_universe_id": universe_id,
        },
    )
