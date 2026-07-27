"""
Shared helpers for Neo4j tool modules.

DRY: Common verification and query patterns used across all neo4j_tools.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from monitor_data.db.neo4j import Neo4jClient


def verify_node_exists(
    client: Neo4jClient,
    label: str,
    node_id: UUID | str,
    *,
    id_field: str = "id",
) -> list[dict[str, Any]]:
    """Verify a Neo4j node exists by label and id field.

    Args:
        client: Neo4j client to execute the query.
        label: Node label (e.g. "Omniverse", "Universe", "Entity").
        node_id: The node identifier value.
        id_field: The property name used as identifier (default "id").

    Returns:
        Query result rows.

    Raises:
        ValueError: If the node does not exist.
    """
    query = f"MATCH (n:{label} {{{id_field}: $node_id}}) RETURN n.{id_field} as id"
    result = client.execute_read(query, {"node_id": str(node_id)})
    if not result:
        raise ValueError(f"{label} {node_id} not found")
    return result


def verify_nodes_exist(
    client: Neo4jClient,
    label: str,
    node_ids: list[UUID | str],
    *,
    id_field: str = "id",
) -> None:
    """Verify multiple nodes exist in a single batch query.

    Args:
        client: Neo4j client.
        label: Node label.
        node_ids: List of identifiers to check.
        id_field: The property name used as identifier.

    Raises:
        ValueError: If any node does not exist, reporting the first missing.
    """
    if not node_ids:
        return

    ids_str = [str(nid) for nid in node_ids]
    query = f"MATCH (n:{label}) WHERE n.{id_field} IN $node_ids RETURN n.{id_field} as id"
    result = client.execute_read(query, {"node_ids": ids_str})
    found_ids = {row["id"] for row in result}

    missing = [nid for nid in ids_str if nid not in found_ids]
    if missing:
        raise ValueError(f"{label} {missing[0]} not found (and {len(missing) - 1} more missing)")
