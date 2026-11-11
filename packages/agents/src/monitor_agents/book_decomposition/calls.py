"""Count the model calls one decomposition run actually makes (I-17, task 10).

The job stores this count beside the estimate `estimate.py` produced before the
run started, so a person can see whether the estimate held. The wrappers count
every entry into a model-facing method, including calls that then fail — a
failed call still spent a request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeVar

STAGE_EXTRACTION = "extraction"
STAGE_VERIFICATION = "verification"
STAGE_SKIP_AUDIT = "skip_audit"
STAGE_STACKING = "stacking"
STAGE_COVERAGE = "coverage"
STAGE_GRAPH = "graph"

STAGES = (
    STAGE_EXTRACTION,
    STAGE_VERIFICATION,
    STAGE_SKIP_AUDIT,
    STAGE_STACKING,
    STAGE_COVERAGE,
    STAGE_GRAPH,
)

T = TypeVar("T")


@dataclass
class CallTally:
    """Model calls made in one run, by stage."""

    counts: dict[str, int] = field(default_factory=dict)

    def add(self, stage: str, count: int = 1) -> None:
        self.counts[stage] = self.counts.get(stage, 0) + count

    def get(self, stage: str) -> int:
        return self.counts.get(stage, 0)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def as_dict(self) -> dict[str, int]:
        """Every stage, zero-filled, so an estimate and a tally compare line by line."""
        return {stage: self.counts.get(stage, 0) for stage in STAGES}


class _TallyingExtractor:
    def __init__(self, inner: Any, tally: CallTally) -> None:
        self._inner = inner
        self._tally = tally

    async def __call__(self, window: Any) -> Any:
        try:
            return await self._inner(window)
        finally:
            self._tally.add(STAGE_EXTRACTION)


_REVIEW_STAGES: dict[str, str] = {
    "verify": STAGE_VERIFICATION,
    "audit_skips": STAGE_SKIP_AUDIT,
    "stack": STAGE_STACKING,
    "find_gaps": STAGE_COVERAGE,
}


class _TallyingReview:
    def __init__(self, inner: Any, tally: CallTally) -> None:
        self._inner = inner
        self._tally = tally

    def __getattr__(self, name: str) -> Any:
        inner = getattr(self._inner, name)
        stage = _REVIEW_STAGES.get(name)
        if stage is None or not callable(inner):
            return inner

        async def call(*args: Any, **kwargs: Any) -> Any:
            try:
                return await inner(*args, **kwargs)
            finally:
                self._tally.add(stage)

        return call


class _TallyingGraph:
    def __init__(self, inner: Any, tally: CallTally) -> None:
        self._inner = inner
        self._tally = tally

    async def propose(self, claims: str) -> Any:
        try:
            return await self._inner.propose(claims)
        finally:
            self._tally.add(STAGE_GRAPH)

    async def find_duplicates(self, names: str) -> Any:
        try:
            return await self._inner.find_duplicates(names)
        finally:
            self._tally.add(STAGE_GRAPH)


def tallying_extractor(extractor: T, tally: CallTally) -> T:
    """Wrap a WindowExtractor so every call is counted under `extraction`."""
    return _TallyingExtractor(extractor, tally)  # type: ignore[return-value]


def tallying_review(model: T, tally: CallTally) -> T:
    """Wrap a ReviewModel so each of its four methods is counted under its stage."""
    return _TallyingReview(model, tally)  # type: ignore[return-value]


def tallying_graph(model: T, tally: CallTally) -> T:
    """Wrap a GraphModel so propose and find_duplicates are counted under `graph`."""
    return _TallyingGraph(model, tally)  # type: ignore[return-value]


def format_counts(counts: dict[str, int]) -> str:
    """`extraction=15, verification=37, ...` for an activity-log line."""
    return ", ".join(f"{stage}={counts.get(stage, 0)}" for stage in STAGES if stage in counts)


def call_line(label: str, counts: dict[str, int]) -> str:
    """One activity-log line: `Calls made: total=160 (extraction=16, ...)`."""
    total = sum(counts.values())
    return f"Calls {label}: total={total} ({format_counts(counts)})"
