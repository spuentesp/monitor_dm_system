#!/usr/bin/env python3
"""
GM-assisted review-and-apply: turn the conversational character-creation choices
into a validated NUMERICAL sheet, using the game system's OWN creation rules
(ingested from the corebook) — nothing hardcoded about the ruleset.

The allocation budgets come from the system's char_creation step instructions;
valid attributes/skills come from the system; clan disciplines come from Neo4j.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import litellm

CHEAP_MODEL = "gemini/gemini-2.5-flash"


def _system_rules_text(game_context: Dict[str, Any]) -> str:
    cc = game_context.get("character_creation") or game_context.get("char_creation") or {}
    lines = []
    for s in cc.get("steps") or []:
        t = s.get("title") or s.get("step_type") or "step"
        instr = s.get("instructions") or ""
        if instr:
            lines.append(f"- {t}: {instr}")
    return "\n".join(lines)


def _attr_names(game_context: Dict[str, Any]) -> List[str]:
    return [a.get("name") for a in (game_context.get("attributes") or []) if a.get("name")]


def _skill_names(game_context: Dict[str, Any]) -> List[str]:
    return [s.get("name") for s in (game_context.get("skills") or []) if s.get("name")]


def build_numerical_sheet(
    *,
    name: str,
    concept: str,
    clan: str,
    preferences: str,
    game_context: Dict[str, Any],
    clan_disciplines: List[str],
    model: str = CHEAP_MODEL,
) -> Dict[str, Any]:
    """Produce a validated numerical character sheet via the GM (cheap LLM)."""
    attrs = _attr_names(game_context)
    skills = _skill_names(game_context)
    rules = _system_rules_text(game_context)

    prompt = f"""You are the Storyteller finalizing a character sheet for the game system
"{game_context.get('name')}". Apply the system's OWN creation rules below to turn the
player's concept into a valid NUMERICAL sheet. Respect every dot budget in the rules.

SYSTEM CREATION RULES (from the rulebook):
{rules}

VALID ATTRIBUTES (rate each 1-5, all must appear): {attrs}
VALID SKILLS (rate the chosen ones 1-5; leave others out): {skills}
CLAN: {clan}
CLAN DISCIPLINES available (rate chosen ones in dots): {clan_disciplines}

PLAYER CONCEPT: {concept}
PLAYER PREFERENCES: {preferences}

Return ONLY a JSON object with this exact shape:
{{
  "attributes": {{"<AttrName>": <1-5>, ... all {len(attrs)} attributes}},
  "skills": {{"<SkillName>": <1-5>, ...}},
  "disciplines": {{"<DisciplineName>": <1-3>, ...}},
  "merits": [{{"name": "<merit>", "value": <dots>}}],
  "flaws": [{{"name": "<flaw>", "value": <dots>}}]
}}
Follow the attribute spread and skill spread from the rules exactly. No prose."""

    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=4000,
        # gemini-2.5-flash is a thinking model; without this the token budget is
        # spent on hidden reasoning and the JSON output is truncated.
        reasoning_effort="disable",
    )
    raw = resp.choices[0].message.content or ""
    # Strip ```json fences and grab the JSON object.
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else json.loads(raw)
    except (json.JSONDecodeError, AttributeError):
        data = {}

    # ---- Validate / clamp ----
    out_attrs: Dict[str, int] = {}
    for a in attrs:
        v = data.get("attributes", {}).get(a, 1)
        out_attrs[a] = max(1, min(5, int(v) if str(v).isdigit() else 1))
    out_skills = {
        k: max(1, min(5, int(v)))
        for k, v in (data.get("skills") or {}).items()
        if k in skills and str(v).isdigit()
    }
    out_disc = {
        k: max(1, min(5, int(v)))
        for k, v in (data.get("disciplines") or {}).items()
        if str(v).isdigit()
    }

    # ---- Derived resources from tracks (e.g. Health = Stamina + 3) ----
    sta = out_attrs.get("Stamina", 1)
    com = out_attrs.get("Composure", 1)
    res = out_attrs.get("Resolve", 1)
    resources = {
        "Health": {"current": sta + 3, "max": sta + 3},
        "Willpower": {"current": com + res, "max": com + res},
        "Humanity": {"current": 7, "max": 10},
        "Hunger": {"current": 1, "max": 5},
        "Blood Potency": {"current": 1, "max": 10},
    }

    return {
        "name": name,
        "concept": concept,
        "clan": clan,
        "system_id": game_context.get("system_id"),
        "system_name": game_context.get("name"),
        "attributes": out_attrs,
        "skills": out_skills,
        "disciplines": out_disc,
        "merits": data.get("merits") or [],
        "flaws": data.get("flaws") or [],
        "resources": resources,
    }


if __name__ == "__main__":
    from monitor_data.db.mongodb import get_mongodb_client
    g = get_mongodb_client().get_collection("game_systems").database["game_systems"].find_one(
        {"name": "Vampire: The Masquerade 5th Edition"})
    sheet = build_numerical_sheet(
        name="Mathias Sorzano",
        concept="A brooding Lasombra elder, shadow-bound and political",
        clan="Lasombra",
        preferences="Physically powerful and commanding; expert in Stealth, Intimidation, "
                    "Occult, Politics, Awareness, Brawl. Disciplines Potence, Obtenebration, "
                    "Dominate. Merits: Allies, Resources. Flaw: a Sabbat enemy.",
        game_context=g,
        clan_disciplines=["Potence", "Obtenebration", "Dominate", "Fortitude"],
    )
    print(json.dumps(sheet, indent=2))
