"""
MongoDB CRUD for character/universe lorebook entries.

Provides keyword scanning, priority ordering, trigger counting, auto-keyword
generation, and SillyTavern-compatible semantics:

  - scan depth (search current input + recent history)
  - constant entries
  - secondary keywords with selective logic
  - probability roll
  - insertion position/order
  - timing (sticky / cooldown / delay)
  - inclusion groups
  - recursive scanning
  - token budgets
"""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import structlog

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.lorebook import (
    LorebookEntry,
    LorebookEntryCreate,
    LorebookEntryUpdate,
    LorebookScanConfig,
    LorebookScanResult,
    SelectiveLogic,
)

log = structlog.get_logger()


def _coll() -> Any:
    return get_mongodb_client().get_collection("lorebook_entries")


def _config_coll() -> Any:
    return get_mongodb_client().get_collection("lorebook_configs")


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


def _resolve_keywords(data: LorebookEntryCreate) -> list[str]:
    if data.keywords:
        return list(data.keywords)
    if data.auto_generate_keywords:
        return _extract_keywords_via_dspy(data.content)
    return _auto_keywords(data.content)


def mongodb_create_lorebook_entry(
    character_id: str,
    data: LorebookEntryCreate,
    *,
    created_turn_index: int | None = None,
) -> LorebookEntry:
    """Insert a lorebook entry. Auto-derives keywords if none provided."""
    now = datetime.now(UTC).isoformat()
    keywords = _resolve_keywords(data)

    doc = {
        "id": str(uuid4()),
        "character_id": character_id,
        "keywords": keywords,
        "secondary_keywords": list(data.secondary_keywords or []),
        "content": data.content,
        "comment": data.comment or "",
        "priority": data.priority,
        "order": data.order,
        "position": data.position,
        "depth": data.depth,
        "is_active": data.is_active,
        "constant": data.constant,
        "selective": data.selective,
        "selective_logic": data.selective_logic,
        "probability": data.probability,
        "use_probability": data.use_probability,
        "case_sensitive": data.case_sensitive,
        "match_whole_words": data.match_whole_words,
        "tags": list(data.tags) if data.tags else [],
        "scene_filter": data.scene_filter,
        "group": data.group or "",
        "group_override": data.group_override,
        "sticky": data.sticky,
        "cooldown": data.cooldown,
        "delay": data.delay,
        "exclude_recursion": data.exclude_recursion,
        "prevent_recursion": data.prevent_recursion,
        "vectorized": data.vectorized,
        "trigger_count": 0,
        "last_triggered": None,
        "last_triggered_turn_index": None,
        "created_turn_index": created_turn_index,
        "st_extensions": dict(data.st_extensions) if getattr(data, "st_extensions", None) else {},
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
    sort_by: Literal["priority", "trigger_count", "created_at", "order"] = "priority",
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
        _coll().find({"character_id": character_id, "is_active": True}).sort(sort_by, direction).sort("created_at", 1)
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
            "secondary_keywords": updates.secondary_keywords,
            "content": updates.content,
            "comment": updates.comment,
            "priority": updates.priority,
            "order": updates.order,
            "position": updates.position,
            "depth": updates.depth,
            "is_active": updates.is_active,
            "constant": updates.constant,
            "selective": updates.selective,
            "selective_logic": updates.selective_logic,
            "probability": updates.probability,
            "use_probability": updates.use_probability,
            "case_sensitive": updates.case_sensitive,
            "match_whole_words": updates.match_whole_words,
            "tags": updates.tags,
            "scene_filter": updates.scene_filter,
            "group": updates.group,
            "group_override": updates.group_override,
            "sticky": updates.sticky,
            "cooldown": updates.cooldown,
            "delay": updates.delay,
            "exclude_recursion": updates.exclude_recursion,
            "prevent_recursion": updates.prevent_recursion,
            "vectorized": updates.vectorized,
            "updated_at": datetime.now(UTC).isoformat(),
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


# ---------------------------------------------------------------------------
# Scan engine
# ---------------------------------------------------------------------------


def _keyword_matcher(keyword: str, text: str, case_sensitive: bool, whole_words: bool) -> bool:
    if not keyword:
        return False
    if whole_words:
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = r"\b" + re.escape(keyword) + r"\b"
        return bool(re.search(pattern, text, flags=flags))
    if case_sensitive:
        return keyword in text
    return keyword.lower() in text.lower()


def _entry_matches(
    entry: LorebookEntry,
    text: str,
    case_sensitive: bool,
    whole_words: bool,
) -> bool:
    """Check primary keyword match. Does not evaluate timing/constant."""
    if entry.constant:
        return True
    entry_case = entry.case_sensitive if entry.case_sensitive is not None else case_sensitive
    entry_whole = entry.match_whole_words if entry.match_whole_words is not None else whole_words
    return any(
        _keyword_matcher(kw, text, entry_case, entry_whole) for kw in entry.keywords
    )


def _secondary_matches(
    entry: LorebookEntry,
    text: str,
    case_sensitive: bool,
    whole_words: bool,
) -> bool:
    """Evaluate secondary keyword requirement according to selective_logic."""
    if not entry.selective or not entry.secondary_keywords:
        return True

    entry_case = entry.case_sensitive if entry.case_sensitive is not None else case_sensitive
    entry_whole = entry.match_whole_words if entry.match_whole_words is not None else whole_words
    matches = [
        _keyword_matcher(kw, text, entry_case, entry_whole)
        for kw in entry.secondary_keywords
    ]
    logic = int(entry.selective_logic or SelectiveLogic.AND_ANY)

    if logic == SelectiveLogic.AND_ANY:
        return any(matches)
    if logic == SelectiveLogic.NOT_ALL:
        return not all(matches)
    if logic == SelectiveLogic.NOT_ANY:
        return not any(matches)
    if logic == SelectiveLogic.AND_ALL:
        return all(matches)
    return any(matches)


def _timing_eligible(entry: LorebookEntry, turn_index: int | None) -> bool:
    """Check delay, sticky, and cooldown windows."""
    if turn_index is None:
        return True

    # Delay: entry cannot trigger until N turns after creation.
    if entry.created_turn_index is not None:
        if turn_index < entry.created_turn_index + entry.delay:
            return False

    last = entry.last_triggered_turn_index
    if last is None:
        return True

    sticky_end = last + entry.sticky
    cooldown_end = sticky_end + entry.cooldown

    if turn_index <= sticky_end:
        return True  # sticky active; eligible regardless of keyword
    if turn_index <= cooldown_end:
        return False  # cooldown active

    return True


def _is_sticky_active(entry: LorebookEntry, turn_index: int | None) -> bool:
    """Return True if the entry should be included because of a sticky window."""
    if turn_index is None or entry.last_triggered_turn_index is None:
        return False
    return turn_index <= entry.last_triggered_turn_index + entry.sticky


def _build_scan_text(
    text: str,
    history: list[str] | None,
    config: LorebookScanConfig,
) -> str:
    """Concatenate current input with recent history for scanning."""
    parts = [text]
    if history:
        # Take the most recent `scan_depth` turns, oldest first.
        recent = history[-config.scan_depth :] if config.scan_depth > 0 else []
        parts = list(recent) + parts
    return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    """Very rough token estimate (chars / 4). Good enough for budget enforcement."""
    return max(1, len(text) // 4)


def _apply_token_budget(entries: list[LorebookEntry], budget: int) -> list[LorebookEntry]:
    """Keep entries in order until the token budget is exhausted."""
    if budget <= 0:
        return entries
    selected: list[LorebookEntry] = []
    used = 0
    for entry in entries:
        cost = _estimate_tokens(entry.content)
        if used + cost > budget and selected:
            break
        selected.append(entry)
        used += cost
    return selected


def _apply_group_competition(entries: list[LorebookEntry]) -> list[LorebookEntry]:
    """Within each inclusion group, keep only the highest-priority member."""
    winners: dict[str, LorebookEntry] = {}
    overrides: list[LorebookEntry] = []

    for entry in entries:
        group = entry.group.strip()
        if not group or entry.group_override:
            overrides.append(entry)
            continue
        current = winners.get(group)
        if current is None:
            winners[group] = entry
            continue
        # Tie-break: higher priority, then lower order, then older creation.
        if (entry.priority, -entry.order, entry.created_at) > (
            current.priority,
            -current.order,
            current.created_at,
        ):
            winners[group] = entry

    result = list(winners.values()) + overrides
    # Re-sort by (order, priority desc, created_at).
    result.sort(key=lambda e: (e.order, -e.priority, e.created_at))
    return result


def mongodb_scan_lorebook(
    character_ids: list[str],
    text: str,
    *,
    history: list[str] | None = None,
    config: LorebookScanConfig | None = None,
    scene_context: str | None = None,
    turn_index: int | None = None,
    increment_triggers: bool = True,
    rng: random.Random | None = None,
) -> LorebookScanResult:
    """
    SillyTavern-aware lorebook scan.

    Scans the current input plus up to ``config.scan_depth`` recent history
    messages, applies constant entries, selective logic, probability,
    timing, group competition, recursion, token budget, and position grouping.

    Args:
        character_ids: IDs to scan (character + optional ``universe:<id>``).
        text: Current player/narrator input.
        history: Recent turn texts (oldest → newest). Last ``scan_depth`` are used.
        config: Scan settings. Defaults to LorebookScanConfig().
        scene_context: Optional scene tag for scene_filter filtering.
        turn_index: Current turn number for sticky/cooldown/delay math.
        increment_triggers: Whether to bump trigger_count/last_triggered on matches.
        rng: Optional random.Random for deterministic probability tests.

    Returns:
        A LorebookScanResult with position-grouped contents and triggered IDs.
    """
    config = config or LorebookScanConfig()
    rng = rng or random.Random()

    all_entries: list[LorebookEntry] = []
    seen_ids: set[str] = set()
    for cid in character_ids:
        for entry in mongodb_get_lorebook_entries(cid):
            if entry.id not in seen_ids:
                all_entries.append(entry)
                seen_ids.add(entry.id)

    if not all_entries:
        return LorebookScanResult()

    scan_text = _build_scan_text(text, history, config)
    triggered: set[str] = set()
    triggered_entries: list[LorebookEntry] = []

    # Recursion cap to prevent infinite loops.
    recursion_rounds = 3 if config.recursive_scanning else 0
    current_scan_text = scan_text

    for round_idx in range(recursion_rounds + 1):
        round_new: list[LorebookEntry] = []
        for entry in all_entries:
            if entry.id in triggered:
                continue
            if not entry.is_active:
                continue
            if scene_context and entry.scene_filter and entry.scene_filter != scene_context:
                continue
            if not _timing_eligible(entry, turn_index):
                continue
            # excludeRecursion: entry cannot be triggered by recursive scans.
            if round_idx > 0 and entry.exclude_recursion:
                continue

            sticky = _is_sticky_active(entry, turn_index)
            if sticky:
                matched = True
            else:
                matched = _entry_matches(entry, current_scan_text, config.case_sensitive, config.match_whole_words)

            if matched and entry.selective:
                matched = _secondary_matches(
                    entry, current_scan_text, config.case_sensitive, config.match_whole_words
                )

            if matched and entry.use_probability and entry.probability < 100:
                matched = rng.random() * 100 < entry.probability

            if matched:
                triggered.add(entry.id)
                round_new.append(entry)

        if not round_new:
            break

        triggered_entries.extend(round_new)

        # Build recursion text from newly triggered entries.
        recursion_pieces: list[str] = []
        for entry in round_new:
            if entry.prevent_recursion:
                continue
            if not entry.exclude_recursion:
                recursion_pieces.append(entry.content)
        if not recursion_pieces:
            break
        current_scan_text = "\n".join(recursion_pieces)

    # Scene tag deprioritization: already filtered above if strict; keep as-is.
    # Apply group competition and token budget.
    triggered_entries = _apply_group_competition(triggered_entries)
    triggered_entries = _apply_token_budget(triggered_entries, config.token_budget)

    # Deduplicate by content while preserving order (first occurrence wins).
    seen_content: set[str] = set()
    unique_entries: list[LorebookEntry] = []
    for entry in triggered_entries:
        if entry.content not in seen_content:
            seen_content.add(entry.content)
            unique_entries.append(entry)

    result = LorebookScanResult()
    for entry in unique_entries:
        if entry.position == 0:
            result.before.append(entry.content)
        elif entry.position == 4:
            result.depth.append(entry.content)
        else:
            result.after.append(entry.content)
        result.triggered_entry_ids.append(entry.id)

    if increment_triggers and result.triggered_entry_ids:
        now = datetime.now(UTC).isoformat()
        _coll().update_many(
            {"id": {"$in": result.triggered_entry_ids}},
            {
                "$inc": {"trigger_count": 1},
                "$set": {"last_triggered": now, "last_triggered_turn_index": turn_index},
            },
        )

    log.info(
        "lorebook_scan_complete",
        character_ids=character_ids,
        triggered=len(result.triggered_entry_ids),
        before=len(result.before),
        after=len(result.after),
        depth=len(result.depth),
    )
    return result


def mongodb_inject_lorebook_entries(
    character_id: str,
    text: str,
    scene_context: str | None = None,
    increment_triggers: bool = True,
) -> list[str]:
    """
    Legacy single-character scan. Returns matched entry contents.

    Case-insensitive keyword matching. Each entry matches at most once per call.
    This wrapper exists for backward compatibility; new callers should use
    ``mongodb_scan_lorebook`` for full SillyTavern semantics.
    """
    result = mongodb_scan_lorebook(
        character_ids=[character_id],
        text=text,
        scene_context=scene_context,
        increment_triggers=increment_triggers,
    )
    return result.after + result.depth


def mongodb_bulk_create_lorebook_entries(
    character_id: str,
    entries: list[LorebookEntryCreate],
    *,
    created_turn_index: int | None = None,
) -> list[LorebookEntry]:
    """Insert multiple lorebook entries at once. Returns created entries."""
    if not entries:
        return []

    now = datetime.now(UTC).isoformat()
    docs = []
    for data in entries:
        keywords = _resolve_keywords(data)
        docs.append(
            {
                "id": str(uuid4()),
                "character_id": character_id,
                "keywords": keywords,
                "secondary_keywords": list(data.secondary_keywords or []),
                "content": data.content,
                "comment": data.comment or "",
                "priority": data.priority,
                "order": data.order,
                "position": data.position,
                "depth": data.depth,
                "is_active": data.is_active,
                "constant": data.constant,
                "selective": data.selective,
                "selective_logic": data.selective_logic,
                "probability": data.probability,
                "use_probability": data.use_probability,
                "case_sensitive": data.case_sensitive,
                "match_whole_words": data.match_whole_words,
                "tags": list(data.tags) if data.tags else [],
                "scene_filter": data.scene_filter,
                "group": data.group or "",
                "group_override": data.group_override,
                "sticky": data.sticky,
                "cooldown": data.cooldown,
                "delay": data.delay,
                "exclude_recursion": data.exclude_recursion,
                "prevent_recursion": data.prevent_recursion,
                "vectorized": data.vectorized,
                "trigger_count": 0,
                "last_triggered": None,
                "last_triggered_turn_index": None,
                "created_turn_index": created_turn_index,
                "st_extensions": dict(data.st_extensions) if getattr(data, "st_extensions", None) else {},
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
    cursor = _coll().find({"character_id": character_id, "is_active": True}).sort("trigger_count", -1).limit(limit)
    return [LorebookEntry(**d) for d in cursor]


# ---------------------------------------------------------------------------
# Scan config persistence
# ---------------------------------------------------------------------------


def mongodb_get_scan_config(character_id: str) -> LorebookScanConfig:
    """Return persisted scan config for a character, or defaults."""
    doc = _config_coll().find_one({"character_id": character_id})
    if not doc:
        return LorebookScanConfig()
    return LorebookScanConfig(**{k: v for k, v in doc.items() if k != "_id"})


def mongodb_save_scan_config(character_id: str, config: LorebookScanConfig) -> LorebookScanConfig:
    """Persist scan config for a character."""
    payload = config.model_dump()
    payload["character_id"] = character_id
    _config_coll().replace_one(
        {"character_id": character_id},
        payload,
        upsert=True,
    )
    log.info("lorebook_scan_config_saved", character_id=character_id)
    return config
