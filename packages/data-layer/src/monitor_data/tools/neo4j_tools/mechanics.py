"""
Thin mechanic reference node writes for Neo4j.

Authority: CanonKeeper only.
These functions write minimal traversal-oriented nodes.
Full mechanic definitions live in MongoDB KnowledgePacks.
"""

from monitor_data.db.neo4j import get_neo4j_client


def neo4j_create_ability_system(
    *,
    name: str,
    system_id: str,
    parent_category: str | None = None,
) -> None:
    """MERGE an :AbilitySystem node. Idempotent."""
    client = get_neo4j_client()
    client.execute_write(
        """
        MERGE (a:AbilitySystem {name: $name, system_id: $system_id})
        SET a.parent_category = $parent_category
        """,
        {"name": name, "system_id": system_id, "parent_category": parent_category},
    )


def neo4j_create_track(
    *,
    name: str,
    system_id: str,
    track_type: str,
) -> None:
    """MERGE a :Track node. Idempotent."""
    client = get_neo4j_client()
    client.execute_write(
        """
        MERGE (t:Track {name: $name, system_id: $system_id})
        SET t.track_type = $track_type
        """,
        {"name": name, "system_id": system_id, "track_type": track_type},
    )


def neo4j_create_condition(
    *,
    name: str,
    system_id: str,
) -> None:
    """MERGE a :Condition node. Idempotent."""
    client = get_neo4j_client()
    client.execute_write(
        """
        MERGE (c:Condition {name: $name, system_id: $system_id})
        """,
        {"name": name, "system_id": system_id},
    )


def neo4j_create_resolution_mechanic(
    *,
    name: str,
    system_id: str,
    mechanic_type: str,
) -> None:
    """MERGE a :ResolutionMechanic node. Idempotent."""
    client = get_neo4j_client()
    client.execute_write(
        """
        MERGE (r:ResolutionMechanic {name: $name, system_id: $system_id})
        SET r.mechanic_type = $mechanic_type
        """,
        {"name": name, "system_id": system_id, "mechanic_type": mechanic_type},
    )


def neo4j_link_entity_to_ability(
    *,
    entity_id: str,
    ability_system_name: str,
) -> None:
    """Create HAS_ACCESS_TO relationship from an entity to an AbilitySystem node."""
    client = get_neo4j_client()
    client.execute_write(
        """
        MATCH (e {id: $entity_id})
        MATCH (a:AbilitySystem {name: $ability_system_name})
        MERGE (e)-[:HAS_ACCESS_TO]->(a)
        """,
        {"entity_id": entity_id, "ability_system_name": ability_system_name},
    )
