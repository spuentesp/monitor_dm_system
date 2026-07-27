"""Narrator — modifier calculation and narrator context compaction.

All functions are pure: they receive a ``SystemData`` snapshot
(and any extra parameters) and return plain data structures.
"""

from __future__ import annotations

from typing import Any

from ._char_generation import _skill_description_for_attr, ability_method_description
from ._types import SystemData

# ---------------------------------------------------------------------------
# Modifier calculation (schema-driven)
# ---------------------------------------------------------------------------


def calc_modifier(sd: SystemData, stat_abbr: str, stat_value: int) -> int:
    """Return the roll modifier for *stat_abbr* with *stat_value*.

    Uses ``modifier_formula`` from the attribute definition if present.
    Heuristic when not present:
      - If the attribute's range is <= 10 wide -> stat value IS the modifier.
      - Otherwise -> generic (value - 10) // 2 (D&D style).
    """
    attr = sd.attr_by_abbr.get(stat_abbr.upper())
    if attr:
        formula = attr.get("modifier_formula")
        if formula:
            try:
                from monitor_data.utils.dice import calculate_modifier

                return calculate_modifier(stat_value, formula.replace("VALUE", str(stat_value)))
            except Exception:
                pass
        width = attr.get("max_value", 20) - attr.get("min_value", 0)
        if width <= 10:
            return stat_value

    try:
        from monitor_data.utils.dice import calculate_modifier

        return calculate_modifier(stat_value, "(VALUE - 10) // 2")
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Narrator injection
# ---------------------------------------------------------------------------


def compact_for_narrator(sd: SystemData) -> dict[str, Any]:
    """Build the compact dict injected into the Narrator's system context."""
    attrs = [
        {
            "abbr": (a.get("abbreviation") or a.get("name", "?")[:4]).upper(),
            "name": a.get("name"),
            "use": a.get("description") or _skill_description_for_attr(sd, (a.get("abbreviation") or "").upper()),
        }
        for a in sd.primary_attributes
    ]

    core = sd.core
    core_mechanic_text = (
        f"Roll {core.get('formula', '1d20')} \u2014 "
        f"success type: {core.get('success_type', 'meet_or_beat')}. "
        + (f"Critical success: {core['critical_success']}. " if core.get("critical_success") else "")
        + (f"Critical failure: {core['critical_failure']}." if core.get("critical_failure") else "")
    ).strip()

    key_rules = [
        {
            "name": r["name"],
            "desc": (r.get("description") or "")[:200],
            "formula": r.get("formula") or "",
        }
        for r in sd.rules
        if r.get("rule_type") in ("mechanic", "condition", "combat")
    ][:10]

    resource_abbrs = [
        (r.get("abbreviation") or r.get("name", "?")[:4]).upper()
        for r in sd.resources
        if r.get("abbreviation") or r.get("name")
    ]

    tracks_summary = []
    for track in sd.tracks:
        thresholds = track.get("threshold_effects") or []
        tracks_summary.append(
            {
                "name": track.get("name"),
                "type": track.get("track_type"),
                "thresholds": [
                    {
                        "at": t.get("value", t.get("threshold")),
                        "direction": t.get("direction", "at_or_below"),
                        "effect": (t.get("effect") or t.get("label") or "")[:100],
                    }
                    for t in thresholds
                ],
                "depleted": (track.get("depleted_effect") or "")[:100] if track.get("depleted_effect") else None,
                "maxed": (track.get("maxed_effect") or "")[:100] if track.get("maxed_effect") else None,
            }
        )

    conditions_summary = [
        {
            "name": c.get("name"),
            "trigger": (c.get("trigger") or "")[:120],
            "effects": (c.get("mechanical_effects") or "")[:120],
            "ends": (c.get("ends_when") or "")[:80],
        }
        for c in sd.conditions
    ]

    damage_summary: dict[str, Any] = {}
    if sd.damage_model:
        damage_summary = {
            "types": [dt.get("name") for dt in (sd.damage_model.get("damage_types") or [])],
            "track": sd.damage_model.get("damage_track"),
            "incapacitated_at": sd.damage_model.get("incapacitated_at"),
            "death": sd.damage_model.get("death_condition"),
        }

    tiered_summary = [
        {
            "name": tas.get("name"),
            "category": tas.get("parent_category"),
            "max_tier": tas.get("max_tier"),
            "acquisition": (tas.get("acquisition_rule") or "")[:100],
            "restriction": (tas.get("access_restriction") or "")[:100],
        }
        for tas in sd.tiered_abilities
    ]

    action_economy_summary: dict[str, Any] = {}
    if sd.action_economy:
        action_economy_summary = {
            "action_types": [
                {"name": at.get("name"), "count": at.get("count_per_turn")}
                for at in (sd.action_economy.get("action_types") or [])
            ],
            "initiative": sd.action_economy.get("initiative_model"),
        }

    return {
        "name": sd.doc.get("name", "Unknown System"),
        "core_mechanic": core_mechanic_text,
        "stats": attrs,
        "character_creation_method": ability_method_description(sd),
        "resources": resource_abbrs,
        "tracks": tracks_summary,
        "conditions": conditions_summary,
        "damage_model": damage_summary or None,
        "tiered_abilities": tiered_summary,
        "action_economy": action_economy_summary or None,
        "key_rules": key_rules,
    }
