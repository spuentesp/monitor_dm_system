"""GDS-backed graph analytics over a universe's Entity subgraph (read-only).

LAYER: 1 (data-layer). Requires the GDS plugin jar in infra/neo4j/plugins
(fetched via scripts/fetch_neo4j_plugins.sh — GDS 2.6.x for Neo4j 5.15).

Each tool projects an in-memory GDS graph scoped to one universe
(`Entity.universe_id`), runs one algorithm, and drops the projection again.
All tools are read-only: they only CALL gds.* stream/project/drop procedures
and never write graph data, so they are safe to expose with wildcard authority.

Intended uses:
- neo4j_universe_connected_components : orphan detection (base-world publish gate)
- neo4j_universe_node_similarity      : duplicate-entity candidates when layering
                                        a story on top of a base world
- neo4j_universe_centrality           : NPC/entity importance ranking for context
- neo4j_shortest_path                 : bounded alternative to hand-rolled BFS
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.tools.neo4j_tools._helpers import verify_node_exists

_GRAPH_PREFIX = "monitor_gds_"

_CENTRALITY_KINDS = ("degree", "betweenness", "pagerank")


def _validate_universe_id(universe_id: Any) -> str:
    """Return the universe id as a canonical UUID string (raises on garbage)."""
    return str(UUID(str(universe_id)))


@contextmanager
def _universe_graph(client: Any, universe_id: str) -> Iterator[str]:
    """Project the universe's Entity subgraph into a private in-memory GDS graph.

    The universe id is validated as a UUID above, so inlining it into the
    nodeQuery/relationshipQuery strings is safe. The projection is always
    dropped, even if the algorithm query fails.
    """
    verify_node_exists(client, "Universe", universe_id)
    graph = f"{_GRAPH_PREFIX}{uuid4().hex[:12]}"
    # universe_id is UUID-validated above, so inlining it into the
    # nodeQuery/relationshipQuery strings is safe.
    client.execute_write(
        f"""
        CALL gds.graph.project.cypher(
          $graph,
          "MATCH (n:Entity) WHERE n.universe_id = '{universe_id}' RETURN id(n) AS id",
          "MATCH (a:Entity)-[r]->(b:Entity) WHERE a.universe_id = '{universe_id}' AND b.universe_id = '{universe_id}' RETURN id(a) AS source, id(b) AS target, type(r) AS type",
          {{}}
        )
        """,
        {"graph": graph},
    )
    try:
        yield graph
    finally:
        client.execute_write(
            "CALL gds.graph.exists($graph) YIELD exists",
            {"graph": graph},
        )
        client.execute_write(
            "CALL gds.graph.drop($graph) YIELD graphName",
            {"graph": graph},
        )


def _entity_lookup(client: Any, node_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Map internal Neo4j node ids to {entity_id, name} for the given ids."""
    if not node_ids:
        return {}
    rows = client.execute_read(
        "MATCH (n:Entity) WHERE id(n) IN $node_ids RETURN id(n) AS node_id, n.id AS entity_id, n.name AS name",
        {"node_ids": node_ids},
    )
    return {int(r["node_id"]): {"entity_id": r["entity_id"], "name": r.get("name")} for r in rows}


def neo4j_graph_algorithms_available() -> dict[str, Any]:
    """Report whether the GDS plugin is loaded (procedure count + version)."""
    client = get_neo4j_client()
    try:
        rows = client.execute_read("CALL gds.list() YIELD name RETURN count(name) AS procedures")
        procedures = int(rows[0]["procedures"]) if rows else 0
    except Exception:  # noqa: BLE001  # reason: plugin-missing surfaces as a Cypher error; report unavailable
        return {"available": False, "procedures": 0}
    version_rows = client.execute_read("CALL gds.version() YIELD gdsVersion RETURN gdsVersion AS version")
    return {
        "available": procedures > 0,
        "procedures": procedures,
        "version": version_rows[0]["version"] if version_rows else None,
    }


def neo4j_universe_connected_components(
    universe_id: Any,
    min_component_size: int = 2,
    limit: int = 50,
) -> dict[str, Any]:
    """Weakly-connected components of a universe's entity graph.

    Entities in components smaller than ``min_component_size`` are reported as
    orphans — the base-world publish gate checks ``orphan_count == 0``.
    """
    uid = _validate_universe_id(universe_id)
    min_size = max(1, min(int(min_component_size), 100))
    safe_limit = max(1, min(int(limit), 200))
    client = get_neo4j_client()
    with _universe_graph(client, uid) as graph:
        rows = client.execute_read(
            "CALL gds.wcc.stream($graph) YIELD nodeId, componentId RETURN nodeId, componentId",
            {"graph": graph},
        )
        lookup = _entity_lookup(client, [int(r["nodeId"]) for r in rows])

    components: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        members = lookup.get(int(r["nodeId"]))
        if members is None:
            continue
        components.setdefault(int(r["componentId"]), []).append(members)

    orphans = sorted(
        (m for members in components.values() if len(members) < min_size for m in members),
        key=lambda m: (m.get("name") or "").lower(),
    )
    ranked = sorted(components.values(), key=len, reverse=True)[:safe_limit]
    return {
        "universe_id": uid,
        "component_count": len(components),
        "orphan_count": len(orphans),
        "orphans": orphans,
        "largest_components": [
            {"size": len(members), "members": sorted(members, key=lambda m: m.get("name") or "")} for members in ranked
        ],
    }


