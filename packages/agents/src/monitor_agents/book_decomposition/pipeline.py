"""Run extraction over every window, validate it, and report coverage.

The model's answer is never taken on trust. Code checks that every unit was accounted for,
retries only what's missing, and reports anything still uncovered instead of hiding it.
Each finished window goes to `on_outcome` immediately, so a crash loses only in-flight work.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter, deque
from collections.abc import Callable, Iterable

import structlog
from monitor_data.schemas.book_graph import AtomKind, ExtractedAtom, WindowExtraction
from pydantic import BaseModel, Field

from monitor_agents.book_decomposition.extractor import (
    CONTENT_ERRORS,
    WindowExtractor,
    failed_call_usage,
)
from monitor_agents.book_decomposition.pacing import GuardedExtractor, RunGuard, RunStopped
from monitor_agents.book_decomposition.windows import Window

log = structlog.get_logger()

DEFAULT_CONCURRENCY = 8
DEFAULT_MAX_ATTEMPTS = 2


class ProvenancedAtom(BaseModel):
    """A validated atom whose citations are resolved to book-tree node IDs."""

    atom: ExtractedAtom
    source_node_ids: list[str]
    page: int


class WindowOutcome(BaseModel):
    """The validated result for one window. Written to the checkpoint as one JSON line."""

    window_id: str
    run_key: str = Field("", description="The model and prompt version that produced this")
    atoms: list[ProvenancedAtom] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict, description="Node ID → skip reason")
    cited: list[str] = Field(default_factory=list, description="Node IDs cited by an atom")
    uncovered: list[str] = Field(default_factory=list, description="Node IDs with no outcome")
    dropped_atoms: int = Field(0, description="Atoms rejected for bad citations or fields")
    attempts: int = 0
    errors: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


def _atom_is_well_formed(atom: ExtractedAtom) -> bool:
    if not atom.statement.strip():
        return False
    if atom.kind == AtomKind.ENTITY:
        return bool(atom.name and atom.name.strip())
    if atom.kind == AtomKind.RELATIONSHIP:
        return bool(atom.subject and atom.predicate and atom.object)
    return True


def validate_extraction(window: Window, extraction: WindowExtraction) -> WindowOutcome:
    """Resolve citations to node IDs and find units that have no outcome."""
    by_label = {unit.label: unit for unit in window.units}
    outcome = WindowOutcome(window_id=window.id)
    cited: set[str] = set()
    for atom in extraction.atoms:
        units = [by_label[label] for label in atom.cites if label in by_label]
        if not units or len(units) != len(atom.cites) or not _atom_is_well_formed(atom):
            # A citation to a unit that doesn't exist means the claim can't be traced.
            outcome.dropped_atoms += 1
            continue
        outcome.atoms.append(
            ProvenancedAtom(
                atom=atom,
                source_node_ids=[unit.node_id for unit in units],
                page=units[0].page,
            )
        )
        cited.update(unit.label for unit in units)
    for skip in extraction.skips:
        if skip.label in by_label and skip.label not in cited:
            outcome.skipped[by_label[skip.label].node_id] = skip.reason.value
    skipped_ids = set(outcome.skipped)
    outcome.cited = [by_label[label].node_id for label in sorted(cited)]
    outcome.uncovered = [
        unit.node_id for unit in window.units if unit.label not in cited and unit.node_id not in skipped_ids
    ]
    return outcome


async def _run_window(window: Window, extractor: WindowExtractor, max_attempts: int) -> WindowOutcome:
    """Run a window until every unit has an outcome or the attempts run out.

    Unparseable output usually means the answer outgrew the token limit, and repeating the
    request would just hit DSPy's cache. So those failures split the units in half. Other
    failures, such as provider errors, retry the same units.
    """
    outcome = WindowOutcome(window_id=window.id)
    started = time.monotonic()
    accounted: set[str] = set()
    queue: deque[tuple[Window, int]] = deque([(window, 0)])
    while queue:
        part, used = queue.popleft()
        outcome.attempts += 1
        try:
            result = await extractor(part)
        except RunStopped as exc:
            # Keep what this window has so far: finished units stay done, and the rest are
            # picked up on resume. The failure that caused the stop may still have cost tokens.
            outcome.attempts -= 1
            _add_failed_usage(outcome, exc.__context__)
            break
        except CONTENT_ERRORS as exc:
            _record_failure(outcome, window, exc)
            labels = [unit.label for unit in part.units]
            if len(labels) > 1:
                middle = len(labels) // 2
                queue.append((part.restricted_to(set(labels[:middle])), 0))
                queue.append((part.restricted_to(set(labels[middle:])), 0))
            continue
        # Any provider failure leaves these units uncovered and in the report.
        except Exception as exc:  # noqa: BLE001  # reason: failure is recorded on the outcome, never swallowed
            _record_failure(outcome, window, exc)
            if used + 1 < max_attempts:
                queue.append((part, used + 1))
            continue
        outcome.input_tokens += result.input_tokens
        outcome.output_tokens += result.output_tokens
        validated = validate_extraction(part, result.extraction)
        outcome.atoms.extend(validated.atoms)
        outcome.skipped.update(validated.skipped)
        outcome.cited.extend(validated.cited)
        outcome.dropped_atoms += validated.dropped_atoms
        accounted.update(validated.cited, validated.skipped)
        if validated.uncovered and used + 1 < max_attempts:
            missing = set(validated.uncovered)
            labels_left = {unit.label for unit in part.units if unit.node_id in missing}
            queue.append((part.restricted_to(labels_left), used + 1))
    outcome.uncovered = [unit.node_id for unit in window.units if unit.node_id not in accounted]
    outcome.seconds = round(time.monotonic() - started, 3)
    return outcome


def _add_failed_usage(outcome: WindowOutcome, exc: BaseException | None) -> None:
    input_tokens, output_tokens = failed_call_usage(exc)
    outcome.input_tokens += input_tokens
    outcome.output_tokens += output_tokens


def _record_failure(outcome: WindowOutcome, window: Window, exc: Exception) -> None:
    _add_failed_usage(outcome, exc)
    log.warning("book_window_failed", window_id=window.id, error=str(exc)[:300])
    outcome.errors.append(f"{type(exc).__name__}: {exc}"[:300])


async def extract_windows(
    windows: Iterable[Window],
    extractor: WindowExtractor,
    *,
    on_outcome: Callable[[WindowOutcome], None] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    guard: RunGuard | None = None,
) -> list[WindowOutcome]:
    """Extract every window concurrently. Output order matches input order.

    With a guard, the run can stop early. Windows it never reached come back with all of
    their units uncovered, and on_outcome isn't called for them.
    """
    window_list = list(windows)
    if guard is not None:
        extractor = GuardedExtractor(extractor, guard)
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(window: Window) -> WindowOutcome:
        async with semaphore:
            if guard is not None and guard.stopped:
                return WindowOutcome(window_id=window.id, uncovered=[unit.node_id for unit in window.units])
            outcome = await _run_window(window, extractor, max_attempts)
        if on_outcome is not None and outcome.attempts:
            on_outcome(outcome)
        return outcome

    return list(await asyncio.gather(*(run_one(window) for window in window_list)))


class CoverageReport(BaseModel):
    """What happened to every unit in the windows that were attempted."""

    windows_total: int = 0
    windows_incomplete: int = 0
    units_total: int = 0
    units_cited: int = 0
    units_skipped: dict[str, int] = Field(default_factory=dict)
    units_uncovered: int = 0
    atoms_by_kind: dict[str, int] = Field(default_factory=dict)
    atoms_dropped: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds_total: float = 0.0

    @property
    def coverage(self) -> float:
        """Share of units with a recorded outcome."""
        if not self.units_total:
            return 1.0
        return (self.units_total - self.units_uncovered) / self.units_total


def build_coverage_report(windows: list[Window], outcomes: list[WindowOutcome]) -> CoverageReport:
    """Build the report from outcomes, counting against the units that should exist."""
    skipped: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    cited: set[str] = set()
    skipped_ids: set[str] = set()
    report = CoverageReport(windows_total=len(windows), units_total=sum(len(w.units) for w in windows))
    for outcome in outcomes:
        cited.update(outcome.cited)
        for node_id, reason in outcome.skipped.items():
            if node_id not in skipped_ids:
                skipped_ids.add(node_id)
                skipped[reason] += 1
        kinds.update(item.atom.kind.value for item in outcome.atoms)
        report.atoms_dropped += outcome.dropped_atoms
        report.windows_incomplete += bool(outcome.uncovered)
        report.input_tokens += outcome.input_tokens
        report.output_tokens += outcome.output_tokens
        report.seconds_total += outcome.seconds
    expected = {unit.node_id for window in windows for unit in window.units}
    report.units_cited = len(cited & expected)
    report.units_skipped = dict(skipped)
    report.units_uncovered = len(expected - cited - skipped_ids)
    report.atoms_by_kind = dict(kinds)
    report.seconds_total = round(report.seconds_total, 3)
    return report
