"""Stale-job watchdog.

Polls ``ingestion_jobs`` on a fixed interval (default 60 s) and
fails any job that has been in ``status=running`` with no
``stage_last_progress_at`` advance for longer than the configured
threshold (default 45 min).

Disabled by default — operators opt in via
``MONITOR_INGEST_WATCHDOG_ENABLED=1``. The watchdog is intentionally
non-destructive outside its scope: it only mutates ``ingestion_jobs``
status, nothing else.

LAYER: layer 3 (ui/backend; reachable from app startup hooks; reads
from data-layer MongoDB).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


# Default config — overridable via env. Values mirror the analyst-facing
# 45-min ceiling on a single ingestion stage.
_DEFAULT_STALE_AFTER_SECONDS = int(os.environ.get("MONITOR_INGEST_STALE_AFTER_SECONDS", str(45 * 60)))
_DEFAULT_INTERVAL_SECONDS = float(os.environ.get("MONITOR_INGEST_WATCHDOG_INTERVAL_SECONDS", "60"))


@dataclass
class WatchdogTickResult:
    """Counters for one watchdog cycle."""

    scanned: int = 0
    failed: int = 0
    skipped: int = 0

    # reason: bare dict return annotation on a frozen dataclass as_dict helper; caller is the FastAPI health endpoint which iterates the dict and stringifies — narrow to dict[str, int] in a follow-up
    def as_dict(self) -> dict:  # type: ignore
        return {
            "scanned": self.scanned,
            "failed": self.failed,
            "skipped": self.skipped,
        }


class StaleJobWatchdog:
    """Async-cooperative loop that fails stale ``running`` jobs.

    Construct with the application's MongoDB collection accessor so the
    watchdog stays Mongo-client-agnostic.

    Usage::

        wd = StaleJobWatchdog(collection=get_collection_callable)
        await wd.start()  # spawns a background task
        ...
        await wd.stop()   # graceful shutdown

    The watchdog never raises; runtime errors are logged at WARNING and
    do not crash the host app.
    """

    # reason: bare __init__ — get_collection is a dynamic-dispatch Callable[[], Any] passed by the FastAPI lifespan hook (see main.py:_get_collection); narrow the parameter type to Callable[[], AsyncIOMotorCollection] once the consumer contract is published
    def __init__(  # type: ignore
        self,
        *,
        get_collection,
        stale_after_seconds: int = _DEFAULT_STALE_AFTER_SECONDS,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._get_collection = get_collection
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._interval = interval_seconds
        # reason: bare asyncio.Task[None] | None annotation — the task body returns coroutine[None]; narrow to asyncio.Task[None] in a follow-up after the watchdog body is typed
        self._task: asyncio.Task | None = None  # type: ignore
        self._stop_event = asyncio.Event()
        self._last_result = WatchdogTickResult()

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Spawn the background tick loop."""
        if self.is_running():
            logger.info("StaleJobWatchdog already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="stale-job-watchdog")
        logger.info(
            "StaleJobWatchdog started: stale_after=%ds, interval=%.1fs",
            self._stale_after.total_seconds(),
            self._interval,
        )

    async def stop(self, timeout: float = 5.0) -> None:
        """Stop the loop gracefully and wait up to ``timeout`` seconds."""
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except TimeoutError:
            self._task.cancel()
        finally:
            self._task = None

    def last_result(self) -> WatchdogTickResult:
        return self._last_result

    async def tick_once(self) -> WatchdogTickResult:
        """One watchdog pass — exposed for unit tests and the
        ``monitor ingest doctor`` CLI invocation path."""
        # reason: in-function lazy import of IngestionStatus to break a circular import between watchdog and the data-layer schema module; suppress until the dependency is restructured
        from monitor_data.schemas.ingestion_jobs import IngestionStatus  # type: ignore

        result = WatchdogTickResult()
        try:
            coll = self._get_collection()
        except Exception as exc:
            logger.warning("StaleJobWatchdog: cannot reach Mongo: %s", exc)
            return result

        cutoff = datetime.now(UTC) - self._stale_after
        running_filter = {"status": IngestionStatus.RUNNING.value}
        try:
            cursor = coll.find(running_filter)
            stale = []
            for doc in cursor:
                # If no stage_last_progress_at, default to started_at.
                last_progress = doc.get("stage_last_progress_at") or doc.get("started_at")
                if last_progress is None:
                    continue
                # Mongo returns naive datetimes; coerce to UTC-aware.
                if last_progress.tzinfo is None:
                    last_progress = last_progress.replace(tzinfo=UTC)
                if last_progress < cutoff:
                    stale.append(doc)
        except Exception as exc:
            logger.warning("StaleJobWatchdog: query failed: %s", exc)
            return result

        result.scanned = len(stale)

        now = datetime.now(UTC)
        stale_min = self._stale_after.total_seconds() / 60
        for doc in stale:
            try:
                # CAS guard: only flip if still running. Concurrency-safe.
                # Read-modify-write on errors[] because $push on an
                # absent path creates it.
                existing_errors = doc.get("errors") or []
                new_errors = list(existing_errors) + [f"watchdog: stale after {stale_min:.0f} min"]
                update_filter = {
                    "_id": doc["_id"],
                    "status": IngestionStatus.RUNNING.value,
                }
                update_doc = {
                    "$set": {
                        "status": IngestionStatus.FAILED.value,
                        "completed_at": now,
                        "kill_reason": "watchdog.timeout",
                        "last_error": {
                            "category": "timeout",
                            "message": (f"No stage progress in {stale_min:.0f} min — failed by watchdog."),
                            "failed_at": now,
                            "detail": (
                                "Stale-job watchdog flipped status=running → "
                                "status=failed after the configured threshold "
                                "elapsed without stage_last_progress_at advance."
                            ),
                        },
                        "errors": new_errors,
                    },
                }
                coll.update_one(update_filter, update_doc)
                result.failed += 1
            except Exception as exc:
                logger.warning(
                    "StaleJobWatchdog: could not fail stale job %s: %s",
                    doc.get("job_id") or doc.get("_id"),
                    exc,
                )

        self._last_result = result
        if result.failed:
            logger.warning(
                "StaleJobWatchdog tick: %d jobs failed (stale=%ds)",
                result.failed,
                self._stale_after.total_seconds(),
            )
        return result

    async def _run(self) -> None:
        """Background loop: tick, sleep, repeat."""
        while not self._stop_event.is_set():
            try:
                await self.tick_once()
            except Exception as exc:
                logger.warning("StaleJobWatchdog: tick error: %s", exc)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)


# Process-singleton — one watchdog per uvicorn worker.
_instance: StaleJobWatchdog | None = None


def set_watchdog(instance: StaleJobWatchdog) -> None:
    """Install the watchdog singleton (called from app startup)."""
    global _instance
    _instance = instance


def get_watchdog() -> StaleJobWatchdog | None:
    return _instance


def reset_watchdog() -> None:
    """Drop the singleton (test seam)."""
    global _instance
    _instance = None


__all__ = ["StaleJobWatchdog", "WatchdogTickResult", "get_watchdog", "set_watchdog"]
