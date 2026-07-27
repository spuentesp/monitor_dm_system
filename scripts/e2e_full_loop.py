#!/usr/bin/env python3
"""Full-loop test harness — real character + real scene + real GM pipeline.

SRP: this script orchestrates; the player speaks through ``InstructablePlayer``;
the persistence lives in ``bootstrap_session``. The CLI glue (``main_async``)
only deals with argparse + transcript rendering.

Phases (run in order, all conditional on the CLI flags):

  A. **World** — pick the first existing universe, OR create a brand-new
     one if ``--create-world`` is set (uses ``neo4j_create_universe``).
  B. **Character creation** — drive ``CharacterCreationLoop`` step by step
     with an ``InstructablePlayer`` answering the GM's prompts:
     ``scripted`` → ``MockSpec`` with the scenario's per-step answers,
     ``llm`` → ``InstructedSpec`` so the LLM answers in voice,
     ``skip`` → bypass the loop entirely (used for resume).
     The resulting character is persisted via
     ``neo4j_create_entity`` + ``mongodb_create_character_sheet``.
  C. **First scene** — ``bootstrap_story_scene(session)`` mints a real
     Story + Scene (UUIDs not fabricated). For resume mode, the story
     already exists; bootstrap just adds a fresh Scene under the same
     story_id and rehydrates the actor_context from the existing
     CharacterSheet.
  D. **Multi-scene loop** — for ``--scenes N``, run one ``SceneLoop`` per
     scene, calling ``finalize()`` between scenes so every prior turn
     canonizes before the next begins.
  E. **Transcript** — one markdown + JSON file with named sections for
     each phase and each scene.

Usage::

    # Pick first existing universe, scripted character creation dialog,
    # one scene with 4 turns (the prior default).
    python scripts/e2e_full_loop.py --system vtm --scenario vtm_primogen

    # Brand-new world + real LLM character dialog + three-scene story.
    python scripts/e2e_full_loop.py \\
        --system vtm --scenario vtm_primogen \\
        --create-world --world-name "Awakening in Seattle" \\
        --character-driver llm --scenes 3 --turns-per-scene 4

    # Resume an existing story with one new scene attached.
    python scripts/e2e_full_loop.py \\
        --resume-from-story-id <uuid> --scenes 1 --turns-per-scene 6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Hard timeouts so a stuck cloud provider can't wedge the harness.
try:
    import litellm

    litellm.request_timeout = int(os.environ.get("LITELLM_REQUEST_TIMEOUT", "45"))
    litellm.num_retries = int(os.environ.get("LITELLM_NUM_RETRIES", "0"))
    litellm.drop_params = True
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, "packages/agents/src")
sys.path.insert(0, "packages/data-layer/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))

logger = logging.getLogger("e2e_full_loop")


# ============================================================================
# Session — output of bootstrap_session; passed to run_scene
# ============================================================================


@dataclass
class Session:
    universe_id: str
    system_id: str
    story_id: str
    scene_id: str
    actor_id: str
    actor_context: dict[str, Any]


# ============================================================================
# Phase A — World (create vs pick)
# ============================================================================


async def create_world(*, universe_name: str, description: str, system_id: str) -> str:
    """Create a fresh Universe under a real Multiverse node."""
    from monitor_data.db.neo4j import get_neo4j_client
    from monitor_data.schemas.universe import UniverseCreate
    from monitor_data.tools.neo4j_tools import neo4j_create_universe

    neo = get_neo4j_client()

    # Find or create a Multiverse node (the parent of every Universe).
    rows = neo.execute_read("MATCH (m:Multiverse) RETURN m.id AS id LIMIT 1", {})
    if rows:
        multiverse_id = uuid.UUID(rows[0]["id"])
    else:
        new_id = str(uuid.uuid4())
        # Multiverse requires an Omniverse parent. Ensure one exists first.
        omni_rows = neo.execute_read("MATCH (o:Omniverse) RETURN o.id AS id LIMIT 1", {})
        if omni_rows:
            omniverse_id = omni_rows[0]["id"]
        else:
            omniverse_id = str(uuid.uuid4())
            neo.execute_write("MERGE (o:Omniverse {id: $id})", {"id": omniverse_id})
        neo.execute_write(
            "MATCH (o:Omniverse {id: $oid}) CREATE (m:Multiverse {id: $mid})-[:BELONGS_TO]->(o)",
            {"oid": omniverse_id, "mid": new_id},
        )
        multiverse_id = uuid.UUID(new_id)

    created = neo4j_create_universe(
        UniverseCreate(
            multiverse_id=multiverse_id,
            name=universe_name,
            description=description,
            genre="urban fantasy",
            tone="dark",
            tech_level="modern",
            default_game_system_id=uuid.UUID(system_id),
            default_system_source_type="generic_library",
            default_system_source_id=system_id,
            default_system_name="Vampire: The Masquerade 5th Edition",
        )
    )
    return str(created.id)


def pick_first_universe() -> str:
    """Pick any Universe — used for non-create runs and resume without explicit ID."""
    from monitor_data.db.neo4j import get_neo4j_client

    neo = get_neo4j_client()
    rows = neo.execute_read(
        "MATCH (u:Universe) RETURN u.id AS id LIMIT 50",
    )
    for r in rows:
        uid = r.get("id")
        if uid:
            return str(uid)
    raise SystemExit("no Universe nodes seeded — run scripts/seed_world.py first")


# ============================================================================
# Phase B — Character creation dialog (real player answering GM)
# ============================================================================


@dataclass
class CharCreationStep:
    """One observed step in the character creation dialog."""

    step_index: int
    gm_prompt: str
    player_answer: str
    player_source: str  # "scripted" | "llm"


@dataclass
class CharacterCreationRun:
    """The transcript of one full character creation dialog."""

    scenario: str
    steps: list[CharCreationStep] = field(default_factory=list)
    final_character: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def build_char_creation_player(args, scenario) -> Any:
    """Player driver for character creation dialog.

    scripted — ScriptedSpec with 8 canned structured answers per scenario
               (one per loop step). The canned answers are intentionally
               PARSEABLE by the system: literal "Konstantin Valois",
               "Ventrue", "STR=2, DEX=3" — not in-character prose.
    llm      — InstructedSpec with a char-creation-tuned system prompt
               so the LLM answers structured questions (not roleplay).
    Both paths use the SAME per-scenario structured canned list when
    scripted; llm mode primes nothing and lets the model produce real
    answers from the GM prompts.
    """
    from monitor_agents.players import (
        InstructablePlayer,
        InstructedSpec,
        PlayerContext,
        ScriptedSpec,
    )

    canned = {
        "vtm_primogen": [
            "Konstantin Valois",
            "Ventrue",
            "STR=2, DEX=2, STA=2, CHA=3, MAN=1, COM=2, INT=1, WIT=2, RES=1",
            "Athletics=2, Brawl=1, Finance=2, Investigation=2, Persuasion=1",
            "Celerity=1, Dominate=1",
            "Resources=2, Influence=1",
            "skip",
            "Sired by Sasha in 2007. Predator: Consensualist.",
        ],
        "vtm_embrace": [
            "Lyra Vandermeer",
            "Toreador",
            "STR=1, DEX=3, STA=2, CHA=3, MAN=2, COM=3, INT=1, WIT=1, RES=1",
            "Athletics=1, Brawl=1, Performance=3, Persuasion=2",
            "Celerity=1, Auspex=1",
            "Herd=1, Resources=1",
            "skip",
            "Sired by Camille. Predator: Siren.",
        ],
        "dis_salvage": [
            "Rook 'Rust' Vane",
            "Chrome",
            "Body=4, Tech=4, Savvy=2, Nerve=3",
            "vac-riveter, suit-40pct, family_tape",
            "skip",
            "skip",
            "skip",
            "Chrome salvager, Rust Belt Drift. Predator: Sandman.",
        ],
        "dis_void_whisper": [
            "Echo",
            "Savvy",
            "Body=2, Tech=3, Savvy=4, Nerve=3",
            "tape_recorder, vacsuit, eidetic_chip",
            "skip",
            "skip",
            "skip",
            "Listens before touching. Predator: Consensualist.",
        ],
    }
    answers = canned.get(scenario.name, ["skip"] * 8)
    context = PlayerContext(
        concept=scenario.character_concept,
        seed="",
        goal="answer the GM's character-creation question with the actual mechanical input it asks for",
    )

    if args.character_driver == "llm":
        # Char-creation-tuned system prompt. System-agnostic: same prompt
        # works for VtM, DiS, D&D 5e, Fate, Mistlands, etc. Tells the LLM
        # to answer with structured mechanical input, NOT a scene reaction.
        context.system_prompt = (
            "You are answering the GM's character-creation questions. "
            "Reply with the mechanical answer only — name, clan/class, dot "
            "assignments, skill picks, discipline names, etc. — and nothing "
            "else. One short line. No prose, no scenes, no examples, no "
            "echoing the GM's question. Use tokens from the GM's listed "
            "options when present."
        )
        spec = InstructedSpec(
            model=args.player_model,
            scripted_opens=[],
            temperature=0.3,  # lower temp = more compliant with the structured format above
            max_tokens=180,
        )
    else:
        spec = ScriptedSpec(arc=[(a, "scripted (cc)") for a in answers])

    return InstructablePlayer(spec=spec, context=context, recent_turns_max=3)


async def drive_character_creation(
    loop,
    player,
    *,
    max_steps: int = 12,
) -> CharacterCreationRun:
    """Drive ``CharacterCreationLoop`` end-to-end through the player's answers.

    Returns a transcript with each step. Stops on ``complete`` or after
    ``max_steps`` as a safety ceiling.
    """
    run = CharacterCreationRun(scenario="")
    step_result = await loop.start()
    if step_result.get("complete"):
        run.final_character = step_result.get("character", {})
        return run

    for step_idx in range(max_steps):
        gm_msg = step_result.get("gm_message") or step_result.get("error") or ""
        answer, intent = await player.next()
        run.steps.append(
            CharCreationStep(
                step_index=step_idx,
                gm_prompt=gm_msg,
                player_answer=answer,
                player_source="scripted" if "scripted" in intent else "llm",
            )
        )
        step_result = await loop.process_player_input(answer)
        if step_result.get("complete"):
            run.final_character = step_result.get("character", {})
            break
        if step_result.get("error") and not step_result.get("gm_message"):
            run.error = step_result["error"]
            break
    return run


# ============================================================================
# Phase C — Story + scene bootstrap (or resume)
# ============================================================================


@dataclass
class BootstrapResult:
    universe_id: str
    system_id: str
    story_id: str
    scene_id: str
    actor_id: str
    actor_context: dict[str, Any]


async def bootstrap_full(
    scenario,
    *,
    system_id: str,
    universe_id: str,
    character_creation_player,
    driver_mode: str,
) -> tuple[BootstrapResult, CharacterCreationRun]:
    """World (picked) → character creation dialog → sheet → story → scene 1.

    Returns ``(result, char_creation_run)`` so the transcript includes the
    full per-step dialog the player had with the GM during creation.
    """
    actor_id = uuid.uuid4()

    if driver_mode == "skip":
        char = {
            "name": scenario.character_spec.get("name") or "Player",
            "concept": scenario.character_spec.get("concept") or scenario.character_concept,
            "attributes": {},
            "skills": {},
            "resources": {},
        }
        cc_run = CharacterCreationRun(scenario=scenario.name, final_character=char)
    else:
        from monitor_agents.loops.character_creation_loop import CharacterCreationLoop

        from monitor_data.db.mongodb import get_mongodb_client

        gs = get_mongodb_client()["game_systems"].find_one({"system_id": system_id})
        if not gs:
            raise SystemExit(f"game system {system_id} not seeded")
        cc_loop = CharacterCreationLoop(game_context=gs)
        cc_run = await drive_character_creation(cc_loop, character_creation_player)
        if cc_run.error and not cc_run.final_character:
            raise SystemExit(f"character creation errored: {cc_run.error}")
        char = cc_run.final_character

    # Synthesize any missing attributes / resources from system defaults.
    from monitor_data.db.mongodb import get_mongodb_client

    gs = get_mongodb_client()["game_systems"].find_one({"system_id": system_id})
    attributes = char.get("attributes") or {}
    if not attributes:
        for attr in gs.get("attributes") or []:
            nm = attr.get("name")
            if not nm:
                continue
            lo = int(attr.get("min_value", 1))
            hi = int(attr.get("max_value", 5))
            attributes[nm] = max(lo, min(hi, (lo + hi) // 2 or 3))

    resources = char.get("resources") or {}
    if not resources:
        # Loud fallback — never silent. Production should wire this to a
        # proper character-creation dialog so this never fires. If it does,
        # we want a noisy log line so the run's transcript isn't a lie.
        logger.warning(
            "character-creation loop returned no resources for PC %r; "
            "falling back to system defaults (max_value/default_value/starting_value/10). "
            "This typically means the player LLM gave prose that didn't parse.",
            char.get("name") or "(no name)",
        )
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
        **char,
        "attributes": attributes,
        "resources": resources,
        "universe_id": universe_id,
        "id": str(actor_id),
    }

    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.character_sheets import CharacterSheetCreate
    from monitor_data.tools.neo4j_tools import neo4j_create_entity
    from monitor_data.tools.mongodb_tools import mongodb_create_character_sheet

    neo4j_create_entity(
        EntityCreate(
            id=actor_id,
            universe_id=uuid.UUID(universe_id),
            name=char.get("name") or "Player",
            entity_type="character",
            sub_type="character",
            is_archetype=False,
            description=char.get("concept") or "",
        )
    )
    mongodb_create_character_sheet(
        CharacterSheetCreate(
            entity_id=actor_id,
            game_system_id=uuid.UUID(system_id),
            system_name=gs.get("name"),
            stats=attributes,
            skills=char.get("skills") or {},
            resources={k: v.get("max", 10) if isinstance(v, dict) else v for k, v in resources.items()},
            background=char.get("concept"),
        )
    )

    from monitor_agents.loops.session_bootstrap import bootstrap_story_scene

    session_dict: dict[str, Any] = {
        "universe_id": universe_id,
        "system_id": system_id,
        "character_id": str(actor_id),
        "title": scenario.name,
        "mode": "autonomous_gm",
        "tone": "dramatic",
    }
    story_id, scene_id, err = bootstrap_story_scene(session_dict)
    if err:
        raise SystemExit(f"bootstrap_story_scene failed: {err}")
    if not story_id or not scene_id:
        raise SystemExit("bootstrap returned empty ids")

    return BootstrapResult(
        universe_id=universe_id,
        system_id=system_id,
        story_id=story_id,
        scene_id=scene_id,
        actor_id=str(actor_id),
        actor_context=actor_context,
        # cc_run is also returned alongside so the caller can render the
        # full character-creation dialog in the transcript.
        # (set via tuple in bootstrap_full)
    ), cc_run


async def bootstrap_resume(
    *,
    system_id: str,
    story_id: str,
    turns_per_scene: int,
) -> BootstrapResult:
    """Resume an existing story. Loads universe + character from the latest
    scene's transcript; the helper then mints a new scene under the same
    story_id via the existing story_id branch in bootstrap_story_scene.
    """
    from monitor_data.db.mongodb import get_mongodb_client
    from monitor_data.db.neo4j import get_neo4j_client

    neo = get_neo4j_client()
    story_rows = neo.execute_read(
        "MATCH (s:Story {id: $sid}) RETURN s.universe_id AS uid",
        {"sid": story_id},
    )
    if not story_rows:
        raise SystemExit(f"story {story_id} not found")
    universe_id = story_rows[0]["uid"]

    actor_context: dict[str, Any] = {}
    actor_id = ""

    # Character identity (name, description) lives on the Neo4j Entity,
    # NOT on the MongoDB CharacterSheet — CharacterSheetCreate has no
    # universe_id or name field by design (see character_sheets.py
    # module docstring: "Canonical identity ... lives in Neo4j."). The
    # prior version of this function queried character_sheets by
    # universe_id, a field that doesn't exist on that schema, so the
    # query silently returned zero results every time and resume always
    # ran with an empty actor_context. Query Neo4j for the most recent
    # character Entity in this universe instead, then pull the
    # mechanical sheet by entity_id (a field the sheet DOES have).
    entity_rows = neo.execute_read(
        "MATCH (e:Entity {universe_id: $uid, entity_type: 'character'}) "
        "RETURN e.id AS id, e.name AS name, e.description AS description "
        "ORDER BY e.created_at DESC LIMIT 1",
        {"uid": str(universe_id)},
    )
    if entity_rows:
        actor_id = entity_rows[0]["id"]
        sheet = get_mongodb_client()["character_sheets"].find_one(
            {"entity_id": actor_id},
            sort=[("created_at", -1)],
        )
        actor_context = {
            "name": entity_rows[0].get("name") or "Resumed Character",
            "concept": entity_rows[0].get("description") or "Continuing",
            "stats": (sheet or {}).get("stats", {}),
            "skills": (sheet or {}).get("skills", {}),
            "resources": (sheet or {}).get("resources", {}),
            "universe_id": universe_id,
            "id": actor_id,
        }
        if not sheet:
            logger.warning(
                "resume found character entity %s (%s) but no CharacterSheet "
                "for it — stats/skills/resources will be empty",
                actor_id, actor_context["name"],
            )
    else:
        logger.warning(
            "resume found no character Entity in universe %s — "
            "actor_context will be empty for the resumed scene",
            universe_id,
        )

    from monitor_agents.loops.session_bootstrap import bootstrap_story_scene

    session_dict: dict[str, Any] = {
        "universe_id": universe_id,
        "system_id": system_id,
        "character_id": actor_id,
        "story_id": story_id,
        "title": "Resumed Story",
        "mode": "autonomous_gm",
        "tone": "dramatic",
    }
    story_id_out, scene_id, err = bootstrap_story_scene(session_dict)
    if err:
        raise SystemExit(f"resume bootstrap failed: {err}")

    return BootstrapResult(
        universe_id=universe_id,
        system_id=system_id,
        story_id=story_id_out,
        scene_id=scene_id,
        actor_id=actor_id,
        actor_context=actor_context,
    )


# ============================================================================
# Phase D — Scene runs (one per scene)
# ============================================================================


@dataclass
class TurnObs:
    index: int
    player_source: str
    player_intent: str
    player_text: str
    gm_narrative_text: str
    player_latency_ms: float
    gm_latency_ms: float
    coherence_overlap: int
    fallback_used: bool = False


@dataclass
class SceneRun:
    scene_index: int
    scene_id: str
    turns: list[TurnObs] = field(default_factory=list)

    @property
    def avg_player_latency_ms(self) -> float:
        return (
            sum(t.player_latency_ms for t in self.turns) / len(self.turns) if self.turns else 0.0
        )

    @property
    def avg_gm_latency_ms(self) -> float:
        return (
            sum(t.gm_latency_ms for t in self.turns) / len(self.turns) if self.turns else 0.0
        )


async def run_scene(
    scene_id: str,
    story_id: str,
    universe_id: str,
    system_id: str,
    actor_id: str,
    actor_context: dict[str, Any],
    *,
    player,
    scene_index: int,
    turns: int,
    per_turn_timeout: float,
    scripted_pairs: list[tuple[str, str]],
) -> SceneRun:
    """Drive one SceneLoop run with the player's lines."""
    from monitor_agents.loops.scene_loop import SceneLoop

    loop = SceneLoop(
        scene_id=uuid.UUID(scene_id),
        story_id=uuid.UUID(story_id),
        universe_id=uuid.UUID(universe_id),
        system_id=system_id,
        actor_id=uuid.UUID(actor_id) if actor_id else None,
        actor_context=actor_context,
        play_mode="dice_game_system",
        roll_mode="auto",
        session_tone="dramatic",
    )

    out = SceneRun(scene_index=scene_index, scene_id=scene_id)

    for i in range(turns):
        t_p0 = time.perf_counter()
        try:
            action_text, intent = await asyncio.wait_for(player.next(), timeout=per_turn_timeout)
        except asyncio.TimeoutError:
            action_text, intent = ("I take stock of the situation.", "fallback (player timeout)")
        player_latency = (time.perf_counter() - t_p0) * 1000
        is_scripted = scripted_pairs and i < len(scripted_pairs)

        t_g0 = time.perf_counter()
        gm_text = ""
        fallback_used = False
        try:
            response = await asyncio.wait_for(loop.run(action_text), timeout=per_turn_timeout)
            gm_text = (response or {}).get("narrative_text") or ""
            if not gm_text:
                # SceneLoop can swallow an internal failure (e.g. the
                # Narrator's LLM call hit a rate limit) and return an
                # empty narrative_text without raising. That's still a
                # fallback from the harness's perspective — a turn with
                # no narration is not a successful turn.
                fallback_used = True
                logger.warning(
                    "turn %d: loop.run() succeeded but narrative_text is empty "
                    "(likely an internal Narrator/Resolver failure — check logs "
                    "for rate limits or provider errors)",
                    i,
                )
        except asyncio.TimeoutError:
            fallback_used = True
            gm_text = "(turn timed out)"
        except Exception as exc:  # noqa: BLE001
            logger.warning("turn %d EXCEPTION: %s", i, exc)
            fallback_used = True
            gm_text = "(turn errored)"
        gm_latency = (time.perf_counter() - t_g0) * 1000

        from monitor_agents.players import coherence_count

        overlap = coherence_count(action_text, gm_text)
        player.observe(gm_text=gm_text, player_text=action_text, intent=intent)

        out.turns.append(
            TurnObs(
                index=i,
                player_source="scripted" if is_scripted else player_source_label(player),
                player_intent=intent,
                player_text=action_text,
                gm_narrative_text=gm_text,
                player_latency_ms=player_latency,
                gm_latency_ms=gm_latency,
                coherence_overlap=overlap,
                fallback_used=fallback_used,
            )
        )

    # Force scene completion so CanonKeeper actually evaluates this scene's
    # accumulated pending_proposals (entity promotion gate, facts, etc.)
    # before the harness moves on. Without this the scene's proposals sit
    # unevaluated forever — canonize_checkpoint only fires on scene_complete
    # or max_turns, and a short test scene hits neither on its own.
    try:
        await asyncio.wait_for(loop.finalize(), timeout=per_turn_timeout)
    except Exception as exc:  # noqa: BLE001
        logger.warning("scene %d: finalize() failed: %s", scene_index, exc)

    return out


