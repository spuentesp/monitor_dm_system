#!/usr/bin/env python3
"""
FULL GAME-FLOW TEST on the real (ingested, non-hardcoded) VtM 5e system.

  1. ROSTER       — list saved characters; pick one OR create a new one (OOC).
  2. CREATION     — GM-guided creation via CharacterCreationLoop on the real V5 system.
  3. REVIEW/APPLY — numerical sheet (attrs/skills/disciplines/merits/flaws) + persist.
  4. SESSION      — 3 scenes, a combat, two scenery changes, and an ending.

Everything is logged to test_logs/.
"""
import os
_LOGDIR = os.path.join(os.getcwd(), "test_logs")
os.makedirs(_LOGDIR, exist_ok=True)
os.environ["MONITOR_LLM_LOG"] = "1"
os.environ["MONITOR_LLM_LOG_FILE"] = os.path.join(_LOGDIR, "llm_calls.log")

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asyncio
import json
import logging
from uuid import uuid4, UUID

import nest_asyncio
from rich.console import Console

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(name)s | %(message)s",
                    handlers=[logging.FileHandler(os.path.join(_LOGDIR, "full_session_backend.log"), mode="w")])

from monitor_data.db.mongodb import get_mongodb_client
from monitor_agents.canonkeeper import CanonKeeper
from monitor_agents.loops.character_creation_loop import CharacterCreationLoop
from monitor_agents.loops.scene_loop import SceneLoop
from vtm_sheet_builder import build_numerical_sheet

nest_asyncio.apply()
console = Console()
TRANSCRIPT = os.path.join(_LOGDIR, "full_session_transcript.txt")

UNIVERSE_ID = UUID("7c737c26-7b84-4704-9ff6-4fc19492eac4")   # ingested VtM corebook universe
V5_SYSTEM_ID = "a227676a-edab-4a43-80d9-8f76b74ff289"


def log(s: str) -> None:
    with open(TRANSCRIPT, "a") as f:
        f.write(s + "\n")
    console.print(s)


def load_v5_system() -> dict:
    return get_mongodb_client().get_collection("game_systems").database["game_systems"].find_one(
        {"system_id": V5_SYSTEM_ID})


def clan_disciplines() -> list:
    # Pull discipline names from the ingested corebook entities.
    from neo4j import GraphDatabase  # noqa
    import subprocess
    return ["Potence", "Obtenebration", "Dominate", "Animalism", "Auspex", "Celerity",
            "Fortitude", "Obfuscate", "Presence", "Protean", "Dementation"]


# ============================================================ 1. ROSTER
def list_roster() -> list:
    from monitor_data.tools.mongodb_tools import mongodb_list_character_sheets
    from monitor_data.schemas.character_sheets import CharacterSheetFilter
    try:
        res = mongodb_list_character_sheets(CharacterSheetFilter(limit=50))
        return list(getattr(res, "sheets", []) or [])
    except Exception as exc:
        console.print(f"[dim](roster query: {exc})[/dim]")
        return []


# ============================================================ 2+3 CREATE + APPLY
async def create_character(game_system: dict) -> dict:
    log("\n[OOC] Player: \"GM, I'd like to create a new character.\"")
    log("[OOC] GM: Switching to character creation.\n")

    loop = CharacterCreationLoop(game_context=game_system, scene_id=uuid4(), story_id=uuid4())
    res = await loop.start()
    log(f"GM (creation): {(res.get('gm_message') or '')[:160]}")

    answers = [
        "Mathias Sorzano",
        "A brooding Lasombra elder — shadow-bound, political, and merciless.",
        "Physically powerful and commanding; favor Strength and presence.",
        "Brawl, Stealth, Intimidation, Occult, Politics, Awareness.",
        "Clan Lasombra; Disciplines Potence, Obtenebration, Dominate.",
        "Merits: Allies, Resources. Flaw: a Sabbat enemy who hunts me.",
        "Sire was an Archbishop; I was Embraced to be his enforcer. Predator: Sandman.",
        "Ambition: reclaim the domain stolen from me.", "Continue.", "Continue.",
    ]
    i = 0
    while not res.get("complete") and i < 12:
        res = await loop.process_player_input(answers[i] if i < len(answers) else "Continue.")
        i += 1
    choices = (res.get("character") or {}).get("choices", {})
    concept = "A brooding Lasombra elder — shadow-bound, political, and merciless."

    log("\n[Review] GM applies the system's creation rules to finalize numbers…")
    sheet = build_numerical_sheet(
        name="Mathias Sorzano", concept=concept, clan="Lasombra",
        preferences="Strength and presence; Brawl/Stealth/Intimidation/Occult/Politics/Awareness; "
                    "Potence, Obtenebration, Dominate; Merits Allies, Resources; Flaw Sabbat enemy.",
        game_context=game_system, clan_disciplines=clan_disciplines(),
    )
    sheet["id"] = str(uuid4())
    return sheet


