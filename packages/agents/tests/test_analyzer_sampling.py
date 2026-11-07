"""The analyzer's chunk sample must be repeatable and span the whole book (I-17)."""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any

import pytest
import structlog
from monitor_agents.analyzer._sampling import log_sample, scroll_all, select_spread


def _point(index: int, **extra: Any) -> SimpleNamespace:
    return SimpleNamespace(payload={"chunk_index": index, "text": f"chunk {index}", **extra})


class _FakeQdrant:
    """Scrolls in an order unrelated to reading order, like hashed point IDs."""

    def __init__(self, points: list[Any], page_size_seen: list[int] | None = None) -> None:
        self.points = list(points)
        random.Random(7).shuffle(self.points)
        self.calls = 0

    async def scroll(self, *, limit: int, offset: Any, **_: Any) -> tuple[list[Any], Any]:
        self.calls += 1
        start = offset or 0
        batch = self.points[start : start + limit]
        following = start + limit
        return batch, following if following < len(self.points) else None


@pytest.mark.unit
async def test_scroll_all_reads_every_point():
    points = [_point(i) for i in range(2000)]
    found = await scroll_all(_FakeQdrant(points), "c", None)
    assert sorted(p.payload["chunk_index"] for p in found) == list(range(2000))


@pytest.mark.unit
async def test_scroll_all_handles_an_empty_collection():
    assert await scroll_all(_FakeQdrant([]), "c", None) == []


@pytest.mark.unit
def test_under_the_limit_keeps_everything_in_reading_order():
    points = [_point(3), _point(1), _point(2)]
    assert [p.payload["chunk_index"] for p in select_spread(points, 10)] == [1, 2, 3]


@pytest.mark.unit
def test_over_the_limit_spans_the_book_and_includes_both_ends():
    chosen = [p.payload["chunk_index"] for p in select_spread([_point(i) for i in range(2000)], 512)]
    assert len(chosen) == len(set(chosen)) == 512
    assert chosen[0] == 0 and chosen[-1] == 1999
    gaps = {b - a for a, b in zip(chosen, chosen[1:], strict=False)}
    assert max(gaps) - min(gaps) <= 1


@pytest.mark.unit
def test_sample_does_not_depend_on_input_order():
    points = [_point(i) for i in range(1000)]
    shuffled = list(points)
    random.Random(1).shuffle(shuffled)
    assert select_spread(points, 100) == select_spread(shuffled, 100)


@pytest.mark.unit
def test_points_without_an_index_do_not_crash_and_stay_repeatable():
    points = [SimpleNamespace(payload={"text": "b"}), SimpleNamespace(payload={"text": "a"}), SimpleNamespace(payload=None)]
    assert [(p.payload or {}).get("text") for p in select_spread(points, 3)] == [None, "a", "b"]


@pytest.mark.unit
@pytest.mark.parametrize(("limit", "count"), [(1, 1), (0, 0)])
def test_tiny_limits(limit, count):
    assert len(select_spread([_point(i) for i in range(5)], limit)) == count


@pytest.mark.unit
def test_truncation_is_reported_as_a_warning():
    with structlog.testing.capture_logs() as logs:
        log_sample("book", "category", found=2000, read=512)
        log_sample("book", "category", found=10, read=10)
    assert logs[0]["log_level"] == "warning"
    assert (logs[0]["chunks_found"], logs[0]["chunks_read"]) == (2000, 512)
    assert logs[1]["log_level"] == "info"
