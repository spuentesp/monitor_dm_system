"""The self-healing loop: reconcile, do what's missing, repeat until settled.

Each failure has its own recovery, so a run ends in only three ways:
- COMPLETE: every unit has an outcome.
- COMPLETE_WITH_QUARANTINE: every unit that can be processed has an outcome, and the ones that
  can't are listed for a person.
- PAUSED: the run hit quota, a budget or a persistent outage. Running again continues from here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, replace
from enum import StrEnum
import asyncio

import structlog

from monitor_agents.book_decomposition.extractor import WindowExtractor
from monitor_agents.book_decomposition.ledger import ExtractionLog, UnitStates, reconcile
from monitor_agents.book_decomposition.pacing import RunGuard, StopKind
from monitor_agents.book_decomposition.pipeline import extract_windows
from monitor_agents.book_decomposition.windows import Window, window_id

log = structlog.get_logger()

DEFAULT_MAX_ROUNDS = 6
_ROUND_BACKOFF_SECONDS = 30.0
_QUOTA_WAIT_SECONDS = 300.0
_MAX_QUOTA_WAIT_SECONDS = 1800.0


class IngestStatus(StrEnum):
    COMPLETE = "complete"
    COMPLETE_WITH_QUARANTINE = "complete_with_quarantine"
    PAUSED = "paused"


@dataclass(frozen=True)
class IngestResult:
    status: IngestStatus
    states: UnitStates
    rounds: int
    pause_reason: str | None = None


def plan_windows(windows: Collection[Window], pending: Collection[str]) -> list[Window]:
    """Narrow windows to units still pending. A fully done window drops out entirely."""
    planned: list[Window] = []
    for window in windows:
        units = tuple(unit for unit in window.units if unit.node_id in pending)
        if units:
            planned.append(replace(window, id=window_id(units), units=units))
    return planned


async def run_until_settled(
    windows: Collection[Window],
    extractor: WindowExtractor,
    extraction_log: ExtractionLog,
    guard: RunGuard,
    *,
    run_key: str = "",
    accept_run: Callable[[str], bool] = lambda _: True,
    concurrency: int = 4,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    wait_for_quota_seconds: float = 0.0,
    retry_quarantined: bool = False,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> IngestResult:
    """Process the given windows, which can be any part of a book, until nothing is left to try.

    Safe to call repeatedly and on overlapping parts: work already in the log is never redone.
    """
    expected = {unit.node_id for window in windows for unit in window.units}
    quota_wait_left = wait_for_quota_seconds
    quota_wait = _QUOTA_WAIT_SECONDS
    rounds = 0

    def current() -> UnitStates:
        accepted = [o for o in extraction_log.read() if accept_run(o.run_key)]
        return reconcile(expected, accepted, retry_quarantined=retry_quarantined)

    def on_outcome(outcome) -> None:  # type: ignore[no-untyped-def]  # reason: WindowOutcome is implied by extract_windows
        extraction_log.append(outcome.model_copy(update={"run_key": run_key}))

    states = current()
    while states.pending and rounds < max_rounds:
        rounds += 1
        before = len(states.pending)
        log.info("book_round_started", round=rounds, pending=before)
        await extract_windows(
            plan_windows(windows, states.pending),
            extractor,
            concurrency=concurrency,
            guard=guard,
            on_outcome=on_outcome,
        )
        retry_quarantined = False  # One fresh try per run is enough.
        states = current()

        if guard.stop_kind == StopKind.QUOTA and quota_wait_left > 0 and states.pending:
            pause = min(quota_wait, quota_wait_left)
            log.warning("book_run_waiting_for_quota", seconds=pause)
            await sleep(pause)
            quota_wait_left -= pause
            quota_wait = min(quota_wait * 2, _MAX_QUOTA_WAIT_SECONDS)
            guard.resume()
            rounds -= 1  # Waiting for quota isn't a failed attempt.
            continue
        if guard.stopped:
            return IngestResult(IngestStatus.PAUSED, states, rounds, guard.stopped_reason)
        if len(states.pending) == before and states.pending:
            # No progress at all, so more immediate tries would only spend money.
            await sleep(_ROUND_BACKOFF_SECONDS * rounds)

    if states.pending:
        reason = f"Units still pending after {rounds} rounds"
        return IngestResult(IngestStatus.PAUSED, states, rounds, reason)
    status = IngestStatus.COMPLETE_WITH_QUARANTINE if states.quarantined else IngestStatus.COMPLETE
    return IngestResult(status, states, rounds)
