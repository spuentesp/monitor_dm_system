"""
Universes & Multiverses router.

A Multiverse groups one or more Universes (fictional worlds).
The frontend hierarchy is: Multiverse → Universe → entities/sessions.

Backed by Neo4j via monitor_data tools. Falls back with a 503 if the
database is unreachable so the frontend can show a clean error state.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from monitor_data.tools.neo4j_tools import (
    neo4j_ensure_omniverse,
    neo4j_create_multiverse,
    neo4j_list_multiverses,
    neo4j_delete_multiverse,
    neo4j_create_universe,
    neo4j_list_universes,
    neo4j_get_universe,
    neo4j_get_universe_state,
    neo4j_update_universe,
    neo4j_delete_universe,
)
from monitor_data.schemas.universe import (
    MultiverseCreate as DLMultiverseCreate,
    UniverseCreate as DLUniverseCreate,
    UniverseUpdate as DLUniverseUpdate,
    UniverseFilter,
)

from .ingest_shared import db_op

router = APIRouter()


# ─── Helpers ──────────────────────────────────────────────────


def _get_omniverse_id() -> UUID:
    """Ensure the omniverse exists and return its ID."""
    result = neo4j_ensure_omniverse()
    return UUID(result["omniverse_id"])


def _mv_to_dict(mv, universe_count: int = 0) -> dict:
    """Shape a MultiverseResponse into the frontend Multiverse type."""
    return {
        "id": str(mv.id),
        "name": mv.name,
        "description": mv.description or None,
        "tags": [mv.system_name] if mv.system_name else [],
        "universe_count": universe_count,
        "created_at": mv.created_at.isoformat()
        if hasattr(mv.created_at, "isoformat")
        else str(mv.created_at),
    }


def _u_to_dict(
    u,
    entity_count: int = 0,
    session_count: int = 0,
    story_count: int = 0,
) -> dict:
    """Shape a UniverseResponse into the frontend Universe type."""
    return {
        "id": str(u.id),
        "name": u.name,
        "multiverse_id": str(u.multiverse_id),
        "genre": u.genre,
        "description": u.description or None,
        "tags": [u.canon_level.value] if u.canon_level else [],
        "is_active": False,
        "entity_count": entity_count,
        "session_count": session_count,
        "story_count": story_count,
        "created_at": u.created_at.isoformat()
        if hasattr(u.created_at, "isoformat")
        else str(u.created_at),
    }


def _universe_counts(universe_ids: list[str]) -> dict[str, dict[str, int]]:
    """Entity/story counts from Neo4j + chat-session counts from Mongo.

    Counts are best-effort decoration: a failure returns zeros rather than
    failing the listing itself.
    """
    counts: dict[str, dict[str, int]] = {
        uid: {"entity_count": 0, "session_count": 0, "story_count": 0}
        for uid in universe_ids
    }
    if not universe_ids:
        return counts

    try:
        from monitor_data.db.neo4j import get_neo4j_client

        client = get_neo4j_client()
        rows = client.execute_read(
            """
            MATCH (u:Universe) WHERE u.id IN $ids
            OPTIONAL MATCH (u)-[:HAS_ENTITY]->(e1)
            OPTIONAL MATCH (e2)-[:IN_UNIVERSE]->(u)
            OPTIONAL MATCH (s:Story {universe_id: u.id})
            RETURN u.id AS id,
                   count(DISTINCT e1) + count(DISTINCT e2) AS entity_count,
                   count(DISTINCT s) AS story_count
            """,
            {"ids": universe_ids},
        )
        for row in rows:
            if row["id"] in counts:
                counts[row["id"]]["entity_count"] = row["entity_count"]
                counts[row["id"]]["story_count"] = row["story_count"]
    except Exception:  # noqa: BLE001
        pass

    try:
        from monitor_data.db.mongodb import get_mongodb_client

        col = get_mongodb_client().get_collection("chat_sessions")
        for row in col.aggregate(
            [
                {"$match": {"universe_id": {"$in": universe_ids}}},
                {"$group": {"_id": "$universe_id", "n": {"$sum": 1}}},
            ]
        ):
            if row["_id"] in counts:
                counts[row["_id"]]["session_count"] = row["n"]
    except Exception:  # noqa: BLE001
        pass

    return counts


# ─── Schemas ──────────────────────────────────────────────────


class MultiverseCreate(BaseModel):
    name: str
    description: str | None = None
    tags: list[str] = []


class UniverseCreate(BaseModel):
    name: str
    multiverse_id: str
    genre: str | None = None
    description: str | None = None
    tags: list[str] = []
    is_active: bool = False


class UniverseUpdate(BaseModel):
    name: str | None = None
    genre: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


# ─── Multiverse endpoints ─────────────────────────────────────


@router.get("/multiverses")
async def list_multiverses() -> list[dict]:
    """Return all multiverses, each annotated with universe count."""
    with db_op("Database unavailable"):
        multiverses = neo4j_list_multiverses()
        universes = neo4j_list_universes(UniverseFilter(limit=100))

        # Count universes per multiverse
        counts: dict[str, int] = {}
        for u in universes:
            key = str(u.multiverse_id)
            counts[key] = counts.get(key, 0) + 1

        return [_mv_to_dict(mv, counts.get(str(mv.id), 0)) for mv in multiverses]


@router.post("/multiverses", status_code=201)
async def create_multiverse(body: MultiverseCreate) -> dict:
    with db_op("Database unavailable"):
        omniverse_id = _get_omniverse_id()
        system_name = body.tags[0] if body.tags else "Custom"
        params = DLMultiverseCreate(
            omniverse_id=omniverse_id,
            name=body.name,
            system_name=system_name,
            description=body.description or "",
        )
        mv = neo4j_create_multiverse(params)
        return _mv_to_dict(mv, 0)


@router.delete("/multiverses/{mv_id}", status_code=204)
async def delete_multiverse(mv_id: str) -> None:
    try:
        neo4j_delete_multiverse(UUID(mv_id), force=True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


# ─── Universe endpoints ────────────────────────────────────────


@router.get("/universes")
async def list_universes(multiverse_id: str | None = None) -> list[dict]:
    with db_op("Database unavailable"):
        f = UniverseFilter(
            multiverse_id=UUID(multiverse_id) if multiverse_id else None,
            limit=200,
        )
        universes = neo4j_list_universes(f)
        counts = _universe_counts([str(u.id) for u in universes])
        return [_u_to_dict(u, **counts.get(str(u.id), {})) for u in universes]


@router.get("/universes/{universe_id}")
async def get_universe(universe_id: str) -> dict:
    with db_op("Database unavailable"):
        u = neo4j_get_universe(UUID(universe_id))
        if not u:
            raise HTTPException(404, "Universe not found")
        counts = _universe_counts([str(u.id)])
        return _u_to_dict(u, **counts.get(str(u.id), {}))


@router.get("/universes/{universe_id}/state")
async def get_universe_state(universe_id: str) -> dict:
    """Full world state: entities, facts, axioms, relationships (O1/O5 view)."""
    with db_op("Database unavailable"):
        return neo4j_get_universe_state(UUID(universe_id))


@router.post("/universes", status_code=201)
async def create_universe(body: UniverseCreate) -> dict:
    try:
        params = DLUniverseCreate(
            multiverse_id=UUID(body.multiverse_id),
            name=body.name,
            description=body.description or "",
            genre=body.genre,
        )
        u = neo4j_create_universe(params)
        return _u_to_dict(u)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


@router.put("/universes/{universe_id}")
async def update_universe(universe_id: str, body: UniverseUpdate) -> dict:
    try:
        params = DLUniverseUpdate(
            name=body.name,
            genre=body.genre,
            description=body.description,
        )
        u = neo4j_update_universe(UUID(universe_id), params)
        return _u_to_dict(u)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


@router.delete("/universes/{universe_id}", status_code=204)
async def delete_universe(universe_id: str) -> None:
    try:
        neo4j_delete_universe(UUID(universe_id), force=True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


@router.post("/universes/{universe_id}/activate")
async def activate_universe(universe_id: str) -> dict:
    """No-op in the graph model — there is no 'active' universe concept at DB level.
    Returns the universe data so the frontend state update still works."""
    try:
        u = neo4j_get_universe(UUID(universe_id))
        if not u:
            raise HTTPException(404, "Universe not found")
        result = _u_to_dict(u)
        result["is_active"] = True
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


# ─── Universe lifecycle endpoints (Phase 2/3) ──────────────────


class SeedRequest(BaseModel):
    """Request to seed a universe with entities from templates and random tables."""

    template_ids: list[str] = []
    random_table_ids: list[str] = []
    entity_count: int = 10
    location_count: int = 3
    npc_count: int = 5
    seed_facts: bool = True


class ForkRequest(BaseModel):
    """Request to fork a universe into a new one."""

    name: str
    description: str | None = None
    include_stories: bool = False


class SnapshotRequest(BaseModel):
    """Request to create a snapshot of a universe."""

    name: str
    description: str | None = None


class SnapshotRestoreRequest(BaseModel):
    """Request to restore a universe from a snapshot."""

    confirm: bool = False


@router.post("/universes/{universe_id}/seed")
async def seed_universe(universe_id: str, body: SeedRequest) -> dict:
    """
    Seed a universe with procedurally generated entities from random tables.

    Uses the WorldArchitect agent to generate locations and NPCs.
    """
    try:
        from monitor_agents.world_architect import WorldArchitect
        import asyncio

        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        architect = WorldArchitect()
        result = asyncio.run(
            architect.seed_universe(
                universe_id=UUID(universe_id),
                num_entities=body.entity_count,
                location_count=body.location_count,
                npc_count=body.npc_count,
            )
        )

        return {
            "universe_id": universe_id,
            "entities_created": result["generated"],
            "entities": result["entities"],
            "errors": result["errors"],
            "status": "seeded" if result["generated"] > 0 else "no_entities_created",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Seed failed: {exc}") from exc


@router.post("/universes/{universe_id}/fork")
async def fork_universe(universe_id: str, body: ForkRequest) -> dict:
    """
    Fork a universe: deep-clone all entities, facts, and relationships
    into a new universe.
    """
    try:
        from monitor_data.tools.neo4j_tools import neo4j_fork_universe

        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        result = neo4j_fork_universe(
            source_universe_id=UUID(universe_id),
            name=body.name,
            description=body.description or f"Fork of {universe.name}",
        )

        return {
            "source_universe_id": universe_id,
            "new_universe_id": result.get("new_universe_id"),
            "name": body.name,
            "entities_cloned": result.get("entities_cloned", 0),
            "relationships_cloned": result.get("relationships_cloned", 0),
            "status": "forked",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Fork failed: {exc}") from exc


@router.post("/universes/{universe_id}/snapshots")
async def create_snapshot(universe_id: str, body: SnapshotRequest) -> dict:
    """Create a snapshot of the current universe state."""
    try:
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_create_world_snapshot,
        )
        from monitor_data.schemas.world_snapshots import WorldSnapshotCreate

        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        snapshot = mongodb_create_world_snapshot(
            WorldSnapshotCreate(
                universe_id=UUID(universe_id),
                name=body.name,
                description=body.description or "",
            )
        )

        return {
            "snapshot_id": str(snapshot.snapshot_id),
            "universe_id": universe_id,
            "name": snapshot.name,
            "entity_count": snapshot.entity_count,
            "fact_count": snapshot.fact_count,
            "status": "created",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Snapshot failed: {exc}") from exc


@router.get("/universes/{universe_id}/snapshots")
async def list_snapshots(universe_id: str) -> list[dict]:
    """List all snapshots for a universe."""
    try:
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_list_world_snapshots,
        )
        from monitor_data.schemas.world_snapshots import WorldSnapshotFilter

        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        snapshots = mongodb_list_world_snapshots(
            WorldSnapshotFilter(universe_id=UUID(universe_id))
        )

        return [
            {
                "id": str(s.snapshot_id),
                "name": s.name,
                "description": s.description,
                "entity_count": s.entity_count,
                "fact_count": s.fact_count,
                "created_at": s.created_at.isoformat()
                if hasattr(s.created_at, "isoformat")
                else str(s.created_at),
            }
            for s in snapshots.snapshots
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


@router.delete("/universes/{universe_id}/snapshots/{snapshot_id}", status_code=204)
async def delete_snapshot(universe_id: str, snapshot_id: str) -> None:
    """Delete a single snapshot. Idempotent — returns 204 whether or not it existed."""
    try:
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_delete_world_snapshot,
        )

        mongodb_delete_world_snapshot(UUID(snapshot_id))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Delete failed: {exc}") from exc


@router.post("/universes/{universe_id}/snapshots/{snapshot_id}/restore")
async def restore_snapshot(
    universe_id: str, snapshot_id: str, body: SnapshotRestoreRequest
) -> dict:
    """Restore a universe from a snapshot."""
    try:
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_restore_world_snapshot,
        )

        if not body.confirm:
            raise HTTPException(400, "Must confirm snapshot restore with confirm=true")

        result = mongodb_restore_world_snapshot(UUID(snapshot_id))

        return {
            "universe_id": universe_id,
            "snapshot_id": snapshot_id,
            "status": "restored",
            "entities_restored": result.get("entities_restored", 0)
            if isinstance(result, dict)
            else 0,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Restore failed: {exc}") from exc


@router.get("/universes/{universe_id}/snapshots/compare")
async def compare_snapshots(
    universe_id: str,
    snapshot_a_id: str,
    snapshot_b_id: str,
) -> dict:
    """
    Compare two snapshots and return a detailed diff.

    Returns entity/fact/relationship changes between the two snapshots.
    """
    try:
        from monitor_data.tools.mongodb_tools.snapshots import mongodb_compare_snapshots

        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        from uuid import UUID as uuid_type

        result = mongodb_compare_snapshots(
            uuid_type(snapshot_a_id), uuid_type(snapshot_b_id)
        )

        return {
            "snapshot_a_id": str(result.snapshot_a_id),
            "snapshot_b_id": str(result.snapshot_b_id),
            "universe_id": str(result.universe_id),
            "entity_summary": {
                "added": result.entities_added,
                "removed": result.entities_removed,
                "modified": result.entities_modified,
            },
            "fact_summary": {
                "added": result.facts_added,
                "removed": result.facts_removed,
                "modified": result.facts_modified,
            },
            "relationship_summary": {
                "added": result.relationships_added,
                "removed": result.relationships_removed,
            },
            "entity_diffs": [
                {
                    "entity_id": d.entity_id,
                    "name": d.name,
                    "diff_type": d.diff_type,
                    "changed_fields": d.changed_fields,
                }
                for d in result.entity_diffs[:50]  # Cap at 50 for response size
            ],
            "fact_diffs": [
                {
                    "fact_id": d.fact_id,
                    "statement": d.statement[:100] + "..."
                    if len(d.statement) > 100
                    else d.statement,
                    "diff_type": d.diff_type,
                    "changed_fields": d.changed_fields,
                }
                for d in result.fact_diffs[:50]
            ],
            "relationship_diffs": [
                {
                    "from_entity_id": d.from_entity_id,
                    "to_entity_id": d.to_entity_id,
                    "relationship_type": d.relationship_type,
                    "diff_type": d.diff_type,
                }
                for d in result.relationship_diffs[:50]
            ],
            "snapshot_a_name": result.snapshot_a_name,
            "snapshot_b_name": result.snapshot_b_name,
            "compared_at": result.compared_at.isoformat()
            if hasattr(result.compared_at, "isoformat")
            else str(result.compared_at),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Compare failed: {exc}") from exc
