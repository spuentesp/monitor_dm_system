"""Character generation — rolling, formatting, and NPC creation.

All functions are pure: they receive a ``SystemData`` snapshot
(and any extra parameters) and return plain data structures.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from ._types import SystemData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def roll_character(sd: SystemData) -> Dict[str, Any]:
    """Roll a complete new character using the system's attribute generation rules.

    Returns a dict::

        {
            "stats":        {abbr: value, ...},
            "derived":      {resource_abbr: value, ...},
            "rolls_detail": {abbr: human-readable roll string, ...},
            "system_name":  str,
        }
    """
    from monitor_data.utils.dice import roll_dice

    formula = _ability_roll_formula(sd)

    stats: Dict[str, int] = {}
    rolls_detail: Dict[str, str] = {}

    for attr in sd.primary_attributes:
        abbr = (attr.get("abbreviation") or attr.get("name", "?")[:3]).upper()
        min_val = attr.get("min_value", 0)
        max_val = attr.get("max_value", 20)

        try:
            result = roll_dice(formula)
            raw = result.total
            value = max(min_val, min(max_val, raw))
            roll_str = f"{formula}({','.join(str(r) for r in result.rolls)}) = {value}"
        except Exception as exc:  # noqa: BLE001
            logger.debug("roll_character: roll failed for %s using %s: %s", abbr, formula, exc)
            value = attr.get("default_value", 0)
            roll_str = f"default = {value}"

        stats[abbr] = value
        rolls_detail[abbr] = roll_str

    derived = _derive_resources(sd, stats)
    for rname, rval in derived.items():
        abbr_r = _resource_abbr(sd, rname)
        detail = _resource_formula_str(sd, rname, stats)
        rolls_detail[abbr_r] = detail

    return {
        "stats": stats,
        "derived": derived,
        "rolls_detail": rolls_detail,
        "system_name": sd.doc.get("name", "Unknown System"),
    }


def format_character_sheet(
    sd: SystemData,
    rolled: Dict[str, Any],
) -> str:
    """Render a character sheet as a Markdown string (stats only)."""
    stats = rolled.get("stats", {})
    derived = rolled.get("derived", {})
    rd = rolled.get("rolls_detail", {})

    lines = ["**Your starting attributes:**\n"]

    for attr in sd.primary_attributes:
        abbr = (attr.get("abbreviation") or attr.get("name", "?")[:3]).upper()
        name = attr.get("name", abbr)
        desc = attr.get("description") or _skill_description_for_attr(sd, abbr)
        val = stats.get(abbr, 0)
        roll_str = rd.get(abbr, "")
        sign = f"+{val}" if val >= 0 else str(val)
        desc_part = f" — {desc}" if desc else ""
        lines.append(f"  **{abbr}** ({name}{desc_part}): `{sign}`  _{roll_str}_")

    if derived:
        lines.append("\n**Derived:**")
        for rname, rval in derived.items():
            abbr_r = _resource_abbr(sd, rname)
            formula_str = rd.get(abbr_r, "")
            lines.append(f"  **{abbr_r}** ({rname}): {rval}  _{formula_str}_")

    return "\n".join(lines)


def build_character_candidate(
    sd: SystemData,
    name: str = "Test Character",
    description: str = "",
    concept: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a structured playable character preview ready for UI or persistence."""
    rolled = roll_character(sd)
    return {
        "kind": "pc",
        "name": name or "Test Character",
        "description": description or concept or "",
        "concept": concept or description or "",
        "system_name": rolled.get("system_name", sd.doc.get("name", "Unknown System")),
        "attributes": rolled.get("stats", {}),
        "resources": rolled.get("derived", {}),
        "skills": {},
        "rolls_detail": rolled.get("rolls_detail", {}),
        "sheet": format_character_sheet(sd, rolled),
        "special_abilities": [],
        "tags": ["pc", "generated"],
        "source": "runtime_roll",
    }


