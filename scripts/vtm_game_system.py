#!/usr/bin/env python3
"""
Define + seed a Vampire: The Masquerade game system into the `game_systems`
collection, and expose VTM_GAME_CONTEXT for the character-creation / scene loops.

Modeled on the existing builtin systems (resources-based, like 'Death In Space').
VTM uses a d10 dice pool counting successes vs a difficulty.
"""
from __future__ import annotations

import os
from uuid import uuid4, UUID
from datetime import datetime, timezone

VTM_SYSTEM_ID = UUID("11111111-1111-4111-8111-111111111111")  # stable id for reuse

VTM_GAME_CONTEXT = {
    "system_id": str(VTM_SYSTEM_ID),
    "name": "Vampire: The Masquerade",
    "description": (
        "World of Darkness storytelling system. Kindred spend Blood (Vitae) to "
        "power Disciplines and heal; low Blood raises Hunger toward Frenzy. "
        "Rolls are d10 dice pools (Attribute + Skill) counting successes vs a difficulty."
    ),
    "version": "1.0",
    "is_builtin": True,
    "core_mechanic": {
        "type": "dice_pool",
        "formula": "(Attribute + Skill)d10 vs difficulty, count successes (>=6)",
        "success_type": "count_successes",
        "success_threshold": 6,
        "critical_success": "two 10s (a crit)",
        "critical_failure": "no successes with a 1 (a bestial failure)",
    },
    # Physical / Social / Mental attributes (rated 1-5).
    "attributes": [
        {"name": "Strength", "abbreviation": "STR", "min_value": 1, "max_value": 5, "default_value": 2},
        {"name": "Dexterity", "abbreviation": "DEX", "min_value": 1, "max_value": 5, "default_value": 2},
        {"name": "Stamina", "abbreviation": "STA", "min_value": 1, "max_value": 5, "default_value": 2},
        {"name": "Charisma", "abbreviation": "CHA", "min_value": 1, "max_value": 5, "default_value": 2},
        {"name": "Manipulation", "abbreviation": "MAN", "min_value": 1, "max_value": 5, "default_value": 2},
        {"name": "Composure", "abbreviation": "COM", "min_value": 1, "max_value": 5, "default_value": 2},
        {"name": "Intelligence", "abbreviation": "INT", "min_value": 1, "max_value": 5, "default_value": 2},
        {"name": "Wits", "abbreviation": "WIT", "min_value": 1, "max_value": 5, "default_value": 2},
        {"name": "Resolve", "abbreviation": "RES", "min_value": 1, "max_value": 5, "default_value": 2},
    ],
    "skills": [
        {"name": "Brawl", "abbreviation": "BRW"},
        {"name": "Athletics", "abbreviation": "ATH"},
        {"name": "Intimidation", "abbreviation": "INT2"},
        {"name": "Occult", "abbreviation": "OCC"},
        {"name": "Awareness", "abbreviation": "AWA"},
    ],
    # Resources / tracks. Blood Pool + Health + Willpower + Hunger.
    "resources": [
        {"name": "Blood Pool", "abbreviation": "BP", "min_value": 0, "max_value": 10,
         "recovers_on": "feeding", "depleted_effect": "Hunger Frenzy"},
        {"name": "Health", "abbreviation": "HP", "min_value": 0, "max_value": 7,
         "recovers_on": "spending blood", "depleted_effect": "torpor or destruction"},
        {"name": "Willpower", "abbreviation": "WP", "min_value": 0, "max_value": 5,
         "recovers_on": "rest", "depleted_effect": "cannot resist frenzy"},
        {"name": "Hunger", "abbreviation": "HGR", "min_value": 0, "max_value": 5,
         "recovers_on": "n/a", "depleted_effect": "frenzy risk"},
    ],
    # Tracks mirror the key resources so the creation loop initialises them too.
    "tracks": [
        {"name": "Blood Pool", "track_type": "resource", "min_value": 0, "max_value": 10},
        {"name": "Health", "track_type": "stress", "min_value": 0, "max_value": 7},
        {"name": "Willpower", "track_type": "resource", "min_value": 0, "max_value": 5},
    ],
    # Disciplines as a tiered ability system (dots 1-5).
    "tiered_abilities": [
        {
            "name": "Disciplines",
            "description": "Supernatural vampiric powers, rated in dots (1-5).",
            "abilities": [
                {"name": "Celerity", "tier": 1, "description": "Supernatural speed and reflexes."},
                {"name": "Potence", "tier": 1, "description": "Supernatural strength."},
                {"name": "Blood Sorcery", "tier": 1, "description": "Mystical manipulation of blood; needs focus."},
                {"name": "Fortitude", "tier": 1, "description": "Supernatural toughness."},
                {"name": "Auspex", "tier": 1, "description": "Heightened senses and perception."},
            ],
        }
    ],
    "resolution_mechanics": [
        {"name": "Discipline activation", "dice_formula": "(Attribute + Discipline)d10",
         "mechanic_type": "dice_pool", "description": "Activate a Discipline; spend 1 Blood."},
        {"name": "Feeding", "dice_formula": "n/a",
         "mechanic_type": "resource", "description": "Drain a mortal to restore Blood Pool; reduces Hunger."},
    ],
    "damage_model": {
        "type": "tracked",
        "damage_types": ["superficial", "aggravated"],
        "track": "Health",
        "description": "Damage fills Health; aggravated cannot be healed by blood.",
    },
    "advancement": {"xp_per_session": 15},
    "character_creation": {
        "steps": [
            {"step_number": 1, "step_type": "choose_name", "title": "Name & Concept",
             "instructions": "Who is your vampire? Give a name and concept.", "is_optional": False, "options": []},
            {"step_number": 2, "step_type": "choose_attributes", "title": "Attributes",
             "instructions": "Describe your physical/social/mental strengths.", "is_optional": False, "options": []},
            {"step_number": 3, "step_type": "choose_disciplines", "title": "Disciplines",
             "instructions": "Which Disciplines does your vampire command?", "is_optional": False,
             "options": ["Celerity", "Potence", "Blood Sorcery", "Fortitude", "Auspex"]},
            {"step_number": 4, "step_type": "choose_background", "title": "Background & Flaws",
             "instructions": "Your history, bonds, and any flaws (e.g. the Mark, Fabien).", "is_optional": False, "options": []},
        ]
    },
}


def seed_vtm_system() -> str:
    """Upsert the VTM system into game_systems. Returns system_id (str)."""
    from monitor_data.db.mongodb import get_mongodb_client

    m = get_mongodb_client()
    coll = m.get_collection("game_systems")
    doc = dict(VTM_GAME_CONTEXT)
    doc["updated_at"] = datetime.now(timezone.utc)
    coll.update_one(
        {"system_id": str(VTM_SYSTEM_ID)},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return str(VTM_SYSTEM_ID)


if __name__ == "__main__":
    sid = seed_vtm_system()
    print(f"Seeded VTM game system: system_id={sid}")
