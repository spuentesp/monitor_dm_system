#!/usr/bin/env python3
"""
Recover the entities lost when extraction batch 15 failed (Lasombra, Tzimisce,
Followers of Set + ~23 others) — WITHOUT re-embedding.

Re-runs only the Analyzer over the corebook's existing Qdrant snippets (now with
the properties-coercion fix so batch 15 succeeds), then commits only the entity
archetypes whose names aren't already in Neo4j.
"""
import os
os.environ["MONITOR_LLM_LOG"] = "1"
os.environ["MONITOR_LLM_LOG_FILE"] = os.path.join(os.getcwd(), "test_logs", "llm_calls.log")
os.environ.setdefault("MONITOR_ANALYZE_TIMEOUT", str(60 * 60))

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(name)s | %(message)s",
                    handlers=[logging.FileHandler("test_logs/clan_recovery.log", mode="w")])

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.tools.mongodb_tools import mongodb_create_ingestion_job
from monitor_data.schemas.ingestion_jobs import IngestionJobCreate
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_agents.analyzer import Analyzer
from monitor_agents.canonkeeper.agent import CanonKeeper

UV = UUID("7c737c26-7b84-4704-9ff6-4fc19492eac4")
MV = UUID("4d3fa067-4bce-44c6-9df4-19b4770c8c2a")
SRC = UUID("cb5c656f-834b-413c-b597-e7e140ce36b0")
DOC = UUID("353d48f8-f59b-4d0d-b3bd-4f1f028a7ece")


def _name_of(p: dict) -> str:
    payload = p.get("payload") or p.get("content") or {}
    if isinstance(payload, dict):
        return str(payload.get("name") or "").strip()
    return ""


async def main() -> None:
    pc = get_mongodb_client().get_collection("proposed_changes").database["proposed_changes"]

    # Existing entity names already committed to this universe (== in Neo4j).
    existing = {
        _name_of(p).lower()
        for p in pc.find({"universe_id": str(UV), "proposal_type": "create_entity_archetype",
                          "status": "committed"})
        if _name_of(p)
    }
    print(f"existing committed entities: {len(existing)}")

    # Re-run extraction over existing snippets (no embedding).
    job = mongodb_create_ingestion_job(IngestionJobCreate(
        universe_id=UV, source_id=SRC, doc_id=DOC, source_title="VtM 20th re-extract (clan recovery)"))
    start = datetime.now(timezone.utc)
    analyzer = Analyzer(agent_id="clan-recover-analyzer")
    print("Re-extracting (reusing snippets)…")
    # IMPORTANT: source_name MUST match what the snippets were indexed under
    # (the original source_title), or the Qdrant section filter matches nothing.
    res = await analyzer.analyze(
        job_id=job.job_id, source_name="Vampire: The Masquerade 20th Anniversary",
        source_document_ids=[DOC], pack_name="VtM 20th re-extract (clan recovery)",
        pack_type=KnowledgePackType.RULEBOOK, universe_id=UV, multiverse_id=MV,
        analysis_layers=["entities"], auto_apply=True,
    )
    print(f"analyze status={getattr(res,'status',None)} "
          f"ok/fail={getattr(res,'succeeded_batches',None)}/{getattr(res,'failed_batches',None)}")

    # New pending proposals from this run.
    new_props = list(pc.find({"universe_id": str(UV), "status": "pending",
                              "created_at": {"$gte": start}}))
    print(f"new pending proposals: {len(new_props)}")

    new_entities = [p for p in new_props
                    if p.get("proposal_type") == "create_entity_archetype"
                    and _name_of(p) and _name_of(p).lower() not in existing]
    recovered_names = sorted({_name_of(p) for p in new_entities})
    print(f"NEW entities not already in Neo4j ({len(new_entities)}): {recovered_names}")

    # Commit the recovered entities + any new relationships (handler skips
    # relationships whose endpoints aren't resolvable).
    new_rels = [p for p in new_props if p.get("proposal_type") == "entity_relationship"]
    keeper = CanonKeeper(agent_id="clan-recover-commit")
    to_commit = new_entities + new_rels
    result = await keeper.bulk_commit_proposals(to_commit, universe_id=UV, contradiction_check=False)
    print(f"COMMIT: committed={result['committed']} rejected={result['rejected']} errors={len(result['errors'])}")

    # Tidy: mark the leftover duplicate new proposals as superseded.
    leftover_ids = [p["proposal_id"] for p in new_props
                    if p.get("status") == "pending" and p not in to_commit]
    if leftover_ids:
        pc.update_many({"proposal_id": {"$in": leftover_ids}, "status": "pending"},
                       {"$set": {"status": "superseded"}})
        print(f"marked {len(leftover_ids)} duplicate proposals superseded")


if __name__ == "__main__":
    asyncio.run(main())