def player_source_label(player) -> str:
    spec_name = type(player.spec).__name__
    return {
        "ScriptedSpec": "scripted",
        "InstructedSpec": "llm",
        "MockSpec": "mock",
    }.get(spec_name, spec_name)


# ============================================================================
# Multi-scene orchestration
# ============================================================================


async def next_scene_in_story(
    *,
    story_id: str,
    universe_id: str,
    system_id: str,
    actor_id: str,
) -> str:
    """Mint a fresh scene under the same story_id via bootstrap_story_scene."""
    from monitor_agents.loops.session_bootstrap import bootstrap_story_scene

    # Just call bootstrap_story_scene with no scene_id — helper will create one.
    session_dict: dict[str, Any] = {
        "story_id": story_id,
        "universe_id": universe_id,
        "system_id": system_id,
        "character_id": actor_id,
        "title": "Continuing Story",
        "mode": "autonomous_gm",
        "tone": "dramatic",
    }
    _, scene_id, err = bootstrap_story_scene(session_dict)
    if err:
        raise SystemExit(f"next-scene bootstrap failed: {err}")
    return scene_id


# ============================================================================
# Phase E — Rendering
# ============================================================================


def render_transcript(
    *,
    mode: str,
    scenario_name: str,
    system_id: str,
    universe_id: str,
    story_id: str,
    world_created: bool | None,
    cc_run: CharacterCreationRun | None,
    scene_runs: list[SceneRun],
    total_turns: int,
    fallback_turns: int,
) -> str:
    lines = [
        f"# E2E full-loop: {scenario_name} ({mode})",
        "",
        f"- system_id: {system_id}",
        f"- universe_id: {universe_id}",
        f"- story_id: {story_id}",
    ]
    if world_created is not None:
        lines.append(f"- world created this run: {world_created}")
    lines += [
        f"- scenes: {len(scene_runs)}",
        f"- turns: {total_turns}",
        f"- fallback turns: {fallback_turns}",
        "",
    ]

    if cc_run is not None:
        lines.append("## Phase B — character creation")
        lines.append("")
        for s in cc_run.steps:
            lines.append(f"### CC step {s.step_index} ({s.player_source})")
            lines.append("")
            lines.append(f"**GM:** {s.gm_prompt}")
            lines.append("")
            lines.append(f"**Player:** {s.player_answer}")
            lines.append("")
        lines.append("---")
        lines.append("")

    for sr in scene_runs:
        lines.append(f"## Scene {sr.scene_index} — {sr.scene_id}")
        lines.append("")
        for t in sr.turns:
            lines.append(
                f"### Turn {t.index} — {t.player_source} / {t.player_intent}"
            )
            lines.append("")
            lines.append(f"**PLAYER:** {t.player_text}")
            lines.append("")
            lines.append(
                f"**GM (player_lat {t.player_latency_ms:.0f}ms; "
                f"gm_lat {t.gm_latency_ms:.0f}ms; coherence={t.coherence_overlap}; "
                f"fallback={t.fallback_used}):**"
            )
            lines.append("")
            lines.append(t.gm_narrative_text or "*(no narrative)*")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================


