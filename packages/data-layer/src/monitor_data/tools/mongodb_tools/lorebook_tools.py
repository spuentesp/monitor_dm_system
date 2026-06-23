"""
MongoDB CRUD for character/universe lorebook entries.

Provides keyword scanning, priority ordering, trigger counting, and auto-keyword generation.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

import structlog

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.lorebook import (
    LorebookEntry,
    LorebookEntryCreate,
    LorebookEntryUpdate,
)

log = structlog.get_logger()


def _coll() -> Any:
    return get_mongodb_client().get_collection("lorebook_entries")


def _auto_keywords(content: str) -> list[str]:
    """Derive up to 5 keywords from content using capitalized noun phrases."""
    nouns = re.findall(r"\b[A-Z][a-z]{2,}\b", content)
    unique = list(dict.fromkeys(nouns))  # preserve order, deduplicate
    return [w.lower() for w in unique[:5]]


def _extract_keywords_via_dspy(content: str) -> list[str]:
    """
    DSPy keyword extraction is handled at the agents layer (Layer 2).
    This fallback uses heuristic extraction. Agents should call the
    LorebookKeywordExtractor DSPy module directly and pass keywords
    when creating entries via mongodb_create_lorebook_entry.
    """
    return _auto_keywords(content)


def mongodb_create_lorebook_entry(
    character_id: str,
    data: LorebookEntryCreate,
) -> LorebookEntry:
    """Insert a lorebook entry. Auto-derives keywords if none provided."""
    now = datetime.now(timezone.utc).isoformat()

    # Keyword resolution: explicit → fallback → DSPy
    if data.keywords:
        keywords = list(data.keywords)
    elif data.auto_generate_keywords:
        keywords = _extract_keywords_via_dspy(data.content)
    else:
        keywords = _auto_keywords(data.content)

    doc = {
        "id": str(uuid4()),
        "character_id": character_id,
        "keywords": keywords,
        "content": data.content,
        "priority": data.priority,
        "is_active": data.is_active,
        "tags": list(data.tags) if data.tags else [],
        "scene_filter": data.scene_filter,
        "trigger_count": 0,
        "last_triggered": None,
        "created_at": now,
        "updated_at": now,
    }
    _coll().insert_one(doc)
    log.info(
        "lorebook_entry_created",
        entry_id=doc["id"],
        character_id=character_id,
        keyword_count=len(keywords),
    )
    return LorebookEntry(**doc)


def mongodb_get_lorebook_entry(entry_id: str) -> LorebookEntry | None:
    """Fetch a single lorebook entry by ID."""
    doc = _coll().find_one({"id": entry_id})
    return LorebookEntry(**doc) if doc else None


def mongodb_get_lorebook_entries(
    character_id: str,
    sort_by: Literal["priority", "trigger_count", "created_at"] = "priority",
    ascending: bool = False,
) -> list[LorebookEntry]:
    """
    List all active lorebook entries for a character.

    Args:
        character_id: The character_id to filter by.
        sort_by: Field to sort by. Default "priority".
        ascending: If True, sort ascending instead of descending.
    """
    direction = 1 if ascending else -1
    cursor = (
        _coll()
        .find({"character_id": character_id, "is_active": True})
        .sort(sort_by, direction)
        .sort("created_at", 1)
    )
    return [LorebookEntry(**d) for d in cursor]


def mongodb_get_lorebook_entries_by_tags(
    character_id: str,
    tags: list[str],
    sort_by: Literal["priority", "trigger_count", "created_at"] = "priority",
) -> list[LorebookEntry]:
    """List entries matching any of the given tags."""
    cursor = (
        _coll()
        .find(
            {
                "character_id": character_id,
                "is_active": True,
                "tags": {"$in": tags},
            }
        )
        .sort(sort_by, -1)
        .sort("created_at", 1)
    )
    return [LorebookEntry(**d) for d in cursor]


def mongodb_list_lorebook_entries_by_ids(entry_ids: list[str]) -> list[LorebookEntry]:
    """Fetch multiple lorebook entries by IDs."""
    cursor = _coll().find({"id": {"$in": entry_ids}, "is_active": True})
    return [LorebookEntry(**d) for d in cursor]


def mongodb_update_lorebook_entry(
    entry_id: str,
    updates: LorebookEntryUpdate,
) -> LorebookEntry | None:
    """Update fields on a lorebook entry. Returns updated doc or None."""
    delta = {
        k: v
        for k, v in {
            "keywords": updates.keywords,
            "content": updates.content,
            "priority": updates.priority,
            "is_active": updates.is_active,
            "tags": updates.tags,
            "scene_filter": updates.scene_filter,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }.items()
        if v is not None
    }
    if not delta:
        return mongodb_get_lorebook_entry(entry_id)

    result = _coll().find_one_and_update(
        {"id": entry_id},
        {"$set": delta},
        return_document=True,
    )
    if result:
        log.info("lorebook_entry_updated", entry_id=entry_id)
    return LorebookEntry(**result) if result else None


def mongodb_delete_lorebook_entry(entry_id: str) -> bool:
    """Delete a lorebook entry. Returns True if deleted."""
    result = _coll().delete_one({"id": entry_id})
    deleted: bool = result.deleted_count > 0
    if deleted:
        log.info("lorebook_entry_deleted", entry_id=entry_id)
    return deleted


def mongodb_inject_lorebook_entries(
    character_id: str,
    text: str,
    scene_context: str | None = None,
    increment_triggers: bool = True,
) -> list[str]:
    """
    Scan `text` against all active lorebook entries for `character_id`.
    Returns matched entry contents, deduplicated, ordered by priority.

    Case-insensitive keyword matching. Each entry matches at most once per call.

    Args:
        character_id: Character to scope lorebook entries to.
        text: Player's input text to scan for keyword matches.
        scene_context: Optional scene tag (e.g., "combat", "social") to filter entries.
            If set, entries with matching scene_filter or tags are preferred.
            Entries with no scene_filter are always eligible.
        increment_triggers: If True, increment trigger_count and set last_triggered
            on each matched entry.
    """
    entries = mongodb_get_lorebook_entries(character_id)
    if not entries:
        return []

    text_lower = text.lower()
    matched: list[tuple[int, str, str, str]] = []  # (-priority, created_at, content, entry_id)

    for entry in entries:
        # Scene filter check
        if scene_context:
            if entry.scene_filter and entry.scene_filter != scene_context:
                continue
            # entries with tags that don't match the scene_context are deprioritized
            # (but not excluded) — we handle this by adding a penalty

        for kw in entry.keywords:
            if kw.lower() in text_lower:
                penalty = 0
                if scene_context and entry.tags and scene_context not in entry.tags:
                    penalty = 1  # deprioritize mismatched tags
                matched.append(
                    (entry.priority - penalty, entry.created_at, entry.content, entry.id)
                )
                break  # Each entry contributes at most once

    matched.sort(key=lambda x: (-x[0], x[1]))

    # Deduplicate by content while preserving priority order
    seen: set[str] = set()
    results: list[str] = []
    triggered_ids: list[str] = []

    for _, _, content, entry_id in matched:
        if content not in seen:
            seen.add(content)
            results.append(content)
            triggered_ids.append(entry_id)

    # Increment trigger_count for all matched entries
    if increment_triggers and triggered_ids:
        now = datetime.now(timezone.utc).isoformat()
        for eid in triggered_ids:
            _coll().update_one(
                {"id": eid},
                {"$inc": {"trigger_count": 1}, "$set": {"last_triggered": now}},
            )

    return results


def mongodb_bulk_create_lorebook_entries(
    character_id: str,
    entries: list[LorebookEntryCreate],
) -> list[LorebookEntry]:
    """Insert multiple lorebook entries at once. Returns created entries."""
    if not entries:
        return []

    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for data in entries:
        if data.keywords:
            keywords = list(data.keywords)
        elif data.auto_generate_keywords:
            keywords = _extract_keywords_via_dspy(data.content)
        else:
            keywords = _auto_keywords(data.content)

        docs.append(
            {
                "id": str(uuid4()),
                "character_id": character_id,
                "keywords": keywords,
                "content": data.content,
                "priority": data.priority,
                "is_active": data.is_active,
                "tags": list(data.tags) if data.tags else [],
                "scene_filter": data.scene_filter,
                "trigger_count": 0,
                "last_triggered": None,
                "created_at": now,
                "updated_at": now,
            }
        )

    _coll().insert_many(docs)
    created = [LorebookEntry(**d) for d in docs]
    log.info("lorebook_bulk_created", count=len(created), character_id=character_id)
    return created


def mongodb_get_lorebook_stats(character_id: str) -> dict[str, Any]:
    """Return aggregate stats for a character's lorebook."""
    pipeline = [
        {"$match": {"character_id": character_id, "is_active": True}},
        {
            "$group": {
                "_id": None,
                "total_entries": {"$sum": 1},
                "total_triggers": {"$sum": "$trigger_count"},
                "avg_priority": {"$avg": "$priority"},
            }
        },
    ]
    result = list(_coll().aggregate(pipeline))
    if not result:
        return {"total_entries": 0, "total_triggers": 0, "avg_priority": 0}
    r = result[0]
    return {
        "total_entries": r["total_entries"],
        "total_triggers": r["total_triggers"],
        "avg_priority": round(r["avg_priority"], 1),
    }


def mongodb_get_top_lorebook_entries(
    character_id: str,
    limit: int = 10,
) -> list[LorebookEntry]:
    """Return entries sorted by trigger_count desc."""
    cursor = (
        _coll()
        .find({"character_id": character_id, "is_active": True})
        .sort("trigger_count", -1)
        .limit(limit)
    )
    return [LorebookEntry(**d) for d in cursor]
