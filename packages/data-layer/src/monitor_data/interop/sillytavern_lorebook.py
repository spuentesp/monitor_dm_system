"""
SillyTavern / character.ai lorebook format interop.

Supports:
  - Standalone SillyTavern World Info JSON (entries as dict keyed by index
    or as a list).
  - ``character_book`` embedded in chara_card_v2 and chara_card_v3 cards.
  - RisuAI ccv3 ``character_book`` shape.

All recognized fields are mapped onto ``LorebookEntryCreate``. Unmapped fields
are preserved in ``st_extensions`` so an export back to ST stays lossless.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from monitor_data.schemas.lorebook import LorebookEntryCreate, LorebookScanConfig, SelectiveLogic


# ---------------------------------------------------------------------------
# ST field names → MONITOR field names (single-value, non-list fields)
# ---------------------------------------------------------------------------

_ST_BOOL_FIELDS = {
    "constant": "constant",
    "selective": "selective",
    "useProbability": "use_probability",
    "caseSensitive": "case_sensitive",
    "matchWholeWords": "match_whole_words",
    "groupOverride": "group_override",
    "excludeRecursion": "exclude_recursion",
    "preventRecursion": "prevent_recursion",
    "vectorized": "vectorized",
}

_ST_INT_FIELDS = {
    "order": "order",
    "position": "position",
    "depth": "depth",
    "probability": "probability",
    "selectiveLogic": "selective_logic",
    "sticky": "sticky",
    "cooldown": "cooldown",
    "delay": "delay",
}

_ST_STRING_FIELDS = {
    "comment": "comment",
    "name": "comment",
    "group": "group",
}

_ST_LIST_FIELDS = {
    "keys": "keywords",
    "keysecondary": "secondary_keywords",
    "tags": "tags",
}

_KNOWN_ST_FIELDS = set(
    list(_ST_BOOL_FIELDS)
    + list(_ST_INT_FIELDS)
    + list(_ST_STRING_FIELDS)
    + list(_ST_LIST_FIELDS)
    + [
        "uid",
        "displayIndex",
        "addMemo",
        "enabled",
        "content",
        "id",
        "status",
        "count",
        "excludeRecursion",
        "preventRecursion",
    ]
)

# Fields that belong to the book-level config rather than individual entries.
_BOOK_CONFIG_FIELDS = {
    "scan_depth",
    "token_budget",
    "recursive_scanning",
    "recursiveScanning",
    "case_sensitive",
    "caseSensitive",
    "match_whole_words",
    "matchWholeWords",
    "include_names",
    "includeNames",
    "name",
    "description",
}


def _clean_keyword(keyword: Any) -> str:
    """ST keywords may arrive as strings; strip whitespace."""
    return str(keyword).strip()


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return bool(value)


def _coerce_int(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if low is not None:
        result = max(result, low)
    if high is not None:
        result = min(result, high)
    return result


def _snip(value: str, max_len: int) -> str:
    return value[:max_len] if len(value) > max_len else value


def parse_st_lorebook_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Convert a single ST World Info entry into a ``LorebookEntryCreate``-compatible dict.

    The returned dict still contains ``st_extensions`` and may be passed to
    ``LorebookEntryCreate(**...)`` or the bulk-create helpers.
    """
    out: dict[str, Any] = {
        "content": str(entry.get("content") or "").strip(),
        "st_extensions": {},
    }

    # Lists
    for st_key, monitor_key in _ST_LIST_FIELDS.items():
        raw = entry.get(st_key)
        if raw is None:
            out[monitor_key] = []
        elif isinstance(raw, list):
            out[monitor_key] = [_clean_keyword(k) for k in raw if k not in (None, "")]
        elif isinstance(raw, str):
            # ST sometimes stores comma-separated keywords.
            out[monitor_key] = [_clean_keyword(k) for k in raw.split(",") if k.strip()]
        else:
            out[monitor_key] = [_clean_keyword(raw)]

    # Strings
    for st_key, monitor_key in _ST_STRING_FIELDS.items():
        if st_key in entry:
            value = str(entry.get(st_key) or "").strip()
            if value:
                out[monitor_key] = value

    # Bools
    for st_key, monitor_key in _ST_BOOL_FIELDS.items():
        if st_key not in entry:
            continue
        out[monitor_key] = _to_bool(entry[st_key])

    # "disable" is an inverted is_active flag.
    if "disable" in entry:
        out["is_active"] = not _to_bool(entry["disable"])

    # Ints
    for st_key, monitor_key in _ST_INT_FIELDS.items():
        if st_key in entry:
            out[monitor_key] = _coerce_int(entry[st_key])

    # Special: selective logic default
    if "selective" in out and out["selective"] and "selective_logic" not in out:
        out["selective_logic"] = SelectiveLogic.AND_ANY

    # Special: disable -> is_active
    if "disable" in entry:
        out["is_active"] = not _to_bool(entry["disable"])

    # Content may be empty for some ST entries; skip them at import time.
    if not out["content"]:
        out["content"] = ""

    # Preserve unmapped fields for lossless round-trip.
    for key, value in entry.items():
        if key not in _KNOWN_ST_FIELDS:
            out["st_extensions"][key] = value

    # Trim comment length.
    if "comment" in out:
        out["comment"] = _snip(out["comment"], 200)

    # Default values for fields ST may omit.
    out.setdefault("order", 100)
    out.setdefault("position", 1)
    out.setdefault("depth", 4)
    out.setdefault("probability", 100)
    out.setdefault("selective_logic", SelectiveLogic.AND_ANY)
    out.setdefault("is_active", True)

    return out


