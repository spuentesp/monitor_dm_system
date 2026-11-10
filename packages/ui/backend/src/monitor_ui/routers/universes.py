"""
Universes & Multiverses router.

A Multiverse groups one or more Universes (fictional worlds).
The frontend hierarchy is: Multiverse → Universe → entities/sessions.

Backed by Neo4j via monitor_data tools. Falls back with a 503 if the
database is unreachable so the frontend can show a clean error state.
"""

import structlog

from typing import Any

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.universe import (
    MultiverseCreate as DLMultiverseCreate,
)
from monitor_data.schemas.universe import (
    MultiverseUpdate as DLMultiverseUpdate,
)
from monitor_data.schemas.universe import (
    UniverseCreate as DLUniverseCreate,
)
from monitor_data.schemas.universe import (
    UniverseFilter,
)
from monitor_data.schemas.universe import (
    UniverseUpdate as DLUniverseUpdate,
)
from monitor_data.db.minio import get_minio_client
from monitor_data.tools.mongodb_tools import mongodb_fork_universe_data
from monitor_data.tools.qdrant_tools import qdrant_clone_collection
from monitor_data.tools.neo4j_tools import (
    neo4j_create_multiverse,
    neo4j_create_universe,
    neo4j_delete_multiverse,
    neo4j_delete_universe,
    neo4j_ensure_omniverse,
    neo4j_get_multiverse,
    neo4j_get_universe,
    neo4j_get_universe_state,
    neo4j_list_multiverses,
    neo4j_list_universes,
    neo4j_update_multiverse,
    neo4j_update_universe,
)
from pydantic import BaseModel

from monitor_ui.auth import Principal, get_current_user, get_postgres
from monitor_ui.ownership import (
    owned_multiverse_ids,
    owned_world_ids,
    require_multiverse_owner,
    require_universe_owner,
    resource_route_guard,
)

from .ingest_shared import db_op

log = structlog.get_logger()

router = APIRouter(dependencies=[Depends(resource_route_guard)])


def _default_world_bindings(world_id: str) -> dict[str, Any]:
    """Per-world DB bindings for a freshly created/forked world.

    Neo4j Community has a single user database, so graph isolation is by the
    Universe node (not neo4j_database); Mongo/Qdrant/MinIO isolate by prefix.
    """
    short = world_id.replace("-", "")[:12]
    return {
        "world_id": world_id,
        "neo4j_database": "neo4j",
        "mongodb_database": "monitor",
        "mongodb_collection_prefix": f"w{short}_",
        "qdrant_collection": f"world_{short}",
        "minio_bucket": "monitor",
        "minio_prefix": f"{short}/",
    }


# ─── Helpers ──────────────────────────────────────────────────


def _get_omniverse_id() -> UUID:
    """Ensure the omniverse exists and return its ID."""
    result = neo4j_ensure_omniverse()
    return UUID(result["omniverse_id"])


# reason: `mv` parameter has no annotation and `-> dict` return is the bare generic missing type parameters; helper builds a heterogeneous multiverse response dict literal
def _mv_to_dict(mv, universe_count: int = 0) -> dict:  # type: ignore
    """Shape a MultiverseResponse into the frontend Multiverse type."""
    return {
        "id": str(mv.id),
        "name": mv.name,
        "description": mv.description or None,
        "tags": [mv.system_name] if mv.system_name else [],
        "system_name": mv.system_name or None,
        "is_template": mv.is_template,
        "knowledge_tree_type": mv.knowledge_tree_type.value if mv.knowledge_tree_type else None,
        "parent_multiverse_id": str(mv.parent_multiverse_id) if mv.parent_multiverse_id else None,
        "universe_count": universe_count,
        "created_at": mv.created_at.isoformat() if hasattr(mv.created_at, "isoformat") else str(mv.created_at),
    }


# reason: _u_to_dict parameter `u` has no annotation (paired with the `-> dict` return-type suppression below); helper takes an untyped UniverseResponse-like object and returns a heterogeneous dict literal
def _u_to_dict(  # type: ignore
    u,
    entity_count: int = 0,
    session_count: int = 0,
    story_count: int = 0,
    # reason: _u_to_dict `-> dict` return is the bare generic missing type parameters (paired with the no-untyped-def suppression above); helper builds a heterogeneous universe response dict literal
) -> dict:  # type: ignore
    """Shape a UniverseResponse into the frontend Universe type."""
    return {
        "id": str(u.id),
        "name": u.name,
        "multiverse_id": str(u.multiverse_id),
        "genre": u.genre,
        "tone": u.tone,
        "description": u.description or None,
        "is_template": u.is_template,
        "default_game_system_id": str(u.default_game_system_id) if u.default_game_system_id else None,
        "tags": [u.canon_level.value] if u.canon_level else [],
        "is_active": False,
        "entity_count": entity_count,
        "session_count": session_count,
        "story_count": story_count,
        "created_at": u.created_at.isoformat() if hasattr(u.created_at, "isoformat") else str(u.created_at),
    }