def neo4j_universe_node_similarity(
    universe_id: Any,
    similarity_cutoff: float = 0.6,
    top_k: int = 10,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Relationship-Jaccard similar entity pairs — duplicate candidates.

    Used when layering a new story onto a base world: pairs above the cutoff
    are merge candidates for CanonKeeper to review.
    """
    uid = _validate_universe_id(universe_id)
    cutoff = max(0.0, min(float(similarity_cutoff), 1.0))
    safe_top_k = max(1, min(int(top_k), 100))
    safe_limit = max(1, min(int(limit), 200))
    client = get_neo4j_client()
    with _universe_graph(client, uid) as graph:
        rows = client.execute_read(
            """
            CALL gds.nodeSimilarity.stream($graph, {similarityCutoff: $cutoff, topK: $top_k})
            YIELD node1, node2, similarity
            RETURN node1, node2, similarity
            """,
            {"graph": graph, "cutoff": cutoff, "top_k": safe_top_k},
        )
        lookup = _entity_lookup(client, [int(r["node1"]) for r in rows] + [int(r["node2"]) for r in rows])

    pairs = []
    for r in rows:
        a, b = lookup.get(int(r["node1"])), lookup.get(int(r["node2"]))
        if a is None or b is None:
            continue
        pairs.append(
            {
                "entity_a": a["entity_id"],
                "name_a": a.get("name"),
                "entity_b": b["entity_id"],
                "name_b": b.get("name"),
                "similarity": round(float(r["similarity"]), 4),
            }
        )
    pairs.sort(key=lambda p: p["similarity"], reverse=True)
    return pairs[:safe_limit]


def neo4j_universe_centrality(
    universe_id: Any,
    kind: str = "degree",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Rank a universe's entities by centrality (degree | betweenness | pagerank)."""
    uid = _validate_universe_id(universe_id)
    kind = str(kind).strip().lower()
    if kind not in _CENTRALITY_KINDS:
        raise ValueError(f"kind must be one of {_CENTRALITY_KINDS}, got {kind!r}")
    safe_limit = max(1, min(int(limit), 100))
    procedure = {"degree": "gds.degree", "betweenness": "gds.betweenness", "pagerank": "gds.pageRank"}[kind]
    client = get_neo4j_client()
    with _universe_graph(client, uid) as graph:
        rows = client.execute_read(
            f"CALL {procedure}.stream($graph) YIELD nodeId, score RETURN nodeId, score ORDER BY score DESC LIMIT $limit",
            {"graph": graph, "limit": safe_limit},
        )
        lookup = _entity_lookup(client, [int(r["nodeId"]) for r in rows])

    result = []
    for r in rows:
        entity = lookup.get(int(r["nodeId"]))
        if entity is None:
            continue
        result.append(
            {
                "entity_id": entity["entity_id"],
                "name": entity.get("name"),
                "score": round(float(r["score"]), 6),
                "kind": kind,
            }
        )
    return result


def neo4j_shortest_path(
    universe_id: Any,
    from_entity_id: str,
    to_entity_id: str,
    max_hops: int = 10,
) -> dict[str, Any] | None:
    """Shortest path (unweighted) between two entities of a universe.

    Returns None when no path exists or the shortest path exceeds max_hops.
    """
    uid = _validate_universe_id(universe_id)
    safe_hops = max(1, min(int(max_hops), 20))
    from_id = str(from_entity_id).strip()
    to_id = str(to_entity_id).strip()
    if not from_id or not to_id:
        raise ValueError("from_entity_id and to_entity_id are required")
    client = get_neo4j_client()
    endpoints = client.execute_read(
        """
        MATCH (a:Entity {id: $from_id, universe_id: $uid}), (b:Entity {id: $to_id, universe_id: $uid})
        RETURN id(a) AS source, id(b) AS target
        """,
        {"from_id": from_id, "to_id": to_id, "uid": uid},
    )
    if not endpoints:
        return None
    source, target = int(endpoints[0]["source"]), int(endpoints[0]["target"])
    with _universe_graph(client, uid) as graph:
        rows = client.execute_read(
            """
            CALL gds.shortestPath.dijkstra.stream($graph, {sourceNode: $source, targetNode: $target})
            YIELD nodeIds, totalCost
            RETURN nodeIds, totalCost
            """,
            {"graph": graph, "source": source, "target": target},
        )
        if not rows:
            return None
        node_ids = [int(n) for n in rows[0]["nodeIds"]]
        lookup = _entity_lookup(client, node_ids)

    hops = len(node_ids) - 1
    if hops > safe_hops:
        return None
    path = [lookup.get(n, {"entity_id": None, "name": None}) for n in node_ids]
    return {
        "universe_id": uid,
        "from_entity_id": from_id,
        "to_entity_id": to_id,
        "hops": hops,
        "path": [{"entity_id": p["entity_id"], "name": p.get("name")} for p in path],
    }
