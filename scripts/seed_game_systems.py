#!/usr/bin/env python3
"""Seed a minimal game system to MongoDB for character creation."""
import sys
sys.path.insert(0, 'packages/data-layer/src')

from pymongo import MongoClient

client = MongoClient("mongodb://monitor:changeme-mongodb@localhost:27017/monitor?authSource=admin")
col = client["monitor"]["game_systems"]

game_system = {
    "name": "Generic Fantasy",
    "system_type": "d20",
    "character_creation": {
        "steps": [
            {
                "step_number": 1,
                "step_type": "choose_name",
                "title": "Character Name",
                "instructions": "What is your character's name?",
                "is_optional": False,
                "options": [],
            },
            {
                "step_number": 2,
                "step_type": "custom",
                "title": "Concept",
                "instructions": "Describe your character concept in a few words",
                "is_optional": False,
                "options": [],
            },
            {
                "step_number": 3,
                "step_type": "generate_attributes",
                "title": "Attributes",
                "instructions": "Roll or assign your attributes (STR, DEX, CON, INT, WIS, CHA)",
                "is_optional": False,
                "options": [],
            },
        ]
    },
    "attributes": [
        {"name": "Strength", "abbreviation": "STR", "min_value": 1, "max_value": 20, "default_value": 10},
        {"name": "Dexterity", "abbreviation": "DEX", "min_value": 1, "max_value": 20, "default_value": 10},
        {"name": "Constitution", "abbreviation": "CON", "min_value": 1, "max_value": 20, "default_value": 10},
        {"name": "Intelligence", "abbreviation": "INT", "min_value": 1, "max_value": 20, "default_value": 10},
        {"name": "Wisdom", "abbreviation": "WIS", "min_value": 1, "max_value": 20, "default_value": 10},
        {"name": "Charisma", "abbreviation": "CHA", "min_value": 1, "max_value": 20, "default_value": 10},
    ],
    "tracks": [
        {"name": "HP", "track_type": "resource", "min_value": 0, "max_value": 20},
    ],
    # [G-8] Provenance — this script bypasses the tool choke point
    # (writes raw via pymongo) but the field is still stamped so the
    # provenance audit can find hand-curated entries later.
    "hand_authored": True,
}

existing = col.find_one({"name": "Generic Fantasy"})
if existing:
    col.replace_one({"_id": existing["_id"]}, game_system)
    print("Updated: Generic Fantasy")
else:
    col.insert_one(game_system)
    print("Inserted: Generic Fantasy")
client.close()
