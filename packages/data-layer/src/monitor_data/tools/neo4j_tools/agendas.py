"""
Neo4j tools for Faction Agendas and Clocks.

LAYER: 1 (data-layer)
Authority: Neo4j
Use Case: M-36 (Faction Drive)
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from monitor_data.db.neo4j import get_neo4j_client

logger = logging.getLogger(__name__)


def neo4j_create_agenda(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new Agenda node and link it to an owner (Faction/NPC).
    """
    client = get_neo4j_client()
    agenda_id = params.get("id") or str(uuid4())
    universe_id = params.get("universe_id")
    owner_id = params.get("owner_id")

    query = """
    MATCH (u:Universe {id: $universe_id})
    CREATE (a:Agenda {
        id: $id,
        title: $title,
        description: $description,
        agenda_type: $agenda_type,
        status: $status,
        total_segments: $total_segments,
        current_segments: $current_segments,
        created_at: datetime(),
        updated_at: datetime()
    })
    CREATE (a)-[:IN_UNIVERSE]->(u)
    WITH a
    OPTIONAL MATCH (owner {id: $owner_id})
    WHERE owner:EntityInstance OR owner:EntityArchetype
    FOREACH (o IN CASE WHEN owner IS NOT NULL THEN [owner] ELSE [] END |
        CREATE (owner)-[:DRIVEN_BY]->(a)
    )
    RETURN a {.*, owner_id: $owner_id} as agenda
    """

    res = client.execute_write(
        query,
        {
            "id": agenda_id,
            "universe_id": str(universe_id),
            "owner_id": str(owner_id) if owner_id else None,
            "title": params.get("title"),
            "description": params.get("description", ""),
            "agenda_type": params.get("agenda_type", "faction_goal"),
            "status": params.get("status", "active"),
            "total_segments": int(params.get("total_segments", 6)),
            "current_segments": int(params.get("current_segments", 0)),
        },
    )

    return res[0]["agenda"] if res else {}


def neo4j_list_agendas(universe_id: UUID, status: Optional[str] = "active") -> List[Dict[str, Any]]:
    """
    List agendas for a universe, optionally filtered by status.
    """
    client = get_neo4j_client()
    query = """
    MATCH (a:Agenda)-[:IN_UNIVERSE]->(u:Universe {id: $uid})
    WHERE ($status IS NULL OR a.status = $status)
    OPTIONAL MATCH (owner)-[:DRIVEN_BY]->(a)
    RETURN a {.*, owner_id: owner.id, owner_name: owner.name} as agenda
    ORDER BY a.created_at DESC
    """
    res = client.execute_read(query, {"uid": str(universe_id), "status": status})
    return [record["agenda"] for record in res]


def neo4j_update_agenda_clock(agenda_id: UUID, tick: int) -> Dict[str, Any]:
    """
    Advance or retreat an agenda's clock.
    """
    client = get_neo4j_client()
    query = """
    MATCH (a:Agenda {id: $id})
    SET a.current_segments = CASE 
        WHEN a.current_segments + $tick < 0 THEN 0
        WHEN a.current_segments + $tick > a.total_segments THEN a.total_segments
        ELSE a.current_segments + $tick 
    END,
    a.updated_at = datetime(),
    a.status = CASE 
        WHEN a.current_segments + $tick >= a.total_segments THEN 'completed'
        ELSE a.status
    END
    RETURN a {.*} as agenda
    """
    res = client.execute_write(query, {"id": str(agenda_id), "tick": tick})
    return res[0]["agenda"] if res else {}
