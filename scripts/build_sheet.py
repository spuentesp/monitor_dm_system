#!/usr/bin/env python3
"""
System-agnostic GM-assisted character-sheet builder.

Reads the allocation rules + valid options from ANY ingested game system
(attributes, skills, resources, and the system's character_creation steps),
then has the cheap LLM turn a concept into a validated NUMERICAL sheet.
Nothing about a specific ruleset is hardcoded.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import litellm

CHEAP_MODEL = "gemini/gemini-2.5-flash"


def _rules_text(gc: Dict[str, Any]) -> str:
    cc = gc.get("character_creation") or gc.get("char_creation") or {}
    out = []
    for s in cc.get("steps") or []:
        t = s.get("title") or s.get("step_type") or "step"
        instr = s.get("instructions") or ""
        if instr:
            out.append(f"- {t}: {instr}")
    return "\n".join(out) or "(no explicit creation procedure; allocate sensibly for the concept)"


def _names(items: Optional[List[Dict[str, Any]]]) -> List[str]:
    return [i.get("name") for i in (items or []) if i.get("name")]


def _resource_max(res: Dict[str, Any]) -> int:
    for k in ("max_value", "default_value", "starting_value"):
        v = res.get(k)
        if isinstance(v, (int, float)):
            return int(v)
    return 10


def build_sheet(
    *,
    name: str,
    concept: str,
    preferences: str,
    game_context: Dict[str, Any],
    special_options: Optional[Dict[str, List[str]]] = None,
    model: str = CHEAP_MODEL,
) -> Dict[str, Any]:
    """Build a validated numerical sheet for any system.

    ``special_options`` maps an extra category (e.g. "disciplines", "items",
    "void_powers") to its valid choices; the LLM rates/selects from them.
    """
    attrs = _names(game_context.get("attributes"))
    skills = _names(game_context.get("skills"))
    rules = _rules_text(game_context)
    special_options = special_options or {}
    special_block = "\n".join(
        f"VALID {cat.upper()} (rate/select chosen ones): {opts}"
        for cat, opts in special_options.items()
    )
    special_json = ", ".join(f'"{cat}": {{}}' for cat in special_options)

    prompt = f"""You are the Game Master finalizing a character sheet for "{game_context.get('name')}".
Apply the system's OWN creation rules below to turn the concept into a valid NUMERICAL sheet.
Respect every dot/point budget in the rules.

SYSTEM CREATION RULES:
{rules}

VALID ATTRIBUTES (rate each, all must appear): {attrs}
VALID SKILLS (rate chosen ones; omit the rest): {skills}
{special_block}

CONCEPT: {concept}
PREFERENCES: {preferences}

Return ONLY JSON:
{{"attributes": {{"<Name>": <int>, ... all {len(attrs)} attributes}},
  "skills": {{"<Name>": <int>}}{(", " + special_json) if special_json else ""},
  "merits": [{{"name":"...","value":1}}], "flaws": [{{"name":"...","value":1}}]}}
No prose."""

    resp = litellm.completion(
        model=model, messages=[{"role": "user", "content": prompt}],
        temperature=0.4, max_tokens=4000, reasoning_effort="disable",
    )
    raw = resp.choices[0].message.content or ""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else json.loads(raw)
    except (json.JSONDecodeError, AttributeError):
        data = {}

    def _clamp(v: Any, lo: int = 0, hi: int = 10) -> int:
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return lo

    # Attribute min/max from the system (default 1..5).
    attr_defs = {a.get("name"): a for a in (game_context.get("attributes") or [])}
    out_attrs: Dict[str, int] = {}
    for a in attrs:
        d = attr_defs.get(a, {})
        lo = int(d.get("min_value", 1)); hi = int(d.get("max_value", 5))
        out_attrs[a] = _clamp(data.get("attributes", {}).get(a, lo), lo, hi)

    out_skills = {k: _clamp(v, 1, 5) for k, v in (data.get("skills") or {}).items() if k in skills}
    out_special = {
        cat: {k: _clamp(v, 1, 5) for k, v in (data.get(cat) or {}).items()}
        for cat in special_options
    }

    # Resources from the system (start at max).
    resources = {}
    seen = set()
    for res in game_context.get("resources") or []:
        nm = res.get("name")
        if not nm or nm.lower() in seen:
            continue
        seen.add(nm.lower())
        mx = _resource_max(res)
        resources[nm] = {"current": mx, "max": mx}

    sheet = {
        "name": name, "concept": concept,
        "system_id": game_context.get("system_id"), "system_name": game_context.get("name"),
        "attributes": out_attrs, "skills": out_skills,
        "merits": data.get("merits") or [], "flaws": data.get("flaws") or [],
        "resources": resources,
    }
    sheet.update(out_special)
    return sheet
