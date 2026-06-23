#!/usr/bin/env python3
"""Quick seed world script."""
import asyncio
import json
import os
import sys
sys.path.insert(0, 'packages/data-layer/src')
os.environ['NEO4J_PASSWORD'] = 'monitor_dev_pass'

from neo4j import AsyncGraphDatabase
from uuid import uuid4
from datetime import datetime, timezone

async def seed():
    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "monitor_dev_pass"),
        connection_timeout=10.0,
    )
    created_at = datetime.now(timezone.utc).isoformat()
    omniverse_id = str(uuid4())
    multiverse_id = str(uuid4())
    universe_id = str(uuid4())
    entity_id = str(uuid4())

    async with driver.session() as session:
        await (await session.run("MATCH (n) DETACH DELETE n")).consume()
        print("Cleared DB")

        await session.run(
            "MERGE (o:Omniverse {name: 'MONITOR Omniverse'}) ON CREATE SET o.id = $id, o.description = 'Root', o.created_at = datetime($created_at)",
            {"id": omniverse_id, "created_at": created_at}
        )
        res = await session.run("MATCH (o:Omniverse) RETURN o.id as id LIMIT 1")
        omniverse_id = (await res.single())["id"]
        print(f"Omniverse: {omniverse_id}")

        await session.run(
            "MATCH (o:Omniverse {id: $omniverse_id}) MERGE (m:Multiverse {name: 'Forgotten Realms Test'}) ON CREATE SET m.id = $id, m.omniverse_id = $omniverse_id, m.system_name = 'Standard Fantasy v5', m.description = 'Test Multiverse', m.created_at = datetime($created_at) MERGE (o)-[:CONTAINS]->(m)",
            {"id": multiverse_id, "omniverse_id": omniverse_id, "created_at": created_at}
        )
        res = await session.run("MATCH (m:Multiverse {name: 'Forgotten Realms Test'}) RETURN m.id as id LIMIT 1")
        multiverse_id = (await res.single())["id"]
        print(f"Multiverse: {multiverse_id}")

        await session.run(
            "MATCH (m:Multiverse {id: $multiverse_id}) MERGE (u:Universe {name: 'Faerun Instance 1'}) ON CREATE SET u.id = $id, u.multiverse_id = $multiverse_id, u.description = 'Main campaign world', u.canon_level = 'canon', u.confidence = 100, u.authority = 'gm', u.created_at = datetime($created_at) MERGE (m)-[:CONTAINS]->(u)",
            {"id": universe_id, "multiverse_id": multiverse_id, "created_at": created_at}
        )
        res = await session.run("MATCH (u:Universe {name: 'Faerun Instance 1'}) RETURN u.id as id LIMIT 1")
        universe_id = (await res.single())["id"]
        print(f"Universe: {universe_id}")

        props = json.dumps({"attributes": {"Strength": 18, "Dexterity": 14, "Constitution": 16}})
        await session.run(
            "MATCH (u:Universe {id: $universe_id}) CREATE (e:Entity {id: $id, universe_id: $universe_id, name: 'Aria Starfall', entity_type: 'character', is_archetype: false, description: 'Rogue with a mysterious past', properties: $props, canon_level: 'canon', confidence: 100, authority: 'system', created_at: datetime($created_at)}) CREATE (u)-[:HAS_ENTITY]->(e)",
            {"id": entity_id, "universe_id": universe_id, "props": props, "created_at": created_at}
        )
        print(f"Character: {entity_id}")
        print("SEED COMPLETE")

    await driver.close()

asyncio.run(seed())
