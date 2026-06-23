"""Shared types for game_system sub-modules — data container and lookup maps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SystemData:
    """Immutable snapshot of a game system document.

    Every sub-module function receives this instead of ``self.*`` attrs.
    Constructed once by ``GameSystemRuntime.__init__``.
    """

    doc: Dict[str, Any]
    attrs: List[Dict[str, Any]]
    resources: List[Dict[str, Any]]
    skills: List[Dict[str, Any]]
    rules: List[Dict[str, Any]]
    core: Dict[str, Any]
    char_creation: Dict[str, Any]
    tracks: List[Dict[str, Any]]
    tiered_abilities: List[Dict[str, Any]]
    damage_model: Optional[Dict[str, Any]]
    conditions: List[Dict[str, Any]]
    scenery_rules: List[Dict[str, Any]]
    action_economy: Optional[Dict[str, Any]]
    advancement: Optional[Dict[str, Any]]
    recovery: Optional[Dict[str, Any]]
    resolution_mechanics: List[Dict[str, Any]]

    # Pre-built lookup maps
    attr_by_abbr: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    track_by_name: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    condition_by_name: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tiered_by_name: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Pre-built routing tables
    skill_routes: List[tuple[list[str], str, int, str]] = field(default_factory=list)
    attribute_routes: List[tuple[list[str], str, int, str]] = field(default_factory=list)
    rule_subject_routes: List[tuple[list[str], str]] = field(default_factory=list)

    @property
    def primary_attributes(self) -> List[Dict[str, Any]]:
        """Return deduplicated primary attribute list (one per abbreviation)."""
        return list(self.attr_by_abbr.values())


# ---------------------------------------------------------------------------
# Factory — builds SystemData from a raw game_systems MongoDB document
# ---------------------------------------------------------------------------


def _build_attr_by_abbr(attrs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index attributes by their abbreviation (upper-cased)."""
    result: Dict[str, Dict[str, Any]] = {}
    for a in attrs:
        abbr = (a.get("abbreviation") or a.get("name", "?")[:4]).upper()
        result[abbr] = a
    return result


def _build_named_index(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index a list of dicts by their ``name`` field (lower-cased)."""
    return {(i.get("name") or "").lower(): i for i in items if i.get("name")}


def build_system_data(doc: Dict[str, Any]) -> SystemData:
    """Extract and index all sections from a ``game_systems`` document."""
    attrs = doc.get("attributes") or []
    skills = doc.get("skills") or []
    rules = doc.get("rules") or []
    tracks = doc.get("tracks") or []
    conditions = doc.get("conditions") or []
    scenery_rules = doc.get("scenery_rules") or []
    tiered = doc.get("tiered_abilities") or []

    attr_by_abbr = _build_attr_by_abbr(attrs)

    # Build routing tables using the same logic as _action_routing
    from ._action_routing import (
        build_skill_routes,
        build_attribute_routes,
        build_rule_subject_routes,
    )

    sd_partial = SystemData(
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

    # Build routing tables with the partial SD (routes don't depend on routes)
    skill_routes = build_skill_routes(sd_partial)
    attribute_routes = build_attribute_routes(sd_partial)
    rule_subject_routes = build_rule_subject_routes(sd_partial)

    # Reconstruct with routing tables included
    return SystemData(
        doc=doc,
        attrs=attrs,
        resources=sd_partial.resources,
        skills=skills,
        rules=rules,
        core=sd_partial.core,
        char_creation=sd_partial.char_creation,
        tracks=tracks,
        tiered_abilities=tiered,
        damage_model=sd_partial.damage_model,
        conditions=conditions,
        scenery_rules=scenery_rules,
        action_economy=sd_partial.action_economy,
        advancement=sd_partial.advancement,
        recovery=sd_partial.recovery,
        resolution_mechanics=sd_partial.resolution_mechanics,
        attr_by_abbr=attr_by_abbr,
        track_by_name=sd_partial.track_by_name,
        condition_by_name=sd_partial.condition_by_name,
        tiered_by_name=sd_partial.tiered_by_name,
        skill_routes=skill_routes,
        attribute_routes=attribute_routes,
        rule_subject_routes=rule_subject_routes,
    )
