#!/usr/bin/env python3
"""
Live roleplay test — define, assemble, and talk to a test character.

This is the conversation-mode sibling of ``live_narration_dis.py``. Where that
script drives the SceneLoop (a GM narrating a scene), this one drives the
ConversationLoop + NPCVoice agent so we can roleplay *as* a single character —
the same path a future "character section" (à la character.ai / Emochi) would
use to let a player pick someone off the roster and just talk to them.

Two modes, mirroring the two NPCVoice modes:

  direct  — In-character live dialogue. The player speaks; the character
            answers AS themselves. We watch emotional_state + relationship
            deltas evolve turn by turn, then dump the staged proposals.

  actor   — Out-of-character "actor reflection" for GM prep. We ask the
            character's actor about motivations and secrets (ACTOR mode loads
            secrets + hidden triggers that DIRECT mode hides).

Setup is self-contained: it spins up a fresh multiverse → universe → Entity
(Neo4j) + NPCProfile (MongoDB) so the run needs no prior ingestion. Use
``setup`` once and pass the printed IDs to ``direct``/``actor`` to re-use the
same character (the "select from roster" flow), or just run ``direct`` and it
will assemble a fresh character first.

Usage:
    python scripts/live_roleplay_character.py setup
    python scripts/live_roleplay_character.py direct
    python scripts/live_roleplay_character.py direct --universe-id <uid> --npc-id <nid>
    python scripts/live_roleplay_character.py actor  --universe-id <uid> --npc-id <nid>
    python scripts/live_roleplay_character.py roster --universe-id <uid>
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import nest_asyncio
import typer
from rich.console import Console
from rich.panel import Panel

from monitor_agents.canonkeeper import CanonKeeper
from monitor_agents.loops.conversation_loop import ConversationLoop, ConversationMode

nest_asyncio.apply()
console = Console()
logger = logging.getLogger(__name__)

app = typer.Typer(help="Define, assemble, and roleplay against a test character.")


# =============================================================================
# THE TEST CHARACTER
# =============================================================================
#
# Maeve Thornwick is designed to exercise every NPC subsystem:
#   - traits/values/fears/desires      → personality grounding
#   - speech_style/catchphrases         → voice consistency
#   - current_emotional_state           → "what they feel" baseline
#   - hidden triggers (is_hidden=True)  → DIRECT must NOT leak; ACTOR may
#   - secrets                           → DIRECT strips; ACTOR sees them
#   - known facts                       → "what they know" knowledge boundary
#
# The scripted player lines escalate (warm → probing → naming the guild →
# threat) so the relationship deltas and emotional_state visibly shift.

TEST_CHARACTER: Dict[str, Any] = {
    "name": "Maeve Thornwick",
    "role": "tavern keeper",
    "description": (
        "The weathered keeper of the Drowned Lantern, a dockside tavern in "
        "Ashvale. Dry, watchful, and slow to trust — but fiercely loyal once "
        "you are on her good side."
    ),
    "profile": {
        "traits": {
            "wariness": 0.85,
            "warmth": 0.45,
            "pride": 0.7,
            "loyalty": 0.6,
            "humor": 0.4,
        },
        "values": ["loyalty to her old crew", "self-preservation", "her regulars"],
        "fears": ["the Ashvale thieves' guild finding her", "being exposed as an informant"],
        "desires": ["a quiet life behind the bar", "to keep her niece Wren safe"],
        "speech_style": "clipped, dry, deflective; warms only once she trusts you",
        "catchphrases": [
            "We don't get much trouble here. Let's keep it that way.",
            "Drink's on the bar. Questions cost extra.",
        ],
        "mannerisms": ["polishes the same glass when nervous", "never turns her back to the door"],
        "current_emotional_state": "guarded",
        "triggers": [
            {
                "condition": "asked about the thieves guild or the Ashvale syndicate",
                "reaction": "goes cold and evasive, deflects with bar talk",
                "intensity": 0.9,
                "is_hidden": True,
            },
            {
                "condition": "someone mentions an informant or a snitch",
                "reaction": "tightens, grip whitens on the glass, watches the exits",
                "intensity": 0.85,
                "is_hidden": True,
            },
            {
                "condition": "someone is kind to her niece Wren",
                "reaction": "visibly softens, becomes generous and talkative",
                "intensity": 0.7,
                "is_hidden": False,
            },
        ],
        "secrets": [
            "Maeve was a paid informant for the Ashvale thieves' guild for nine years.",
            "She sold out her own crew to the city watch and fled with the bounty; that money bought the Drowned Lantern.",
            "Her niece Wren does not know any of this.",
        ],
        "gm_notes": (
            "Maeve is hiding in plain sight. If the guild's name comes up she will lie, "
            "deflect, and try to end the conversation. Genuine warmth toward Wren is the "
            "only reliable key to her trust."
        ),
    },
    # Canonical facts she is aware of (her knowledge boundary).
    # (statement, fact_type) — fact_type ∈ state|relationship|attribute|occurrence.
    "known_facts": [
        ("The Drowned Lantern sits on the Ashvale docks and caters to sailors and smugglers.", "attribute"),
        ("There has been a string of disappearances along the Ashvale waterfront this month.", "occurrence"),
        ("The city watch raided a guild safehouse two streets over last week.", "occurrence"),
    ],
}


# Scripted DIRECT-mode player lines — escalate to pressure the relationship axes.
DIRECT_SCRIPT: List[str] = [
    "Evening. Cold night out there — pour me whatever's warm and strong.",
    "Quiet place you keep. How long have you run the Drowned Lantern?",
    "I heard there've been people going missing down on the docks. You hear anything?",
    "Funny thing — a friend of mine swears this place used to be guild money. The Ashvale syndicate. That ring a bell?",
    "I'm not the watch, Maeve. But I know what an informant looks like. I think you were one.",
    "Relax. I'm not here to turn you in. Your niece Wren — she sounds like she'd be safer if you and I were on the same side.",
]

# Scripted ACTOR-mode GM questions — probe the GM-only layer.
ACTOR_SCRIPT: List[str] = [
    "As Maeve, what is the one thing you would never let a stranger find out about you?",
    "If a player character earned your genuine trust, what would that take, and how would your behavior change?",
    "If someone threatened to expose your past to the guild, how far would you go to stop them?",
    "What do you want for Wren, and what would you sacrifice to protect her?",
]


# =============================================================================
# SETUP — assemble the character into the data layer
# =============================================================================


async def assemble_character(
    keeper: CanonKeeper, character: Dict[str, Any]
) -> Tuple[UUID, UUID]:
    """Create multiverse → universe → Entity (Neo4j) + NPCProfile (MongoDB).

    Returns (universe_id, npc_id).
    """
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.npc_profiles import NPCProfileCreate
    from monitor_data.tools.neo4j_tools import neo4j_create_entity

    # 1. Multiverse + universe (fresh each run)
    mv = await keeper.create_multiverse(
        {
            "name": f"Roleplay Test MV {uuid4().hex[:6]}",
            "system_name": "Freeform",
            "description": "Test bed for NPC roleplay.",
        }
    )
    if "id" not in mv:
        raise RuntimeError(f"create_multiverse failed: {mv}")
    multiverse_id = mv["id"]

    u = await keeper.create_universe(
        {
            "multiverse_id": str(multiverse_id),
            "name": f"Ashvale {uuid4().hex[:6]}",
            "genre": "Low Fantasy",
            "description": "A grimy port city of smugglers, watchmen, and old debts.",
            "tone": "noir",
        }
    )
    universe_id = UUID(u["id"])
    console.print(f"  Universe: [cyan]{universe_id}[/cyan]")

    # 2. Entity (Neo4j) — role lives in properties; NPCVoice reads props['role'].
    npc_id = uuid4()
    neo4j_create_entity(
        EntityCreate(
            universe_id=universe_id,
            id=npc_id,
            name=character["name"],
            entity_type="character",
            sub_type="npc",
            is_archetype=False,
            description=character["description"],
            properties={"role": character["role"]},
        )
    )
    console.print(f"  Entity:   [cyan]{npc_id}[/cyan]  ({character['name']})")

    # 3. NPCProfile (MongoDB) — the psychological backbone.
    profile = character["profile"]
    mongodb_create_npc_profile(
        NPCProfileCreate(
            entity_id=npc_id,
            traits=profile["traits"],
            values=profile["values"],
            fears=profile["fears"],
            desires=profile["desires"],
            speech_style=profile["speech_style"],
            catchphrases=profile["catchphrases"],
            mannerisms=profile["mannerisms"],
            triggers=profile["triggers"],
            secrets=profile["secrets"],
            gm_notes=profile["gm_notes"],
            current_emotional_state=profile["current_emotional_state"],
        )
    )
    console.print("  Profile:  [green]NPCProfile created[/green]")

    # 4. Canonical facts she knows (best-effort; knowledge boundary).
    await _seed_known_facts(keeper, universe_id, npc_id, character.get("known_facts", []))

    return universe_id, npc_id


async def _seed_known_facts(
    keeper: CanonKeeper,
    universe_id: UUID,
    npc_id: UUID,
    facts: List[Tuple[str, str]],
) -> None:
    """Attach a few canonical facts to the entity (best-effort)."""
    created = 0
    for statement, fact_type in facts:
        try:
            res = await keeper.create_fact(
                {
                    "universe_id": str(universe_id),
                    "statement": statement,
                    "fact_type": fact_type,
                    "entity_ids": [str(npc_id)],
                }
            )
            if isinstance(res, dict) and "id" in res:
                created += 1
            else:
                logger.debug("fact seed rejected: %s", res)
        except Exception as exc:  # noqa: BLE001
            logger.debug("fact seed failed: %s", exc)
    console.print(f"  Facts:    [green]{created}/{len(facts)} canonical fact(s) seeded[/green]")


def _import_npc_profile_tool():
    """Imported lazily so ``--help`` works without a live MongoDB."""
    from monitor_data.tools.mongodb_tools import mongodb_create_npc_profile

    return mongodb_create_npc_profile


mongodb_create_npc_profile = None  # populated at runtime


async def _ensure_character(
    keeper: CanonKeeper,
    universe_id: Optional[str],
    npc_id: Optional[str],
) -> Tuple[UUID, UUID]:
    """Return (universe_id, npc_id), assembling a fresh character if not given."""
    global mongodb_create_npc_profile
    if mongodb_create_npc_profile is None:
        mongodb_create_npc_profile = _import_npc_profile_tool()

    if universe_id and npc_id:
        console.print(f"[dim]Using existing character {npc_id}[/dim]")
        return UUID(universe_id), UUID(npc_id)

    console.print("[bold]Assembling test character…[/bold]")
    return await assemble_character(keeper, TEST_CHARACTER)


# =============================================================================
# RENDERING
# =============================================================================


def _render_social(snapshot: Dict[str, Any]) -> str:
    """Compact one-line view of the NPC's stance toward the player."""
    if not snapshot:
        return "[dim](no relationship tracked)[/dim]"
    axes = ("trust", "affinity", "fear", "leverage", "familiarity")
    parts = [f"{a}={snapshot.get(a, 0.0):+.2f}" for a in axes]
    delta = snapshot.get("last_delta")
    delta_str = f"  Δ={delta}" if delta else ""
    return f"stance=[bold]{snapshot.get('stance', '?')}[/bold]  " + " ".join(parts) + delta_str


