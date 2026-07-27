"""Provider-aware concurrency budget.

A single in-flight cap per LLM provider (``MONITOR_LLM_MAX_CONCURRENT_PER_PROVIDER``)
shared across ALL jobs, all ingestion workers, and all CLI invocations that
live in the same process.

Pre-2026-07-23: each analyzer batch had its own ``asyncio.Semaphore(8)``, so
two concurrent ingestion jobs against the same Ollama host would issue
2 × 8 = 16 simultaneous embedding/chat requests. Ollama serializes them
internally to its model-level concurrency limit and reports transient
"model loading" / "queue full" errors. The fix is one cross-process
budget per provider so 8 stays 8 whether one job runs or ten do.

Module-level state is intentional. The class is process-singleton; tests
that need an isolated budget call :func:`reset_for_tests`.

LAYER: 1 (data-layer)
IMPORTS FROM: stdlib only
"""

from __future__ import annotations

import asyncio

from monitor_data.config import settings


class ProviderSemaphoreRegistry:
    """Lazy ``provider_name → asyncio.Semaphore`` map.

    The semaphore value is fixed at construction (read from settings);
    adding providers later inherits the same cap. We use
    :class:`asyncio.Semaphore` (not ``BoundedSemaphore``) because the
    only invariant is the upper bound on simultaneous calls.
    """

    def __init__(self, max_per_provider: int | None = None) -> None:
        self._max = max_per_provider or int(settings.monitor_llm_max_concurrent_per_provider)
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def get(self, provider: str) -> asyncio.Semaphore:
        """Return the semaphore for ``provider``, creating it on first use.

        The cap is shared across all callers (jobs, workers, CLI).
        """
        sem = self._semaphores.get(provider)
        if sem is None:
            sem = asyncio.Semaphore(self._max)
            self._semaphores[provider] = sem
        return sem

    async def acquire(self, provider: str) -> None:
        await self.get(provider).acquire()

    def release(self, provider: str) -> None:
        sem = self._semaphores.get(provider)
        if sem is not None:
            sem.release()

    def reset_for_tests(self) -> None:
        """Drop all cached semaphores. Tests only."""
        self._semaphores.clear()


# Process-singleton — there is no scenario in production where we
# want a second, separately-budgeted instance.
_singleton: ProviderSemaphoreRegistry | None = None


def get_provider_semaphore_registry() -> ProviderSemaphoreRegistry:
    """Return the process-wide :class:`ProviderSemaphoreRegistry`."""
    global _singleton
    if _singleton is None:
        _singleton = ProviderSemaphoreRegistry()
    return _singleton


def reset_for_tests() -> None:
    """Drop the singleton (test seam)."""
    global _singleton
    if _singleton is not None:
        _singleton.reset_for_tests()
    _singleton = None


__all__ = [
    "ProviderSemaphoreRegistry",
    "get_provider_semaphore_registry",
    "reset_for_tests",
]
