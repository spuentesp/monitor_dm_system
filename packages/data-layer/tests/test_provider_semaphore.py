"""Provider-aware concurrency budget tests.

Verify that the shared :class:`ProviderSemaphoreRegistry` enforces a
single global cap on simultaneous embed calls, regardless of how many
``Embedder`` instances share a provider.
"""

from __future__ import annotations

import asyncio

import pytest

from monitor_data.llm import provider_semaphore as ps


@pytest.fixture(autouse=True)
def _reset_singleton():
    ps.reset_for_tests()
    yield
    ps.reset_for_tests()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_default_cap_is_eight():
    reg = ps.ProviderSemaphoreRegistry()
    assert reg._max == 8, "default cap must be 8"


def test_get_creates_semaphore_lazily():
    reg = ps.ProviderSemaphoreRegistry(max_per_provider=3)
    sem = reg.get("ollama")
    assert isinstance(sem, asyncio.Semaphore)
    # Same provider returns same semaphore (shared across callers).
    assert reg.get("ollama") is sem
    # Different provider gets a different semaphore.
    assert reg.get("openai") is not sem


def test_cap_holds_under_simulated_concurrent_load():
    """Three "jobs", each firing 3 calls in parallel against a
    provider with cap=2 — at any instant, no more than 2 calls are
    simultaneously in flight.
    """
    reg = ps.ProviderSemaphoreRegistry(max_per_provider=2)
    simultaneous: list[int] = []
    active_now = 0
    lock = asyncio.Lock()

    async def _fake_embed_call(job_id: int, call_id: int) -> None:
        nonlocal active_now
        sem = reg.get("ollama")
        async with sem:
            async with lock:
                active_now += 1
                simultaneous.append(active_now)
            await asyncio.sleep(0.05)
            async with lock:
                active_now -= 1

    async def _go():
        # Run all "calls" — 3 jobs × 3 calls = 9 simultaneous attempts.
        coros = [_fake_embed_call(job, call) for job in range(3) for call in range(3)]
        await asyncio.gather(*coros)

    _run(_go())

    # Peak in-flight count never exceeded cap=2.
    assert max(simultaneous) <= 2, f"cap violated: peak={max(simultaneous)}"
    # Every call actually ran.
    assert len(simultaneous) == 9
    # We did observe cap utilisation (otherwise this test is a no-op).
    assert max(simultaneous) >= 2


def test_reset_for_tests_clears_state():
    """Singleton reset severs all provider mappings so the next call
    builds a fresh semaphore with the current settings."""
    reg = ps.get_provider_semaphore_registry()
    sem_before = reg.get("ollama")
    ps.reset_for_tests()
    sem_after = reg.get("ollama")
    # After reset_for_tests, get_provider_semaphore_registry() rebuilds
    # the registry; sem_after is from a fresh registry instance.
    assert sem_after is not sem_before