# =============================================================================
# DIRECT mode — in-character live dialogue
# =============================================================================


async def run_direct(universe_id: Optional[str], npc_id: Optional[str]) -> None:
    keeper = CanonKeeper()
    uid, nid = await _ensure_character(keeper, universe_id, npc_id)

    console.rule("[bold cyan]DIRECT mode — talking to the character")
    loop = await ConversationLoop.start(
        universe_id=uid,
        mode=ConversationMode.DIRECT,
        npc_ids=[nid],
        player_entity_id=uuid4(),  # a stand-in PC so relationship_states get keyed
    )

    for idx, line in enumerate(DIRECT_SCRIPT, start=1):
        console.print(f"\n[bold green]Player (turn {idx}):[/bold green] {line}")
        responses = await loop.step(line)
        for r in responses:
            console.print(f"[bold magenta]{r.get('npc_name', 'NPC')}:[/bold magenta] {r.get('text', '')}")
            console.print(f"  [dim]feeling:[/dim] {r.get('emotional_state', '?')}")
            console.print(f"  [dim]social :[/dim] {_render_social(r.get('relationship_snapshot', {}))}")

    proposals = await loop.finish()
    console.print("\n[bold yellow]Staged proposals (for CanonKeeper):[/bold yellow]")
    if not proposals:
        console.print("  [dim](none)[/dim]")
    for p in proposals:
        console.print(
            Panel(
                json.dumps(p.get("content", {}), indent=2, default=str),
                title=f"{p.get('change_type')}  (conf={p.get('confidence')})",
                border_style="yellow",
            )
        )
    console.print("\n[bold cyan]DIRECT test complete.[/bold cyan]")


