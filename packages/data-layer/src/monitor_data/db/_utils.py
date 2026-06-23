"""
Shared utilities for MONITOR db clients.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (tenacity), monitor_data.config

Two things every db client needs but should not define individually:

1. DB_RETRY — Tenacity retry policy (identical across neo4j, mongodb, qdrant, minio).
   PostgreSQL uses a narrower exception filter and is handled locally there.

2. run_sync — bridges async driver calls into synchronous tool functions.
   All MCP tool functions are ``def`` (not ``async def``) so they work as MCP
   tools and can be called from FastAPI handlers without ``await``.  A single
   shared background event loop (one daemon thread) handles the delegation for
   all three async clients (Neo4j, MongoDB, Qdrant).
"""

import asyncio
import threading
from collections.abc import Awaitable, Coroutine
from typing import Any, Optional, cast

from tenacity import (
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitor_data.config import settings

# ---------------------------------------------------------------------------
# Retry policy — shared by neo4j, mongodb, qdrant, minio
# ---------------------------------------------------------------------------

DB_RETRY: dict[str, Any] = dict(
    stop=stop_after_attempt(settings.db_retry_attempts),
    wait=wait_exponential(
        multiplier=1,
        min=settings.db_retry_min_wait,
        max=settings.db_retry_max_wait,
    ),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)

# ---------------------------------------------------------------------------
# Shared background event loop for sync → async bridging
# ---------------------------------------------------------------------------
# One daemon thread runs a persistent asyncio event loop.  All three async
# clients (Neo4j, MongoDB, Qdrant) submit coroutines to this loop via
# ``asyncio.run_coroutine_threadsafe``, which is thread-safe.  Using a single
# loop (rather than one-per-client) reduces thread count and keeps scheduling
# predictable.
#
# DEADLOCK GUARD: if a coroutine already running on the background loop calls
# a sync tool function that calls run_sync() again, blocking the loop thread
# on its own loop would freeze the process forever.  Nested calls are detected
# and dispatched to a one-off overflow loop on a fresh thread instead.

_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_bg_thread: Optional[threading.Thread] = None
_bg_lock = threading.Lock()


def _get_background_loop() -> asyncio.AbstractEventLoop:
    """Return the shared running background event loop, creating it on first call."""
    global _bg_loop, _bg_thread
    with _bg_lock:
        if _bg_loop is None or not _bg_loop.is_running():
            _bg_loop = asyncio.new_event_loop()
            _bg_thread = threading.Thread(
                target=_bg_loop.run_forever,
                daemon=True,
                name="monitor-db-bg-loop",
            )
            _bg_thread.start()
    return _bg_loop


def _run_on_overflow_thread(coro: Coroutine[Any, Any, Any], timeout: Optional[float]) -> Any:
    """Run ``coro`` on a fresh event loop in a fresh thread (nested-call escape hatch)."""
    result: dict[str, Any] = {}

    def _target() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # propagate to caller
            result["error"] = exc

    t = threading.Thread(target=_target, daemon=True, name="monitor-db-overflow")
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(
            f"run_sync (nested) timed out after {timeout}s — coroutine still running"
        )
    if "error" in result:
        raise result["error"]
    return result.get("value")


def run_sync(coro: Awaitable[Any], timeout: Optional[float] = None) -> Any:
    """Run an async coroutine synchronously (thread-safe, works inside FastAPI).

    ``timeout`` defaults to ``settings.db_sync_timeout`` (seconds; ``0`` means
    wait forever).  A bounded wait turns silent deadlocks/hangs into loud,
    diagnosable TimeoutErrors.
    """
    if timeout is None:
        configured = getattr(settings, "db_sync_timeout", 120.0)
        timeout = None if not configured else float(configured)

    c = cast(Coroutine[Any, Any, Any], coro)
    loop = _get_background_loop()

    # Nested call from the background loop thread itself → overflow thread.
    if threading.current_thread() is _bg_thread:
        return _run_on_overflow_thread(c, timeout)

    future = asyncio.run_coroutine_threadsafe(c, loop)
    try:
        return future.result(timeout)
    except TimeoutError:
        future.cancel()
        raise TimeoutError(
            f"run_sync timed out after {timeout}s waiting on {getattr(c, '__qualname__', c)!r}"
        ) from None
