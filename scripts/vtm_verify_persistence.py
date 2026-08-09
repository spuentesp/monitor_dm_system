#!/usr/bin/env python3
"""Post-run verifier -- prints what the VtM Embrace session actually persisted.

Usage:
    uv run python scripts/vtm_verify_persistence.py [actor_id] [story_id]

If actor_id is provided, prints the actor's Neo4j entity count + relationships.
If story_id is provided, scopes MongoDB scene/resolution counts to that story.
With no args, prints global counts (everything in the DB).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://monitor:changeme-mongodb@localhost:27017/monitor?authSource=admin",
)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme-neo4j")


# --- Mongo -----------------------------------------------------------------

async def fetch_scene_stats(story_id: str | None) -> dict[str, Any]:
    """Return counts and details for scenes, turns, resolutions, memories."""
    client = AsyncIOMotorClient(MONGODB_URI)
    try:
        db = client.monitor
        scenes_filter: dict[str, Any] = {}
        if story_id:
            scenes_filter["story_id"] = story_id

        scene_docs = [s async for s in db.scenes.find(scenes_filter)]
        total_turns = 0
        speakers: set[str] = set()
        entity_ids: set[str] = set()
        for s in scene_docs:
            for t in s.get("turns", []) or []:
                total_turns += 1
                sp = t.get("speaker")
                if sp is not None:
                    # Speaker may be an enum -- coerce to its .value or str.
                    speakers.add(str(getattr(sp, "value", sp)))
                eid = t.get("entity_id")
                if eid:
                    entity_ids.add(str(eid))

        scene_ids = [s.get("scene_id") for s in scene_docs if s.get("scene_id")]
        if scene_ids:
            resolutions_count = await db.resolutions.count_documents(
                {"scene_id": {"$in": scene_ids}}
            )
        else:
            resolutions_count = 0

        memory_filter: dict[str, Any] = {}
        if entity_ids:
            memory_filter["entity_id"] = {"$in": list(entity_ids)}
        elif story_id:
            memory_filter["story_id"] = story_id
        memories_count = await db.character_memories.count_documents(memory_filter)

        return {
            "scenes": len(scene_docs),
            "turns": total_turns,
            "speakers": sorted(speakers),
            "resolutions": resolutions_count,
            "memories": memories_count,
            "scene_ids": scene_ids,
        }
    finally:
        client.close()


# --- Neo4j -----------------------------------------------------------------

def fetch_neo4j_stats(actor_id: str) -> dict[str, Any]:
    """Return entity count + outgoing/incoming relationships for the actor."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            ent = s.run(
                "MATCH (e:Entity) WHERE toString(e.id) = $id "
                "RETURN count(e) AS n",
                id=actor_id,
            ).single()
            entities_count = ent["n"] if ent else 0

            rels_out = s.run(
                "MATCH (e:Entity)-[r]->() WHERE toString(e.id) = $id "
                "RETURN type(r) AS t, count(r) AS c ORDER BY c DESC",
                id=actor_id,
            ).data()
            rels_in = s.run(
                "MATCH ()-[r]->(e:Entity) WHERE toString(e.id) = $id "
                "RETURN type(r) AS t, count(r) AS c ORDER BY c DESC",
                id=actor_id,
            ).data()
            return {
                "entities": entities_count,
                "outgoing": rels_out,
                "incoming": rels_in,
            }
    finally:
        driver.close()


# --- Main ------------------------------------------------------------------

async def main() -> None:
    actor_id = sys.argv[1] if len(sys.argv) > 1 else None
    story_id = sys.argv[2] if len(sys.argv) > 2 else None

    print("=== MONITOR VtM Embrace persistence dump ===\n")
    stats = await fetch_scene_stats(story_id)
    print(f"MongoDB scenes:        {stats['scenes']}")
    print(f"MongoDB turns:         {stats['turns']}")
    print(f"MongoDB speakers:      {', '.join(stats['speakers']) or '(none)'}")
    print(f"MongoDB resolutions:   {stats['resolutions']}")
    print(f"MongoDB memories:      {stats['memories']}")
    print()

    if actor_id:
        neo = fetch_neo4j_stats(actor_id)
        print(f"Neo4j entities for actor {actor_id[:8]}: {neo['entities']}")
        if neo["outgoing"]:
            print("Outgoing relationships:")
            for r in neo["outgoing"]:
                print(f"  -[:{r['t']}]->  x {r['c']}")
        if neo["incoming"]:
            print("Incoming relationships:")
            for r in neo["incoming"]:
                print(f"  -[:{r['t']}]->  x {r['c']}")
        if not neo["outgoing"] and not neo["incoming"]:
            print("  (no relationships)")
    else:
        print("(no actor_id provided -- skipping Neo4j entity/relationship dump)")


if __name__ == "__main__":
    asyncio.run(main())