# =============================================================================
# ACTOR mode — out-of-character reflection (GM prep)
# =============================================================================


async def run_actor(universe_id: Optional[str], npc_id: Optional[str]) -> None:
    keeper = CanonKeeper()
    uid, nid = await _ensure_character(keeper, universe_id, npc_id)

    console.rule("[bold cyan]ACTOR mode — questioning the actor (sees secrets)")
    loop = await ConversationLoop.start(
        universe_id=uid,
        mode=ConversationMode.ACTOR,
        npc_ids=[nid],
    )

    for idx, question in enumerate(ACTOR_SCRIPT, start=1):
        console.print(f"\n[bold green]GM (q{idx}):[/bold green] {question}")
        responses = await loop.step(question)
        for r in responses:
            console.print(f"[bold magenta]Actor as {r.get('npc_name', 'NPC')}:[/bold magenta] {r.get('text', '')}")
            insight = r.get("canon_insight")
            if insight and insight.strip().lower() != "none":
                console.print(f"  [dim]canon insight:[/dim] {insight}")

    proposals = await loop.finish()
    console.print(f"\n[bold yellow]Staged proposals:[/bold yellow] {len(proposals)}")
    console.print("\n[bold cyan]ACTOR test complete.[/bold cyan]")


# =============================================================================
# ROSTER — list characters you could talk to (the "select a character" view)
# =============================================================================


