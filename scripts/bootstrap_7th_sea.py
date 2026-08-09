"""Bootstrap a minimal 7th Sea 2e game system + universe in MONITOR.

Idempotent: safe to re-run. Seeds:

  * A 7th Sea 2e game system in MongoDB ``game_systems``
    - Attributes: Brawn, Finesse, Resolve, Wits, Panache (2-5 each)
    - Skills grouped under Combat / Basic / Dirty Fighting / Social
    - Resources: Wounds (max 5), Hero Points (max 5), Drama (max 10)
    - core_mechanic.type = "dice_pool" (d10s, count sets of 10 as Raises)
    - success_threshold = 10
  * A "Theah" universe in Neo4j if none matches yet

The system_id printed at the end can be plugged into a scenario via
``SCN["system_id"]`` in ``scripts/vtm_embrace_session.py``.

Run from repo root:
    uv run python scripts/bootstrap_7th_sea.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
for _env in (
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent.parent / ".env.tokens",
):
    if _env.exists():
        load_dotenv(_env, override=False)

import structlog

log = structlog.get_logger()

SEVENTH_SEA_SYSTEM_ID = "f0e1d2c3-b4a5-4968-9876-543210fedcba"

SEVENTH_SEA_SYSTEM: dict = {
    "system_id": SEVENTH_SEA_SYSTEM_ID,
    "name": "7th Sea 2nd Edition",
    "edition": "2nd Edition",
    "version": "1.0",
    "description": (
        "Cinematic swashbuckling tabletop RPG by John Wick Presents. "
        "Hero Points buy drama. D10 pools counted in Raises (sets of 10)."
    ),
    "is_builtin": False,
    "core_mechanic": {
        "type": "dice_pool",
        "success_type": "count_sets_of_ten",
        "success_threshold": 10,
        "die_size": 10,
        "formula": "Xd10 where X = attribute + skill",
    },
    "attributes": [
        {"name": "Brawn",   "abbreviation": "BRW", "description": "Strength, endurance.",
         "min_value": 2, "max_value": 5, "default_value": 2},
        {"name": "Finesse", "abbreviation": "FIN", "description": "Agility, poise, bladework.",
         "min_value": 2, "max_value": 5, "default_value": 2},
        {"name": "Resolve", "abbreviation": "RES", "description": "Will, courage, faith.",
         "min_value": 2, "max_value": 5, "default_value": 2},
        {"name": "Wits",    "abbreviation": "WIT", "description": "Cunning, perception, learning.",
         "min_value": 2, "max_value": 5, "default_value": 2},
        {"name": "Panache", "abbreviation": "PAN", "description": "Style, charm, presence.",
         "min_value": 2, "max_value": 5, "default_value": 2},
    ],
    "skills": [
        # Combat
        {"name": "Attack",        "attribute": "Finesse", "category": "Combat"},
        {"name": "Defense",       "attribute": "Finesse", "category": "Combat"},
        {"name": "Firearms",      "attribute": "Wits",    "category": "Combat"},
        {"name": "Weaponry",      "attribute": "Brawn",   "category": "Combat"},
        # Basic
        {"name": "Awareness",     "attribute": "Wits",    "category": "Basic"},
        {"name": "Athletics",     "attribute": "Brawn",   "category": "Basic"},
        {"name": "Brawl",         "attribute": "Brawn",   "category": "Basic"},
        {"name": "Conviction",    "attribute": "Resolve", "category": "Basic"},
        {"name": "Intimidate",    "attribute": "Brawn",   "category": "Basic"},
        {"name": "Ride",          "attribute": "Finesse", "category": "Basic"},
        {"name": "Stealth",       "attribute": "Finesse", "category": "Basic"},
        {"name": "Survival",      "attribute": "Wits",    "category": "Basic"},
        {"name": "Swim",          "attribute": "Brawn",   "category": "Basic"},
        {"name": "Thievery",      "attribute": "Finesse", "category": "Basic"},
        # Dirty Fighting
        {"name": "Clubs",         "attribute": "Brawn",   "category": "Dirty Fighting"},
        {"name": "Fencing",       "attribute": "Finesse", "category": "Dirty Fighting"},
        {"name": "Knives",        "attribute": "Finesse", "category": "Dirty Fighting"},
        {"name": "Pistols",       "attribute": "Wits",    "category": "Dirty Fighting"},
        {"name": "Rope",          "attribute": "Finesse", "category": "Dirty Fighting"},
        {"name": "Whips",         "attribute": "Finesse", "category": "Dirty Fighting"},
        # Social (linked to Panache)
        {"name": "Charm",         "attribute": "Panache", "category": "Social"},
        {"name": "Command",       "attribute": "Panache", "category": "Social"},
        {"name": "Confront",      "attribute": "Brawn",   "category": "Social"},
        {"name": "Empathy",       "attribute": "Wits",    "category": "Social"},
        {"name": "Oratory",       "attribute": "Panache", "category": "Social"},
        {"name": "Politics",      "attribute": "Wits",    "category": "Social"},
        {"name": "Seduction",     "attribute": "Panache", "category": "Social"},
        {"name": "Torture",       "attribute": "Resolve", "category": "Social"},
        # Sorcery
        {"name": "Glamour",       "attribute": "Panache", "category": "Sorcery"},
        {"name": "Hex",           "attribute": "Wits",    "category": "Sorcery"},
        {"name": "Kindrift",      "attribute": "Resolve", "category": "Sorcery"},
        {"name": "Pyrematica",    "attribute": "Wits",    "category": "Sorcery"},
        {"name": "Sorte",         "attribute": "Wits",    "category": "Sorcery"},
        {"name": "Bara",          "attribute": "Brawn",   "category": "Sorcery"},
        {"name": "Maleficio",     "attribute": "Resolve", "category": "Sorcery"},
        {"name": "Scelto",        "attribute": "Finesse", "category": "Sorcery"},
        {"name": "Spiritus",      "attribute": "Resolve", "category": "Sorcery"},
        {"name": "Voidus",        "attribute": "Resolve", "category": "Sorcery"},
    ],
    "resources": [
        {"name": "Wounds",     "abbreviation": "WND", "calculation": "varies",
         "min_value": 0, "max_value": 5, "recovers_on": "scene break"},
        {"name": "Hero Points","abbreviation": "HP",  "calculation": "varies",
         "min_value": 0, "max_value": 5, "recovers_on": "scene break"},
        {"name": "Drama",      "abbreviation": "DRM", "calculation": "10 - Backgrounds",
         "min_value": 0, "max_value": 10, "recovers_on": "session start"},
    ],
    "resolution_mechanics": [
        {"mechanic_type": "dice_pool",
         "dice_formula": "Xd10, count sets of 10",
         "success_degrees": [
             {"threshold": "0", "label": "botch", "effect": "Catastrophic failure"},
             {"threshold": "1", "label": "raise", "effect": "1 Raise to spend"},
             {"threshold": "2", "label": "raises", "effect": "2 Raises to spend"},
         ],
         "critical_success": "A natural 10 + Hero Point may upgrade to 'with style'.",
         "critical_failure": "Zero Raises with at least one die showing 1 = botch."}
    ],
    "action_economy": {
        "type": "action_sequence",
        "description": "Risks, Raises, and Consequences are declared before rolling.",
    },
}


def seed_system() -> str:
    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client()["game_systems"]
    existing = coll.find_one({"system_id": SEVENTH_SEA_SYSTEM_ID})
    if existing:
        log.info("system.exists", system_id=SEVENTH_SEA_SYSTEM_ID, name=existing.get("name"))
    else:
        coll.insert_one(SEVENTH_SEA_SYSTEM)
        log.info("system.created", system_id=SEVENTH_SEA_SYSTEM_ID, name=SEVENTH_SEA_SYSTEM["name"])
    return SEVENTH_SEA_SYSTEM_ID


def seed_universe() -> str:
    import uuid

    from monitor_data.tools.neo4j_tools.core import (
        neo4j_list_universes, neo4j_create_universe, neo4j_list_multiverses,
        neo4j_create_multiverse,
    )
    from monitor_data.schemas.universe import (
        UniverseCreate, MultiverseCreate,
    )

    keywords = ["theah", "7th sea"]
    for u in neo4j_list_universes():
        if u.name and any(k in u.name.lower() for k in keywords):
            log.info("universe.exists", universe_id=str(u.id), name=u.name)
            return str(u.id)

    # Need a multiverse to host the universe.
    mvs = neo4j_list_multiverses()
    if mvs:
        multiverse_id = mvs[0].id
    else:
        mv = neo4j_create_multiverse(
            MultiverseCreate(name="MONITOR Sandbox Multiverse")
        )
        multiverse_id = mv.id
        log.info("multiverse.created", multiverse_id=str(multiverse_id))

    new = neo4j_create_universe(
        UniverseCreate(
            multiverse_id=multiverse_id,
            name="Theah (7th Sea)",
            description=(
                "The continent of Théah: Vodacce city-states, Montaigne court, "
                "Castille and the Inquisition, Eisenfürst, Avalon, Ussura, "
                "and the Vendel League. Swashbuckling, sorcery, and intrigue."
            ),
        )
    )
    log.info("universe.created", universe_id=str(new.id))
    return str(new.id)


def main() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ]
    )
    sys_id = seed_system()
    univ_id = seed_universe()
    print(f"\n7th Sea system_id:  {sys_id}")
    print(f"Theah universe_id:  {univ_id}")
    print(f"\nTo run a session:")
    print(f"  SCENARIO=7th_sea_masquerade uv run python scripts/vtm_embrace_session.py")


if __name__ == "__main__":
    main()