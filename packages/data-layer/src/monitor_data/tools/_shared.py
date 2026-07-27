"""
Shared private helpers for MONITOR data-layer tools.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and monitor_data.db only

Consolidates small utilities that had drifted into per-module copies
(`_to_native_datetime`, `_utcnow`, `_pydantic_to_dict`, `_levenshtein_ratio`,
`_call_sync`). Tool modules import these with a leading-underscore alias to
keep their internal naming conventions.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

from rapidfuzz.distance import Levenshtein as _Levenshtein

from monitor_data.db._utils import run_sync


def to_native_datetime(value: Any) -> Any:
    """Convert Neo4j temporal values into native Python datetimes when present."""
    if value is None:
        return None
    return value.to_native() if hasattr(value, "to_native") else value


def utcnow() -> datetime:
    """Timezone-aware UTC now (single source for tool timestamps)."""
    return datetime.now(UTC)


def pydantic_to_dict(item: Any) -> dict[str, Any]:
    """Convert a Pydantic model (v1 or v2) to a JSON-mode dict."""
    if hasattr(item, "model_dump"):
        return dict(item.model_dump(mode="json"))
    if hasattr(item, "dict"):
        return dict(item.dict())
    return {}


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Normalized Levenshtein similarity (1.0 identical, 0.0 disjoint).

    rapidfuzz C++ backend — ~50-100x faster than the pure-Python DP this
    replaces in contradiction detection.
    """
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return float(_Levenshtein.normalized_similarity(s1, s2))


def call_sync(result_or_coro: Any) -> Any:
    """Return sync results directly; await coroutine results via the shared DB loop."""
    if inspect.isawaitable(result_or_coro):
        return run_sync(result_or_coro)
    return result_or_coro
