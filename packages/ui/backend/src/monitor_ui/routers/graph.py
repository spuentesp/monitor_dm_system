"""
World Graph router.

Returns the full world hierarchy shaped as ReactFlow nodes + edges:
  Omniverse → Multiverse → Universe → Entity (characters, locations, factions…)
  Plus typed relationships between entities.

Supports optional query-param filters to scope the graph:
  - multiverse_id: show only one setting (multiverse + its universes + entities)
  - universe_id: show only one universe + its entities
  - entity_types: comma-separated list of entity types to include
  - related_to: entity ID — show only entities directly related to this one

Falls back with an empty graph if Neo4j is unreachable.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from monitor_data.schemas.entities import EntityFilter
from monitor_data.schemas.relationships import RelationshipFilter
from monitor_data.schemas.universe import UniverseFilter
from monitor_data.tools.neo4j_tools import (
    neo4j_ensure_omniverse,
    neo4j_get_entity,
    neo4j_list_entities,
    neo4j_list_multiverses,
    neo4j_list_relationships,
    neo4j_list_universes,
)

router = APIRouter()

# ─── Entity type → graph kind ─────────────────────────────────

_ENTITY_KIND: dict[str, str] = {
    "character": "character",
    "location": "location",
    "faction": "faction",
    "concept": "concept",
    "object": "concept",
    "organization": "faction",
}


# ─── Layout helpers ───────────────────────────────────────────


def _tier_layout(
    items: list,  # type: ignore
    y: float,
    parent_x: float | None = None,
    x_spread: float = 220,
) -> list[tuple[object, float, float]]:
    """Place items in a horizontal row centred on parent_x."""
    n = len(items)
    if n == 0:
        return []
    cx = parent_x if parent_x is not None else 0.0
    start = cx - (n - 1) * x_spread / 2
    return [(item, start + i * x_spread, y) for i, item in enumerate(items)]


# ─── Route ────────────────────────────────────────────────────


@router.get("/world")
async def get_world_graph(
    multiverse_id: UUID | None = Query(None, description="Scope to a single setting"),
    universe_id: UUID | None = Query(None, description="Scope to a single universe"),
    entity_types: str | None = Query(None, description="Comma-separated entity types"),
    related_to: UUID | None = Query(None, description="Show only entities related to this entity"),
) -> dict:  # type: ignore
    """
    Return the world graph as ReactFlow nodes and edges.

    Hierarchy rendered:
      Multiverse nodes (row 0)
        └─ Universe nodes (row 1)
             └─ Entity nodes (rows 2+, max 20 per universe)
                  └─ Entity→Entity relationship edges (dashed)

    Filters narrow the result without changing the layout algorithm.
    """
    try:
        neo4j_ensure_omniverse()

        multiverses = neo4j_list_multiverses()

        # ── Scope universes at the DB level ─────────────────────
        universe_filter = UniverseFilter(limit=500)
        if multiverse_id:
            universe_filter = UniverseFilter(multiverse_id=multiverse_id, limit=500)
        universes = neo4j_list_universes(universe_filter)

        # ── Narrow multiverses to only those with visible universes
        if multiverse_id:
            mv_str = str(multiverse_id)
            multiverses = [mv for mv in multiverses if str(mv.id) == mv_str]

        if universe_id:
            u_str = str(universe_id)
            universes = [u for u in universes if str(u.id) == u_str]
            # ensure the parent multiverse is also shown
            mv_ids = {str(u.multiverse_id) for u in universes}
            multiverses = [mv for mv in multiverses if str(mv.id) in mv_ids]

        # ── Parse entity type filter ────────────────────────────
        allowed_entity_types: set[str] | None = None
        if entity_types:
            allowed_entity_types = {t.strip().lower() for t in entity_types.split(",") if t.strip()}

        # ── Load entities (scoped to visible universes) ─────────
        entity_filter = EntityFilter(limit=500)
        if universe_id:
            entity_filter = EntityFilter(universe_id=universe_id, limit=500)
        elif multiverse_id and universes:
            # Load entities only for universes in this multiverse
            # Query per-universe to stay scoped (avoids fetching all)
            entity_filter = EntityFilter(universe_id=universes[0].id, limit=500)

        entities_r = neo4j_list_entities(entity_filter)

        # If multiverse filter is set and there are multiple universes,
        # fetch entities for the remaining universes too
        if multiverse_id and len(universes) > 1:
            for u in universes[1:]:
                extra = neo4j_list_entities(EntityFilter(universe_id=u.id, limit=500))
                entities_r.entities.extend(extra.entities)

        rels_r = neo4j_list_relationships(RelationshipFilter(limit=1000))

        # If scoping to a specific entity, collect only its neighbors
        related_entity_ids: set[str] | None = None
        if related_to:
            rt_str = str(related_to)
            related_entity_ids = {rt_str}
            for rel in rels_r.relationships:
                from_id = str(rel.from_entity_id)
                to_id = str(rel.to_entity_id)
                if from_id == rt_str:
                    related_entity_ids.add(to_id)
                elif to_id == rt_str:
                    related_entity_ids.add(from_id)
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    nodes: list[dict] = []  # type: ignore
    edges: list[dict] = []  # type: ignore

    # ── Multiverses (row 0) ───────────────────────────────────
    mv_positions: dict[str, float] = {}  # multiverse_id → x
    MV_SPREAD = 340

    for _i, mv in enumerate(_tier_layout(multiverses, y=0, x_spread=MV_SPREAD)):
        mv_obj, x, y = mv
        mv_id = str(mv_obj.id)  # type: ignore
        mv_positions[mv_id] = x
        nodes.append(
            {
                "id": mv_id,
                "type": "worldNode",
                "position": {"x": x, "y": y},
                "data": {
                    "label": mv_obj.name,  # type: ignore
                    "kind": "multiverse",
                    "subtitle": mv_obj.system_name or None,  # type: ignore
                },
            }
        )

    # ── Universes (row 1) ─────────────────────────────────────
    # Group universes by their parent multiverse
    mv_children: dict[str, list] = {}  # type: ignore
    for u in universes:
        mv_children.setdefault(str(u.multiverse_id), []).append(u)

    u_positions: dict[str, float] = {}  # universe_id → x

    for mv_id, mv_univs in mv_children.items():
        parent_x = mv_positions.get(mv_id, 0.0)
        for u_obj, x, y in _tier_layout(mv_univs, y=220, parent_x=parent_x, x_spread=240):
            u_id = str(u_obj.id)  # type: ignore
            u_positions[u_id] = x
            nodes.append(
                {
                    "id": u_id,
                    "type": "worldNode",
                    "position": {"x": x, "y": y},
                    "data": {
                        "label": u_obj.name,  # type: ignore
                        "kind": "universe",
                        "subtitle": u_obj.genre or None,  # type: ignore
                        "tags": [u_obj.canon_level.value] if u_obj.canon_level else [],  # type: ignore
                    },
                }
            )
            edges.append(
                {
                    "id": f"e-mv-{mv_id}-u-{u_id}",
                    "source": mv_id,
                    "target": u_id,
                    "type": "smoothstep",
                }
            )

    # ── Entities (rows 2+) ────────────────────────────────────
    # Group entities by their parent universe (cap at 20 per universe)
    # Apply entity_type and related_to filters
    u_entities: dict[str, list] = {}  # type: ignore
    for e in entities_r.entities:
        u_id = str(e.universe_id)
        # Skip entities from universes not in our visible set
        if u_id not in u_positions:
            continue
        # Apply entity type filter
        if allowed_entity_types and e.entity_type.lower() not in allowed_entity_types:
            continue
        # Apply related_to filter
        if related_entity_ids and str(e.id) not in related_entity_ids:
            continue
        bucket = u_entities.setdefault(u_id, [])
        if len(bucket) < 20:
            bucket.append(e)

    entity_ids: set[str] = set()

    for u_id, entities in u_entities.items():
        parent_x = u_positions.get(u_id, 0.0)
        cols = 5
        col_spread = 180
        row_spread = 160

        for idx, e in enumerate(entities):
            col = idx % cols
            row = idx // cols
            x = parent_x + (col - (min(len(entities), cols) - 1) / 2) * col_spread
            y = 460 + row * row_spread

            e_id = str(e.id)
            entity_ids.add(e_id)
            kind = _ENTITY_KIND.get(e.entity_type, "concept")

            nodes.append(
                {
                    "id": e_id,
                    "type": "worldNode",
                    "position": {"x": x, "y": y},
                    "data": {
                        "label": e.name,
                        "kind": kind,
                        "subtitle": e.entity_type if e.is_archetype else None,
                        "description": e.description,
                        "tags": list(e.state_tags[:3]),
                    },
                }
            )
            edges.append(
                {
                    "id": f"e-u-{u_id}-e-{e_id}",
                    "source": u_id,
                    "target": e_id,
                }
            )

    # ── Entity relationships (dashed) ─────────────────────────
    for rel in rels_r.relationships:
        from_id = str(rel.from_entity_id)
        to_id = str(rel.to_entity_id)
        if from_id in entity_ids and to_id in entity_ids:
            label = rel.rel_type.replace("_", " ").lower() if rel.rel_type else None
            edges.append(
                {
                    "id": f"rel-{rel.relationship_id}",
                    "source": from_id,
                    "target": to_id,
                    "label": label,
                    "style": {"strokeDasharray": "4 2", "opacity": 0.6},
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "entity_types": sorted({e.entity_type for e in entities_r.entities}),
        "rel_types": sorted({rel.rel_type for rel in rels_r.relationships if rel.rel_type}),
    }


# =============================================================================
# Q-11: World Graph Explorer — universe-scoped and ego-graph endpoints
# =============================================================================


@router.get("/universes/{universe_id}/graph")
async def get_universe_graph(
    universe_id: UUID,
    depth: int = Query(default=1, ge=1, le=5, description="Traversal depth (1-5)"),
    entity_types: str | None = Query(default=None, description="Comma-separated entity types to include"),
    rel_types: str | None = Query(default=None, description="Comma-separated relationship types to include"),
    limit_per_depth: int = Query(default=50, ge=1, le=200, description="Max entities per depth level"),
) -> dict:  # type: ignore
    """
    Return the world graph scoped to a single universe.

    Like /graph/world but filtered to one universe, with configurable
    traversal depth (default 1 = direct children only, up to 5 for deep graphs).

    This is the primary Q-11 endpoint for the graph explorer UI.
    """
    try:
        # ── Load universe ───────────────────────────────────────
        universe_filter = UniverseFilter(id=universe_id, limit=1)
        universes = neo4j_list_universes(universe_filter)
        if not universes:
            return {
                "nodes": [],
                "edges": [],
                "error": f"Universe {universe_id} not found",
            }
        universe = universes[0]

        # ── Parse filters ──────────────────────────────────────
        allowed_entity_types: set[str] | None = None
        if entity_types:
            allowed_entity_types = {t.strip().lower() for t in entity_types.split(",") if t.strip()}

        allowed_rel_types: set[str] | None = None
        if rel_types:
            allowed_rel_types = {t.strip().lower() for t in rel_types.split(",") if t.strip()}

        # ── Load entities (scoped to universe) ──────────────────
        entity_filter = EntityFilter(universe_id=universe_id, limit=limit_per_depth)
        entities_r = neo4j_list_entities(entity_filter)

        # ── Load relationships ───────────────────────────────────
        rels_r = neo4j_list_relationships(RelationshipFilter(limit=1000))

        # ── Apply filters ──────────────────────────────────────
        filtered_entities = entities_r.entities
        if allowed_entity_types:
            filtered_entities = [e for e in filtered_entities if e.entity_type.lower() in allowed_entity_types]

        filtered_rels = rels_r.relationships
        if allowed_rel_types:
            filtered_rels = [r for r in filtered_rels if r.rel_type and r.rel_type.lower() in allowed_rel_types]

    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    nodes: list[dict] = []  # type: ignore
    edges: list[dict] = []  # type: ignore

    # ── Universe node (center) ─────────────────────────────────
    u_id = str(universe.id)
    nodes.append(
        {
            "id": u_id,
            "type": "worldNode",
            "position": {"x": 0, "y": 0},
            "data": {
                "label": universe.name,
                "kind": "universe",
                "subtitle": universe.genre or None,
                "tags": [universe.canon_level.value] if universe.canon_level else [],
            },
        }
    )

    # ── Entity nodes (surrounding universe) ────────────────────
    entity_ids: set[str] = set()
    cols = 6
    col_spread = 200
    row_spread = 160
    n = len(filtered_entities)
    start_x = -(min(n, cols) - 1) * col_spread / 2

    for idx, e in enumerate(filtered_entities[:limit_per_depth]):
        e_id = str(e.id)
        entity_ids.add(e_id)
        col = idx % cols
        row = idx // cols
        x = start_x + col * col_spread
        y = 200 + row * row_spread
        kind = _ENTITY_KIND.get(e.entity_type, "concept")

        nodes.append(
            {
                "id": e_id,
                "type": "worldNode",
                "position": {"x": x, "y": y},
                "data": {
                    "label": e.name,
                    "kind": kind,
                    "subtitle": e.entity_type if e.is_archetype else None,
                    "description": e.description,
                    "tags": list(e.state_tags[:3]),
                },
            }
        )
        edges.append(
            {
                "id": f"e-u-{u_id}-e-{e_id}",
                "source": u_id,
                "target": e_id,
            }
        )

    # ── Entity→Entity relationship edges ──────────────────────
    for rel in filtered_rels:
        from_id = str(rel.from_entity_id)
        to_id = str(rel.to_entity_id)
        if from_id in entity_ids and to_id in entity_ids:
            label = rel.rel_type.replace("_", " ").lower() if rel.rel_type else None
            edges.append(
                {
                    "id": f"rel-{rel.relationship_id}",
                    "source": from_id,
                    "target": to_id,
                    "label": label,
                    "style": {"strokeDasharray": "4 2", "opacity": 0.6},
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "entity_types": sorted({e.entity_type for e in filtered_entities}),
        "rel_types": sorted({rel.rel_type for rel in filtered_rels if rel.rel_type}),
        "total_entities": len(filtered_entities),
        "total_relationships": len(filtered_rels),
    }


@router.get("/universes/{universe_id}/graph/entity/{entity_id}")
async def get_entity_ego_graph(
    entity_id: UUID,
    universe_id: UUID,
    depth: int = Query(default=1, ge=1, le=3, description="Neighbour depth (1-3)"),
) -> dict:  # type: ignore
    """
    Return the ego-graph centred on a specific entity.

    Shows the entity at the center and its direct neighbours (depth=1),
    their neighbours (depth=2), etc. Useful for exploring connections
    without loading the full universe graph.

    Maximum depth is 3 to keep response bounded.
    """
    try:
        # Load the central entity
        entity_filter = EntityFilter(id=entity_id, universe_id=universe_id, limit=1)
        entities_r = neo4j_list_entities(entity_filter)
        central = entities_r.entities[0] if entities_r.entities else None
        if not central:
            return {
                "nodes": [],
                "edges": [],
                "error": f"Entity {entity_id} not found in universe {universe_id}",
            }

        # Load all relationships in this universe
        rels_r = neo4j_list_relationships(RelationshipFilter(universe_id=universe_id, limit=2000))

    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    # ── BFS to collect neighbours up to depth ──────────────────
    visited: dict[str, int] = {str(entity_id): 0}  # entity_id → depth
    queue = [str(entity_id)]

    for current_depth in range(depth):
        next_queue = []
        for current_id in queue:
            for rel in rels_r.relationships:
                from_id = str(rel.from_entity_id)
                to_id = str(rel.to_entity_id)
                neighbor = None
                if from_id == current_id and to_id not in visited:
                    neighbor = to_id
                elif to_id == current_id and from_id not in visited:
                    neighbor = from_id
                if neighbor:
                    visited[neighbor] = current_depth + 1
                    next_queue.append(neighbor)
        queue = next_queue
        if not queue:
            break

    # ── Load all neighbour entities (by id — a list filter does not exist) ──
    neighbor_ids = list(visited.keys())
    all_entities = []

    for nid in neighbor_ids:
        try:
            e = neo4j_get_entity(UUID(nid))
        except Exception:
            e = None
        if e is not None:
            all_entities.append(e)

    # Build entity lookup
    entity_map: dict[str, Any] = {str(e.id): e for e in all_entities}

    # ── Build nodes ─────────────────────────────────────────────
    nodes: list[dict] = []  # type: ignore
    edges: list[dict] = []  # type: ignore
    entity_ids: set[str] = set()

    # Central entity at center
    central_id = str(central.id)
    entity_ids.add(central_id)
    kind = _ENTITY_KIND.get(central.entity_type, "concept")
    nodes.append(
        {
            "id": central_id,
            "type": "worldNode",
            "position": {"x": 0, "y": 0},
            "data": {
                "label": central.name,
                "kind": kind,
                "subtitle": central.entity_type if central.is_archetype else None,
                "description": central.description,
                "tags": list(central.state_tags[:3]),
            },
        }
    )

    # Neighbour entities in concentric rings by depth
    by_depth: dict[int, list[str]] = {}
    for eid, d in visited.items():
        if eid != central_id:
            by_depth.setdefault(d, []).append(eid)

    ring_spread = 220
    ring_row_spread = 160
    max_per_ring = 8

    for depth_level, eids in sorted(by_depth.items()):
        ring_radius = depth_level * ring_spread
        n = len(eids)
        start_x = -(min(n, max_per_ring) - 1) * ring_spread / 2

        for idx, eid in enumerate(eids[:max_per_ring]):
            if eid not in entity_map:
                continue
            e = entity_map[eid]
            entity_ids.add(eid)
            col = idx % max_per_ring
            row = idx // max_per_ring
            x = start_x + col * ring_spread
            y = ring_radius + row * ring_row_spread
            ekind = _ENTITY_KIND.get(e.entity_type, "concept")

            nodes.append(
                {
                    "id": eid,
                    "type": "worldNode",
                    "position": {"x": x, "y": y},
                    "data": {
                        "label": e.name,
                        "kind": ekind,
                        "subtitle": e.entity_type if e.is_archetype else None,
                        "description": e.description,
                        "tags": list(e.state_tags[:3]),
                    },
                }
            )

    # ── Build edges (only for visited entities) ─────────────────
    for rel in rels_r.relationships:
        from_id = str(rel.from_entity_id)
        to_id = str(rel.to_entity_id)
        if from_id in entity_ids and to_id in entity_ids:
            label = rel.rel_type.replace("_", " ").lower() if rel.rel_type else None
            edges.append(
                {
                    "id": f"rel-{rel.relationship_id}",
                    "source": from_id,
                    "target": to_id,
                    "label": label,
                    "style": {"strokeDasharray": "4 2", "opacity": 0.6},
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "central_entity_id": central_id,
        "depth": depth,
        "entity_types": sorted(
            {entity_map.get(eid, type("E", (), {"entity_type": "unknown"})()).entity_type for eid in entity_ids}
        ),
        "rel_types": sorted(
            {
                rel.rel_type
                for rel in rels_r.relationships
                if rel.rel_type and str(rel.from_entity_id) in entity_ids and str(rel.to_entity_id) in entity_ids
            }
        ),
    }
