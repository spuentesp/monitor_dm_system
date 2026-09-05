"""
Databases router — health checks and statistics for all MONITOR databases.

Pings Neo4j, MongoDB, Qdrant, MinIO, and OpenSearch and returns
connection status, latency, and key stats.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from monitor_ui.config import get_settings

router = APIRouter()
_settings = get_settings()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DatabaseStatus(BaseModel):
    name: str
    db_type: str  # neo4j | mongodb | qdrant | minio | opensearch
    url: str
    status: str  # online | offline | degraded
    latency_ms: float | None = None
    version: str | None = None
    # reason: Pydantic v2 forbids mutable default `{}` on BaseModel fields; the bare `dict` annotation defers typing of the heterogeneous per-database stat payload (nodes/relationships/collections/counts) — narrow to dict[str, int | str] in a follow-up
    stats: dict = {}  # type: ignore
    error: str | None = None


# ---------------------------------------------------------------------------
# DRY helper — wraps any check coroutine with timing + error handling
# ---------------------------------------------------------------------------


def _make_offline(name: str, db_type: str, url: str, error: str) -> DatabaseStatus:
    """Build a standard offline status payload."""
    return DatabaseStatus(name=name, db_type=db_type, url=url, status="offline", error=error)


async def _timed_check(
    name: str,
    db_type: str,
    url: str,
    check_fn: Callable[[], Coroutine[Any, Any, DatabaseStatus]],
) -> DatabaseStatus:
    """Run *check_fn* with monotonic timing; return offline on any exception."""
    t0 = time.monotonic()
    try:
        result = await check_fn()
        result.latency_ms = (time.monotonic() - t0) * 1000
        return result
    except Exception as exc:
        return _make_offline(name, db_type, url, str(exc))


# ---------------------------------------------------------------------------
# Individual health checks (pure logic, no error handling — _timed_check does that)
# ---------------------------------------------------------------------------


async def _probe_neo4j() -> DatabaseStatus:
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        _settings.neo4j_uri,
        auth=(_settings.neo4j_user, _settings.neo4j_password),
        max_connection_lifetime=5,
    )
    async with driver.session() as session:
        result = await session.run(
            "CALL apoc.meta.stats() YIELD nodeCount, relCount, labelCount RETURN nodeCount, relCount, labelCount"
        )
        row = await result.single()
    await driver.close()
    # reason: bare dict local — populated conditionally from apoc.meta.stats() row; the return is assigned into DatabaseStatus.stats (typed dict) so mypy sees Any at the assignment site without narrowing
    stats: dict = {}  # type: ignore
    if row:
        stats = {
            "nodes": row["nodeCount"],
            "relationships": row["relCount"],
            "labels": row["labelCount"],
        }
    return DatabaseStatus(
        name="Neo4j",
        db_type="neo4j",
        url=_settings.neo4j_uri,
        status="online",
        stats=stats,
    )


async def _probe_mongodb() -> DatabaseStatus:
    from motor.motor_asyncio import AsyncIOMotorClient

    # reason: motor.motor_asyncio.AsyncIOMotorClient constructor's overloaded return type is wider than the variable annotation; mypy can't narrow the assignment
    client: AsyncIOMotorClient = AsyncIOMotorClient(_settings.mongodb_uri, serverSelectionTimeoutMS=3000)  # type: ignore
    await client.admin.command("ping")
    db = client[_settings.mongodb_database]
    collections = await db.list_collection_names()
    # reason: bare dict local — entries are int | list count_documents results; mirrors the DatabaseStatus.stats typing gap above
    stats: dict = {"collections": len(collections)}  # type: ignore
    for coll in collections[:6]:
        stats[coll] = await db[coll].count_documents({})
    info = await client.server_info()
    client.close()
    return DatabaseStatus(
        name="MongoDB",
        db_type="mongodb",
        url=_settings.mongodb_uri,
        status="online",
        version=info.get("version"),
        stats=stats,
    )


async def _probe_qdrant() -> DatabaseStatus:
    url = _settings.qdrant_endpoint
    async with httpx.AsyncClient(timeout=4) as http:
        resp = await http.get(f"{url}/collections")
        resp.raise_for_status()
        data = resp.json()
    collections = data.get("result", {}).get("collections", [])
    return DatabaseStatus(
        name="Qdrant",
        db_type="qdrant",
        url=url,
        status="online",
        stats={
            "collections": len(collections),
            "names": [c["name"] for c in collections[:8]],
        },
    )


async def _probe_minio() -> DatabaseStatus:
    raw = _settings.minio_endpoint
    for prefix in ("https://", "http://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    scheme = "https" if _settings.minio_secure else "http"
    url = f"{scheme}://{raw}"
    async with httpx.AsyncClient(timeout=4) as http:
        resp = await http.get(f"{url}/minio/health/live")
        resp.raise_for_status()
    return DatabaseStatus(
        name="MinIO",
        db_type="minio",
        url=url,
        status="online",
        stats={"bucket": _settings.minio_endpoint},
    )


async def _probe_opensearch() -> DatabaseStatus:
    url = _settings.opensearch_url
    async with httpx.AsyncClient(timeout=4) as http:
        resp = await http.get(url)
        resp.raise_for_status()
        data = resp.json()
    return DatabaseStatus(
        name="OpenSearch",
        db_type="opensearch",
        url=url,
        status="online",
        version=data.get("version", {}).get("number"),
        stats={"cluster_name": data.get("cluster_name", "")},
    )


# ---------------------------------------------------------------------------
# Registry — single source of truth for all probes
# ---------------------------------------------------------------------------

_PROBES: dict[str, tuple[str, str, Callable[[], Coroutine[Any, Any, DatabaseStatus]]]] = {
    "neo4j": ("Neo4j", _settings.neo4j_uri, _probe_neo4j),
    "mongodb": ("MongoDB", _settings.mongodb_uri, _probe_mongodb),
    "qdrant": ("Qdrant", _settings.qdrant_endpoint, _probe_qdrant),
    "minio": ("MinIO", "", _probe_minio),  # url built inside probe
    "opensearch": ("OpenSearch", _settings.opensearch_url, _probe_opensearch),
}


async def _check_db(db_type: str) -> DatabaseStatus:
    """Run a single database health check with timing and error handling."""
    name, url, probe_fn = _PROBES[db_type]
    return await _timed_check(name, db_type, url or "<built-in>", probe_fn)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[DatabaseStatus])
async def get_all_status() -> list[DatabaseStatus]:
    results = await asyncio.gather(*[_check_db(key) for key in _PROBES])
    return list(results)


@router.get("/{db_type}", response_model=DatabaseStatus)
async def get_db_status(db_type: str) -> DatabaseStatus:
    if db_type not in _PROBES:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Unknown db: {db_type}")
    return await _check_db(db_type)
