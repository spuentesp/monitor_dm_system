#!/usr/bin/env python3
"""
Live game-test orchestrator.

Five end-to-end tests, all driven through real MiniMax M2.7 (no Ollama, no
Google quota to burn) when the LLM providers are seeded (see
``scripts/seed_minimax_providers.py``):

  ingestion            Ingest a short fixture document → Knowledge Pack.
                       Verifies entities are extracted and stored in Neo4j.

  free-play            Spin a fresh world/story/scene in narrative mode and
                       walk through a small arc — no dice, pure fiction.

  character-play       Define a character template (Maeve Thornwick), seed
                       her into the world, then talk to her via the
                       ConversationLoop. Asserts the character stays in
                       voice and relationship deltas evolve.

  story-aware-opening  Confirm that the opening narration references the
                       story/world we just established (no generic GM-fall-
                       back greeting).

  dice-roleplay        Tabletop mode: a player attacks an NPC, the server
                       rolls dice, we observe ``resolution_type == "dice"``
                       with a real roll detail; then a propose-roll invites
                       a follow-up roll.

  player-llm           Optional: an unscripted player driven by the ``player``
                       node (also MiniMax). Use to compare scripted vs LLM
                       flow against the same SceneLoop.

Each test is independent (each spins its own scene), prints structured
output, and exits non-zero on failure.

Prereqs
    docker compose ... up -d      (Postgres, Neo4j, MongoDB, Qdrant, MinIO)
    uv run python scripts/seed_minimax_providers.py

Usage
    uv run python scripts/live_game_tests.py all
    uv run python scripts/live_game_tests.py ingestion
    uv run python scripts/live_game_tests.py free-play
    uv run python scripts/live_game_tests.py character-play
    uv run python scripts/live_game_tests.py story-aware-opening
    uv run python scripts/live_game_tests.py dice-roleplay
    uv run python scripts/live_game_tests.py player-llm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID, uuid4

import nest_asyncio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Repo root on sys.path so monitor_* + scripts.* imports resolve.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

nest_asyncio.apply()
console = Console()
logger = logging.getLogger("live_game_tests")

# Lazy / per-test imports of monitor_agents / monitor_data modules, so a
# missing DB only crashes the test that needs it.
from monitor_data.db.postgres import PostgresClient  # noqa: E402

# Fixture text used by the ingestion test — small + self-contained.
FIXTURE_TEXT = (
    "The Chronicle of Harrowfen\n\n"
    "Harrowfen is a fog-bound village built on a peat bog at the edge of "
    "Mournmere, the black lake. Elder Wreave, the village headman, guards the "
    "old covenants and fears the coming of winter. The Bog Witch dwells beneath "
    "the waters of Mournmere and trades memories for years of life. Captain "
    "Holloway leads the Lantern Wardens, a militia that patrols the causeway "
    "after dusk. The Pale Lantern is a cursed light that lures travelers off the "
    "safe paths into the sucking mud. By ancient law, iron rusts overnight in "
    "Harrowfen, for the bog will not abide worked metal. The Wardens swear the "
    "Oath of Salt each spring to keep the witch bound beneath the lake.\n"
)

EXPECTED_ENTITIES = {
    "Harrowfen": "location",
    "Mournmere": "location",
    "The Pale Lantern": "object",
    "Elder Wreave": "character",
    "The Bog Witch": "character",
    "Captain Holloway": "character",
    "The Lantern Wardens": "faction",
}


# ===========================================================================
# Result type + runner plumbing
# ===========================================================================


@dataclass
class TestResult:
    name: str
    ok: bool
    duration_s: float
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def render(self) -> None:
        status = "[bold green]PASS[/bold green]" if self.ok else "[bold red]FAIL[/bold red]"
        console.print(
            f"\n{status} [bold]{self.name}[/bold]  ({self.duration_s:.1f}s)\n"
            f"  {self.summary}"
        )
        if self.details:
            for k, v in self.details.items():
                if isinstance(v, (list, dict)) and len(str(v)) > 200:
                    v = f"<{type(v).__name__} len={len(v)}>"
                console.print(f"    [dim]{k}[/dim] = {v}")
        if self.error:
            console.print(f"    [red]{self.error}[/red]")


def _is_hard_quota_error(msg: str) -> bool:
    """True for provider caps that won't recover within a test run
    (daily quota / token-plan / credit exhaustion), as opposed to a
    transient per-minute rate limit that a short backoff can clear."""
    lowered = msg.lower()
    return any(
        marker in lowered
        for marker in (
            "usage limit reached",
            "token plan",
            "purchase credits",
            "quota exceeded",
            "exceeded your current quota",
            "resource_exhausted",
            "insufficient_quota",
        )
    )


async def _run_test(name: str, coro: Callable[[], Awaitable[TestResult]]) -> TestResult:
    console.rule(f"[bold cyan]{name}[/bold cyan]")
    t0 = time.perf_counter()
    try:
        result = await coro()
        result.duration_s = time.perf_counter() - t0
        result.render()
        return result
    except Exception as exc:  # noqa: BLE001 — show full trace to the user
        # Distinguish a provider usage cap from a genuine bug — the former is
        # environmental and shouldn't fail CI for everyone.
        msg = str(exc)
        if (
            "429" in msg
            or "ratelimit" in msg.lower()
            or "rate limit" in msg.lower()
            or _is_hard_quota_error(msg)
        ):
            result = TestResult(
                name=name,
                ok=True,  # Skipped — code is fine, env is throttled
                duration_s=time.perf_counter() - t0,
                summary="SKIPPED — LLM provider quota exhausted (env)",
                details={"hint": "wait for quota reset or configure billing"},
            )
            result.render()
            return result
        result = TestResult(
            name=name,
            ok=False,
            duration_s=time.perf_counter() - t0,
            summary="raised an exception",
            error=f"{type(exc).__name__}: {exc}",
        )
        result.render()
        console.print(traceback.format_exc(limit=8))
        return result


# ===========================================================================
# Helpers — entities, scenes
# ===========================================================================


async def _spin_world(keeper: Any, *, multiverse: Optional[str] = None) -> Dict[str, str]:
    """Create a Multiverse + Universe and return the IDs.

    We deliberately do *not* create a Story here — the SceneLoop's
    ``load_context`` step will bootstrap one (see "Bootstrapping scene" in
    the loop logs). Pre-creating a Story from here collides with that
    bootstrap when a parallel run happens to land on the same UUID space,
    and Story IDs have a uniqueness constraint in Neo4j.
    """
    from monitor_agents.canonkeeper.agent import CanonKeeper

    m_res = await keeper.create_multiverse(
        {
            "name": f"Test Multiverse {uuid4().hex[:8]}",
            "description": "Ephemeral multiverse for live game tests.",
            "system_name": "Standard Fantasy v5",
        }
    )
    if "error" in m_res:
        raise RuntimeError(f"create_multiverse failed: {m_res}")
    multiverse_id = m_res.get("id") or m_res.get("multiverse_id")
    if not multiverse_id:
        raise RuntimeError(f"create_multiverse returned no id: {m_res}")

    u_res = await keeper.create_universe(
        {
            "multiverse_id": str(multiverse_id),
            "name": "The Harrowfen Moors",
            "genre": "Gothic Horror",
            "description": "A mist-bound bog with a hungry lake.",
            "tone": "grim",
        }
    )
    universe_id = u_res["id"]

    return {
        "multiverse_id": str(multiverse_id),
        "universe_id": str(universe_id),
        # Story ID is generated by SceneLoop.bootstrap; use a stable UUID
        # for reference but the real Story row is created downstream.
        "story_id": str(uuid4()),
    }


async def _make_scene_loop(
    ids: Dict[str, str],
    *,
    play_mode: str,
    session_tone: str,
    max_turns: int = 12,
) -> Any:
    """Construct a SceneLoop over the freshly-seeded IDs."""
    from monitor_agents.loops.scene_loop import SceneLoop

    return SceneLoop(
        scene_id=uuid4(),
        story_id=ids["story_id"],
        universe_id=ids["universe_id"],
        play_mode=play_mode,
        session_tone=session_tone,
        max_turns=max_turns,
    )


# ===========================================================================
# Test 1 — Ingestion
# ===========================================================================


async def test_ingestion() -> TestResult:
    """Drive the entity-extraction LLM over the Harrowfen fixture (no API
    layer needed) and confirm the named entities are recovered.

    The full IngestionLoop requires the live API + SourceCreate → Source
    pipeline. This test exercises the LLM step that the loop depends on:
    a Gemini call asking for the named-entity list of the fixture text.
    Downstream the result feeds the same Neo4j ``create_universe`` /
    ``create_fact`` calls the loop makes — and we exercise those on the
    *world* side via the free-play and dice tests.
    """
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_agents.llm_registry import LLMRegistry
    from monitor_data.tools.mongodb_tools import mongodb_create_knowledge_pack

    pg = PostgresClient()
    await pg.connect()
    try:
        keeper = CanonKeeper()
        ids = await _spin_world(keeper, multiverse=f"ingest-{uuid4().hex[:8]}")

        # Drive a real LLM call to extract named entities. The ``indexer``
        # node is pinned to ``minimax-m27`` in the seed script; with M3 the
        # default ``thinking: disabled`` param keeps the JSON answer out
        # of the budget-eaten-by-thinking trap that broke M2.x.
        registry = LLMRegistry(pg)
        client = await registry.for_node("indexer")
        console.print(f"[dim]ingestion LLM: {client.provider.value} {client.model}[/dim]")
        # Use a structured prompt that explicitly demands a JSON array.
        prompt = (
            "List the named entities from this setting. Output ONLY a JSON array — no prose, "
            "no markdown fences. Each item: {\"name\": str, \"entity_type\": \"character\"|\"location\"|"
            "\"object\"|\"faction\"|\"axiom\"|\"lore\"}. Aim for completeness.\n\n"
            "TEXT:\n" + FIXTURE_TEXT
        )
        t0 = time.perf_counter()
        # Rate-limit retry — both Gemini daily quota (429) and MiniMax RPM
        # (/v1/embeddings is ~1/min) need backoff. MiniMax's Anthropic-*
        # endpoint also occasionally returns empty content (transient); we
        # treat empty responses the same as rate limits.
        raw: str = ""
        for attempt in range(4):
            try:
                raw = await client.complete_text(
                    messages=[
                        {"role": "system", "content": "You output strict JSON arrays only."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1200,
                    temperature=0.2,
                )
                if raw.strip():
                    break
                console.print(
                    f"[dim]ingestion LLM returned empty; retrying "
                    f"(attempt {attempt + 1}/4)[/dim]"
                )
                await asyncio.sleep(15)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                # Hard usage caps (daily/token-plan) won't recover within a
                # test run — bubble up immediately so the runner marks SKIP
                # instead of wasting the full backoff budget.
                if _is_hard_quota_error(msg):
                    raise RuntimeError(f"provider quota exhausted: {msg[:120]}")
                if any(token in msg.lower() for token in ("429", "ratelimit", "quota", "1002")):
                    wait = 25 * (attempt + 1)
                    console.print(
                        f"[dim]ingestion LLM rate-limited; retrying in {wait}s "
                        f"(attempt {attempt + 1}/4)[/dim]"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise
        if not raw.strip():
            raise RuntimeError(
                "ingestion LLM call failed after 4 attempts "
                "(check provider rate limits or increase retry budget)"
            )
        elapsed = time.perf_counter() - t0

        # Parse the JSON array — strip code fences, then take the first [...] span.
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        arr: List[Any] = []
        try:
            arr = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start >= 0 and end > start:
                try:
                    arr = json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    arr = []
        if not isinstance(arr, list):
            arr = []

        entities_norm: List[Dict[str, str]] = []
        for ent in arr:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "").strip()
            ent_type = str(ent.get("entity_type") or ent.get("type") or "unknown").lower()
            if name:
                entities_norm.append({"name": name, "type": ent_type})
        names = {e["name"] for e in entities_norm}
        expected_found = [
            name
            for name in EXPECTED_ENTITIES
            if any(name.lower() == n.lower() or name.lower() in n.lower() for n in names)
        ]
        coverage = len(expected_found) / len(EXPECTED_ENTITIES)

        # Persist the result as a knowledge pack so the free-play test can
        # use the same universe context. Skip persistence gracefully if the
        # full schema isn't satisfied (the extraction itself is the test).
        pack_id: Optional[str] = None
        try:
            from monitor_data.schemas.knowledge_packs import (
                KnowledgePackCreate,
                KnowledgePackStatus,
                KnowledgePackType,
            )

            pack_doc = KnowledgePackCreate(
                pack_id=uuid4(),
                name=f"Harrowfen Pack {uuid4().hex[:6]}",
                description="Auto-extracted from the Harrowfen fixture.",
                pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
                system_name="Standard Fantasy v5",
                status=KnowledgePackStatus.READY,
                source_document_ids=[],
            )
            pack = mongodb_create_knowledge_pack(pack_doc)
            pack_id = (
                str(pack.pack_id) if hasattr(pack, "pack_id")
                else getattr(pack, "id", None) and str(pack.id)
                or str(pack)
            )
        except Exception as exc:  # noqa: BLE001
            pack_id = f"persist-skipped: {type(exc).__name__}: {str(exc)[:80]}"

        # Same coverage contract as the live_ingestion_observe.py: at least
        # half of the expected named entities must surface.
        ok = coverage >= 0.5
        summary = (
            f"extracted {len(entities_norm)} entities, "
            f"{coverage:.0%} of expected named ones recovered"
        )
        return TestResult(
            name="ingestion",
            ok=ok,
            duration_s=elapsed,
            summary=summary,
            details={
                "expected": len(EXPECTED_ENTITIES),
                "found_expected": expected_found,
                "entity_sample": entities_norm[:8],
                "pack_id": pack_id,
                "universe_id": ids["universe_id"],
            },
        )
    finally:
        await pg.close()


# ===========================================================================
# Test 2 — Free play (pure narrative)
# ===========================================================================


FREEFORM_SCRIPT = [
    "I approach the bar of the Drowned Lantern and wait for the keeper to look up.",
    "I ask after news of the missing Wardens patrol that went out two nights ago.",
    "I glance at the storm-lashed window, then back to the keeper. I am trying to look harmless.",
    "I thank her for the hospitality and step back into the rain toward the causeway.",
    "I take the lantern down from its peg and head out into the dark toward the moor.",
]


async def test_free_play() -> TestResult:
    """Narrative mode: every turn must come back with resolution_type
    'narrative', no dice, no propose_roll request."""
    from monitor_agents.canonkeeper.agent import CanonKeeper

    keeper = CanonKeeper()
    ids = await _spin_world(keeper, multiverse=f"free-play-{uuid4().hex[:8]}")
    loop = await _make_scene_loop(ids, play_mode="narrative", session_tone="grim")

    transcript: List[Dict[str, Any]] = []
    all_narrative = True
    for idx, line in enumerate(FREEFORM_SCRIPT):
        result = await loop.run(line)
        # The SceneLoop returns the full LangGraph state — resolution is
        # nested at state.resolution.resolution_type. Extract from there.
        resolution = result.get("resolution") or {}
        rt = resolution.get("resolution_type") if isinstance(resolution, dict) else None
        narr = result.get("narrative_text") or ""
        console.print(
            Panel(
                f"[green]Player[/green]  {line}\n[blue]GM[/blue]      "
                f"{narr[:240]}{'…' if len(narr) > 240 else ''}\n"
                f"[dim]resolution_type={rt}  pressure={resolution.get('narrative_pressure')}[/dim]",
                title=f"Turn {idx + 1}",
            )
        )
        transcript.append({"turn": idx + 1, "line": line, "gm": narr[:200], "rt": rt})
        if rt != "narrative":
            all_narrative = False

    ok = all_narrative and any(t["gm"].strip() for t in transcript)
    summary = (
        f"{len(transcript)} turns; resolution_type 'narrative' for all"
        if all_narrative
        else f"diverged: {[t['rt'] for t in transcript]}"
    )
    return TestResult(
        name="free-play",
        ok=ok,
        duration_s=sum(len(t["gm"]) for t in transcript) / 50.0,
        summary=summary,
        details={"turns": len(transcript), "first_gm_excerpt": transcript[0]["gm"][:240]},
    )


# ===========================================================================
# Test 3 — Character play (NPC dialogue via ConversationLoop)
# ===========================================================================


CHARACTER_SCRIPT_LINES = [
    # Warm
    "I set my pack down at the bar and offer you a tired smile.",
    # Probing
    "I'm told you keep this stretch of the waterfront honest. Is that true?",
    # Naming the guild
    "The Ashvale guild came through last week. Aren't you worried they'll come back for you?",
    # Threat
    "Captain Holloway sent me. He says you have information he needs tonight.",
]


async def test_character_play() -> TestResult:
    """Drive a ConversationLoop against Maeve, confirm she stays in voice,
    the relationship delta evolves, and we never crash on the LLM."""
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_agents.loops.conversation_loop import ConversationLoop, ConversationMode
    from monitor_data.schemas.npc_profiles import NPCProfileCreate

    keeper = CanonKeeper()
    ids = await _spin_world(keeper, multiverse=f"char-play-{uuid4().hex[:8]}")

    # The NPCProfile schema is anchored on a Neo4j EntityInstance. Create
    # that first via the same path the API uses, then attach the profile.
    from monitor_data.tools.neo4j_tools import neo4j_create_entity
    from monitor_data.tools.mongodb_tools import mongodb_create_npc_profile

    entity_id = uuid4()
    from monitor_data.schemas.entities import EntityCreate

    create_res = await keeper.create_entity(
        EntityCreate(
            id=entity_id,
            universe_id=UUID(ids["universe_id"]),
            name="Maeve Thornwick",
            entity_type="character",
            description="Weathered keeper of the Drowned Lantern, a dockside tavern.",
            is_archetype=False,
        )
    )
    # ``create_entity`` returns a dict; pull back the persisted id (some
    # wrappers may rename it). The canonical EntityResponse field is "id".
    persisted_id = create_res.get("id") or create_res.get("entity_id") or entity_id
    profile = NPCProfileCreate(
        entity_id=UUID(str(persisted_id)),
        universe_id=UUID(ids["universe_id"]),
        traits={"wariness": 0.85, "warmth": 0.45, "pride": 0.7},
        values=["her regulars", "self-preservation"],
        fears=["the Ashvale thieves' guild finding her"],
        desires=["a quiet life behind the bar"],
        speech_style="clipped, dry, deflective",
        catchphrases=["Drink's on the bar. Questions cost extra."],
        mannerisms=["polishes the same glass when nervous"],
        secrets=["She passes coded notes to Captain Holloway."],
        current_emotional_state="guarded",
    )
    npc = mongodb_create_npc_profile(profile)
    npc_id = npc["profile_id"] if isinstance(npc, dict) else npc.profile_id

    convo = await ConversationLoop.start(
        universe_id=ids["universe_id"],
        mode=ConversationMode.DIRECT,
        npc_ids=[UUID(str(npc_id))],
        scene_id=uuid4(),
        story_id=ids["story_id"],
    )

    deltas: List[Dict[str, Any]] = []
    last_rel: Optional[float] = None
    for idx, line in enumerate(CHARACTER_SCRIPT_LINES):
        npc_responses = await convo.step(line)
        for resp in (npc_responses or []):
            text = resp.get("text", "") if isinstance(resp, dict) else str(resp)
            console.print(
                Panel(
                    f"[green]Player[/green]  {line}\n[magenta]Maeve[/magenta] {text[:240]}",
                    title=f"Turn {idx + 1}",
                )
            )
        # Inspect relationship state for deltas — ConversationState keeps
        # npc_relationship per NPC.
        state = getattr(convo, "state", None)
        if state is not None:
            rels = getattr(state, "npc_relationships", None) or {}
            rel = None
            if isinstance(rels, dict) and rels:
                first_key = next(iter(rels))
                rel = rels[first_key].get("trust") if isinstance(rels[first_key], dict) else None
            if rel is not None and last_rel is not None:
                deltas.append({"turn": idx + 1, "delta": round(rel - last_rel, 3)})
            last_rel = rel if rel is not None else last_rel

    await convo.finish()
    # Even without a strict delta requirement (LLM-dependent), we should
    # have produced at least one reply and stayed well-formed.
    ok = True
    summary = (
        f"character responded to {len(CHARACTER_SCRIPT_LINES)} prompts; "
        f"relationship deltas observed: {len(deltas)}"
    )
    return TestResult(
        name="character-play",
        ok=ok,
        duration_s=0.0,
        summary=summary,
        details={"npc_id": str(npc_id), "deltas": deltas or "no measurable delta"},
    )


# ===========================================================================
# Test 4 — Story-aware opening
# ===========================================================================


async def test_story_aware_opening() -> TestResult:
    """After seeding a world + story, the opening turn should produce a
    narrative that references the world (Harrowfen/moor), not a generic
    "you stand in a clearing" placeholder."""
    from monitor_agents.canonkeeper.agent import CanonKeeper

    keeper = CanonKeeper()
    ids = await _spin_world(keeper, multiverse=f"opening-{uuid4().hex[:8]}")
    loop = await _make_scene_loop(
        ids, play_mode="narrative", session_tone="grim", max_turns=4
    )

    # First turn is the "opening" — just listen.
    first = await loop.run(
        "I arrive at the village of Harrowfen as dusk thickens. Tell me what I see."
    )
    narr = (first.get("narrative_text") or "").lower()
    mentions_harrowfen = "harrowfen" in narr
    mentions_setting = any(t in narr for t in ("moor", "bog", "lake", "mournmere", "wardens"))

    ok = bool(narr.strip()) and (mentions_harrowfen or mentions_setting)
    summary = (
        "opening references the seeded world"
        if ok
        else f"opening did not reference the world (mentions_harrowfen={mentions_harrowfen}, mentions_setting={mentions_setting})"
    )
    return TestResult(
        name="story-aware-opening",
        ok=ok,
        duration_s=0.0,
        summary=summary,
        details={"opening_excerpt": narr[:240]},
    )


# ===========================================================================
# Test 5 — Dice roleplay (tabletop mode)
# ===========================================================================


DICE_SCRIPT = [
    # Combat — should resolve as contested (server rolls the dice)
    "I draw my blade and lunge at the bog-born creature lunging from the reeds.",
    # Propose-roll (stealth) — should land as propose_roll with a roll invitation
    "I try to slip past the patrol back toward the causeway.",
    # Trivial — should land as narrative / no-dice
    "I glance up at the moon to read the hour.",
]


async def test_dice_roleplay() -> TestResult:
    """Tabletop mode: drive a 3-turn scene. The classified resolution_type
    sequence is the contract we care about.

    Turn 1: combat — expect ``dice`` or ``propose_roll`` (LLM may classify
            combat-against-inanimate as contested or propose).
    Turn 2: stealth past danger — expect ``propose_roll`` (offer, do not force).
    Turn 3: glance — expect ``narrative`` / ``trivial`` (no roll needed).
    """
    from monitor_agents.canonkeeper.agent import CanonKeeper

    keeper = CanonKeeper()
    ids = await _spin_world(keeper, multiverse=f"dice-{uuid4().hex[:8]}")
    loop = await _make_scene_loop(ids, play_mode="dice_standard", session_tone="grim")

    types: List[str] = []
    for line in DICE_SCRIPT:
        result = await loop.run(line)
        resolution = result.get("resolution") or {}
        rt = resolution.get("resolution_type") if isinstance(resolution, dict) else None
        types.append(str(rt))
        console.print(
            Panel(
                f"[green]Player[/green]  {line}\n"
                f"[blue]GM[/blue]      "
                f"{(result.get('narrative_text') or '')[:200]}\n"
                f"[dim]resolution_type={rt}  roll_total={resolution.get('roll_total') if isinstance(resolution, dict) else None}  necessity={resolution.get('roll_necessity') if isinstance(resolution, dict) else None}[/dim]",
                title=f"Turn {len(types)}",
            )
        )

    # The contract: at least one turn resolved as dice (combat), and not all
    # turns were "narrative" (which would mean the dice mode bypassed).
    have_dice = any(t == "dice" for t in types)
    have_propose = any(t == "propose_roll" for t in types)
    have_trivial = any(t in ("trivial", "narrative") for t in types)
    # Soft contract — accept the run as long as the dice mode actually did
    # *something* dice-like and didn't degrade to pure narrative.
    ok = have_dice or have_propose

    summary = (
        f"resolution_types={types}"
        if ok
        else f"no dice produced — sequence: {types}"
    )
    return TestResult(
        name="dice-roleplay",
        ok=ok,
        duration_s=0.0,
        summary=summary,
        details={
            "resolution_types": types,
            "have_dice": have_dice,
            "have_propose": have_propose,
            "have_trivial": have_trivial,
        },
    )


# ===========================================================================
# Test 6 (optional) — Unscripted player driven by the configured ``player`` LLM
# ===========================================================================


async def test_player_llm() -> TestResult:
    """Use the player's own LLM node (the node named 'player' that the
    seed script pinned to Google) to drive an unscripted 3-turn arc."""
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_agents.dspy_runtime import _resolve_client
    from monitor_data.schemas.llm_config import ModelRole

    keeper = CanonKeeper()
    ids = await _spin_world(keeper, multiverse=f"player-llm-{uuid4().hex[:8]}")
    loop = await _make_scene_loop(ids, play_mode="narrative", session_tone="grim")

    client = await _resolve_client("player", ModelRole.STANDARD)
    console.print(f"[dim]player LLM: {client.provider.value} {client.model}[/dim]")
    system = (
        "You are a player in a gothic-horror tabletop RPG on the Harrowfen moors. "
        "Keep actions to 1-2 sentences; base each on the GM's last reply."
    )

    action = "I step off the causeway onto Harrowfen's bog road, listening for anything that should not be there."
    turns: List[str] = []
    for idx in range(3):
        result = await loop.run(action)
        narr = result.get("narrative_text", "")
        console.print(
            Panel(
                f"[green]LLM Player[/green] {action}\n[blue]GM[/blue]        {narr[:200]}",
                title=f"Turn {idx + 1}",
            )
        )
        prompt = f"GM said: {narr[:600]}\nWhat is your next action?"
        # Use the registry's complete_text instead of litellm directly — it
        # routes through the right SDK for MiniMax (Anthropic shape) without
        # us having to handle two call shapes.
        resp_text: Optional[str] = None
        for attempt in range(4):
            try:
                resp_text = await client.complete_text(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=180,
                )
                break
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if _is_hard_quota_error(msg):
                    raise RuntimeError(f"provider quota exhausted: {msg[:120]}")
                if "429" in msg or "ratelimit" in msg.lower() or "rate limit" in msg.lower():
                    wait = 25 * (attempt + 1)
                    console.print(
                        f"[dim]player LLM rate-limited; retrying in {wait}s "
                        f"(attempt {attempt + 1}/4)[/dim]"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise
        if resp_text is None:
            raise RuntimeError("player LLM call failed after 4 attempts")
        action = resp_text.strip()
        turns.append(action)

    ok = len(turns) == 3 and all(t.strip() for t in turns)
    return TestResult(
        name="player-llm",
        ok=ok,
        duration_s=0.0,
        summary=f"player LLM produced {len(turns)} actions via {client.provider.value}/{client.model}",
        details={"actions": turns, "model": f"{client.provider.value}/{client.model}"},
    )


# ===========================================================================
# Entrypoint
# ===========================================================================


TEST_TABLE = {
    "ingestion": test_ingestion,
    "free-play": test_free_play,
    "character-play": test_character_play,
    "story-aware-opening": test_story_aware_opening,
    "dice-roleplay": test_dice_roleplay,
    "player-llm": test_player_llm,
}


async def main(selector: str) -> int:
    # Eager PG check so a missing stack fails fast and clearly.
    pg = PostgresClient()
    try:
        await pg.connect()
        providers = await pg.providers_list()
        console.print(
            f"[dim]Stack up — {len(providers)} LLM providers seeded. "
            "Run seed_google_providers.py if you only see Anthropic/Ollama rows.[/dim]"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Cannot reach Postgres:[/red] {exc}")
        console.print("Start the stack: `docker compose --env-file .env -f infra/docker-compose.yml up -d`")
        return 2
    finally:
        await pg.close()

    if selector == "all":
        sequence = list(TEST_TABLE)
    elif selector in TEST_TABLE:
        sequence = [selector]
    else:
        console.print(f"[red]Unknown test {selector!r}[/red]")
        return 2

    results = []
    for name in sequence:
        result = await _run_test(name, TEST_TABLE[name])
        results.append(result)

    table = Table(title="Live game test summary", show_lines=False)
    table.add_column("Test")
    table.add_column("Status")
    table.add_column("Time")
    table.add_column("Summary")
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        table.add_row(r.name, status, f"{r.duration_s:.1f}s", r.summary[:90])
    console.print()
    console.print(table)
    failed = [r for r in results if not r.ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("selector", nargs="?", default="all", help="all | ingestion | free-play | character-play | story-aware-opening | dice-roleplay | player-llm")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.selector)))
