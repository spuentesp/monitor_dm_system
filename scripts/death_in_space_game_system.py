#!/usr/bin/env python3
"""
Define + seed a Death in Space game system into the ``game_systems``
collection, and expose ``DIS_GAME_CONTEXT`` for the character-creation /
scene loops.

Modeled on the existing builtin systems (resources-based, like VtM). DiS
uses a d20 dice pool with attribute-only rolls (no skills) plus Void Points
as a meta-currency. Resources are Stress / Oxygen / Void.
"""
from __future__ import annotations

from uuid import UUID

DIS_SYSTEM_ID = UUID("22222222-2222-4222-8222-222222222222")  # stable id for reuse

DIS_GAME_CONTEXT = {
    "system_id": str(DIS_SYSTEM_ID),
    "name": "Death in Space",
    "description": (
        "Blue-collar sci-fi survival on the edges of colonized space. "
        "Characters roll d20 + attribute modifier (Body / Dexterity / Savvy / "
        "Tech) against a Difficulty Rating (DR). Failed rolls may earn Void "
        "Points, a meta-currency that can be spent for Advantage."
    ),
    "version": "1.0",
    "is_builtin": True,
    "core_mechanic": {
        "type": "d20",
        "formula": "1d20 + attribute_modifier vs DR",
        "success_type": "meet_or_beat",
        "success_threshold": "DR (set per check)",
        "advantage": "Spend 1 Void Point to roll 2d20 keep highest",
        "disadvantage": "Spend 1 Void Point (GM option) to roll 2d20 keep lowest",
    },
    "attributes": [
        {"name": "Body", "abbreviation": "BOD", "min_value": -3, "max_value": 3, "default_value": 0,
         "description": "Strength, endurance, hauling heavy things."},
        {"name": "Dexterity", "abbreviation": "DEX", "min_value": -3, "max_value": 3, "default_value": 0,
         "description": "Agility, reflexes, fine motor."},
        {"name": "Savvy", "abbreviation": "SAV", "min_value": -3, "max_value": 3, "default_value": 0,
         "description": "Awareness, intuition, gut instinct."},
        {"name": "Tech", "abbreviation": "TEC", "min_value": -3, "max_value": 3, "default_value": 0,
         "description": "Mechanical, electrical, technical."},
    ],
    "skills": [],  # DiS uses attribute-only rolls; no skill list
    "resources": [
        {"name": "Stress", "abbreviation": "STR", "min_value": 0, "max_value": 10,
         "recovers_on": "rest", "depleted_effect": "collapse"},
        {"name": "Oxygen", "abbreviation": "O2", "min_value": 0, "max_value": 15,
         "recovers_on": "refill", "depleted_effect": "suffocation"},
        {"name": "Void Points", "abbreviation": "VP", "min_value": 0, "max_value": 5,
         "recovers_on": "milestone", "depleted_effect": "void corruption risk"},
    ],
    "tracks": [
        {"name": "Stress", "min_value": 0, "max_value": 10, "min_threshold": 0, "max_threshold": 10,
         "depleted_effect": "collapse", "maxed_effect": "hardened"},
        {"name": "Oxygen", "min_value": 0, "max_value": 15, "min_threshold": 0, "max_threshold": 15,
         "depleted_effect": "suffocation", "maxed_effect": "fully pressurized"},
        {"name": "Void Points", "min_value": 0, "max_value": 5, "min_threshold": 0, "max_threshold": 5,
         "depleted_effect": "void corruption risk", "maxed_effect": "void-touched"},
    ],
    "conditions": [
        {"name": "Bleeding", "roll_modifier": -1, "roll_mode_override": "disadvantage"},
        {"name": "Inspired", "roll_modifier": 1, "roll_mode_override": "advantage"},
        {"name": "Low Oxygen", "roll_modifier": -2, "roll_mode_override": "disadvantage",
         "reason_text": "Suit pressure dropping"},
        {"name": "Void-Touched", "tags": ["corruption"]},
    ],
    "scenery_rules": [
        {"keyword": "zero-g", "trigger_verbs": ["pilot", "drift", "maneuver"],
         "roll_modifier": -1, "roll_mode_override": "disadvantage",
         "reason_text": "Zero-G orientation is tricky"},
        {"keyword": "pressurized", "trigger_verbs": ["search", "hack", "work"],
         "roll_modifier": 0, "roll_mode_override": "normal",
         "reason_text": "Cabin pressure is stable"},
        {"keyword": "debris", "trigger_verbs": ["drift", "search", "run"],
         "roll_modifier": -1, "roll_mode_override": "disadvantage",
         "reason_text": "Debris everywhere"},
    ],
    "core_mechanic_summary": "d20 + attribute_mod vs DR; DR typically 10/12/15.",
}


def seed_dis_system() -> str:
    """Seed DiS into MongoDB. Returns the system_id string. Idempotent."""
    import os
    import sys

    sys.path.insert(0, "packages/data-layer/src")
    from pymongo import MongoClient

    client = MongoClient(
        os.getenv(
            "MONGODB_URI",
            "mongodb://monitor:changeme-mongodb@localhost:27017/monitor?authSource=admin",
        )
    )
    col = client["monitor"]["game_systems"]
    doc = dict(DIS_GAME_CONTEXT)
    existing = col.find_one({"system_id": doc["system_id"]})
    if existing:
        col.replace_one({"_id": existing["_id"]}, doc)
        print(f"Updated: Death in Space ({doc['system_id']})")
    else:
        col.insert_one(doc)
        print(f"Inserted: Death in Space ({doc['system_id']})")
    return doc["system_id"]


if __name__ == "__main__":
    seed_dis_system()