def build_player(args, scenario) -> Any:
    from monitor_agents.players import (
        InstructablePlayer,
        InstructedSpec,
        PlayerContext,
        ScriptedSpec,
    )

    context = PlayerContext(
        concept=scenario.character_concept,
        seed=scenario.seed,
        goal="drive the scene forward; react to the GM's last narration.",
    )

    if args.mock_llm:
        spec = ScriptedSpec(
            arc=[(t.player_action, t.intent) for t in scenario.scripted_opens]
            or [("I look around.", "observe"), ("I take stock of the situation.", "reflection")]
        )
        return InstructablePlayer(spec=spec, context=context, recent_turns_max=3)

    spec = InstructedSpec(
        model=args.player_model,
        scripted_opens=[(t.player_action, t.intent) for t in scenario.scripted_opens],
        temperature=0.7,
        max_tokens=220,
    )
    return InstructablePlayer(spec=spec, context=context, recent_turns_max=3)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    from e2e_full_loop_scenarios import SCENARIOS, SYSTEM_ID_BY_WORLD

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scenario", default="vtm_primogen", choices=list(SCENARIOS.keys()))
    ap.add_argument("--system", default="vtm", choices=["vtm", "dis"])
    ap.add_argument("--universe-id", default=None)
    ap.add_argument("--turns", type=int, default=4,
                    help="Legacy: turns per scene (deprecated — use --turns-per-scene)")
    ap.add_argument("--turns-per-scene", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--mock-llm", action="store_true")
    ap.add_argument("--player-model", default=os.environ.get("MONITOR_PLAYTEST_MODEL", "ollama/qwen2.5:latest"))
    ap.add_argument("--output-dir", default="tests/e2e/logs/full_loop")

    # New flow flags
    ap.add_argument("--create-world", action="store_true",
                    help="Create a fresh Universe instead of picking the first existing one.")
    ap.add_argument("--world-name", default=None,
                    help="Used with --create-world. Auto-generated if not set.")
    ap.add_argument("--character-driver", default="scripted",
                    choices=["scripted", "llm", "skip"],
                    help="How to drive character creation dialog (default: scripted per scenario).")
    ap.add_argument("--scenes", type=int, default=1,
                    help="Number of consecutive scenes under one story_id.")
    ap.add_argument("--resume-from-story-id", default=None,
                    help="Skip world+character creation; resume an existing story.")

    args = ap.parse_args(argv)
    if args.turns_per_scene is None:
        args.turns_per_scene = args.turns
    args.system_id = SYSTEM_ID_BY_WORLD[f"{args.system}-demo"]
    if args.world_name is None:
        args.world_name = f"E2E full-loop {datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    return args


# ============================================================================
# Entry point
# ============================================================================


async def main_async(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from e2e_full_loop_scenarios import SCENARIOS

    scenario = SCENARIOS[args.scenario]

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "WARNING"),
        format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Phase A — world
    if args.resume_from_story_id:
        world_created = None
        universe_id = "(resolved from story)"
    elif args.create_world:
        universe_id = await create_world(
            universe_name=args.world_name,
            description=(
                f"An e2e-created world for the {scenario.name} scenario on {args.system}. "
                "Authored by the harness; meant to be a working test bed, not a hand-tuned canon."
            ),
            system_id=args.system_id,
        )
        world_created = True
    else:
        universe_id = args.universe_id or pick_first_universe()
        world_created = False

    # Phase B — character creation (skip on resume)
    cc_run: CharacterCreationRun | None = None
    story_id: str | None = None

    if args.resume_from_story_id:
        resume = await bootstrap_resume(
            system_id=args.system_id,
            story_id=args.resume_from_story_id,
            turns_per_scene=args.turns_per_scene,
        )
        universe_id = resume.universe_id
        story_id = resume.story_id
        actor_id = resume.actor_id
        actor_context = resume.actor_context
        scene_id = resume.scene_id
        cc_run = None  # skip — resume has no character-creation phase
    else:
        cc_player = build_char_creation_player(args, scenario)
        boot, cc_run = await bootstrap_full(
            scenario,
            system_id=args.system_id,
            universe_id=universe_id,
            character_creation_player=cc_player,
            driver_mode=args.character_driver,
        )
        story_id = boot.story_id
        actor_id = boot.actor_id
        actor_context = boot.actor_context
        scene_id = boot.scene_id

    # Phase D — multi-scene
    scene_runs: list[SceneRun] = []
    gameplay_player = build_player(args, scenario)
    scripted_pairs = [(t.player_action, t.intent) for t in scenario.scripted_opens]

    for scene_idx in range(args.scenes):
        run = await run_scene(
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
            system_id=args.system_id,
            actor_id=actor_id,
            actor_context=actor_context,
            player=gameplay_player,
            scene_index=scene_idx,
            turns=args.turns_per_scene,
            per_turn_timeout=args.timeout,
            scripted_pairs=scripted_pairs,
        )
        scene_runs.append(run)

        # Mint the next scene under the same story.
        if scene_idx + 1 < args.scenes:
            scene_id = await next_scene_in_story(
                story_id=story_id,
                universe_id=universe_id,
                system_id=args.system_id,
                actor_id=actor_id,
            )

    total_turns = sum(len(s.turns) for s in scene_runs)
    fallback_turns = sum(1 for s in scene_runs for t in s.turns if t.fallback_used)

    md = render_transcript(
        mode=("resume" if args.resume_from_story_id else ("create-world" if args.create_world else "pick-world")),
        scenario_name=scenario.name,
        system_id=args.system_id,
        universe_id=universe_id,
        story_id=story_id,
        world_created=world_created,
        cc_run=cc_run,
        scene_runs=scene_runs,
        total_turns=total_turns,
        fallback_turns=fallback_turns,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = "_resume" if args.resume_from_story_id else ("_new" if args.create_world else "_pick")
    md_path = output_dir / f"full_loop_{scenario.name}{suffix}_{stamp}.md"
    json_path = output_dir / f"full_loop_{scenario.name}{suffix}_{stamp}.json"
    md_path.write_text(md, encoding="utf-8")
    json_payload = {
        "scenario": scenario.name,
        "universe_id": universe_id,
        "story_id": story_id,
        "world_created": world_created,
        "scene_runs": [asdict(s) for s in scene_runs],
        "total_turns": total_turns,
        "fallback_turns": fallback_turns,
    }
    json_path.write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")

    print(f"mode:            {'resume' if args.resume_from_story_id else ('create-world' if args.create_world else 'pick-world')}")
    print(f"scenario:        {scenario.name}")
    print(f"universe_id:     {universe_id}")
    print(f"story_id:        {story_id}")
    print(f"scenes:          {len(scene_runs)}")
    print(f"turns:           {total_turns}")
    print(f"fallback turns:  {fallback_turns}")
    print(f"md:              {md_path}")
    print(f"json:            {json_path}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