async def run_roster(universe_id: str) -> None:
    keeper = CanonKeeper()
    raw = await keeper.call_tool(
        "neo4j_list_entities",
        {"filters": {"universe_id": universe_id, "entity_type": "character", "limit": 100}},
    )
    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
    if isinstance(parsed, dict):
        entities = parsed.get("entities", [])
    elif isinstance(parsed, list):
        entities = parsed
    else:
        entities = getattr(parsed, "entities", []) or []
    console.rule(f"[bold cyan]Character roster — universe {universe_id}")
    if not entities:
        console.print("  [dim](no characters)[/dim]")
        return
    for e in entities:
        props = e.get("properties", {}) or {}
        console.print(
            f"  [cyan]{e.get('id')}[/cyan]  [bold]{e.get('name')}[/bold]"
            f"  [dim]{props.get('role', '')}[/dim]"
        )


# =============================================================================
# CONVERSATORY — the real product path (character card → expand → chat)
#
# These exercise monitor_ui.routers.character_conversation directly: the same
# service the Characters tab calls. Two entry points the user asked for:
#   import-card  — import a SillyTavern / RisuAI card, expand, chat
#   assist       — LLM drafts a card from a concept, expand, chat
# =============================================================================


# A realistic SillyTavern chara_card_v2 (nested under "data").
SAMPLE_ST_CARD_V2: Dict[str, Any] = {
    "spec": "chara_card_v2",
    "spec_version": "2.0",
    "data": {
        "name": "Sister Veil",
        "description": (
            "A hooded confessor of the Ashen Order who keeps the lighthouse chapel on the "
            "smuggler's coast. Calm, exacting, and unnervingly perceptive."
        ),
        "personality": "Soft-spoken, patient, morally certain; reads people like open ledgers.",
        "scenario": "A traveler ducks into her chapel out of the storm.",
        "first_mes": "*She does not look up from the candle she is trimming.* The door was unlocked for a reason. Sit.",
        "mes_example": "",
        "creator_notes": "She is secretly sheltering a deserter the watch is hunting.",
        "system_prompt": "Stay reserved; never volunteer the deserter unless deeply trusted.",
        "tags": ["mystery", "religious"],
        "creator": "demo",
        "character_version": "1.0",
    },
}

# A RisuAI-style v3 card (RisuAI writes chara_card_v3 / 'ccv3').
SAMPLE_RISU_CARD_V3: Dict[str, Any] = {
    "spec": "chara_card_v3",
    "spec_version": "3.0",
    "data": {
        "name": "Rust",
        "description": "A void-scarred salvage mechanic who works the dead hulls of Dead Space.",
        "personality": "Blunt, dry-humored, fiercely independent; trusts machines over people.",
        "first_mes": "*wipes grease off a wrench* You lost? Nobody comes this deep for the view.",
        "creator_notes": "Hides that she sold a crew's coordinates once and a ship died for it.",
        "tags": ["sci-fi", "salvage"],
    },
}

# Short escalating lines used by both conversatory demos.
CONVERSATORY_SCRIPT: List[str] = [
    "Evening. Mind if I sit a while out of the cold?",
    "People say you're hiding something here. Care to tell me what?",
    "I'm not here to cause trouble — I'd rather have you as a friend than a problem.",
]


