"""Durable extraction state: an append-only log, reduced to the state of each unit.

Progress is tracked per sentence or table instead of per window or per run. That makes every
operation idempotent. Whatever crashed, whichever parts ran and in whatever order, the next
run reads the log, works out what's still missing, and does only that.

The log is the only source of truth, and nothing is ever rewritten. A process killed mid-write
leaves at most one torn last line, which is ignored and redone.
"""

from __future__ import annotations

import fcntl
import os
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import structlog
from pydantic import ValidationError

from monitor_agents.book_decomposition.pipeline import WindowOutcome

log = structlog.get_logger()

DEFAULT_QUARANTINE_AFTER = 3
_CONTENT_FAILURES = ("AdapterParseError", "ValidationError", "TruncatedOutput")


class LogBusy(Exception):
    """Another process is already working on this book."""


class ExtractionLog:
    """An append-only JSONL file of window outcomes."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, outcome: WindowOutcome) -> None:
        """Write one outcome and force it to disk before returning."""
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(outcome.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read(self) -> list[WindowOutcome]:
        """Read every intact outcome, ignoring a torn line left by a crash."""
        if not self.path.exists():
            return []
        outcomes: list[WindowOutcome] = []
        torn = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                outcomes.append(WindowOutcome.model_validate_json(line))
            except ValidationError:
                torn += 1
        if torn:
            log.warning("extraction_log_torn_lines", count=torn, path=str(self.path))
        return outcomes

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Stop two runs from paying for the same work.

        The operating system drops the lock when a process dies, so a crash can't leave
        a stale lock behind.
        """
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("w") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise LogBusy(f"Another run is using {self.path.name}") from exc
            yield


@dataclass(frozen=True)
class UnitStates:
    """Where every expected unit stands."""

    done: frozenset[str]
    pending: frozenset[str]
    quarantined: frozenset[str]

    @property
    def is_settled(self) -> bool:
        """True when nothing is left to try."""
        return not self.pending


def _counts_against_content(outcome: WindowOutcome) -> bool:
    """True when a failure says something about the text, as opposed to the provider.

    A network failure or outage says nothing about a sentence, so it must never quarantine one.
    """
    return all(error.startswith(_CONTENT_FAILURES) for error in outcome.errors)


def reconcile(
    expected: Iterable[str],
    outcomes: Iterable[WindowOutcome],
    *,
    quarantine_after: int = DEFAULT_QUARANTINE_AFTER,
    retry_quarantined: bool = False,
) -> UnitStates:
    """Work out each unit's state purely from the log.

    A unit with any recorded outcome is done, even if a later retry failed. A unit that keeps
    failing for content reasons gets quarantined, so it can't block the rest of the book.
    """
    expected_ids = frozenset(expected)
    done: set[str] = set()
    failures: Counter[str] = Counter()
    for outcome in outcomes:
        done.update(outcome.cited)
        done.update(outcome.skipped)
        if _counts_against_content(outcome):
            failures.update(outcome.uncovered)
    finished = frozenset(done & expected_ids)
    quarantined: frozenset[str] = frozenset()
    if not retry_quarantined:
        quarantined = frozenset(unit for unit in expected_ids - finished if failures[unit] >= quarantine_after)
    return UnitStates(finished, expected_ids - finished - quarantined, quarantined)
