#!/usr/bin/env python3
"""
LIVE TEST: ingest the REAL Vampire: The Masquerade 20th Anniversary corebook
(108 MB PDF) through the full pipeline, so we can find and fix real ingestion
issues on a large rulebook.

Runs on the already-configured cheap models (MiniMax heavy + gemini-2.5-flash).
"""
import os

_LOGDIR = os.path.join(os.getcwd(), "test_logs")
os.makedirs(_LOGDIR, exist_ok=True)
os.environ["MONITOR_LLM_LOG"] = "1"
os.environ["MONITOR_LLM_LOG_FILE"] = os.path.join(_LOGDIR, "llm_calls.log")
os.environ.setdefault("MONITOR_AUTO_CANONIZE", "true")
# A 108 MB corebook fans out many extraction batches — give the analyze stage room.
os.environ.setdefault("MONITOR_ANALYZE_TIMEOUT", str(90 * 60))

import asyncio
import json
import logging
from uuid import uuid4

import nest_asyncio
from rich.console import Console

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(_LOGDIR, "corebook_ingest.log"), mode="w"),
        logging.StreamHandler(),
    ],
)

from monitor_agents.canonkeeper import CanonKeeper
from monitor_agents.ingestion_pipeline import IngestionPipeline
from monitor_data.schemas.knowledge_packs import KnowledgePackType

nest_asyncio.apply()
console = Console()

COREBOOK_PATH = ".local_storage/monitor/uploads/None/20260405_201601_WtWf-VtM20th.pdf"


async def main() -> None:
    console.rule("[bold cyan]LIVE INGEST: VtM 20th Anniversary Corebook")
    keeper = CanonKeeper()
    pipeline = IngestionPipeline()

    multiverse_id = uuid4()
    universe_id = uuid4()
    await keeper.create_multiverse({
        "id": str(multiverse_id), "name": "World of Darkness (corebook live-test)",
        "system_name": "Vampire: The Masquerade", "description": "Live ingest of the VtM 20th corebook.",
    })
    await keeper.create_universe({
        "id": str(universe_id), "multiverse_id": str(multiverse_id),
        "name": "Vampire: The Masquerade (corebook)", "genre": "Gothic-Punk Horror", "tone": "grim",
        "description": "Canonical VtM world ingested from the 20th Anniversary corebook.",
    })
    console.print(f"multiverse={multiverse_id}\nuniverse={universe_id}")

    size_mb = os.path.getsize(COREBOOK_PATH) / (1024 * 1024)
    console.print(f"Reading corebook ({size_mb:.0f} MB) → {COREBOOK_PATH}")
    with open(COREBOOK_PATH, "rb") as f:
        file_bytes = f.read()

    console.print("[bold yellow]Starting ingest_file (this will take a while)…[/bold yellow]")
    job = await pipeline.ingest_file(
        file_bytes=file_bytes,
        filename="WtWf-VtM20th.pdf",
        source_title="Vampire: The Masquerade 20th Anniversary",
        universe_id=universe_id,
        pack_name="VtM 20th Anniversary Corebook",
        pack_type=KnowledgePackType.RULEBOOK,
        multiverse_id=multiverse_id,
        analysis_layers=["axioms", "entities", "lore", "game_system", "rules"],
        auto_apply=True,
    )
    console.print(f"[bold green]JOB DONE[/bold green] status={job.status.value} "
                  f"job_id={job.job_id} snippets={getattr(job,'snippet_count',None)} "
                  f"batches ok/fail={getattr(job,'succeeded_batches',None)}/{getattr(job,'failed_batches',None)} "
                  f"last_error={getattr(job,'last_error',None)}")

    with open(os.path.join(_LOGDIR, "corebook_session.json"), "w") as f:
        json.dump({"multiverse_id": str(multiverse_id), "universe_id": str(universe_id),
                   "job_id": str(job.job_id), "status": job.status.value}, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