def parse_st_lorebook_book(book: dict[str, Any]) -> tuple[list[dict[str, Any]], LorebookScanConfig]:
    """Parse a SillyTavern ``character_book`` / World Info book object.

    Returns a list of entry dicts and a scan-config extracted from book-level fields.
    """
    raw_entries: list[dict[str, Any]] = []
    entries_raw = book.get("entries")

    if isinstance(entries_raw, dict):
        # Standard ST export: {"entries": {"0": {...}, "1": {...}}}
        # Sort by the numeric key to preserve display order.
        def _sort_key(item: tuple[str, Any]) -> int:
            try:
                return int(item[0])
            except ValueError:
                return 0

        raw_entries = [entry for _, entry in sorted(entries_raw.items(), key=_sort_key)]
    elif isinstance(entries_raw, list):
        raw_entries = entries_raw
    else:
        raw_entries = []

    parsed: list[dict[str, Any]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        parsed_entry = parse_st_lorebook_entry(entry)
        if parsed_entry["content"]:
            parsed.append(parsed_entry)

    config = LorebookScanConfig()
    if "scan_depth" in book:
        config.scan_depth = _coerce_int(book["scan_depth"], default=2, low=0, high=100)
    if "token_budget" in book:
        config.token_budget = _coerce_int(book["token_budget"], default=500, low=0, high=10000)
    if "recursive_scanning" in book:
        config.recursive_scanning = _to_bool(book["recursive_scanning"])
    if "case_sensitive" in book:
        config.case_sensitive = _to_bool(book["case_sensitive"])
    if "match_whole_words" in book:
        config.match_whole_words = _to_bool(book["match_whole_words"])
    if "include_names" in book:
        config.include_names = _to_bool(book["include_names"])

    return parsed, config


def parse_st_lorebook_raw(raw: bytes | str | dict[str, Any]) -> tuple[list[dict[str, Any]], LorebookScanConfig]:
    """Parse raw bytes/string JSON or an already-loaded dict."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        data = raw

    if not isinstance(data, dict):
        raise ValueError("SillyTavern lorebook JSON must be an object.")

    # Could be a plain book object or a wrapper containing a book.
    for key in ("character_book", "world_info", "lorebook"):
        if isinstance(data.get(key), dict):
            return parse_st_lorebook_book(data[key])

    # chara_card_v2/v3 cards nest the book under data.character_book.
    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        for key in ("character_book", "world_info", "lorebook"):
            if isinstance(nested_data.get(key), dict):
                return parse_st_lorebook_book(nested_data[key])
        if isinstance(nested_data.get("entries"), (dict, list)):
            return parse_st_lorebook_book(nested_data)

    # If the top-level has "entries", treat it as the book itself.
    if isinstance(data.get("entries"), (dict, list)):
        return parse_st_lorebook_book(data)

    raise ValueError("No recognized lorebook structure found (expected 'entries' or 'character_book').")


def parse_character_book_from_card(card: dict[str, Any]) -> tuple[list[dict[str, Any]], LorebookScanConfig] | None:
    """Extract a ``character_book`` from a loaded chara_card_v2/v3 or RisuAI ccv3 card."""
    data = card.get("data") if isinstance(card.get("data"), dict) else card
    if not isinstance(data, dict):
        return None

    book = data.get("character_book")
    if not isinstance(book, dict):
        return None

    return parse_st_lorebook_book(book)


def build_st_lorebook_entry(entry: LorebookEntryCreate | BaseModel | dict[str, Any], uid: int) -> dict[str, Any]:
    """Serialize a MONITOR lorebook entry to ST World Info entry format."""
    if isinstance(entry, LorebookEntryCreate):
        data = entry.model_dump()
    elif isinstance(entry, BaseModel):
        data = entry.model_dump()
    else:
        data = dict(entry)

    st_extensions = dict(data.get("st_extensions") or {})

    out: dict[str, Any] = {
        "uid": uid,
        "displayIndex": uid,
        "comment": data.get("comment") or "",
        "content": data["content"],
        "constant": data.get("constant", False),
        "selective": data.get("selective", False),
        "selectiveLogic": data.get("selective_logic", SelectiveLogic.AND_ANY),
        "order": data.get("order", 100),
        "position": data.get("position", 1),
        "depth": data.get("depth", 4),
        "probability": data.get("probability", 100),
        "useProbability": data.get("use_probability", True),
        "disable": not data.get("is_active", True),
        "group": data.get("group") or "",
        "groupOverride": data.get("group_override", False),
        "sticky": data.get("sticky", 0),
        "cooldown": data.get("cooldown", 0),
        "delay": data.get("delay", 0),
        "excludeRecursion": data.get("exclude_recursion", False),
        "preventRecursion": data.get("prevent_recursion", False),
        "vectorized": data.get("vectorized", False),
        "caseSensitive": data.get("case_sensitive") if data.get("case_sensitive") is not None else False,
        "matchWholeWords": data.get("match_whole_words") if data.get("match_whole_words") is not None else False,
        "keys": list(data.get("keywords", [])),
        "keysecondary": list(data.get("secondary_keywords", [])),
        "addMemo": True,
    }

    # If explicit ST field values are present in extensions, let them win.
    out.update(st_extensions)
    return out


def build_st_lorebook(
    entries: Sequence[LorebookEntryCreate | BaseModel | dict[str, Any]],
    *,
    name: str = "MONITOR lorebook",
    description: str = "",
    config: LorebookScanConfig | None = None,
) -> dict[str, Any]:
    """Serialize entries to a SillyTavern World Info JSON object."""
    config = config or LorebookScanConfig()
    out_entries: dict[str, Any] = {}
    for idx, entry in enumerate(entries):
        out_entries[str(idx)] = build_st_lorebook_entry(entry, uid=idx)

    return {
        "name": name,
        "description": description,
        "scan_depth": config.scan_depth,
        "token_budget": config.token_budget,
        "recursive_scanning": config.recursive_scanning,
        "case_sensitive": config.case_sensitive,
        "match_whole_words": config.match_whole_words,
        "include_names": config.include_names,
        "entries": out_entries,
    }


def build_character_book(
    entries: Sequence[LorebookEntryCreate | BaseModel | dict[str, Any]],
    *,
    name: str = "",
    description: str = "",
    config: LorebookScanConfig | None = None,
) -> dict[str, Any]:
    """Build a ``character_book`` dict suitable for embedding in chara_card_v2."""
    book = build_st_lorebook(entries, name=name, description=description, config=config)
    return {
        "name": book["name"],
        "description": book["description"],
        "scan_depth": book["scan_depth"],
        "token_budget": book["token_budget"],
        "recursive_scanning": book["recursive_scanning"],
        "entries": book["entries"],
    }
