#!/usr/bin/env python3
"""
Test Script 1 (Phase 1): Build a VTM x AO3 crossover world and ingest into it.

Real-API version. The flow is:

    1. ensure Omniverse -> create Multiverse -> create Universe   (CanonKeeper)
    2. ingest VTM core rules text (as a file) into that Universe   (IngestionPipeline.ingest_file)
    3. ingest the AO3 "Apostate" chapter (as a file) into the same Universe
    4. with auto_apply=True, CanonKeeper canonizes the extracted proposals into Neo4j
    5. persist {multiverse_id, universe_id} to test_logs/current_session.json so that
       scripts 2 (character creation) and 3 (mechanics) reuse the SAME populated world.

Observability: every LLM prompt/response is appended to test_logs/llm_calls.log
(MONITOR_LLM_LOG), and backend/system logs go to test_logs/backend.log.
"""

import os

# ---- Observability env MUST be set before importing monitor_agents ----
_LOGDIR = os.path.join(os.getcwd(), "test_logs")
os.makedirs(_LOGDIR, exist_ok=True)
os.environ["MONITOR_LLM_LOG"] = "1"
os.environ["MONITOR_LLM_LOG_FILE"] = os.path.join(_LOGDIR, "llm_calls.log")
os.environ.setdefault("MONITOR_AUTO_CANONIZE", "true")

import asyncio
import json
import logging
from uuid import uuid4, UUID

import nest_asyncio
from rich.console import Console

# Capture backend/system logs to a file (the "backend logs" the plan asks for).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(_LOGDIR, "backend.log"), mode="a"),
        logging.StreamHandler(),
    ],
)

from monitor_agents.canonkeeper import CanonKeeper
from monitor_agents.ingestion_pipeline import IngestionPipeline
from monitor_data.schemas.knowledge_packs import KnowledgePackType

nest_asyncio.apply()
console = Console()

VTM_CORE_TEXT = """Vampire: The Masquerade — Core Rules Summary

Vampires (called Kindred) must drink mortal blood to survive. Each vampire tracks a
Blood Pool. Spending blood powers Disciplines and heals wounds; when the Blood Pool
runs low the vampire's Hunger rises, pushing them toward Frenzy — a feral, uncontrolled
state in which they attack the nearest source of blood.

Elder vampires who awaken from Torpor (a death-like sleep that can last centuries) emerge
ravenous. The first thing such an elder does upon waking is feed, often killing a mortal.

Clans grant access to Disciplines (supernatural powers):
- Celerity grants supernatural speed and reflexes; a vampire may act and dodge faster than mortals can follow.
- Potence grants supernatural physical strength; a single blow can shatter bone.
- Blood Sorcery (Thaumaturgy) allows mystical manipulation of blood, but demands intense concentration and ritual focus.

Damage is tracked as Health levels. Bashing and lethal damage fill Health boxes; a vampire
with no remaining Health enters torpor or is destroyed. Vampires heal lethal damage by
spending blood from their Blood Pool.
"""

AO3_STORY_PATH = (
    "/home/sebastian/.gemini/antigravity-cli/brain/"
    "4d53ccf6-a5f1-4141-b8ca-323343262f7a/.system_generated/steps/3748/content.md"
)


async def _ingest(pipeline: IngestionPipeline, *, text: str, filename: str,
                  source_title: str, pack_name: str, pack_type: KnowledgePackType,
                  universe_id: UUID, multiverse_id: UUID) -> None:
    console.print(f"[bold yellow]Ingesting:[/bold yellow] {source_title} "
                  f"({len(text)} chars)")
    job = await pipeline.ingest_file(
        file_bytes=text.encode("utf-8"),
        filename=filename,
        source_title=source_title,
        universe_id=universe_id,
        pack_name=pack_name,
        pack_type=pack_type,
        multiverse_id=multiverse_id,
        auto_apply=True,  # create proposals AND canonize them into Neo4j
    )
    console.print(
        f"  -> job={job.job_id} status={job.status.value} "
        f"snippets={getattr(job, 'snippet_count', '?')} "
        f"batches ok/fail={getattr(job, 'succeeded_batches', '?')}/"
        f"{getattr(job, 'failed_batches', '?')}"
    )


async def main() -> None:
    console.print("[bold cyan]Phase 1: World setup + ingestion[/bold cyan]")
    keeper = CanonKeeper()
    pipeline = IngestionPipeline()

    # ── 1. Multiverse + Universe ──────────────────────────────────────
    multiverse_id = uuid4()
    universe_id = uuid4()

    mv = await keeper.create_multiverse({
        "id": str(multiverse_id),
        "name": "VTM x AO3 Crossover Multiverse",
        "system_name": "Vampire: The Masquerade",
        "description": "World of Darkness fused with the AO3 'Apostate' storyline "
                       "(Phyre, Fabien, the binding Mark, Hotel Sorrento).",
    })
    console.print(f"Multiverse: {mv.get('id', multiverse_id)}")

    uv = await keeper.create_universe({
        "id": str(universe_id),
        "multiverse_id": str(multiverse_id),
        "name": "Seattle by Night (Apostate)",
        "genre": "Urban Fantasy / Gothic Horror",
        "tone": "grim",
        "description": "A dark, modern Seattle of Kindred intrigue where an elder named "
                       "Phyre awakens from torpor bound by a mysterious Mark.",
    })
    console.print(f"Universe: {uv.get('id', universe_id)}")

    # ── 2. Ingest VTM core rules ──────────────────────────────────────
    await _ingest(
        pipeline, text=VTM_CORE_TEXT, filename="vtm_core_rules.md",
        source_title="VTM Core Mechanics", pack_name="VTM Core",
        pack_type=KnowledgePackType.RULEBOOK,
        universe_id=universe_id, multiverse_id=multiverse_id,
    )

    # ── 3. Ingest the AO3 story crossover ─────────────────────────────
    if not os.path.exists(AO3_STORY_PATH):
        console.print(f"[bold red]AO3 story not found at {AO3_STORY_PATH}[/bold red]")
    else:
        with open(AO3_STORY_PATH, "r", encoding="utf-8") as f:
            ao3_text = f.read()
        # Skip AO3 nav boilerplate; keep the narrative body (awakening, Frank/Henry, Mark).
        ao3_body = ao3_text[3000:20000]
        await _ingest(
            pipeline, text=ao3_body, filename="apostate_ch1.md",
            source_title="Apostate — Chapter 1 (AO3)", pack_name="Apostate AO3",
            pack_type=KnowledgePackType.WIKI,
            universe_id=universe_id, multiverse_id=multiverse_id,
        )

    # ── 4. Persist the real IDs for downstream scripts ────────────────
    session = {"multiverse_id": str(multiverse_id), "universe_id": str(universe_id)}
    with open(os.path.join(_LOGDIR, "current_session.json"), "w") as f:
        json.dump(session, f, indent=2)
    console.print(f"[bold cyan]Phase 1 complete.[/bold cyan] Wrote {session}")


if __name__ == "__main__":
    asyncio.run(main())
