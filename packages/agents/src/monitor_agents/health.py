"""
Layer-2 wrapper around monitor_data.health.

The CLI cannot import monitor_data directly (three-layer rule: cli → agents →
data-layer). This module re-exports the data-layer health probes through the
agents layer so `monitor doctor`, `monitor init`, and any other CLI tool can
read component health without violating the dependency direction.

Reuse: every function delegates to monitor_data.health — no new logic lives
here. The only added value is the `check_all_services()` aggregator, which
calls the per-component probes concurrently and produces a single dict that
the CLI can render as a Rich table.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries
CALLED BY: monitor_cli.commands.doctor, monitor_cli.commands.init
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from monitor_data.health import (
    HealthStatus,
    check_llm_providers,
    check_minio_connectivity,
    check_mongodb_connectivity,
    check_neo4j_connectivity,
    check_postgres_connectivity,
    check_qdrant_connectivity,
    get_health_status,
    is_healthy,
)

logger = logging.getLogger(__name__)

__all__ = [
    "HealthStatus",
    "check_all_services",
    "check_llm_providers",
    "check_minio_connectivity",
    "check_mongodb_connectivity",
    "check_neo4j_connectivity",
    "check_postgres_connectivity",
    "check_qdrant_connectivity",
    "get_health_status",
    "is_healthy",
    "run_health_check_sync",
]


async def check_all_services(*, force: bool = False) -> dict[str, Any]:
    """
    Run every per-component probe and return the aggregated health dict.

    This is a thin async wrapper over `monitor_data.health.get_health_status()`
    — it returns the same shape (`overall_status`, `components`, `version`,
    `timestamp`) and adds `force=False` as a forward-compatible hook so a
    later change can bypass the embedder health cache without breaking callers.

    Args:
        force: Reserved for future use (e.g. bypass caches). Currently has no
            effect — kept in the signature so callers can opt-in once caching
            is added.

    Returns:
        Dict with `overall_status`, `components` (one entry per service),
        `version`, and `timestamp`.

    Examples:
        >>> import asyncio
        >>> status = asyncio.run(check_all_services())
        >>> status['overall_status'] in ('healthy', 'degraded', 'unhealthy')
        True
    """
    # `get_health_status()` already runs every probe; we keep the wrapper so
    # `force` is part of the public signature and so CLI code does not import
    # data-layer modules directly.
    status = await get_health_status()
    if force and status.get("llm"):
        # When force is requested, refresh LLM/embedding probe caches too.
        try:
            from monitor_data.retrieval.embedding_health import (
                get_embedding_health_checker,
            )

            checker = get_embedding_health_checker()
            checker.last_cached_status(force=True)
        except Exception as exc:
            logger.debug("Force-refresh of embedding cache failed: %s", exc)
    return status


def run_health_check_sync(*, force: bool = False) -> dict[str, Any]:
    """
    Synchronous wrapper for callers (Typer commands, shell scripts) that
    cannot `await`. Internally uses `asyncio.run`; do not call from inside
    an existing event loop.

    This is the function `monitor doctor` and `scripts/doctor.sh` should use
    when invoked from sync code paths.
    """
    return asyncio.run(check_all_services(force=force))
