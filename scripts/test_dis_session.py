#!/usr/bin/env python3
"""
Death in Space session on the ingested DiS world — proving the whole flow is
system-agnostic (no VtM assumptions).

  1. ROSTER  — list saved characters (incl. ones from OTHER worlds → "import");
               player creates a new DiS character (or could select/import one).
  2. CREATE  — generic GM-assisted numerical sheet on the extracted DiS system.
  3. PLAY    — a 5-scene sci-fi-horror story with auto-roll + DiS resource
               economy (Hit Points / Void Points / Fuel), a combat, and changes
               of scenery, ending the run.
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
                    handlers=[logging.FileHandler(os.path.join(_LOGDIR, "dis_session_backend.log"), mode="w")])

from monitor_data.db.mongodb import get_mongodb_client
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.loops.scene_loop import SceneLoop
from build_sheet import build_sheet

nest_asyncio.apply()
console = Console()
TRANSCRIPT = os.path.join(_LOGDIR, "dis_session_transcript.txt")

DIS_SYSTEM_ID = "04dba354-5211-44a2-8bdd-20fae64c016f"  # authentic ingested Death In Space


def log(s: str) -> None:
    with open(TRANSCRIPT, "a") as f:
        f.write(s + "\n")
    console.print(s)


def load_dis_system() -> dict:
    db = get_mongodb_client().get_collection("game_systems").database["game_systems"]
    return db.find_one({"system_id": DIS_SYSTEM_ID})


def configure_dis_economy(coll) -> None:
    """Attach DiS resource action_rules (data, not code) so play changes numbers."""
    g = coll.find_one({"system_id": DIS_SYSTEM_ID})
    resources = g.get("resources") or []
    rules = {
        "Hit Points": [{"keywords": ["hit", "shot", "wound", "claw", "slam", "bite", "blast",
                                     "attack", "impact", "burn", "explosion"], "delta": -1,
                        "requires": "harm", "reason": "Took damage"}],
        "Void Points": [{"keywords": ["void", "psychic", "warp", "corrupt", "unreal",
                                      "mutation", "reality"], "delta": -1,
                         "reason": "Spent Void Point against the warp"}],
        "Fuel": [{"keywords": ["jump", "burn fuel", "thrusters", "travel", "fly", "depart",
                               "launch", "escape"], "delta": -1, "reason": "Burned fuel"}],
    }
    for r in resources:
        nm = r.get("name")
        if nm in rules:
            r["action_rules"] = rules[nm]
    coll.update_one({"system_id": DIS_SYSTEM_ID}, {"$set": {"resources": resources}})


async def play_scene(story_id, actor, n, title, setting, turns):
    log(f"\n{'='*60}\nSCENE {n}: {title}\nSetting: {setting}\n{'='*60}")
    scene_id = uuid4()
    from monitor_data.schemas.working_state import WorkingStateCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_working_state
    try:
        mongodb_create_working_state(WorkingStateCreate(
            entity_id=UUID(actor["id"]), scene_id=scene_id, story_id=story_id,
            base_stats=actor["attributes"], resources=actor["resources"]))
    except Exception as exc:
        console.print(f"[dim](ws: {exc})[/dim]")
    loop = SceneLoop(scene_id=scene_id, story_id=story_id, universe_id=actor["universe_id"],
                     system_id=DIS_SYSTEM_ID, play_mode="dice_game_system", roll_mode="auto",
                     actor_id=UUID(actor["id"]), actor_context=actor, session_tone="grim, used-future")
    for t in turns:
        log(f"\nPlayer: {t}")
        r = await loop.run(t)
        log(f"GM: {r.get('narrative_text') or ''}")
        res = r.get("resolution") or {}
        if res.get("success_level") not in (None, "narrative"):
            log(f"   [roll: {res.get('stat')} -> {res.get('success_level')}]")
        if r.get("resource_deltas"):
            log(f"   [resources: {r.get('resource_deltas')}]")


async def main():
    console.rule("[bold cyan]Death in Space — Full Session (extracted system)")
    log("===== DEATH IN SPACE SESSION =====")
    db = get_mongodb_client().get_collection("game_systems").database["game_systems"]
    configure_dis_economy(db)
    gs = load_dis_system()
    console.print(f"System: {gs['name']} | attrs={[a.get('name') for a in gs['attributes']]} "
                  f"| resources={[r.get('name') for r in gs.get('resources',[])]}")

    with open(os.path.join(_LOGDIR, "dis_session.json")) as f:
        universe_id = UUID(json.load(f)["universe_id"])

    # 1. ROSTER — show saved characters (incl. other worlds = import); create new.
    from monitor_data.tools.mongodb_tools import mongodb_list_character_sheets
    from monitor_data.schemas.character_sheets import CharacterSheetFilter
    roster = list(getattr(mongodb_list_character_sheets(CharacterSheetFilter(limit=50)), "sheets", []) or [])
    log(f"\n[ROSTER] {len(roster)} saved character(s) across worlds (any could be imported):")
    for s in roster[:6]:
        log(f"  - {getattr(s,'system_name','?')}  (entity {getattr(s,'entity_id','?')})")
    log("  [OOC] Player: \"New character for this run.\"  GM: rolling up a salvager.\n")

    # 2. CREATE on the extracted DiS system
    sheet = build_sheet(
        name="Корра 'Rust' Vane",
        concept="A hard-luck salvager and void-scarred mechanic working the Dead Space wrecks.",
        preferences="Strong Body and Tech; competent Dexterity; weak Savvy. A scavenger who fixes "
                    "broken machines and survives the warp.",
        game_context=gs,
    )
    sheet["id"] = str(uuid4())
    sheet["universe_id"] = universe_id
    log("[SHEET] " + json.dumps({k: sheet[k] for k in ("name","attributes","skills","resources")}, indent=2, ensure_ascii=False))

    # persist to roster (entity + sheet)
    try:
        from monitor_data.tools.neo4j_tools import neo4j_create_entity
        from monitor_data.schemas.entities import EntityCreate
        from monitor_data.tools.mongodb_tools import mongodb_create_character_sheet
        from monitor_data.schemas.character_sheets import CharacterSheetCreate
        neo4j_create_entity(EntityCreate(universe_id=universe_id, id=UUID(sheet["id"]), name=sheet["name"],
                                         entity_type="character", sub_type="character", is_archetype=False,
                                         description=sheet["concept"]))
        mongodb_create_character_sheet(CharacterSheetCreate(
            entity_id=UUID(sheet["id"]), game_system_id=UUID(DIS_SYSTEM_ID), system_name=gs["name"],
            stats=sheet["attributes"], skills=sheet["skills"],
            resources={k: v["max"] for k, v in sheet["resources"].items()},
            background=sheet["concept"]))
        console.print("[green]DiS character saved to roster.[/green]")
    except Exception as exc:
        console.print(f"[yellow]persist: {exc}[/yellow]")

    # 3. PLAY — 5 scenes
    keeper = CanonKeeper()
    story_id = uuid4()
    await keeper.create_story(story_id=story_id, universe_id=universe_id, title="Salvage Run: Dead Space", story_type="chronicle")

    await play_scene(story_id, sheet, 1, "Distress Beacon",
        "The hauler 'Carrion Lily', drifting dark in Dead Space; airlock cycling on emergency power.",
        ["I dock and board the derelict, scanning the dark corridor for survivors and salvage.",
         "I pry open the jammed bulkhead with my Tech tools to reach the bridge."])
    await play_scene(story_id, sheet, 2, "The Bridge",
        "Cryopods sparking with malfunctions; one survivor raving about Void Corruption spreading through the ship.",
        ["I try to calm the raving survivor and get him to tell me what happened here.",
         "I jack into the ship's core to read the logs about the corruption."])
    await play_scene(story_id, sheet, 3, "Cosmic Mutation",
        "A void-corrupted crewmember — flesh warped by Cosmic Mutation — lunges from the dark.",
        ["The mutated thing attacks. I draw my vacuum pistol and fire at the warped crewman.",
         "It claws into me; I spend a Void Point to steady my mind against the unreality and strike back."])
    await play_scene(story_id, sheet, 4, "The Reactor",
        "The Power Source is failing; Frame Integrity dropping as the ship groans toward breakup.",
        ["I rush to the reactor and use Tech to reroute Output Power and stabilize the failing core.",
         "Sparks and radiation — I push through the burn to lock down the breach."])
    await play_scene(story_id, sheet, 5, "Escape into Dead Space",
        "The Carrion Lily is tearing apart; my salvage shuttle waits at the airlock.",
        ["I grab the salvage I came for and burn the thrusters to escape before the hull splits.",
         "Clear of the wreck, I set course for the Hub, the void still whispering behind me — the run is over."])

    log("\n===== SESSION COMPLETE =====")
    console.rule("[bold cyan]DiS session complete")


if __name__ == "__main__":
    asyncio.run(main())
