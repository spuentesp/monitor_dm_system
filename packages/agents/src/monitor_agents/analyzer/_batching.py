"""Word-budget batches that are verified complete before they are accepted (I-17, I-2).

Three failure modes can lose content in one model call:

* a provider refusal — handled by ``monitor_agents.book_batching`` (Part C),
  which halves the batch and retries each half once;
* a reply cut off at the output cap — it no longer parses, so nothing usable
  comes back;
* a reply that parses but does not cover every section it was sent — the model
  quietly dropped part of the batch.

This module plans batches by a word budget, composes with the refusal helper,
and guarantees coverage: a call whose reply fails to cover its units is split
and the uncovered units are retried, recursively down to one unit. A unit whose
dedicated reply still does not cover it comes back as a held item with its id
and the reason — never silently dropped.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from monitor_agents.book_batching import HeldItem, run_batch_with_refusal_split

T = TypeVar("T")
R = TypeVar("R")

_REASON_LIMIT = 300


@dataclass(slots=True)
class BatchRun(Generic[R]):
    """What a coverage-verified run produced."""

    results: list[R] = field(default_factory=list)
    held: list[HeldItem] = field(default_factory=list)
    calls: int = 0  # model-call attempts made (including refused ones)


def plan_word_batches(
    items: Sequence[T],
    *,
    words_of: Callable[[T], int],
    max_words: int,
    max_sections: int,
) -> list[list[T]]:
    """Group items so each batch stays within ``max_words`` and ``max_sections``.

    An item longer than ``max_words`` still travels alone: sections are atomic,
    and splitting one would lose its heading path. With ``max_words`` set very
    high and ``max_sections=2`` this reproduces the pre-phase fixed-size
    batching exactly.
    """
    batches: list[list[T]] = []
    current: list[T] = []
    words = 0
    for item in items:
        size = max(0, words_of(item))
        if current and (words + size > max_words or len(current) >= max_sections):
            batches.append(current)
            current, words = [], 0
        current.append(item)
        words += size
    if current:
        batches.append(current)
    return batches


def is_parse_failure(exc: BaseException) -> bool:
    """True for a reply the adapter could not parse (usually cut off at the cap).

    Same test ``analyzer._call_module`` uses before its one parse retry, so a
    truncation that survives that retry reaches the split logic here.
    """
    msg = f"{type(exc).__name__}: {exc}".lower()
    return "adapterparseerror" in msg or "failed to parse" in msg


def sections_covered(result: object, units: Sequence[T], *, id_of: Callable[[T], str]) -> list[T]:
    """The units the reply's ``sections_covered`` list names, in ``units`` order.

    A result that carries no coverage list at all is trusted (a test double, or
    a signature that does not declare one; real analyzer batches run through
    signatures that declare ``sections_covered``, where a reply missing the
    field is a parse error long before it reaches this code). An empty list
    covers nothing.
    """
    if not hasattr(result, "sections_covered"):
        return list(units)
    claimed = getattr(result, "sections_covered") or []
    seen = {str(entry).strip().casefold() for entry in claimed}
    return [unit for unit in units if id_of(unit).strip().casefold() in seen]


def _reason(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:_REASON_LIMIT]


async def run_covered_batch(
    items: Sequence[T],
    run: Callable[[Sequence[T]], Awaitable[R]],
    *,
    id_of: Callable[[T], str],
    covered_by: Callable[[R, Sequence[T]], Sequence[T]] | None = None,
) -> BatchRun[R]:
    """Run ``items`` through ``run`` until every unit is covered or held.

    Refusals split via the shared Part C helper (each half retried once);
    parse failures and uncovered units split here and retry only what is
    missing. Non-refusal, non-parse errors propagate to the caller — the
    caller records them as failures for the whole batch. An empty item list
    is not run at all.
    """
    cover = covered_by or (lambda result, units: sections_covered(result, units, id_of=id_of))
    outcome: BatchRun[R] = BatchRun()
    await _run_into(items, run, covered_by=cover, id_of=id_of, out=outcome)
    return outcome


async def _run_into(
    items: Sequence[T],
    run: Callable[[Sequence[T]], Awaitable[R]],
    *,
    covered_by: Callable[[R, Sequence[T]], Sequence[T]],
    id_of: Callable[[T], str],
    out: BatchRun[R],
) -> None:
    if not items:
        return

    recorded: list[tuple[list[T], R]] = []

    async def recording_run(sub: Sequence[T]) -> R:
        out.calls += 1
        value = await run(sub)
        recorded.append((list(sub), value))
        return value

    try:
        outcome = await run_batch_with_refusal_split(items, recording_run, id_of=id_of)
    except Exception as exc:  # noqa: BLE001  # reason: classified below; non-split failures re-raise
        if not is_parse_failure(exc):
            raise
        if len(items) == 1:
            out.held.append(HeldItem(id=id_of(items[0]), reason=_reason(exc)))
            return
        mid = len(items) // 2
        await _run_into(items[:mid], run, covered_by=covered_by, id_of=id_of, out=out)
        await _run_into(items[mid:], run, covered_by=covered_by, id_of=id_of, out=out)
        return

    out.held.extend(outcome.held)

    for sub, result in recorded:
        covered = list(covered_by(result, sub))
        uncovered = [unit for unit in sub if unit not in covered]
        if not uncovered:
            out.results.append(result)
            continue
        if len(sub) == 1:
            # A dedicated reply for this one unit still did not cover it: hold
            # the unit with a record and discard the unreliable reply instead
            # of pretending it was complete.
            out.held.append(HeldItem(id=id_of(sub[0]), reason="Reply did not cover this unit (possible truncation)"))
            continue
        # Partial reply: keep it for the units it did cover, retry the rest.
        out.results.append(result)
        await _run_into(uncovered, run, covered_by=covered_by, id_of=id_of, out=out)
