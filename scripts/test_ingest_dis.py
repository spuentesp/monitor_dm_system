#!/usr/bin/env python3
"""
SECONDARY LIVE INGESTION TEST: ingest the Death in Space core rules PDF (51 MB)
through the full pipeline into a fresh world — validating the ingestion +
game-system extraction on a DIFFERENT system than VtM.

Runs on the cheap configured models. Uses the fast bulk canonization.
"""
import os
_LOGDIR = os.path.join(os.getcwd(), "test_logs")
os.makedirs(_LOGDIR, exist_ok=True)
os.environ["MONITOR_LLM_LOG"] = "1"
os.environ["MONITOR_LLM_LOG_FILE"] = os.path.join(_LOGDIR, "llm_calls.log")
os.environ.setdefault("MONITOR_AUTO_CANONIZE", "true")
os.environ.setdefault("MONITOR_ANALYZE_TIMEOUT", str(60 * 60))

import asyncio
import json
import logging
from uuid import uuid4

import nest_asyncio
from rich.console import Console

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(name)s | %(message)s",
                    handlers=[logging.FileHandler(os.path.join(_LOGDIR, "dis_ingest.log"), mode="w"),
                              logging.StreamHandler()])

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.ingestion.agent import IngestionPipeline
from monitor_data.schemas.knowledge_packs import KnowledgePackType

nest_asyncio.apply()
console = Console()

DIS_PATH = ".local_storage/monitor/uploads/5f5b7414-3010-41d4-bd38-13ca7f7ce896/20260405_180523_Death_in_Space_Core_Rules.pdf"


async def main() -> None:
    console.rule("[bold cyan]LIVE INGEST: Death in Space")
    keeper = CanonKeeper()
    pipeline = IngestionPipeline()

    multiverse_id = uuid4()
    universe_id = uuid4()
    await keeper.create_multiverse({
        "id": str(multiverse_id), "name": "Death in Space (live-test)",
        "system_name": "Death in Space", "description": "Live ingest of the Death in Space core rules."})
    await keeper.create_universe({
        "id": str(universe_id), "multiverse_id": str(multiverse_id),
        "name": "The Tenebris Sector", "genre": "Sci-fi horror / used-future",
        "tone": "grim, broke, claustrophobic",
        "description": "A decaying corner of space ingested from the Death in Space rulebook."})
    console.print(f"multiverse={multiverse_id}\nuniverse={universe_id}")

    with open(DIS_PATH, "rb") as f:
        data = f.read()
    console.print(f"Ingesting Death in Space ({len(data)/1024/1024:.0f} MB)…")
    job = await pipeline.ingest_file(
        file_bytes=data, filename="Death_in_Space_Core_Rules.pdf",
        source_title="Death in Space Core Rules", universe_id=universe_id,
        pack_name="Death in Space Core", pack_type=KnowledgePackType.RULEBOOK,
        multiverse_id=multiverse_id,
        analysis_layers=["axioms", "entities", "lore", "game_system", "rules"],
        auto_apply=True)
    console.print(f"[bold green]JOB DONE[/bold green] status={job.status.value} job={job.job_id} "
                  f"snippets={getattr(job,'snippet_count',None)} "
                  f"batches ok/fail={getattr(job,'succeeded_batches',None)}/{getattr(job,'failed_batches',None)}")

    with open(os.path.join(_LOGDIR, "dis_session.json"), "w") as f:
        json.dump({"multiverse_id": str(multiverse_id), "universe_id": str(universe_id),
                   "job_id": str(job.job_id), "status": job.status.value}, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
