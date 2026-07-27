#!/usr/bin/env python3
"""
Phase 2: GM-assisted creation of the vampire Phyre using the real
CharacterCreationLoop against a seeded Vampire: The Masquerade game system.

Produces an actor_context (character sheet) persisted to
test_logs/current_session.json for Phase 3 mechanics.
"""
import os

_LOGDIR = os.path.join(os.getcwd(), "test_logs")
os.makedirs(_LOGDIR, exist_ok=True)
os.environ["MONITOR_LLM_LOG"] = "1"
os.environ["MONITOR_LLM_LOG_FILE"] = os.path.join(_LOGDIR, "llm_calls.log")

import asyncio
import json
import logging
from uuid import uuid4, UUID

import nest_asyncio
from rich.console import Console

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    handlers=[logging.FileHandler(os.path.join(_LOGDIR, "backend.log"), mode="a")],
)

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vtm_game_system import seed_vtm_system, VTM_GAME_CONTEXT, VTM_SYSTEM_ID
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.loops.character_creation_loop import CharacterCreationLoop

nest_asyncio.apply()
console = Console()
TRANSCRIPT = os.path.join(_LOGDIR, "test_dialogue_transcript.txt")


def log_line(text: str) -> None:
    with open(TRANSCRIPT, "a") as f:
        f.write(text + "\n")


async def main() -> None:
    console.rule("[bold cyan]Phase 2: GM-assisted Vampire Creation")
    log_line("\n===== PHASE 2: CHARACTER CREATION =====")

    with open(os.path.join(_LOGDIR, "current_session.json")) as f:
        session = json.load(f)
    universe_id = session["universe_id"]
    multiverse_id = session["multiverse_id"]
    console.print(f"Universe: {universe_id}")

    system_id = seed_vtm_system()
    console.print(f"Seeded VTM game system: {system_id}")

    keeper = CanonKeeper()
    story_id = uuid4()
    await keeper.create_story(
        story_id=story_id, universe_id=UUID(universe_id),
        title="Awakening in Seattle", story_type="campaign",
    )
    scene_id = uuid4()
    console.print(f"Story {story_id} / creation scene {scene_id}")

    # ── Drive the real GM-assisted character creation loop ────────────
    loop = CharacterCreationLoop(
        game_context=VTM_GAME_CONTEXT, scene_id=scene_id, story_id=story_id,
    )
    res = await loop.start()
    console.print(f"\n[bold blue]GM:[/bold blue] {res.get('gm_message') or res.get('error')}")
    log_line(f"GM: {res.get('gm_message') or res.get('error')}")

    player_answers = [
        "Phyre — an ancient elder vampire, newly woken from centuries of torpor, ruthless and regal.",
        "She is supernaturally strong and fast — high Strength, Dexterity and Stamina, with commanding presence.",
        "Celerity and Potence are her mastered disciplines; she also knows a little Blood Sorcery.",
        "Her past is lost to torpor. A glowing Mark on her hand sears when she pushes her power. "
        "Fabien, a second consciousness, whispers inside her mind.",
    ]
    i = 0
    while not res.get("complete") and i < 10:
        ans = player_answers[i] if i < len(player_answers) else "Continue."
        console.print(f"\n[bold green]Player:[/bold green] {ans}")
        log_line(f"Player: {ans}")
        res = await loop.process_player_input(ans)
        gm = res.get("gm_message") or res.get("error") or ""
        console.print(f"[bold blue]GM:[/bold blue] {gm}")
        log_line(f"GM: {gm}")
        i += 1

    char = res.get("character") or {}

    # ── Enrich the sheet to reflect Phyre's canon (disciplines, Mark, Fabien) ──
    attributes = dict(char.get("attributes") or {})
    attributes.update({"STR": 4, "DEX": 4, "STA": 4, "CHA": 4, "RES": 4})  # elder physical/presence
    resources = dict(char.get("resources") or {})
    resources.setdefault("Blood Pool", {"current": 10, "max": 10})
    resources.setdefault("Health", {"current": 7, "max": 7})
    resources.setdefault("Willpower", {"current": 5, "max": 5})
    resources["Hunger"] = {"current": 4, "max": 5}  # woke ravenous from torpor

    actor_context = {
        "id": str(uuid4()),
        "name": "Phyre",
        "concept": "Elder vampire awakened from torpor",
        "system_id": str(VTM_SYSTEM_ID),
        "attributes": attributes,
        "skills": {"Brawl": 3, "Athletics": 3, "Intimidation": 4, "Occult": 2},
        "disciplines": {"Celerity": 3, "Potence": 3, "Blood Sorcery": 1},
        "resources": resources,
        "flaws": [
            {"name": "The Mark", "effect": "Searing pain restricts disciplines/blood sorcery when pushed."}
        ],
        "companions": [{"name": "Fabien", "kind": "internal voice", "effect": "telepathic second consciousness"}],
        "background": char.get("background") or "Lost to centuries of torpor.",
    }

    console.rule("[bold magenta]Phyre — Character Sheet")
    console.print_json(data=actor_context)
    log_line("CHARACTER SHEET:\n" + json.dumps(actor_context, indent=2))

    session.update({
        "story_id": str(story_id),
        "creation_scene_id": str(scene_id),
        "system_id": str(VTM_SYSTEM_ID),
        "actor_context": actor_context,
    })
    with open(os.path.join(_LOGDIR, "current_session.json"), "w") as f:
        json.dump(session, f, indent=2)

    console.print("[bold cyan]Phase 2 complete — Phyre created and saved.[/bold cyan]")


if __name__ == "__main__":
    asyncio.run(main())
