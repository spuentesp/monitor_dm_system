"""
Script to seed the world with basic hierarchy for testing.
"""

import json
from uuid import uuid4
from datetime import datetime, timezone
from monitor_data.db.neo4j import get_neo4j_client

def seed():
    client = get_neo4j_client()
    created_at = datetime.now(timezone.utc).isoformat()
    
    # Clear existing data
    print("Clearing database...")
    client.execute_write("MATCH (n) DETACH DELETE n")

    # 1. Omniverse
    omniverse_id = str(uuid4())
    print(f"Creating Omniverse: {omniverse_id}")
    client.execute_write(
        """
        MERGE (o:Omniverse {name: "MONITOR Omniverse"})
        ON CREATE SET o.id = $id, o.description = "Root", o.created_at = datetime($created_at)
        RETURN o.id as id
        """, 
        {"id": omniverse_id, "created_at": created_at}
    )
    # Fetch actual ID if MERGE matched existing
    res = client.execute_read("MATCH (o:Omniverse) RETURN o.id as id LIMIT 1")
    omniverse_id = res[0]["id"]

    # 2. Multiverse (D&D)
    multiverse_id = str(uuid4())
    print(f"Creating Multiverse: {multiverse_id}")
    client.execute_write(
        """
        MATCH (o:Omniverse {id: $omniverse_id})
        MERGE (m:Multiverse {name: "Forgotten Realms Test"})
        ON CREATE SET 
            m.id = $id, 
            m.omniverse_id = $omniverse_id,
            m.system_name = "Standard Fantasy v5",
            m.description = "Test Multiverse",
            m.created_at = datetime($created_at)
        MERGE (o)-[:CONTAINS]->(m)
        RETURN m.id as id
        """,
        {"id": multiverse_id, "omniverse_id": omniverse_id, "created_at": created_at}
    )
    res = client.execute_read("MATCH (m:Multiverse {name: 'Forgotten Realms Test'}) RETURN m.id as id LIMIT 1")
    multiverse_id = res[0]["id"]

    # 3. Universe
    universe_id = str(uuid4())
    print(f"Creating Universe: {universe_id}")
    client.execute_write(
        """
        MATCH (m:Multiverse {id: $multiverse_id})
        MERGE (u:Universe {name: "Faerun Instance 1"})
        ON CREATE SET
            u.id = $id,
            u.multiverse_id = $multiverse_id,
            u.description = "Main campaign world",
            u.canon_level = "canon",
            u.confidence = 100,
            u.authority = "gm",
            u.created_at = datetime($created_at)
        MERGE (m)-[:CONTAINS]->(u)
        RETURN u.id as id
        """,
        {"id": universe_id, "multiverse_id": multiverse_id, "created_at": created_at}
    )
    res = client.execute_read("MATCH (u:Universe {name: 'Faerun Instance 1'}) RETURN u.id as id LIMIT 1")
    universe_id = res[0]["id"]

    # 4. Entity (Hero)
    entity_id = str(uuid4())
    print(f"Creating Entity: {entity_id}")
    # Attributes: Str 18 (+4 mod)
    props = {"attributes": {"Strength": 18, "Dexterity": 14, "Constitution": 16}}
    props_str = json.dumps(props)
    
    client.execute_write(
        """
        MATCH (u:Universe {id: $universe_id})
        CREATE (e:Entity {
            id: $id,
            universe_id: $universe_id,
            name: "Aragorn Test",
            entity_type: "character",
            is_archetype: false,
            description: "Ranger of the North",
            properties: $props,
            canon_level: "canon",
            confidence: 100,
            authority: "system",
            created_at: datetime($created_at)
        })
        CREATE (u)-[:HAS_ENTITY]->(e)
        RETURN e.id as id
        """,
        {"id": entity_id, "universe_id": universe_id, "props": props_str, "created_at": created_at}
    )
    
    print("-" * 50)
    print("SEED COMPLETE")
    print(f"Entity ID: {entity_id}")
    print("-" * 50)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    seed()
