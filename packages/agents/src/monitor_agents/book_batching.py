"""Split a refused batch instead of dropping it.

LAYER: 2 (agents)
IMPORTS FROM: monitor_agents.llm_errors
CALLED BY: book_decomposition and analyzer batch loops (Parts A and B wire it)

A provider content refusal kills the whole request, so the fix is a smaller
request: on CONTENT_REFUSED this helper halves the batch and retries each half
exactly once. Anything that still refuses is returned as a held item with its
id and the refusal reason, so no section or claim disappears without a record.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from monitor_agents.llm_errors import LLMErrorClass, classify_llm_error

T = TypeVar("T")
R = TypeVar("R")

_REASON_LIMIT = 300


@dataclass(frozen=True, slots=True)
class HeldItem:
    """One item that could not be processed, with the reason it was held."""

    id: str
    reason: str


@dataclass(frozen=True, slots=True)
class BatchOutcome(Generic[R]):
    """What a batch run produced: one entry in `results` per successful call."""

    results: list[R]
    held: list[HeldItem]


def _reason(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:_REASON_LIMIT]


def _is_refusal(exc: BaseException) -> bool:
    return classify_llm_error(exc).error_class == LLMErrorClass.CONTENT_REFUSED


async def run_batch_with_refusal_split(
    items: Sequence[T],
    run: Callable[[list[T]], Awaitable[R]],
    *,
    id_of: Callable[[T], str],
) -> BatchOutcome[R]:
    """Run `items` through `run`; on CONTENT_REFUSED split in half and retry each half once.

    The refusal is never retried with the same items: a one-item batch is held
    immediately, and each half of a split gets exactly one further attempt. Each
    successful call contributes one entry to `results`, in the order the calls
    succeeded (left half before right half). Items in halves that refuse again are
    returned in `held` with their ids and the refusal reason. Non-refusal failures
    propagate to the caller unchanged. An empty batch is not run at all.
    """
    if not items:
        return BatchOutcome(results=[], held=[])

    try:
        value = await run(list(items))
    except Exception as exc:
        if not _is_refusal(exc):
            raise
        if len(items) == 1:
            return BatchOutcome(results=[], held=[HeldItem(id=id_of(items[0]), reason=_reason(exc))])
        mid = len(items) // 2
        halves = (list(items[:mid]), list(items[mid:]))
        results: list[R] = []
        held: list[HeldItem] = []
        for half in halves:
            try:
                results.append(await run(half))
            except Exception as half_exc:
                if not _is_refusal(half_exc):
                    raise
                held.extend(HeldItem(id=id_of(item), reason=_reason(half_exc)) for item in half)
        return BatchOutcome(results=results, held=held)

    return BatchOutcome(results=[value], held=[])
