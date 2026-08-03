#!/usr/bin/env python3
"""
Tactical fix: re-populate the Qdrant `entities` and `knowledge` collections
from the current Neo4j + Mongo state.

Why this script exists
---------------------
The proper long-term fix is to have the canonkeeper upsert to Qdrant on
every entity/axiom/fact commit (and the indexer does that for snippets).
But the LOOKUP / GM-assistant RAG handler reads from `entities` and
`knowledge` collections, and a fresh ingestion sometimes leaves those
empty. This script is the escape hatch: after a wipe + re-ingest, run
this to repopulate the RAG collections without a full re-ingest.

Usage (from repo root, with infra up):

    uv run python scripts/_reindex_qdrant.py [--universe-id UUID]

If --universe-id is given, only that universe is indexed. Otherwise
the most recent universe (by source timestamp) is used.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "packages/data-layer/src")
sys.path.insert(0, "packages/agents/src")


def _resolve_universe() -> str | None:
    """Pick the universe to reindex. Prefer explicit --universe-id, else
    fall back to the most recent Neo4j universe."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-id", default=None)
    args, _unknown = parser.parse_known_args()
    if args.universe_id:
        return args.universe_id
    from monitor_data.db.neo4j import Neo4jClient
    from monitor_data.db import get_neo4j_client
    return None


async def main() -> None:
    from monitor_data.db.neo4j import Neo4jClient
    from monitor_data.db.qdrant import QdrantClient
    from monitor_data.retrieval import default_retrieval_service
    from qdrant_client.http import models

    universe_id = _resolve_universe()

    neo4j = Neo4jClient()
    await neo4j.connect()
    if not universe_id:
        rows = neo4j.execute_read(
            "MATCH (u:Universe) RETURN u.id AS id, u.name AS name "
            "ORDER BY u.created_at DESC LIMIT 1"
        )
        if not rows:
            print("ERROR: no Universe node found in Neo4j.")
            sys.exit(1)
        universe_id = rows[0]["id"]
        print(f"Using most recent universe: {rows[0]['name']} ({universe_id})")
    else:
        print(f"Using specified universe: {universe_id}")

    qdrant = QdrantClient()
    await qdrant.connect()
    await qdrant.ensure_collection("entities")
    await qdrant.ensure_collection("knowledge")
    retrieval = default_retrieval_service()

    # Entities.
    print("\nFetching entities from Neo4j...")
    rows = neo4j.execute_read(
        "MATCH (e:Entity) WHERE e.universe_id = $uid "
        "RETURN e.id AS id, e.name AS name, e.universe_id AS universe_id, "
        "e.entity_type AS entity_type, e.sub_type AS sub_type, "
        "e.group_type AS group_type, e.place_type AS place_type, "
        "e.description AS description, e.is_archetype AS is_archetype "
        "LIMIT 1000",
        {"uid": universe_id},
    )
    print(f"  found {len(rows)} entities")
    points = []
    for i in range(0, len(rows), 16):
        batch = rows[i:i + 16]
        texts = [f"{(r['name'] or '')}: {(r['description'] or '')}" for r in batch]
        vectors = await retrieval.embed_docs(texts)
        for r, v, t in zip(batch, vectors, texts):
            payload = {
                "entity_id": r["id"], "universe_id": r["universe_id"],
                "name": r["name"], "entity_type": r["entity_type"],
                "sub_type": r["sub_type"] or "",
                "group_type": r["group_type"] or "",
                "place_type": r["place_type"] or "",
                "description": r["description"] or "",
                "is_archetype": r["is_archetype"] or False,
                "text": t,
            }
            points.append(models.PointStruct(id=str(r["id"]), vector=v, payload=payload))
    print(f"  upserting {len(points)} entity points...")
    client = qdrant.get_client()
    await client.upsert("entities", points=points, wait=True)
    print(f"  done: entities collection has {len(points)} points")

    # Knowledge (axioms + facts).
    print("\nFetching knowledge from Neo4j...")
    rows = neo4j.execute_read(
        "MATCH (a:Axiom) WHERE a.universe_id = $uid "
        "RETURN a.id AS id, a.statement AS statement, "
        "a.universe_id AS universe_id, a.domain AS domain, "
        "a.canon_level AS canon_level "
        "UNION ALL "
        "MATCH (f:Fact) WHERE f.universe_id = $uid "
        "RETURN f.id AS id, f.statement AS statement, "
        "f.universe_id AS universe_id, f.fact_type AS domain, "
        "f.canon_level AS canon_level LIMIT 1000",
        {"uid": universe_id},
    )
    print(f"  found {len(rows)} knowledge nodes")
    points = []
    for i in range(0, len(rows), 16):
        batch = rows[i:i + 16]
        texts = [(r["statement"] or "")[:1000] for r in batch]
        vectors = await retrieval.embed_docs(texts)
        for r, v, t in zip(batch, vectors, texts):
            payload = {
                "node_id": r["id"], "universe_id": r["universe_id"],
                "node_type": r["domain"] or "unknown",
                "statement": r["statement"] or "",
                "canon_level": r["canon_level"] or "proposed",
                "text": t,
            }
            points.append(models.PointStruct(id=str(r["id"]), vector=v, payload=payload))
    print(f"  upserting {len(points)} knowledge points...")
    await client.upsert("knowledge", points=points, wait=True)
    print(f"  done: knowledge collection has {len(points)} points")
    print("\nDone. RAG collections are populated.")


if __name__ == "__main__":
    asyncio.run(main())
