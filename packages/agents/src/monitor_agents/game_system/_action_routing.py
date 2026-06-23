"""Action routing — infer which stat/subsystem an action targets.

All functions are pure: they receive a ``SystemData`` snapshot
(and any extra parameters) and return plain data structures.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from monitor_agents.utils.runtime_profile_support import (
    expand_query_with_profile,
    normalize_source_profile,
)

from ._constants import SOCIAL_SIGNALS, SHIP_SIGNALS, COMBAT_SIGNALS
from ._types import SystemData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Route builders (called once at construction)
# ---------------------------------------------------------------------------


def build_skill_routes(sd: SystemData) -> List[Tuple[List[str], str, int, str]]:
    """Build keyword routing table from the skills schema."""
    routes: List[Tuple[List[str], str, int, str]] = []

    name_to_abbr: Dict[str, str] = {}
    for attr in sd.attrs:
        aname = (attr.get("name") or "").lower()
        abbr = (attr.get("abbreviation") or attr.get("name", "")[:4]).upper()
        if aname:
            name_to_abbr[aname] = abbr

    for skill in sd.skills:
        linked = (skill.get("linked_attribute") or "").strip()
        abbr = name_to_abbr.get(linked.lower()) or linked.upper()[:4]
        if not abbr:
            continue

        skill_name = skill.get("name") or ""
        skill_desc = skill.get("description") or ""
        keywords = _tokenize_route_keywords(f"{skill_name} {skill_desc}")
        if not keywords:
            continue

        atype = (
            "dialogue"
            if SOCIAL_SIGNALS.search(skill_name) or SOCIAL_SIGNALS.search(skill_desc)
            else "action"
        )
        attr_def = sd.attr_by_abbr.get(abbr, {})
        dc = 12 if (attr_def.get("max_value", 20) - attr_def.get("min_value", 0)) <= 10 else 13
        routes.append((keywords, abbr, dc, atype))

    return routes


def build_attribute_routes(sd: SystemData) -> List[Tuple[List[str], str, int, str]]:
    """Build fallback routing hints directly from attribute names/descriptions."""
    routes: List[Tuple[List[str], str, int, str]] = []
    for attr in sd.primary_attributes:
        abbr = (attr.get("abbreviation") or attr.get("name", "STAT")[:4]).upper()
        combined = f"{attr.get('name', '')} {attr.get('description', '')}"
        keywords = _tokenize_route_keywords(combined)
        if not keywords:
            continue
        width = attr.get("max_value", 20) - attr.get("min_value", 0)
        dc = 12 if width <= 10 else 13
        atype = "dialogue" if SOCIAL_SIGNALS.search(combined) else "action"
        routes.append((keywords, abbr, dc, atype))
    return routes


def build_rule_subject_routes(sd: SystemData) -> List[Tuple[List[str], str]]:
    """Build lightweight subsystem routing hints from the rules schema."""
    routes: List[Tuple[List[str], str]] = []
    for rule in sd.rules:
        subject = str(rule.get("applies_to_subject") or "").strip().lower() or "character"
        combined = f"{rule.get('name', '')} {rule.get('description', '')} {subject}"
        keywords = _tokenize_route_keywords(combined)
        if keywords:
            routes.append((keywords, subject))
    return routes


# ---------------------------------------------------------------------------
# Public routing API
# ---------------------------------------------------------------------------


def infer_action_context(
    sd: SystemData,
    user_input: str,
    source_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return action routing details including subsystem hints for the input."""
    query = user_input or ""
    expanded_text = expand_query_with_profile(query, query, source_profile or {}, limit=16).lower()

    for routes in (sd.skill_routes, sd.attribute_routes):
        for keywords, abbr, dc, atype in routes:
            if any(kw in expanded_text for kw in keywords):
                subsystem_hint = infer_subsystem_hint(sd, query, source_profile=source_profile)
                if subsystem_hint is None and atype == "dialogue":
                    subsystem_hint = "social"
                return {
                    "action_type": atype,
                    "stat_name": abbr,
                    "difficulty_class": dc,
                    "subsystem_hint": subsystem_hint,
                }

    if SOCIAL_SIGNALS.search(expanded_text):
        social_abbr = _preferred_social_attr(sd)
        if social_abbr:
            attr_def = sd.attr_by_abbr.get(social_abbr, {})
            width = attr_def.get("max_value", 20) - attr_def.get("min_value", 0)
            dc = 12 if width <= 10 else 13
            return {
                "action_type": "dialogue",
                "stat_name": social_abbr,
                "difficulty_class": dc,
                "subsystem_hint": "social",
            }

    first = sd.primary_attributes
    if first:
        abbr = (first[0].get("abbreviation") or first[0].get("name", "STAT")[:4]).upper()
        return {
            "action_type": "action",
            "stat_name": abbr,
            "difficulty_class": 12,
            "subsystem_hint": infer_subsystem_hint(sd, query, source_profile=source_profile),
        }

    return {
        "action_type": "action",
        "stat_name": "STR",
        "difficulty_class": 12,
        "subsystem_hint": infer_subsystem_hint(sd, query, source_profile=source_profile),
    }


def infer_action_stat(
    sd: SystemData,
    user_input: str,
    source_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, int]:
    """Backward-compatible tuple wrapper around ``infer_action_context()``."""
    routed = infer_action_context(sd, user_input, source_profile=source_profile)
    return (
        str(routed.get("action_type", "action")),
        str(routed.get("stat_name", "STR")),
        int(routed.get("difficulty_class", 12)),
    )


def infer_subsystem_hint(
    sd: SystemData,
    user_input: str,
    source_profile: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Infer the most likely rule family/subsystem for the current action."""
    query = user_input or ""
    expanded_text = expand_query_with_profile(query, query, source_profile or {}, limit=16).lower()

    for keywords, subject in sd.rule_subject_routes:
        if any(kw in expanded_text for kw in keywords):
            return str(subject)

    profile = normalize_source_profile(source_profile or {})
    for name in profile.get("important_named_sets", []):
        lowered = str(name).lower()
        if lowered and lowered in expanded_text:
            if "ship" in lowered:
                return "ship"
            if "social" in lowered or "duel" in lowered:
                return "social"

    if SHIP_SIGNALS.search(expanded_text):
        return "ship"
    if SOCIAL_SIGNALS.search(expanded_text):
        return "social"
    if COMBAT_SIGNALS.search(expanded_text):
        return "combat"
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tokenize_route_keywords(text: str) -> List[str]:
    """Extract meaningful routing keywords from schema text."""
    stopwords = {
        "with",
        "that",
        "this",
        "from",
        "have",
        "been",
        "used",
        "and",
        "for",
        "the",
        "use",
        "can",
        "their",
        "they",
        "other",
        "some",
        "into",
        "ability",
        "skill",
        "tasks",
        "task",
        "combat",
        "competency",
        "during",
        "scene",
        "scenes",
        "action",
        "actions",
        "rules",
        "system",
    }
    return [
        word for word in re.findall(r"[a-z]{3,}", (text or "").lower()) if word not in stopwords
    ]


def _preferred_social_attr(sd: SystemData) -> Optional[str]:
    """Return the best social-facing attribute abbreviation if the schema exposes one."""
    for attr in sd.primary_attributes:
        combined = f"{attr.get('name', '')} {attr.get('description', '')}"
        if SOCIAL_SIGNALS.search(combined):
            return str(attr.get("abbreviation") or attr.get("name", "STAT")[:4]).upper()
    return None