def generate_npc(
    sd: SystemData,
    name: Optional[str] = None,
    tier: Optional[str] = None,
    concept: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a structured NPC preview using embedded stat blocks when available."""
    blocks = sd.doc.get("npc_stat_blocks") or []
    chosen: Dict[str, Any] | None = None
    desired_tier = (tier or "").strip().lower()

    if desired_tier:
        for block in blocks:
            if str(block.get("tier", "")).lower() == desired_tier:
                chosen = block
                break
    if chosen is None and blocks:
        chosen = blocks[0]

    if chosen is not None:
        npc_name = name or chosen.get("name") or "Test NPC"
        attributes = dict(chosen.get("attributes") or {})
        resources: Dict[str, Any] = {}
        if chosen.get("hp") is not None:
            resources["HP"] = chosen.get("hp")
        if chosen.get("defense") is not None:
            resources["DEF"] = chosen.get("defense")

        lines = [f"**{npc_name}** — {str(chosen.get('tier', 'standard')).title()} NPC\n"]
        if concept:
            lines.append(f"_{concept}_\n")
        if attributes:
            lines.append("**Attributes:**")
            for abbr, value in attributes.items():
                lines.append(f"- **{abbr}**: {value}")
        if resources:
            lines.append("\n**Resources:**")
            for key, value in resources.items():
                lines.append(f"- **{key}**: {value}")
        if chosen.get("special_abilities"):
            lines.append("\n**Special abilities:**")
            lines.extend(f"- {ability}" for ability in chosen.get("special_abilities", []))

        tags = list(dict.fromkeys([*(chosen.get("tags") or []), "npc", "generated"]))
        return {
            "kind": "npc",
            "name": npc_name,
            "description": concept or "",
            "concept": concept or "",
            "system_name": sd.doc.get("name", "Unknown System"),
            "tier": str(chosen.get("tier", "standard")),
            "attributes": attributes,
            "resources": resources,
            "skills": {},
            "attacks": chosen.get("attacks", []),
            "special_abilities": chosen.get("special_abilities", []),
            "tags": tags,
            "sheet": "\n".join(lines),
            "source": "npc_stat_block",
        }

    fallback = build_character_candidate(
        sd,
        name=name or "Test NPC",
        description=concept or "",
        concept=concept,
    )
    fallback["kind"] = "npc"
    fallback["tags"] = ["npc", "generated"]
    fallback["source"] = "runtime_roll"
    fallback["tier"] = desired_tier or "standard"
    return fallback


def ability_method_description(sd: SystemData) -> str:
    """Return a one-sentence description of how ability scores are generated."""
    cc = sd.char_creation
    if isinstance(cc, dict):
        agen = cc.get("ability_score_generation") or {}
        method = agen.get("method") or ""
        formula = agen.get("roll_formula") or ""
        if method and formula:
            return (
                f"Attributes are generated by {method.replace('_', ' ')} "
                f"using the formula: {formula}."
            )
        if method:
            return f"Attributes are generated by {method.replace('_', ' ')}."

    for rule in sd.rules:
        rname = (rule.get("name") or "").lower()
        if "abilit" in rname or "generation" in rname:
            return (rule.get("description") or "")[:200]

    return ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ability_roll_formula(sd: SystemData) -> str:
    """Determine the dice formula for rolling one ability score."""
    cc = sd.char_creation
    if isinstance(cc, dict):
        agen = cc.get("ability_score_generation") or {}
        f = agen.get("roll_formula") or ""
        if f and re.search(r"\d*d\d+", f, re.IGNORECASE):
            return f.strip()

    dice_re = re.compile(r"\d*d\d+", re.IGNORECASE)
    for rule in sd.rules:
        rname = (rule.get("name") or "").lower()
        if "abilit" in rname or "stat" in rname or "attribute" in rname:
            formula = rule.get("formula") or rule.get("description") or ""
            m = dice_re.search(formula)
            if m:
                return m.group(0)

    cm_formula = sd.core.get("formula") or ""
    m = dice_re.search(cm_formula)
    if m:
        return m.group(0)

    return "1d6"


def _derive_resources(sd: SystemData, stats: Dict[str, int]) -> Dict[str, int]:
    """Calculate derived resource values from rolled stats using formulas in the schema."""
    from monitor_data.utils.dice import roll_dice

    derived: Dict[str, int] = {}

    from ._narrator import calc_modifier as _calc_modifier

    # Pre-compute attribute modifiers so formulas like "10 + Grit_modifier"
    # resolve from the system's modifier_formula instead of a hardcoded curve.
    modifiers: Dict[str, int] = {}
    for attr in sd.primary_attributes:
        abbr = (attr.get("abbreviation") or attr.get("name", "?")[:3]).upper()
        name = (attr.get("name") or abbr).upper()
        if abbr in stats:
            mod = _calc_modifier(sd, abbr, stats[abbr])
            modifiers[f"{abbr}_MODIFIER"] = mod
            modifiers[f"{name}_MODIFIER"] = mod

    for res in sd.resources:
        abbr = (res.get("abbreviation") or res.get("name", "?")[:4]).upper()
        formula = res.get("calculation") or ""

        if not formula:
            formula = _find_resource_formula(sd, res.get("name") or abbr, stats)

        if not formula:
            continue

        try:
            resolved = formula.upper()
            # Substitute "<ATTR>_MODIFIER" tokens before raw stat values so the
            # trailing "_MODIFIER" is not left dangling as an unknown name.
            for token, mod in modifiers.items():
                resolved = re.sub(rf"\b{re.escape(token)}\b", str(mod), resolved)
            for stat_abbr, val in stats.items():
                resolved = re.sub(rf"\b{re.escape(stat_abbr)}\b", str(val), resolved)

            dice_match = re.search(r"\d*d\d+", resolved, re.IGNORECASE)
            if dice_match:
                roll_result = roll_dice(dice_match.group(0))
                resolved = resolved.replace(dice_match.group(0), str(roll_result.total))

            value = int(eval(resolved, {"__builtins__": {}}, {}))  # noqa: S307
            derived[res.get("name") or abbr] = value
        except Exception:  # noqa: BLE001
            pass

    return derived


def _find_resource_formula(sd: SystemData, resource_name: str, stats: Dict[str, int]) -> str:
    """Search rules for an initial-value formula for the given resource."""
    rname_lower = resource_name.lower()
    for rule in sd.rules:
        rule_name = (rule.get("name") or "").lower()
        rule_desc = (rule.get("description") or "").lower()
        if rname_lower in rule_name or rname_lower in rule_desc:
            formula = rule.get("formula") or ""
            if formula and re.search(r"\d*d\d+|[+\-*/]", formula):
                return formula
    return ""


def _resource_abbr(sd: SystemData, resource_name: str) -> str:
    for res in sd.resources:
        if res.get("name") == resource_name:
            return (res.get("abbreviation") or resource_name[:4]).upper()
    return resource_name[:4].upper()


def _resource_formula_str(sd: SystemData, resource_name: str, stats: Dict[str, int]) -> str:
    for res in sd.resources:
        if res.get("name") == resource_name:
            formula = res.get("calculation") or ""
            if formula:
                return formula
    return ""


def _skill_description_for_attr(sd: SystemData, abbr: str) -> str:
    """Collect skill descriptions linked to this attribute as a summary."""
    parts: list[str] = []
    for skill in sd.skills:
        linked = (skill.get("linked_attribute") or "").strip().upper()
        skill_abbr = linked[: len(abbr)]
        if linked == abbr or skill_abbr == abbr:
            parts.append(skill.get("name") or "")
    return ", ".join(p for p in parts if p)[:120]
