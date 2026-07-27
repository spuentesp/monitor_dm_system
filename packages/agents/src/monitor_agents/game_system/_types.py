"""Shared types for game_system sub-modules — data container and lookup maps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SystemData:
    """Immutable snapshot of a game system document.

    Every sub-module function receives this instead of ``self.*`` attrs.
    Constructed once by ``GameSystemRuntime.__init__``.
    """

    doc: dict[str, Any]
    attrs: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    skills: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    core: dict[str, Any]
    char_creation: dict[str, Any]
    tracks: list[dict[str, Any]]
    tiered_abilities: list[dict[str, Any]]
    damage_model: dict[str, Any] | None
    conditions: list[dict[str, Any]]
    scenery_rules: list[dict[str, Any]]
    action_economy: dict[str, Any] | None
    advancement: dict[str, Any] | None
    recovery: dict[str, Any] | None
    resolution_mechanics: list[dict[str, Any]]

    # Pre-built lookup maps
    attr_by_abbr: dict[str, dict[str, Any]] = field(default_factory=dict)
    track_by_name: dict[str, dict[str, Any]] = field(default_factory=dict)
    condition_by_name: dict[str, dict[str, Any]] = field(default_factory=dict)
    tiered_by_name: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Action routing is semantic (embeddings) — see ``_action_routing`` — so no
    # keyword route tables are precomputed here anymore.

    @property
    def primary_attributes(self) -> list[dict[str, Any]]:
        """Return deduplicated primary attribute list (one per abbreviation)."""
        return list(self.attr_by_abbr.values())


# ---------------------------------------------------------------------------
# Factory — builds SystemData from a raw game_systems MongoDB document
# ---------------------------------------------------------------------------


def _build_attr_by_abbr(attrs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index attributes by their abbreviation (upper-cased)."""
    result: dict[str, dict[str, Any]] = {}
    for a in attrs:
        abbr = (a.get("abbreviation") or a.get("name", "?")[:4]).upper()
        result[abbr] = a
    return result


def _build_named_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index a list of dicts by their ``name`` field (lower-cased)."""
    return {(i.get("name") or "").lower(): i for i in items if i.get("name")}


def build_system_data(doc: dict[str, Any]) -> SystemData:
    """Extract and index all sections from a ``game_systems`` document."""
    attrs = doc.get("attributes") or []
    skills = doc.get("skills") or []
    rules = doc.get("rules") or []
    tracks = doc.get("tracks") or []
    conditions = doc.get("conditions") or []
    scenery_rules = doc.get("scenery_rules") or []
    tiered = doc.get("tiered_abilities") or []

    attr_by_abbr = _build_attr_by_abbr(attrs)

    return SystemData(
        doc=doc,
        attrs=attrs,
        resources=doc.get("resources") or [],
        skills=skills,
        rules=rules,
        core=doc.get("core_mechanic") or {},
        char_creation=doc.get("character_creation") or {},
        tracks=tracks,
        tiered_abilities=tiered,
        damage_model=doc.get("damage_model"),
        conditions=conditions,
        scenery_rules=scenery_rules,
        action_economy=doc.get("action_economy"),
        advancement=doc.get("advancement"),
        recovery=doc.get("recovery"),
        resolution_mechanics=doc.get("resolution_mechanics") or [],
        attr_by_abbr=attr_by_abbr,
        track_by_name=_build_named_index(tracks),
        condition_by_name=_build_named_index(conditions),
        tiered_by_name=_build_named_index(tiered),
    )
