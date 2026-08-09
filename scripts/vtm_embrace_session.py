#!/usr/bin/env python3
"""VtM Embrace session harness — character creation, scene loop, transcript.

Run from repo root:
    uv run python scripts/vtm_embrace_session.py

Drives the existing CharacterCreationLoop and SceneLoop with an LLM player
(InstructablePlayer over Gemini 2.5 Flash via litellm). Writes a markdown +
JSON transcript to tests/e2e/logs/vtm_embrace/.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

# Make sibling modules importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog  # noqa: E402

from scripts._shared_vtm import (  # noqa: E402
    format_dice_highlight,
    make_minimax_player_spec,
    ping_player_model,
    setup_logging,
    utc_timestamp,
)

log = structlog.get_logger()

# --- Scenario constants -----------------------------------------------------

# Scenario pack. Pick via env: SCENARIO=dis_salvage uv run python ...
import os as _os

SCENARIOS: dict[str, dict[str, Any]] = {
    "vtm_embrace": {
        "system_id": "a227676a-edab-4a43-80d9-8f76b74ff289",  # VtM v5 (resolved dynamically if missing)
        "system_name_hint": "Masquerade",
        "player_concept": (
            "Cassia Vance, 24, just Embraced by a Ventrue elder in Los Angeles, 1999. "
            "Former junior copywriter at a downtown ad agency. Quiet, observant, "
            "pragmatic -- but the Beast is new and hungry."
        ),
        "player_seed": (
            "You've woken up in a downtown LA motel room. Your Sire is gone. "
            "The sun is coming up outside the blackout curtains. The neon sign "
            "across the street bleeds pink through the gaps."
        ),
        "player_goal": (
            "Drive the scene forward; react to the GM's last narration. "
            "Stay in character as a frightened neonate who is trying not to die."
        ),
        "scene_titles": [
            "Chapter 1: The Motel Room",
            "Chapter 2: First Hunt",
            "Chapter 3: The Sheriff's Summons",
            "Chapter 4: Court Politics",
            "Chapter 5: The Beast Stirs",
        ],
        "transcript_subdir": "vtm_embrace",
    },
    "dis_salvage": {
        "system_id": "8ad46bf1-3cdd-48c9-9c29-b9139fae0a00",  # Death in Space
        "system_name_hint": "Death in Space",
        "player_concept": (
            "Cass Rix, 31, chrome-augmented salvager aboard the Ozymandias, "
            "a beat-up Scrapper-class hauler. Ten years scraping derelicts in "
            "the Outer Belt. Cynical, practical, dry-humored -- but the last "
            "salvage run went sideways and you know it."
        ),
        "player_seed": (
            "You're on the bridge of the Ozymandias, drifting in the shadow of "
            "a half-decommissioned orbital platform. The hull's been breached "
            "twice, the captain's missing, and the life-support is bleeding "
            "oxy at a rate you can't afford."
        ),
        "player_goal": (
            "Drive the scene forward; react to the GM's last narration. "
            "Stay in character as a hardened salvager making impossible choices."
        ),
        "scene_titles": [
            "Chapter 1: Drift",
            "Chapter 2: Breach",
            "Chapter 3: The Derelict",
            "Chapter 4: Signal in the Black",
            "Chapter 5: The Airlock",
        ],
        "transcript_subdir": "dis_salvage",
    },
    "7th_sea_masquerade": {
        "system_id": "f0e1d2c3-b4a5-4968-9876-543210fedcba",
        "system_name_hint": "7th Sea",
        "universe_keywords": ["7th sea", "theah"],
        "player_concept": (
            "Donatello, 28, a Vodacce duelist and courtier -- eloquent, vain, "
            "reckless in love and lethal with a rapier. You were raised on the "
            "dueling grounds of half a dozen Vodacce city-states. Tonight "
            "matters."
        ),
        "player_seed": (
            "You are at the masked ball in the Palazzo d'Oro in Venice, the "
            "first night of Carnevale. The Vodacce fleet dominates the inner "
            "sea. Somewhere beneath the music and the masks, knives are "
            "already out."
        ),
        "player_goal": (
            "Drive the scene forward; react to the GM's last narration. "
            "Speak and act with swashbuckling style; every Raise you spend "
            "should *look* good. Keep it 1-3 sentences per turn."
        ),
        "scene_titles": [
            "Chapter 1: The Masquerade",
            "Chapter 2: Three Daggers",
            "Chapter 3: The Ambassador's Neck",
            "Chapter 4: The Wax Letter",
            "Chapter 5: The Second Dance",
        ],
        "transcript_subdir": "7th_sea_masquerade",
    },
}

SCENARIO_NAME = _os.environ.get("SCENARIO", "vtm_embrace")
if SCENARIO_NAME not in SCENARIOS:
    raise SystemExit(f"unknown SCENARIO={SCENARIO_NAME!r}; choices: {sorted(SCENARIOS)}")
SCN = SCENARIOS[SCENARIO_NAME]

VTM_SYSTEM_ID = SCN["system_id"]
PLAYER_CONCEPT = SCN["player_concept"]
PLAYER_SEED = SCN["player_seed"]
PLAYER_GOAL = SCN["player_goal"]
PLAYER_LANGUAGE = "en"
PLAYER_MODEL = "openai/MiniMax-M2.7"  # MiniMax-M2.7 is a thinking model — see make_minimax_player_spec
PLAYER_TEMPERATURE = 0.9
SCENE_TITLES = SCN["scene_titles"]

# Default 5 turns/scene. Override via env: SCENARIO_TURNS_PER_SCENE=1 uv run ...
TURNS_PER_SCENE = int(_os.environ.get("SCENARIO_TURNS_PER_SCENE", "5"))
PER_TURN_TIMEOUT_SECONDS = float(_os.environ.get("SCENARIO_PER_TURN_TIMEOUT", "120"))

TRANSCRIPT_DIR = Path("tests/e2e/logs") / SCN["transcript_subdir"]


# --- Player builder ---------------------------------------------------------

def _build_player():
    from monitor_agents.players import InstructablePlayer, PlayerContext

    return InstructablePlayer(
        spec=make_minimax_player_spec(
            model=PLAYER_MODEL,
            temperature=PLAYER_TEMPERATURE,
            max_tokens=220,
        ),
        context=PlayerContext(
            concept=PLAYER_CONCEPT,
            seed=PLAYER_SEED,
            goal=PLAYER_GOAL,
            language=PLAYER_LANGUAGE,
        ),
        recent_turns_max=3,
    )


# --- Phase B: character creation --------------------------------------------

async def _ensure_universe() -> str:
    """Find an existing universe matching this scenario, or create one. Return universe_id."""
    from monitor_data.tools.neo4j_tools.core import (
        neo4j_list_universes, neo4j_create_universe,
        neo4j_list_multiverses, neo4j_create_multiverse,
    )
    from monitor_data.schemas.universe import UniverseCreate, MultiverseCreate

    # Scenario-specific keywords; fall back to scenario name
    keywords = SCN.get("universe_keywords") or [SCN["system_name_hint"].lower()]
    universes = neo4j_list_universes()
    for u in universes:
        if not u.name:
            continue
        ln = u.name.lower()
        if any(k in ln for k in keywords):
            log.info("universe.found", universe_id=str(u.id), name=u.name, keywords=keywords)
            return str(u.id)

    mvs = neo4j_list_multiverses()
    multiverse_id = mvs[0].id if mvs else neo4j_create_multiverse(
        MultiverseCreate(name="MONITOR Sandbox Multiverse")
    ).id

    new = neo4j_create_universe(
        UniverseCreate(
            multiverse_id=multiverse_id,
            name=f"{SCN['system_name_hint']} Sandbox",
            description=f"Sandbox universe for {SCN['system_name_hint']} sessions.",
        )
    )
    log.info("universe.created", universe_id=str(new.id))
    return str(new.id)


async def run_character_creation(player, universe_id: str) -> tuple[str, dict[str, Any]]:
    """Drive character creation via the player LLM.

    Returns (actor_id, actor_context) where actor_context is the dict that
    SceneLoop accepts (includes attributes/resources/skills).
    """
    from monitor_agents.loops.character_creation_loop import CharacterCreationLoop
    from monitor_data.db.mongodb import get_mongodb_client

    # Resolve the VtM system ID dynamically -- several VtM variants exist
    # and the hardcoded e2e_full_loop_scenarios id may not be seeded.
    gs = None
    coll = get_mongodb_client()["game_systems"]
    candidate = coll.find_one({"system_id": VTM_SYSTEM_ID})
    if candidate:
        gs = candidate
    else:
        hint = SCN["system_name_hint"]
        for c in coll.find({"name": {"$regex": hint, "$options": "i"}}):
            gs = c
            log.warning("system.fallback", system_id=c.get("system_id"), name=c.get("name"))
            break
    if not gs:
        raise RuntimeError(
            f"no '{SCN['system_name_hint']}' game system seeded; "
            "run the scenario's bootstrap script first."
        )

    cc_loop = CharacterCreationLoop(game_context=gs)

    step_result = await cc_loop.start()
    if step_result.get("complete"):
        final_character = step_result.get("character", {})
    else:
        final_character = None
        for step_idx in range(12):
            gm_msg = step_result.get("gm_message") or step_result.get("error") or ""
            log.info("character_creation.gm", step=step_idx, msg=str(gm_msg)[:200])
            answer, intent = await player.next()
            log.info(
                "character_creation.player",
                step=step_idx,
                answer=str(answer)[:200],
                intent=str(intent),
            )
            step_result = await cc_loop.process_player_input(answer)
            if step_result.get("complete"):
                final_character = step_result.get("character", {})
                break
            if step_result.get("error") and not step_result.get("gm_message"):
                log.error("character_creation.error", error=step_result["error"])
                break
        if final_character is None:
            raise RuntimeError("Character creation did not complete in 12 steps")

    actor_id = str(uuid.uuid4())

    # Fill in missing attributes/resources from system defaults
    attributes = final_character.get("attributes") or {}
    if not attributes:
        for attr in gs.get("attributes") or []:
            nm = attr.get("name")
            if not nm:
                continue
            lo = int(attr.get("min_value", 1))
            hi = int(attr.get("max_value", 5))
            attributes[nm] = max(lo, min(hi, (lo + hi) // 2 or 3))

    resources = final_character.get("resources") or {}
    if not resources:
        log.warning("character_creation.no_resources", name=final_character.get("name"))
        seen = set()
        for res in gs.get("resources") or []:
            nm = res.get("name")
            if not nm or nm.lower() in seen:
                continue
            seen.add(nm.lower())
            mx = int(
                res.get("max_value")
                or res.get("default_value")
                or res.get("starting_value")
                or 10
            )
            resources[nm] = {"current": mx, "max": mx}

    actor_context = {
        **final_character,
        "attributes": attributes,
        "resources": resources,
        "id": actor_id,
    }

    # Persist to Neo4j + Mongo
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.character_sheets import CharacterSheetCreate
    from monitor_data.tools.neo4j_tools import neo4j_create_entity
    from monitor_data.tools.mongodb_tools import mongodb_create_character_sheet

    neo4j_create_entity(
        EntityCreate(
            id=uuid.UUID(actor_id),
            universe_id=uuid.UUID(universe_id),
            name=final_character.get("name") or "Cassia Vance",
            entity_type="character",
            sub_type="character",
            is_archetype=False,
            description=final_character.get("concept") or "",
        )
    )
    resolved_system_id = gs.get("system_id") or VTM_SYSTEM_ID
    mongodb_create_character_sheet(
        CharacterSheetCreate(
            entity_id=uuid.UUID(actor_id),
            game_system_id=uuid.UUID(resolved_system_id),
            system_name=gs.get("name"),
            stats=attributes,
            skills=final_character.get("skills") or {},
            resources={k: v.get("max", 10) if isinstance(v, dict) else v for k, v in resources.items()},
            background=final_character.get("concept"),
        )
    )

    log.info(
        "character_creation.done",
        actor_id=actor_id,
        name=final_character.get("name"),
        attrs=list(attributes.keys()),
    )
    # Stash the resolved system id so later phases don't need to re-resolve.
    actor_context["_resolved_system_id"] = resolved_system_id
    return actor_id, actor_context


def _resolved_system_id(actor_context: dict[str, Any]) -> str:
    return actor_context.get("_resolved_system_id") or VTM_SYSTEM_ID


# --- Phase C: bootstrap story + scene ---------------------------------------

def bootstrap_session(
    actor_id: str, universe_id: str, system_id: str,
) -> tuple[str, str]:
    """Return (story_id, scene_id). Universe must already exist."""
    from monitor_agents.loops.session_bootstrap import bootstrap_story_scene

    session_dict = {
        "universe_id": universe_id,
        "system_id": system_id,
        "character_id": actor_id,
        "title": "VtM Embrace -- Cassia Vance",
        "mode": "autonomous_gm",
        "tone": "grim",
    }
    story_id, scene_id, err = bootstrap_story_scene(session_dict)
    if err:
        raise RuntimeError(f"bootstrap_story_scene failed: {err}")
    log.info("bootstrap.story_scene", story_id=str(story_id), scene_id=str(scene_id))
    return str(story_id), str(scene_id)


# --- Phase D: scene loop with multi-scene progression -----------------------

def _next_scene(story_id: str, universe_id: str, actor_id: str, system_id: str) -> str:
    """Mint a fresh scene under the same story_id."""
    from monitor_agents.loops.session_bootstrap import bootstrap_story_scene

    session_dict = {
        "story_id": story_id,
        "universe_id": universe_id,
        "system_id": system_id,
        "character_id": actor_id,
        "title": "Continuing Story",
        "mode": "autonomous_gm",
        "tone": "grim",
    }
    _, scene_id, err = bootstrap_story_scene(session_dict)
    if err:
        raise RuntimeError(f"next-scene bootstrap failed: {err}")
    return str(scene_id)


async def run_scenes(
    story_id: str,
    universe_id: str,
    actor_id: str,
    actor_context: dict[str, Any],
    player,
) -> list[dict[str, Any]]:
    """Run 5 scenes x TURNS_PER_SCENE turns; return list of per-turn dicts."""
    from monitor_agents.loops.scene_loop import SceneLoop

    system_id = _resolved_system_id(actor_context)
    transcript: list[dict[str, Any]] = []
    current_scene_id = None

    for scene_idx, title in enumerate(SCENE_TITLES):
        current_scene_id = _next_scene(story_id, universe_id, actor_id, system_id)

        loop = SceneLoop(
            scene_id=uuid.UUID(current_scene_id),
            story_id=uuid.UUID(story_id),
            universe_id=uuid.UUID(universe_id),
            system_id=system_id,
            actor_id=uuid.UUID(actor_id),
            actor_context=actor_context,
            play_mode="dice_game_system",
            roll_mode="auto",
            session_tone="grim",
        )

        log.info("scene.start", scene_idx=scene_idx, title=title)

        for turn_idx in range(TURNS_PER_SCENE):
            try:
                action_text, intent = await asyncio.wait_for(
                    player.next(), timeout=PER_TURN_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                action_text, intent = ("I take stock of the situation.", "fallback (player timeout)")
                log.warning("turn.player_timeout", scene=scene_idx, turn=turn_idx)

            gm_text = ""
            degraded = None
            resolution = None
            fallback_used = False
            try:
                response = await asyncio.wait_for(
                    loop.run(action_text), timeout=PER_TURN_TIMEOUT_SECONDS
                )
                gm_text = (response or {}).get("narrative_text") or ""
                resolution = (response or {}).get("resolution")
                degraded = (response or {}).get("degraded")
                if not gm_text:
                    fallback_used = True
                    log.warning(
                        "turn.empty_narrative",
                        scene=scene_idx,
                        turn=turn_idx,
                        response_keys=list((response or {}).keys()),
                    )
            except asyncio.TimeoutError:
                fallback_used = True
                gm_text = "(turn timed out)"
                log.error("turn.gm_timeout", scene=scene_idx, turn=turn_idx)
            except Exception as exc:  # noqa: BLE001
                fallback_used = True
                gm_text = "(turn errored)"
                degraded = {"error_class": type(exc).__name__, "message": str(exc)}
                log.error("turn.exception", scene=scene_idx, turn=turn_idx, err=str(exc))

            try:
                player.observe(gm_text=gm_text, player_text=action_text, intent=intent)
            except Exception as exc:  # noqa: BLE001
                log.warning("turn.observe_failed", err=str(exc))

            transcript.append({
                "scene_idx": scene_idx,
                "scene_title": title,
                "turn_idx": turn_idx,
                "action": action_text,
                "intent": intent,
                "gm_text": gm_text,
                "resolution": resolution,
                "degraded": degraded,
                "fallback_used": fallback_used,
            })

        # Force canonization between scenes
        try:
            await asyncio.wait_for(loop.finalize(), timeout=PER_TURN_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001
            log.warning("scene.finalize_failed", scene=scene_idx, err=str(exc))

    return transcript


# --- Phase E: transcript rendering ------------------------------------------

def render_transcript(
    *,
    actor_id: str,
    actor_name: str,
    transcript: list[dict[str, Any]],
    ts: str,
) -> tuple[Path, Path]:
    """Render the run as markdown + JSON. Return paths."""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = TRANSCRIPT_DIR / f"vtm_embrace_{ts}.md"
    json_path = TRANSCRIPT_DIR / f"vtm_embrace_{ts}.json"

    md_lines = [
        f"# VtM Embrace -- {actor_name}",
        "",
        f"_Run timestamp (UTC): {ts}_",
        f"_Actor ID: {actor_id}_",
        f"_Player LLM: {PLAYER_MODEL}_",
        "",
    ]
    for scene_idx, title in enumerate(SCENE_TITLES):
        md_lines.append(f"## {title}")
        md_lines.append("")
        scene_turns = [t for t in transcript if t["scene_idx"] == scene_idx]
        for turn in scene_turns:
            dice = (turn.get("resolution") or {}).get("dice_results") if turn.get("resolution") else None
            dice_line = format_dice_highlight(turn["action"], dice)
            md_lines.append(f"**You:** {turn['action']}")
            if dice_line:
                md_lines.append(f"_{dice_line}_")
            md_lines.append("")
            degraded = turn.get("degraded")
            fallback = turn.get("fallback_used")
            if degraded:
                md_lines.append(
                    f"_degraded: [{degraded.get('error_class','?')}] {degraded.get('message','')[:200]}_"
                )
            elif fallback:
                md_lines.append("_fallback: empty narrative returned_")
            md_lines.append(f"**GM:** {turn['gm_text']}")
            md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines))
    json_path.write_text(json.dumps(transcript, indent=2, default=str))
    return md_path, json_path


# --- Entry point ------------------------------------------------------------

async def main() -> None:
    setup_logging()
    ts = utc_timestamp()
    log.info("session.start", ts=ts)

    await ping_player_model(PLAYER_MODEL)

    player = _build_player()
    universe_id = await _ensure_universe()
    actor_id, actor_context = await run_character_creation(player, universe_id)
    actor_name = actor_context.get("name") or "Cassia Vance"
    log.info("session.character_done", actor_id=actor_id, name=actor_name)

    story_id, scene_id = bootstrap_session(actor_id, universe_id, _resolved_system_id(actor_context))
    log.info("session.boostrapped", story_id=story_id, scene_id=scene_id, universe_id=universe_id)

    transcript = await run_scenes(story_id, universe_id, actor_id, actor_context, player)
    log.info("session.scenes_done", turns=len(transcript))

    md_path, json_path = render_transcript(
        actor_id=actor_id, actor_name=actor_name, transcript=transcript, ts=ts
    )
    print(f"\nTranscript markdown: {md_path}")
    print(f"Transcript JSON:     {json_path}")
    print(f"Actor ID:            {actor_id}")
    print(f"Story ID:            {story_id}")
    print(f"Universe ID:         {universe_id}")


if __name__ == "__main__":
    asyncio.run(main())