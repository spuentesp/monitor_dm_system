"""Read all of a book's matching chunks, then choose a repeatable sample spread across it.

Qdrant scrolls in point ID order, and chunk IDs are hashes, so stopping a scroll at a cap reads an
arbitrary part of the book. This reads every match first, and only then applies the cap.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog

log = structlog.get_logger()

_SCROLL_PAGE_SIZE = 64


async def scroll_all(qdrant: Any, collection: str, scroll_filter: Any) -> list[Any]:
    """Read every point matching a filter, with payloads and without vectors."""
    points: list[Any] = []
    offset = None
    while True:
        batch, offset = await qdrant.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=_SCROLL_PAGE_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(batch)
        if not batch or offset is None:
            return points


def _reading_order(point: Any) -> tuple[int, int, str]:
    payload = point.payload or {}
    return (
        payload.get("chunk_index") or 0,
        payload.get("page_number") or 0,
        str(payload.get("text", "")),
    )


def select_spread(points: Sequence[Any], limit: int) -> list[Any]:
    """Put points in reading order, and take evenly spaced ones if there are too many.

    The first and last chunks are always included, and the result doesn't depend on input order.
    """
    ordered = sorted(points, key=_reading_order)
    if len(ordered) <= limit:
        return ordered
    if limit <= 1:
        return ordered[: max(limit, 0)]
    last = len(ordered) - 1
    return [ordered[round(i * last / (limit - 1))] for i in range(limit)]


def log_sample(source_name: str, purpose: str, found: int, read: int) -> None:
    """Record how much of a book a sample covers, so a cut-off is visible."""
    if read < found:
        log.warning(
            "analyzer_sample_truncated",
            source_name=source_name,
            purpose=purpose,
            chunks_found=found,
            chunks_read=read,
        )
    else:
        log.info(
            "analyzer_sample_complete",
            source_name=source_name,
            purpose=purpose,
            chunks_read=read,
        )
