"""
Health check endpoint for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: MCP server (server.py), k8s probes

This module provides health check functionality to verify:
- Server is running
- Database connectivity (Neo4j, MongoDB, Qdrant)
- Server version information
"""

import logging
from datetime import datetime
from typing import Any

from monitor_data.db.minio import get_minio_client
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.db.postgres import get_postgres_client
from monitor_data.db.qdrant import get_qdrant_client

logger = logging.getLogger(__name__)

# Version from package metadata
__version__ = "0.1.0"


class HealthStatus:
    """Health status constants."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


async def check_neo4j_connectivity() -> dict[str, Any]:
    """
    Check Neo4j database connectivity.

    Returns:
        Dict with status and details

    Examples:
        >>> result = await check_neo4j_connectivity()
        >>> result['status']
        'healthy'
    """
    try:
        client = get_neo4j_client()
        is_connected = await client.verify_connectivity()

        if is_connected:
            return {
                "status": HealthStatus.HEALTHY,
                "message": "Neo4j connection established",
            }
        else:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": "Neo4j connection failed",
            }
    except Exception as e:
        logger.error(f"Neo4j health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": f"Neo4j error: {e!s}",
        }


async def check_mongodb_connectivity() -> dict[str, Any]:
    """
    Check MongoDB database connectivity.

    Returns:
        Dict with status and details

    Examples:
        >>> result = await check_mongodb_connectivity()
        >>> result['status']
        'healthy'
    """
    try:
        client = get_mongodb_client()
        is_connected = await client.verify_connectivity()

        if is_connected:
            return {
                "status": HealthStatus.HEALTHY,
                "message": "MongoDB connection established",
            }
        else:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": "MongoDB connection failed",
            }
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": f"MongoDB error: {e!s}",
        }


def check_qdrant_connectivity() -> dict[str, Any]:
    """
    Check Qdrant database connectivity.

    Returns:
        Dict with status and details

    Examples:
        >>> result = check_qdrant_connectivity()
        >>> result['status']
        'healthy'
    """
    try:
        client = get_qdrant_client()
        is_connected = client.verify_connectivity()

        if is_connected:
            return {
                "status": HealthStatus.HEALTHY,
                "message": "Qdrant connection established",
            }
        else:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": "Qdrant connection failed",
            }
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": f"Qdrant error: {e!s}",
        }


async def check_postgres_connectivity() -> dict[str, Any]:
    """
    Check PostgreSQL connectivity (used by llm_providers / model_pairs / worlds).

    Returns:
        Dict with status and details
    """
    try:
        client = get_postgres_client()
        is_connected = await client.verify_connectivity()

        if is_connected:
            return {
                "status": HealthStatus.HEALTHY,
                "message": "PostgreSQL connection established",
            }
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": "PostgreSQL connection failed",
        }
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": f"PostgreSQL error: {e!s}",
        }


async def check_minio_connectivity() -> dict[str, Any]:
    """
    Check MinIO/S3 connectivity (used for file/object storage).

    Returns:
        Dict with status and details
    """
    try:
        client = get_minio_client()
        is_connected = await client.verify_connectivity()

        if is_connected:
            return {
                "status": HealthStatus.HEALTHY,
                "message": "MinIO connection established",
            }
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": "MinIO connection failed",
        }
    except Exception as e:
        logger.error(f"MinIO health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": f"MinIO error: {e!s}",
        }


async def check_llm_providers() -> dict[str, Any]:
    """Surface LLM-provider health on /healthz without 60-second waits.

    Iterates the configured providers in Postgres (``llm_providers``
    table) and reads the most-recent probe result on each row. The
    embedder health checker maintains its own cache (TTL 5 min); we
    reuse that for the *active* embedding pair so this endpoint stays
    cheap.

    Returns ``{"status": "healthy" | "degraded" | "unhealthy",
    "providers": {<name>: {status, detail}}}``.
    """
    out_providers: dict[str, dict[str, Any]] = {}
    try:
        from monitor_data.config import get_settings
        from monitor_data.db.postgres import PostgresClient

        settings = get_settings()
        pg = PostgresClient()
        try:
            rows = await pg.providers_list()
        finally:
            await pg.close()
        for r in rows:
            provider = r.get("provider") or r.get("name") or "unknown"
            status = r.get("status", "unknown")
            out_providers[provider] = {
                "status": status,
                "model": r.get("model"),
                "is_default": bool(r.get("is_default")),
                "last_error": r.get("last_error"),
            }

        # Active embedding pair — pull from EmbeddingHealthChecker cache
        # without forcing a probe (cheap path).
        try:
            from monitor_data.retrieval.embedding_health import (
                get_embedding_health_checker,
            )

            checker = get_embedding_health_checker()
            cached = checker.last_cached_status(force=False)
            if cached is not None:
                out_providers["_embedding_active"] = {
                    "status": "healthy" if cached.healthy else "unhealthy",
                    "model": cached.model,
                    "vector_dim": cached.vector_dim,
                    "detail": cached.detail,
                }
            else:
                out_providers["_embedding_active"] = {
                    "status": "unknown",
                    "model": settings.embedding_model,
                }
        except Exception as exc:
            logger.warning("Embedding health cache unavailable: %s", exc)
            out_providers["_embedding_active"] = {"status": "unknown"}
    except Exception as exc:
        logger.warning("LLM provider health check failed: %s", exc)
        return {
            "status": HealthStatus.UNHEALTHY,
            "providers": out_providers,
            "message": str(exc),
        }

    statuses = [p["status"] for p in out_providers.values()]
    if not statuses or all(s in ("healthy", "connected", "ok", "unknown") for s in statuses):
        overall = HealthStatus.HEALTHY
    elif any(s in ("error", "unhealthy", "down") for s in statuses):
        overall = HealthStatus.DEGRADED
    else:
        overall = HealthStatus.DEGRADED

    return {
        "status": overall,
        "providers": out_providers,
    }


async def get_health_status() -> dict[str, Any]:
    """
    Get comprehensive health status for all components.

    Returns:
        Dict with overall status, component statuses, and metadata

    Examples:
        >>> status = await get_health_status()
        >>> status['overall_status']
        'healthy'
        >>> status['components']['neo4j']['status']
        'healthy'
    """
    # Check all components
    neo4j_health = await check_neo4j_connectivity()
    mongodb_health = await check_mongodb_connectivity()
    qdrant_health = check_qdrant_connectivity()
    postgres_health = await check_postgres_connectivity()
    minio_health = await check_minio_connectivity()
    llm_health = await check_llm_providers()

    components = {
        "neo4j": neo4j_health,
        "mongodb": mongodb_health,
        "qdrant": qdrant_health,
        "postgres": postgres_health,
        "minio": minio_health,
        "llm": llm_health,
    }

    # Determine overall status
    statuses = [comp["status"] for comp in components.values()]

    if all(s == HealthStatus.HEALTHY for s in statuses):
        overall_status = HealthStatus.HEALTHY
    elif all(s == HealthStatus.UNHEALTHY for s in statuses):
        overall_status = HealthStatus.UNHEALTHY
    else:
        overall_status = HealthStatus.DEGRADED

    return {
        "overall_status": overall_status,
        "components": components,
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


async def is_healthy() -> bool:
    """
    Quick health check - returns True if all components are healthy.

    Returns:
        True if healthy, False otherwise

    Examples:
        >>> await is_healthy()
        True
    """
    try:
        status = await get_health_status()
        return bool(status["overall_status"] == HealthStatus.HEALTHY)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False