def _universe_counts(universe_ids: list[str]) -> dict[str, dict[str, int]]:
    """Entity/story counts from Neo4j + chat-session counts from Mongo.

    Counts are best-effort decoration: a failure returns zeros rather than
    failing the listing itself.
    """
    counts: dict[str, dict[str, int]] = {
        uid: {"entity_count": 0, "session_count": 0, "story_count": 0} for uid in universe_ids
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
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _universe_counts)
        log.debug("universe counts aggregation failed", exc_info=True)

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
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _universe_counts)
        log.debug("session counts aggregation failed", exc_info=True)

    return counts


# ─── Schemas ──────────────────────────────────────────────────


class MultiverseCreate(BaseModel):
    name: str
    description: str | None = None
    tags: list[str] = []


class MultiverseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_name: str | None = None


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
    tone: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


# ─── Multiverse endpoints ─────────────────────────────────────


@router.get("/multiverses")
# reason: `-> list[dict]` return is the bare generic missing type parameters; handler delegates to `_mv_to_dict` which builds a heterogeneous multiverse response literal
async def list_multiverses(
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> list[dict]:  # type: ignore
    """Return the caller's multiverses, each annotated with universe count.

    Owner-before-pagination: the owned-ID allowlist comes from the Postgres
    registry and is pushed into the Cypher query; an empty allowlist returns
    an empty list, never an unscoped one.
    """
    with db_op("Database unavailable"):
        owned_mv = await owned_multiverse_ids(db, principal)
        if owned_mv is not None and not owned_mv:
            return []
        owned_w = await owned_world_ids(db, principal)
        if owned_w is not None and not owned_w:
            multiverses = neo4j_list_multiverses(ids=[UUID(i) for i in owned_mv] if owned_mv else None)
            return [_mv_to_dict(mv, 0) for mv in multiverses]
        multiverses = neo4j_list_multiverses(ids=[UUID(i) for i in owned_mv] if owned_mv else None)
        universes = neo4j_list_universes(
            UniverseFilter(
                limit=1000,
                ids=[UUID(i) for i in owned_w] if owned_w is not None else None,
            )
        )

        # Count universes per multiverse
        counts: dict[str, int] = {}
        for u in universes:
            key = str(u.multiverse_id)
            counts[key] = counts.get(key, 0) + 1

        return [_mv_to_dict(mv, counts.get(str(mv.id), 0)) for mv in multiverses]


@router.post("/multiverses", status_code=201)
# reason: `-> dict` return is the bare generic missing type parameters; handler delegates to `_mv_to_dict` which builds a heterogeneous multiverse response literal
async def create_multiverse(
    body: MultiverseCreate,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
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
        # Register ownership in Postgres (authoritative registry, plan D3).
        # Neo4j and Postgres share no transaction: on registration failure,
        # roll back the canonical node so we never return an ownerless world.
        try:
            await db.multiverse_upsert(
                {
                    "id": str(mv.id),
                    "owner_id": principal.user_id,
                    "label": mv.name,
                    "active": True,
                }
            )
        except Exception as exc:
            try:
                neo4j_delete_multiverse(mv.id, force=True)
            except Exception:  # noqa: BLE001  # reason: compensating rollback is best-effort; the orphan is logged for reconciliation
                log.warning("compensating delete of multiverse failed", mv_id=str(mv.id), exc_info=True)
            raise HTTPException(503, f"Database unavailable: {exc}") from exc
        return _mv_to_dict(mv, 0)


@router.put("/multiverses/{mv_id}")
@router.patch("/multiverses/{mv_id}")
# reason: `-> dict` return is the bare generic missing type parameters; handler delegates to `_mv_to_dict` which builds a heterogeneous multiverse response literal
async def update_multiverse(
    mv_id: str,
    body: MultiverseUpdate,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    try:
        await require_multiverse_owner(db, principal, mv_id)
        params = DLMultiverseUpdate(
            name=body.name,
            system_name=body.system_name,
            description=body.description,
        )
        mv = neo4j_update_multiverse(UUID(mv_id), params)
        if body.name is not None:
            await db.multiverse_upsert(
                {"id": str(mv.id), "owner_id": principal.user_id, "label": mv.name, "active": True}
            )
        return _mv_to_dict(mv)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


@router.delete("/multiverses/{mv_id}", status_code=204)
async def delete_multiverse(
    mv_id: str,
    force: bool = False,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> None:
    """Delete a multiverse. Non-empty multiverses require an explicit
    ?force=true cascade; otherwise they are refused with 409."""
    try:
        await require_multiverse_owner(db, principal, mv_id)
        mv_uuid = UUID(mv_id)
        if neo4j_get_multiverse(mv_uuid) is None:
            raise HTTPException(404, f"Multiverse {mv_id} not found")
        children = neo4j_list_universes(UniverseFilter(multiverse_id=mv_uuid, limit=1000))
        if children and not force:
            raise HTTPException(
                409,
                f"Multiverse contains {len(children)} universe(s). "
                "Delete them first, or retry with ?force=true to cascade.",
            )
        neo4j_delete_multiverse(mv_uuid, force=force)
        # Canonical delete succeeded: detach registry rows (worlds first).
        for child in children:
            await db.world_delete(str(child.id))
        await db.multiverse_delete(str(mv_uuid))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


# ─── Universe endpoints ────────────────────────────────────────


@router.get("/universes")
# reason: `-> list[dict]` return is the bare generic missing type parameters; handler delegates to `_u_to_dict` which builds a heterogeneous universe response literal
async def list_universes(
    multiverse_id: str | None = None,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> list[dict]:  # type: ignore
    """List the caller's universes, optionally within an owned multiverse."""
    with db_op("Database unavailable"):
        if multiverse_id is not None:
            await require_multiverse_owner(db, principal, multiverse_id)
        owned = await owned_world_ids(db, principal)
        if owned is not None and not owned:
            return []
        f = UniverseFilter(
            multiverse_id=UUID(multiverse_id) if multiverse_id else None,
            ids=[UUID(i) for i in owned] if owned is not None else None,
            limit=200,
        )
        universes = neo4j_list_universes(f)
        counts = _universe_counts([str(u.id) for u in universes])
        return [_u_to_dict(u, **counts.get(str(u.id), {})) for u in universes]


@router.get("/universes/{universe_id}")
# reason: `-> dict` return is the bare generic missing type parameters; handler delegates to `_u_to_dict` which builds a heterogeneous universe response literal
async def get_universe(
    universe_id: str,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    with db_op("Database unavailable"):
        await require_universe_owner(db, principal, universe_id)
        u = neo4j_get_universe(UUID(universe_id))
        if not u:
            raise HTTPException(404, "Universe not found")
        counts = _universe_counts([str(u.id)])
        return _u_to_dict(u, **counts.get(str(u.id), {}))


@router.get("/universes/{universe_id}/state")
# reason: `-> dict` return is the bare generic missing type parameters; handler returns the full Neo4j state dict directly (`entities`, `facts`, `axioms`, `relationships`) with heterogeneous value types
async def get_universe_state(
    universe_id: str,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    """Full world state: entities, facts, axioms, relationships (O1/O5 view)."""
    with db_op("Database unavailable"):
        await require_universe_owner(db, principal, universe_id)
        return neo4j_get_universe_state(UUID(universe_id))


@router.post("/universes", status_code=201)
# reason: `-> dict` return is the bare generic missing type parameters; handler delegates to `_u_to_dict` which builds a heterogeneous universe response literal
async def create_universe(
    body: UniverseCreate,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    try:
        # The parent multiverse must belong to the caller — a foreign or
        # missing parent is a generic 404, never an error that reveals it.
        await require_multiverse_owner(db, principal, body.multiverse_id)
        params = DLUniverseCreate(
            multiverse_id=UUID(body.multiverse_id),
            name=body.name,
            description=body.description or "",
            genre=body.genre,
        )
        u = neo4j_create_universe(params)
        # Register ownership (compensating delete on failure, as above).
        try:
            await db.world_upsert(
                {
                    "id": str(u.id),
                    "owner_id": principal.user_id,
                    "multiverse_id": str(u.multiverse_id),
                    "label": u.name,
                    "active": True,
                }
            )
        except Exception as exc:
            try:
                neo4j_delete_universe(u.id, force=True)
            except Exception:  # noqa: BLE001  # reason: compensating rollback is best-effort; the orphan is logged for reconciliation
                log.warning("compensating delete of universe failed", universe_id=str(u.id), exc_info=True)
            raise HTTPException(503, f"Database unavailable: {exc}") from exc
        await db.world_bindings_upsert(_default_world_bindings(str(u.id)))
        return _u_to_dict(u)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


@router.put("/universes/{universe_id}")
# reason: `-> dict` return is the bare generic missing type parameters; handler delegates to `_u_to_dict` which builds a heterogeneous universe response literal
async def update_universe(
    universe_id: str,
    body: UniverseUpdate,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    try:
        await require_universe_owner(db, principal, universe_id)
        params = DLUniverseUpdate(
            name=body.name,
            genre=body.genre,
            tone=body.tone,
            description=body.description,
        )
        u = neo4j_update_universe(UUID(universe_id), params)
        if body.name is not None:
            await db.world_upsert(
                {
                    "id": str(u.id),
                    "owner_id": principal.user_id,
                    "multiverse_id": str(u.multiverse_id),
                    "label": u.name,
                    "active": True,
                }
            )
        return _u_to_dict(u)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


@router.delete("/universes/{universe_id}", status_code=204)
async def delete_universe(
    universe_id: str,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> None:
    try:
        await require_universe_owner(db, principal, universe_id)
        neo4j_delete_universe(UUID(universe_id), force=True)
        # Canonical delete succeeded: detach the ownership registry row.
        await db.world_delete(str(universe_id))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
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
# reason: `-> dict` return is the bare generic missing type parameters; handler builds a heterogeneous seed response literal (`universe_id`, `entities_created`, `entities`, `errors`, `status`)
async def seed_universe(
    universe_id: str,
    body: SeedRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    """
    Seed a universe with procedurally generated entities from random tables.

    Uses the WorldArchitect agent to generate locations and NPCs.
    """
    try:
        from monitor_agents.world_architect.agent import WorldArchitect

        await require_universe_owner(db, principal, universe_id)
        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        architect = WorldArchitect()
        result = await architect.seed_universe(
            universe_id=UUID(universe_id),
            num_entities=body.entity_count,
            location_count=body.location_count,
            npc_count=body.npc_count,
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
# reason: `-> dict` return is the bare generic missing type parameters; handler builds a heterogeneous fork response literal (`source_universe_id`, `new_universe_id`, `name`, `entities_cloned`, `relationships_cloned`, `status`)
async def fork_universe(
    universe_id: str,
    body: ForkRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    """
    Fork a universe: deep-clone all entities, facts, and relationships
    into a new universe registered under the CALLER, not the source owner.
    """
    try:
        from monitor_data.tools.neo4j_tools import neo4j_fork_universe

        await require_universe_owner(db, principal, universe_id)
        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        result = neo4j_fork_universe(
            source_universe_id=UUID(universe_id),
            name=body.name,
            description=body.description or f"Fork of {universe.name}",
        )

        # Register the fork under the caller (compensating delete on failure).
        new_id = result.get("new_universe_id")
        try:
            await db.world_upsert(
                {
                    "id": str(new_id),
                    "owner_id": principal.user_id,
                    "multiverse_id": str(universe.multiverse_id),
                    "label": body.name,
                    "active": True,
                }
            )
        except Exception as exc:
            try:
                neo4j_delete_universe(UUID(str(new_id)), force=True)
            except Exception:  # noqa: BLE001  # reason: compensating rollback is best-effort; the orphan is logged for reconciliation
                log.warning("compensating delete of fork failed", universe_id=str(new_id), exc_info=True)
            raise HTTPException(503, f"Database unavailable: {exc}") from exc

        # Register per-world DB bindings and clone the world's data into the
        # forked world's prefixed Mongo collections / Qdrant collection /
        # MinIO prefix (multi-world isolation).
        src_bindings = await db.world_bindings_get(universe_id) or {}
        dst_bindings = _default_world_bindings(str(new_id))
        await db.world_bindings_upsert(dst_bindings)
        mongo_res = mongodb_fork_universe_data(universe_id, str(new_id), dst_bindings["mongodb_collection_prefix"])
        qdrant_res = qdrant_clone_collection(
            src_bindings.get("qdrant_collection", "monitor_memories"),
            dst_bindings["qdrant_collection"],
        )
        minio_res = await get_minio_client().copy_prefix(
            src_bindings.get("minio_prefix", ""), dst_bindings["minio_prefix"]
        )

        return {
            "source_universe_id": universe_id,
            "new_universe_id": result.get("new_universe_id"),
            "name": body.name,
            "entities_cloned": result.get("entities_cloned", 0),
            "relationships_cloned": result.get("relationships_cloned", 0),
            "bindings": dst_bindings,
            "mongo": mongo_res,
            "qdrant": qdrant_res,
            "minio": minio_res,
            "status": "forked",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Fork failed: {exc}") from exc


@router.post("/universes/{universe_id}/snapshots")
# reason: `-> dict` return is the bare generic missing type parameters; handler builds a heterogeneous snapshot-create response literal (`snapshot_id`, `universe_id`, `name`, `entity_count`, `fact_count`, `status`)
async def create_snapshot(
    universe_id: str,
    body: SnapshotRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    """Create a snapshot of the current universe state."""
    try:
        from monitor_data.schemas.world_snapshots import WorldSnapshotCreate
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_create_world_snapshot,
        )

        await require_universe_owner(db, principal, universe_id)
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
# reason: `-> list[dict]` return is the bare generic missing type parameters; handler builds a list of heterogeneous per-snapshot dict literals (`id`, `name`, `description`, `entity_count`, `fact_count`, `created_at`)
async def list_snapshots(
    universe_id: str,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> list[dict]:  # type: ignore
    """List all snapshots for a universe."""
    try:
        from monitor_data.schemas.world_snapshots import WorldSnapshotFilter
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_list_world_snapshots,
        )

        await require_universe_owner(db, principal, universe_id)
        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        snapshots = mongodb_list_world_snapshots(WorldSnapshotFilter(universe_id=UUID(universe_id)))

        return [
            {
                "id": str(s.snapshot_id),
                "name": s.name,
                "description": s.description,
                "entity_count": s.entity_count,
                "fact_count": s.fact_count,
                "created_at": s.created_at.isoformat() if hasattr(s.created_at, "isoformat") else str(s.created_at),
            }
            for s in snapshots.snapshots
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


async def _require_snapshot_in_universe(
    universe_id: str,
    snapshot_id: str,
) -> None:
    """The snapshot must exist AND belong to the path universe, else 404."""
    from monitor_data.tools.mongodb_tools.snapshots import mongodb_get_world_snapshot

    snapshot = mongodb_get_world_snapshot(UUID(snapshot_id))
    if snapshot is None or str(snapshot.universe_id) != str(universe_id):
        raise HTTPException(404, "Not found")


@router.delete("/universes/{universe_id}/snapshots/{snapshot_id}", status_code=204)
async def delete_snapshot(
    universe_id: str,
    snapshot_id: str,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> None:
    """Delete a single snapshot that belongs to the caller's universe."""
    try:
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_delete_world_snapshot,
        )

        await require_universe_owner(db, principal, universe_id)
        await _require_snapshot_in_universe(universe_id, snapshot_id)
        mongodb_delete_world_snapshot(UUID(snapshot_id))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Delete failed: {exc}") from exc


@router.post("/universes/{universe_id}/snapshots/{snapshot_id}/restore")
# reason: `-> dict` return is the bare generic missing type parameters; handler builds a heterogeneous snapshot-restore response literal (`universe_id`, `snapshot_id`, `status`, `entities_restored`)
async def restore_snapshot(
    universe_id: str,
    snapshot_id: str,
    body: SnapshotRestoreRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict:  # type: ignore
    """Restore a universe from a snapshot."""
    try:
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_restore_world_snapshot,
        )

        await require_universe_owner(db, principal, universe_id)
        await _require_snapshot_in_universe(universe_id, snapshot_id)
        if not body.confirm:
            raise HTTPException(400, "Must confirm snapshot restore with confirm=true")

        result = mongodb_restore_world_snapshot(UUID(snapshot_id))

        return {
            "universe_id": universe_id,
            "snapshot_id": snapshot_id,
            "status": "restored",
            "entities_restored": result.get("entities_restored", 0) if isinstance(result, dict) else 0,
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
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
    # reason: `-> dict` return is the bare generic missing type parameters; handler builds a heterogeneous snapshot-compare response literal (`snapshot_a_id`, `snapshot_b_id`, `universe_id`, three summary dicts, three diff lists, two name fields, `compared_at`)
) -> dict:  # type: ignore
    """
    Compare two snapshots and return a detailed diff.

    Returns entity/fact/relationship changes between the two snapshots.
    """
    try:
        from monitor_data.tools.mongodb_tools.snapshots import mongodb_compare_snapshots

        await require_universe_owner(db, principal, universe_id)
        await _require_snapshot_in_universe(universe_id, snapshot_a_id)
        await _require_snapshot_in_universe(universe_id, snapshot_b_id)
        universe = neo4j_get_universe(UUID(universe_id))
        if not universe:
            raise HTTPException(404, "Universe not found")

        from uuid import UUID as uuid_type

        result = mongodb_compare_snapshots(uuid_type(snapshot_a_id), uuid_type(snapshot_b_id))

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
                    "statement": d.statement[:100] + "..." if len(d.statement) > 100 else d.statement,
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