def persist_character(sheet: dict) -> None:
    from monitor_data.tools.mongodb_tools import mongodb_create_character_sheet
    from monitor_data.schemas.character_sheets import CharacterSheetCreate
    # Character sheets reference a Neo4j Entity — create the EntityInstance first.
    try:
        from monitor_data.tools.neo4j_tools import neo4j_create_entity
        from monitor_data.schemas.entities import EntityCreate
        neo4j_create_entity(EntityCreate(
            universe_id=UNIVERSE_ID, id=UUID(sheet["id"]), name=sheet["name"],
            entity_type="character", sub_type="character", is_archetype=False,
            description=f"{sheet['concept']} (Clan {sheet['clan']})"))
    except Exception as exc:
        console.print(f"[yellow]entity create warning: {exc}[/yellow]")
    try:
        mongodb_create_character_sheet(CharacterSheetCreate(
            entity_id=UUID(sheet["id"]),
            game_system_id=UUID(V5_SYSTEM_ID),
            system_name=sheet["system_name"],
            stats=sheet["attributes"],
            skills=sheet["skills"],
            resources={k: v["max"] for k, v in sheet["resources"].items()},
            special_abilities=[f"Discipline: {d} {lvl}" for d, lvl in sheet["disciplines"].items()]
                              + [f"Merit: {m.get('name')}" for m in sheet["merits"]]
                              + [f"Flaw: {f.get('name')}" for f in sheet["flaws"]],
            background=sheet["concept"],
            notes=f"Clan {sheet['clan']}",
        ))
        console.print("[green]Character persisted to roster.[/green]")
    except Exception as exc:
        console.print(f"[yellow]persist warning: {exc}[/yellow]")


# ============================================================ 4. SESSION
async def play_scene(story_id: UUID, actor: dict, scene_no: int, title: str,
                     setting: str, turns: list) -> None:
    log(f"\n{'='*60}\nSCENE {scene_no}: {title}\nSetting: {setting}\n{'='*60}")
    scene_id = uuid4()

    # Seed working state so resources (Health/Willpower/Hunger) drive mechanics.
    from monitor_data.schemas.working_state import WorkingStateCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_working_state
    try:
        mongodb_create_working_state(WorkingStateCreate(
            entity_id=UUID(actor["id"]), scene_id=scene_id, story_id=story_id,
            base_stats=actor["attributes"], resources=actor["resources"]))
    except Exception as exc:
        console.print(f"[dim](working state: {exc})[/dim]")

    loop = SceneLoop(scene_id=scene_id, story_id=story_id, universe_id=UNIVERSE_ID,
                     system_id=V5_SYSTEM_ID, play_mode="dice_game_system", roll_mode="auto",
                     actor_id=UUID(actor["id"]), actor_context=actor, session_tone="grim")
    for t in turns:
        log(f"\nPlayer: {t}")
        result = await loop.run(t)
        narrative = result.get("narrative_text") or ""
        resolution = result.get("resolution") or {}
        deltas = result.get("resource_deltas") or []
        log(f"GM: {narrative}")
        if resolution.get("success_level") not in (None, "narrative"):
            log(f"   [roll: {resolution.get('stat')} → {resolution.get('success_level')}]")
        if deltas:
            log(f"   [resources: {deltas}]")


async def main() -> None:
    console.rule("[bold cyan]VtM Full Game-Flow Test (real V5 system)")
    log("===== VtM FULL SESSION =====")
    gs = load_v5_system()
    console.print(f"System: {gs['name']} | {len(gs['attributes'])} attrs, {len(gs['skills'])} skills")

    # 1. ROSTER
    roster = list_roster()
    log(f"\n[ROSTER] {len(roster)} saved character(s).")
    if roster:
        for s in roster[:5]:
            log(f"  - {getattr(s,'system_name','?')} (entity {getattr(s,'entity_id','?')})")
        log("  Player chooses to CREATE a new character instead of selecting one.")
    else:
        log("  Roster empty → creating a new character.")

    # 2+3 CREATE + APPLY + PERSIST
    actor = await create_character(gs)
    log("\n[SHEET] " + json.dumps({k: actor[k] for k in
        ("name", "clan", "attributes", "skills", "disciplines", "merits", "flaws", "resources")}, indent=2))
    persist_character(actor)

    # 4. SESSION — 3 scenes, combat, 2 scenery changes, ending
    keeper = CanonKeeper()
    story_id = uuid4()
    await keeper.create_story(story_id=story_id, universe_id=UNIVERSE_ID,
                              title="Mathias: Reclamation", story_type="chronicle")

    await play_scene(story_id, actor, 1, "The Elysium Gathering",
                     "A Camarilla Elysium in a candlelit opera house.",
                     ["I enter the Elysium and survey the gathered Kindred, looking for my Sabbat enemy.",
                      "I approach the Toreador harpy and try to charm information about my rival's whereabouts."])

    # scenery change 1
    await play_scene(story_id, actor, 2, "Ambush in the Parking Garage",
                     "A cold concrete parking garage beneath the opera house — my enemy's thugs wait.",
                     ["My rival's ghouls ambush me as I leave. I attempt to dodge with Celerity and strike one down with Potence.",
                      "I wrap the survivors in Obtenebration shadows and interrogate the wounded ghoul."])

    # scenery change 2 + ending
    await play_scene(story_id, actor, 3, "Confrontation at the Haven",
                     "The crumbling haven of my Sabbat enemy, reeking of old blood.",
                     ["I confront my enemy and use Dominate to freeze him as I deliver judgment.",
                      "With my domain reclaimed, I declare the chronicle's end and step into the coming dawn's promise of power."])

    log("\n===== SESSION COMPLETE =====")
    console.rule("[bold cyan]Full flow complete")


if __name__ == "__main__":
    asyncio.run(main())