async def _converse_with_character(character_id: str, name: str) -> None:
    """Expand-if-needed and run a short scripted conversatory session."""
    from monitor_ui.routers import character_conversation as cc

    console.print("[bold]Expanding into a MONITOR profile…[/bold]")
    backing = await cc.ensure_character_backed(character_id)
    console.print(
        f"  entity=[cyan]{backing['entity_id']}[/cyan]  universe=[cyan]{backing['universe_id']}[/cyan]"
    )

    started = await cc.start_conversation(character_id)
    conv_id = started["conversation_id"]
    console.rule(f"[bold cyan]Conversatory — {name}")
    console.print(f"[bold magenta]{name}:[/bold magenta] {started['opening']}\n")

    for line in CONVERSATORY_SCRIPT:
        console.print(f"[bold green]You:[/bold green] {line}")
        reply = await cc.send_message(conv_id, line)
        snap = reply.get("relationship_snapshot") or {}
        console.print(f"[bold magenta]{name}:[/bold magenta] {reply.get('text', '')}")
        console.print(
            f"  [dim]feeling={reply.get('emotional_state')}  stance={snap.get('stance')}  "
            f"trust={snap.get('trust')} fear={snap.get('fear')} familiarity={snap.get('familiarity')}[/dim]\n"
        )

    ended = await cc.end_conversation(conv_id)
    console.print(f"[dim]session ended: {ended}[/dim]")


async def run_import_card(path: Optional[str], flavor: str) -> None:
    """Import a SillyTavern/RisuAI card → create → expand → chat."""
    from monitor_ui.routers.character_cards import parse_character_card
    from monitor_ui.routers.character_storage import create_character

    if path:
        with open(path, "rb") as fh:
            raw = fh.read()
        filename = path
    else:
        sample = SAMPLE_RISU_CARD_V3 if flavor == "risu" else SAMPLE_ST_CARD_V2
        raw = json.dumps(sample).encode("utf-8")
        filename = "sample.json"
        console.print(f"[dim]No path given — using embedded {flavor.upper()} sample card.[/dim]")

    card = parse_character_card(raw, filename=filename)
    console.print(f"[bold]Imported card:[/bold] {card.name}")
    console.print(f"  [dim]{card.description[:120]}[/dim]")

    doc = create_character(card.model_dump())
    await _converse_with_character(doc["id"], card.name)


async def run_assist(concept: str) -> None:
    """LLM drafts a card from a concept → create → expand → chat."""
    from monitor_ui.routers import character_conversation as cc
    from monitor_ui.routers.character_storage import create_character

    console.print(f"[bold]Asking the LLM to draft a card from:[/bold] {concept!r}")
    draft = await cc.draft_card(concept=concept)
    console.print(f"  name:        [bold]{draft['name']}[/bold]")
    console.print(f"  description: [dim]{draft['description'][:140]}[/dim]")
    console.print(f"  personality: [dim]{draft['personality'][:140]}[/dim]")
    console.print(f"  first line:  [dim]{draft['first_message'][:140]}[/dim]")

    doc = create_character(draft)
    await _converse_with_character(doc["id"], draft["name"])


# =============================================================================
# CLI
# =============================================================================


@app.command()
def setup() -> None:
    """Assemble the test character and print its IDs (for re-use)."""

    async def _go() -> None:
        keeper = CanonKeeper()
        global mongodb_create_npc_profile
        mongodb_create_npc_profile = _import_npc_profile_tool()
        uid, nid = await assemble_character(keeper, TEST_CHARACTER)
        console.print("\n[bold green]Done. Re-use with:[/bold green]")
        console.print(f"  --universe-id {uid} --npc-id {nid}")

    asyncio.run(_go())


@app.command()
def direct(
    universe_id: Optional[str] = typer.Option(None, help="Existing universe id"),
    npc_id: Optional[str] = typer.Option(None, help="Existing character entity id"),
) -> None:
    """Talk to the character in-character (DIRECT mode)."""
    asyncio.run(run_direct(universe_id, npc_id))


@app.command()
def actor(
    universe_id: Optional[str] = typer.Option(None, help="Existing universe id"),
    npc_id: Optional[str] = typer.Option(None, help="Existing character entity id"),
) -> None:
    """Question the character's actor (ACTOR mode — sees secrets)."""
    asyncio.run(run_actor(universe_id, npc_id))


@app.command()
def roster(universe_id: str = typer.Argument(..., help="Universe id to list characters for")) -> None:
    """List characters in a universe (the 'select a character' roster view)."""
    asyncio.run(run_roster(universe_id))


@app.command("import-card")
def import_card(
    path: Optional[str] = typer.Argument(None, help="Path to a .json/.png card; omit to use a sample"),
    flavor: str = typer.Option("st", help="Sample flavor when no path: 'st' (SillyTavern) or 'risu' (RisuAI)"),
) -> None:
    """Import a SillyTavern/RisuAI character card, expand it, and chat."""
    asyncio.run(run_import_card(path, flavor))


@app.command()
def assist(concept: str = typer.Argument(..., help="Concept for the LLM to draft a card from")) -> None:
    """LLM-assisted creation: draft a card from a concept, expand, and chat."""
    asyncio.run(run_assist(concept))


if __name__ == "__main__":
    app()
