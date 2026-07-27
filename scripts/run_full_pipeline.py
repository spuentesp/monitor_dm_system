#!/usr/bin/env python3
"""Run the full IngestionPipeline end-to-end and report results."""

import asyncio
import logging
import os
import sys
import time
from uuid import UUID

os.environ["MONITOR_LLM_LOG"] = "1"
os.environ["MONITOR_LLM_TIMEOUT"] = "180"  # give extra time for large batches

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("full_pipeline")

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)


UNIVERSE_ID = UUID("d2bf8aa9-f398-43fd-931f-08c01f97722c")
MINIO_KEY = "uploads/0a876e75-1e6f-4c37-bd89-4c395c2a8580/20260407_023339_Death_in_Space_Core_Rules.pdf"
SOURCE_TITLE = "Death in Space Core Rules"
PACK_NAME = "Death in Space Core Rules Pack"


async def main():
    from monitor_agents.ingestion.agent import IngestionPipeline
    from monitor_data.db.minio import get_minio_client
    from monitor_data.schemas.knowledge_packs import KnowledgePackType

    log.info("=" * 60)
    log.info("FULL PIPELINE TEST — %s", SOURCE_TITLE)
    log.info("=" * 60)

    # Download PDF from MinIO
    log.info("Downloading PDF from MinIO...")
    minio = get_minio_client()
    pdf_bytes = await minio.download(MINIO_KEY)
    log.info(
        "Downloaded: %d bytes (%.1f MB)", len(pdf_bytes), len(pdf_bytes) / 1024 / 1024
    )

    # Create and run pipeline
    pipeline = IngestionPipeline()
    log.info("Starting pipeline...")
    t0 = time.time()

    try:
        job = await pipeline.ingest_file(
            file_bytes=pdf_bytes,
            filename="Death_in_Space_Core_Rules.pdf",
            source_title=SOURCE_TITLE,
            universe_id=UNIVERSE_ID,
            pack_name=PACK_NAME,
            pack_type=KnowledgePackType.RULEBOOK,
            analysis_layers=["axioms", "entities", "lore", "game_system", "rules"],
            auto_apply=False,
        )
        elapsed = time.time() - t0
        log.info("=" * 60)
        log.info("PIPELINE COMPLETED in %.1fs", elapsed)
        log.info("Job: %s", job.model_dump_json(indent=2))
    except Exception as e:
        elapsed = time.time() - t0
        log.error("PIPELINE FAILED after %.1fs: %s", elapsed, e)
        import traceback

        traceback.print_exc()
        return

    # Verify results
    log.info("=" * 60)
    log.info("VERIFYING RESULTS")
    log.info("=" * 60)

    from monitor_data.tools.mongodb_tools import mongodb_list_knowledge_packs

    packs = mongodb_list_knowledge_packs()
    if packs:
        for p in packs:
            log.info("Pack: %s status=%s", p.name, p.status.value)
            log.info(
                "  axioms=%d entities=%d lore_facts=%d relationships=%d",
                len(p.axioms or []),
                len(p.entity_archetypes or []),
                len(p.lore_facts or []),
                len(p.entity_relationships or []),
            )
            if p.game_system_id:
                log.info(
                    "  game_system_id=%s system_name=%s",
                    p.game_system_id,
                    p.system_name,
                )
    else:
        log.error("NO KNOWLEDGE PACKS FOUND!")

    # Check Qdrant
    from monitor_data.db.qdrant import get_qdrant_client

    qclient = get_qdrant_client()
    qdrant = qclient.get_client()
    try:
        collections = await qdrant.get_collections()
        for c in collections.collections:
            info = await qdrant.get_collection(c.name)
            log.info("Qdrant %s: %d points", c.name, info.points_count)
    except Exception as e:
        log.warning("Qdrant check: %s", e)

    # Check Neo4j Source node
    from monitor_data.db.neo4j import get_neo4j_client

    neo = get_neo4j_client()
    sources = neo.execute_read("MATCH (s:Source) RETURN s.id AS id, s.title AS title")
    for s in sources:
        log.info("Neo4j Source: %s title=%s", s["id"], s["title"])

    log.info("=" * 60)
    log.info("DONE — Check results above for completeness")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
