"""Neo4j traversal-oriented read helpers for retrieval-time graph navigation.

These operations are read-only and provide bounded neighborhood/path signals
for agents that perform query-aware traversal.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from monitor_data.db.neo4j import get_neo4j_client


def neo4j_get_entities_by_scene(scene_id: UUID, limit: int = 30) -> list[dict[str, Any]]:
    """Return entities connected to a Scene through fact evidence links.

    The primary relationship path is:
      (:Scene {id})<-[:SUPPORTED_BY]-(:Fact)-[:INVOLVES]->(:Entity)
    """
    client = get_neo4j_client()
    safe_limit = max(1, min(int(limit), 100))
    results = client.execute_read(
        """
        MATCH (s:Scene {id: $scene_id})<-[:SUPPORTED_BY]-(f:Fact)-[:INVOLVES]->(e:Entity)
        RETURN DISTINCT
          e.id AS id,
          e.name AS name,
          e.entity_type AS entity_type,
          e.description AS description,
          e.canon_level AS canon_level
        LIMIT $limit
        """,
        {"scene_id": str(scene_id), "limit": safe_limit},
    )
    return [dict(row) for row in results]


def neo4j_get_scene_relevant_entities(scene_id: UUID, limit: int = 30) -> list[dict[str, Any]]:
    """Alias for scene-scoped entity retrieval used by traversal pipelines."""
    return neo4j_get_entities_by_scene(scene_id=scene_id, limit=limit)


def neo4j_get_entity_neighborhood(
    entity_id: UUID,
    rel_types: list[str] | None = None,
    direction: str = "both",
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return a bounded one-hop neighborhood around an entity.

    Args:
        entity_id: Anchor entity ID.
        rel_types: Optional allow-list of relation type names.
        direction: one of "incoming", "outgoing", "both".
        limit: max number of relationship rows.
    """
    client = get_neo4j_client()
    safe_limit = max(1, min(int(limit), 100))
    normalized_direction = (direction or "both").strip().lower()
    if normalized_direction not in {"incoming", "outgoing", "both"}:
        normalized_direction = "both"

    rel_type_filter = [str(value).strip().upper() for value in (rel_types or []) if str(value).strip()]

    query = """
    MATCH (anchor:Entity {id: $entity_id})-[r]-(other:Entity)
    WHERE (
      $direction = 'both'
      OR ($direction = 'outgoing' AND startNode(r).id = anchor.id)
      OR ($direction = 'incoming' AND endNode(r).id = anchor.id)
    )
      AND (
        size($rel_types) = 0
        OR type(r) IN $rel_types
      )
    RETURN
      id(r) AS relationship_id,
      type(r) AS rel_type,
      properties(r) AS properties,
      startNode(r).id AS from_entity_id,
      endNode(r).id AS to_entity_id,
      other.id AS counterpart_entity_id,
      other.name AS counterpart_name,
      other.entity_type AS counterpart_entity_type,
      other.canon_level AS counterpart_canon_level
    ORDER BY relationship_id DESC
    LIMIT $limit
    """

    results = client.execute_read(
        query,
        {
            "entity_id": str(entity_id),
            "direction": normalized_direction,
            "rel_types": rel_type_filter,
            "limit": safe_limit,
        },
    )
    return [dict(row) for row in results]


def neo4j_find_ranked_paths(
    seed_entity_ids: list[str],
    rel_types: list[str] | None = None,
    hop_limit: int = 2,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return bounded 1-2 hop path candidates from a seed set.

    This intentionally favors conservative traversal: it returns simple path
    rows with relation type chains and endpoint metadata rather than executing
    open-ended graph searches.
    """
    if not seed_entity_ids:
        return []

    client = get_neo4j_client()
    safe_limit = max(1, min(int(limit), 100))
    safe_hops = max(1, min(int(hop_limit), 2))
    rel_type_filter = [str(value).strip().upper() for value in (rel_types or []) if str(value).strip()]
    normalized_seed_ids = [str(value).strip() for value in seed_entity_ids if str(value).strip()][:20]
    if not normalized_seed_ids:
        return []

    query = f"""
    UNWIND $seed_ids AS seed_id
    MATCH p=(start:Entity {{id: seed_id}})-[*1..{safe_hops}]-(target:Entity)
    WITH p, start, target, [rel IN relationships(p) | type(rel)] AS rel_chain
    WHERE size($rel_types) = 0 OR any(rel IN rel_chain WHERE rel IN $rel_types)
    RETURN DISTINCT
      start.id AS seed_entity_id,
      start.name AS seed_name,
      target.id AS target_entity_id,
      target.name AS target_name,
      rel_chain AS rel_chain,
      length(p) AS hop_count
    ORDER BY hop_count ASC
    LIMIT $limit
    """

    results = client.execute_read(
        query,
        {
            "seed_ids": normalized_seed_ids,
            "rel_types": rel_type_filter,
            "limit": safe_limit,
        },
    )
    return [dict(row) for row in results]
