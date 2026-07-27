#!/usr/bin/env python3
"""
Phase 3: Play a short VTM scene with Phyre, exercising core mechanics against
the seeded game system + her actor sheet:

  Turn 1 — Feeding   (drain Frank → Blood Pool up, Hunger down)
  Turn 2 — Combat    (Celerity dodge + Potence strike on Henry; damage)
  Turn 3 — Blood Sorcery, restricted by the Mark

Captures narrative, resolution, and resource deltas to the transcript + logs.
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

from monitor_agents.loops.scene_loop import SceneLoop

nest_asyncio.apply()
console = Console()
TRANSCRIPT = os.path.join(_LOGDIR, "test_dialogue_transcript.txt")


def log_line(text: str) -> None:
    with open(TRANSCRIPT, "a") as f:
        f.write(text + "\n")


async def play_turn(loop: SceneLoop, n: int, label: str, player_input: str) -> dict:
    console.rule(f"[bold]Turn {n}: {label}")
    console.print(f"[bold green]Player:[/bold green] {player_input}")
    log_line(f"\n--- Turn {n}: {label} ---")
    log_line(f"Player: {player_input}")

    result = await loop.run(player_input)

    narrative = result.get("narrative_text") or ""
    resolution = result.get("resolution") or {}
    deltas = result.get("resource_deltas") or []

    console.print(f"[bold blue]GM:[/bold blue] {narrative}")
    res_summary = {
        k: resolution.get(k)
        for k in ("action_type", "stat_used", "success_level", "outcome", "difficulty", "total_successes", "has_harm")
        if resolution.get(k) is not None
    }
    console.print(f"[dim]resolution:[/dim] {res_summary}")
    console.print(f"[dim]resource_deltas:[/dim] {deltas}")

    log_line(f"GM: {narrative}")
    log_line(f"resolution: {json.dumps(res_summary, default=str)}")
    log_line(f"resource_deltas: {json.dumps(deltas, default=str)}")
    return result


async def main() -> None:
    console.rule("[bold cyan]Phase 3: VTM Mechanics Playtest")
    log_line("\n===== PHASE 3: MECHANICS PLAYTEST =====")

    with open(os.path.join(_LOGDIR, "current_session.json")) as f:
        session = json.load(f)
    universe_id = session["universe_id"]
    story_id = session["story_id"]
    system_id = session["system_id"]
    actor = session["actor_context"]

    console.print(f"Universe {universe_id} | System {system_id}")
    console.print(f"Actor: {actor['name']} | Blood {actor['resources']['Blood Pool']} | "
                  f"Health {actor['resources']['Health']} | disciplines {actor['disciplines']}")

    gameplay_scene_id = uuid4()

    # Seed Phyre's working state so the ResourceEngine has Blood Pool / Health /
    # Hunger to operate on from the very first turn.
    from monitor_data.schemas.working_state import WorkingStateCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_working_state
    mongodb_create_working_state(WorkingStateCreate(
        entity_id=UUID(actor["id"]),
        scene_id=gameplay_scene_id,
        story_id=UUID(story_id),
        base_stats={k: v for k, v in actor["attributes"].items()},
        resources=actor["resources"],
    ))
    console.print("[dim]Seeded working state for Phyre.[/dim]")

    loop = SceneLoop(
        scene_id=gameplay_scene_id,
        story_id=UUID(story_id),
        universe_id=UUID(universe_id),
        system_id=system_id,
        play_mode="dice_game_system",
        actor_id=UUID(actor["id"]),
        actor_context=actor,
        session_tone="grim",
    )

    # Actions phrased as ATTEMPTS (not declared outcomes) so the resolver rolls
    # dice instead of triggering forced-narrative pushback.
    await play_turn(
        loop, 1, "Feeding",
        "Ravenous from torpor, I lunge at Frank the squatter and try to pin him and feed, "
        "spending no blood — I want to drain him to refill my Blood Pool and ease my Hunger.",
    )
    await play_turn(
        loop, 2, "Combat (Celerity + Potence)",
        "Henry charges me with a steel pipe. I spend a point of blood to fuel Celerity and try to "
        "dodge, then attempt a Potence-powered strike to his ribs.",
    )
    await play_turn(
        loop, 3, "Blood Sorcery vs the Mark",
        "I spend blood and attempt to invoke Blood Sorcery on the pooled blood — knowing the Mark "
        "on my hand may flare and resist me. I try anyway.",
    )

    console.print("[bold cyan]Phase 3 complete. Full transcript in test_logs/test_dialogue_transcript.txt[/bold cyan]")
    log_line("\n===== END OF PLAYTEST =====")


if __name__ == "__main__":
    asyncio.run(main())
