"""Game system schema filtering — NPC stats, category headers, prompt echoes."""

from __future__ import annotations

from typing import Any

from monitor_agents.utils.analyzer_support._constants import (
    _CATEGORY_HEADER_NAMES,
    _NPC_STAT_PATTERNS,
    _PLACEHOLDER_SCHEMA_NAMES,
    _PROMPT_ECHO_PATTERN,
)

# ---------------------------------------------------------------------------
# Simple predicate filters
# ---------------------------------------------------------------------------


def is_npc_stat_name(name: str) -> bool:
    """Return True if the name looks like it comes from an NPC/creature stat block.

    PRE-FILTER, not a gameplay decision — see
    ``docs/architecture/DE_HEURISTIC_PRINCIPLE.md``. Runs during schema
    extraction before the LLM dedup/canonicalization pass. The downstream LLM
    is the actual decision-maker; this just narrows what we send it.
    """
    return bool(_NPC_STAT_PATTERNS.search(name))


def is_category_header(name: str) -> bool:
    """Return True if the name is a category heading, not an actual attribute/skill."""
    return name.lower().strip() in _CATEGORY_HEADER_NAMES


def is_prompt_echo(name: str) -> bool:
    """Return True if the name looks like an echoed prompt question, not a real field."""
    n = name.strip()
    if len(n) > 50:
        return True
    return bool(_PROMPT_ECHO_PATTERN.search(n))


# ---------------------------------------------------------------------------
# Helper for Pydantic / dict field access
# ---------------------------------------------------------------------------


def _get_field(obj: Any, field: str, default: Any = "") -> Any:
    """Get a field from either a Pydantic model or a dict."""
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


# ---------------------------------------------------------------------------
# Player-facing attribute/skill/resource filters
# ---------------------------------------------------------------------------


def filter_player_attributes(
    attributes: list[Any],
) -> list[Any]:
    """Remove NPC stats, category headers, and prompt echoes from an attribute list."""
    filtered: list[Any] = []
    seen: set[str] = set()
    for attr in attributes:
        name = str(_get_field(attr, "name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in _PLACEHOLDER_SCHEMA_NAMES or key in seen:
            continue
        if is_category_header(name):
            continue
        if is_npc_stat_name(name):
            continue
        if is_prompt_echo(name):
            continue
        abbr = str(_get_field(attr, "abbreviation", "")).strip().upper()
        if abbr and any(str(_get_field(existing, "abbreviation", "")).strip().upper() == abbr for existing in filtered):
            continue
        seen.add(key)
        filtered.append(attr)
    return filtered


def filter_player_skills(
    skills: list[Any],
) -> list[Any]:
    """Remove NPC-only skills, 'N/A' entries, prompt echoes, and category headers from a skills list."""
    filtered: list[Any] = []
    seen: set[str] = set()
    for skill in skills:
        name = str(_get_field(skill, "name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in _PLACEHOLDER_SCHEMA_NAMES or key in seen:
            continue
        if key in {"n/a", "na", "none", "---", "-"}:
            continue
        if is_category_header(name):
            continue
        if is_npc_stat_name(name):
            continue
        if is_prompt_echo(name):
            continue
        seen.add(key)
        filtered.append(skill)
    return filtered


def filter_player_resources(
    resources: list[Any],
) -> list[Any]:
    """Remove NPC-only resources, prompt echoes, and category headers from a resources list."""
    filtered: list[Any] = []
    seen: set[str] = set()
    for res in resources:
        name = str(_get_field(res, "name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in _PLACEHOLDER_SCHEMA_NAMES or key in seen:
            continue
        if is_npc_stat_name(name):
            continue
        if is_prompt_echo(name):
            continue
        seen.add(key)
        filtered.append(res)
    return filtered
