"""Lightweight in-process metrics for MONITOR.

Provides simple counters, gauges, and histograms tracked per-process
with thread-safe access. Designed to be cheap, allocation-free, and
snapshot-able in tests. Suitable as a building block for Prometheus
export or for inline log emission.

Covers Phase 5.2 — Logging & Observability (SYS-12):
  - scene duration (histogram)
  - LLM latency (histogram)
  - canonization success rate (counter)
  - external service health (gauge)

Usage:
    from monitor_agents.utils.metrics import metrics

    metrics.incr("scenes.completed")
    metrics.observe("llm.latency_ms", 230.5)
    metrics.set_gauge("neo4j.healthy", 1)

    snapshot = metrics.snapshot()
    # {"counters": {...}, "gauges": {...}, "histograms": {...}}
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Tuple


class Histogram:
    """Online histogram with quantile + mean/std tracking.

    Lightweight: O(N) memory in number of samples. Suitable for
    thousands of observations per process.
    """

    __slots__ = ("_samples", "_max_size")

    def __init__(self, max_size: int = 10_000) -> None:
        self._samples: List[float] = []
        self._max_size = max_size

    def observe(self, value: float) -> None:
        if len(self._samples) < self._max_size:
            self._samples.append(float(value))
        else:
            # Reservoir sampling: replace a random index
            import random

            idx = random.randrange(self._max_size)
            self._samples[idx] = float(value)

    def count(self) -> int:
        return len(self._samples)

    def mean(self) -> float:
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)

    def min(self) -> float:
        return min(self._samples) if self._samples else 0.0

    def max(self) -> float:
        return max(self._samples) if self._samples else 0.0

    def stddev(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        m = self.mean()
        variance = sum((x - m) ** 2 for x in self._samples) / (len(self._samples) - 1)
        return math.sqrt(variance)

    def quantile(self, q: float) -> float:
        if not 0.0 <= q <= 1.0:
            raise ValueError("q must be in [0, 1]")
        if not self._samples:
            return 0.0
        ordered = sorted(self._samples)
        idx = int(q * (len(ordered) - 1))
        return ordered[idx]

    def snapshot(self) -> Dict[str, float]:
        return {
            "count": float(self.count()),
            "mean": self.mean(),
            "min": self.min(),
            "max": self.max(),
            "stddev": self.stddev(),
            "p50": self.quantile(0.5),
            "p95": self.quantile(0.95),
            "p99": self.quantile(0.99),
        }

    def reset(self) -> None:
        self._samples = []


class Metrics:
    """Thread-safe in-process metrics store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: DefaultDict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, Histogram] = {}
        # Tag support: counter + tags -> count
        self._tagged_counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}

    # ---- counters --------------------------------------------------------

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        if value < 0:
            raise ValueError("incr value must be non-negative")
        with self._lock:
            if tags:
                key = self._tag_key(name, tags)
                self._tagged_counters[key] = self._tagged_counters.get(key, 0.0) + value
            else:
                self._counters[name] += value

    def get_counter(self, name: str) -> float:
        with self._lock:
            return self._counters.get(name, 0.0)

    def get_tagged_counter(self, name: str, tags: Optional[Dict[str, str]] = None) -> float:
        if not tags:
            return self.get_counter(name)
        with self._lock:
            return self._tagged_counters.get(self._tag_key(name, tags), 0.0)

    # ---- gauges ----------------------------------------------------------

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = float(value)

    def get_gauge(self, name: str) -> Optional[float]:
        with self._lock:
            return self._gauges.get(name)

    # ---- histograms ------------------------------------------------------

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            hist = self._histograms.get(name)
            if hist is None:
                hist = Histogram()
                self._histograms[name] = hist
            hist.observe(value)

    def get_histogram(self, name: str) -> Optional[Histogram]:
        with self._lock:
            return self._histograms.get(name)

    # ---- snapshot --------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            histograms = {name: hist.snapshot() for name, hist in self._histograms.items()}
            tagged = {
                self._tagged_key_to_name(key): value for key, value in self._tagged_counters.items()
            }
        return {
            "counters": counters,
            "gauges": gauges,
            "histograms": histograms,
            "tagged_counters": tagged,
        }

    def reset(self) -> None:
        """Reset all metrics. Test helper."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._tagged_counters.clear()

    # ---- internals -------------------------------------------------------

    @staticmethod
    def _tag_key(name: str, tags: Dict[str, str]) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
        return (name, tuple(sorted(tags.items())))

    @staticmethod
    def _tagged_key_to_name(
        key: Tuple[str, Tuple[Tuple[str, str], ...]],
    ) -> str:
        name, tag_items = key
        if not tag_items:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in tag_items)
        return f"{name}{{{tag_str}}}"


# Process-wide singleton
metrics = Metrics()


# =============================================================================
# Convenience timing helpers
# =============================================================================


class Timer:
    """Context manager for timing and recording durations.

    Usage:
        with Timer("scene.duration_ms"):
            run_scene()
    """

    __slots__ = ("_name", "_start", "_elapsed_ms")

    def __init__(self, name: str) -> None:
        self._name = name
        self._start: float = 0.0
        self._elapsed_ms: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        elapsed = time.perf_counter() - self._start
        self._elapsed_ms = elapsed * 1000.0
        metrics.observe(self._name, self._elapsed_ms)

    @property
    def elapsed_ms(self) -> float:
        return self._elapsed_ms


class AsyncTimer:
    """Async context manager for timing and recording durations.

    Usage:
        async with AsyncTimer("llm.latency_ms"):
            result = await call_llm()
    """

    __slots__ = ("_name", "_start", "_elapsed_ms")

    def __init__(self, name: str) -> None:
        self._name = name
        self._start: float = 0.0
        self._elapsed_ms: float = 0.0

    async def __aenter__(self) -> "AsyncTimer":
        self._start = time.perf_counter()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        elapsed = time.perf_counter() - self._start
        self._elapsed_ms = elapsed * 1000.0
        metrics.observe(self._name, self._elapsed_ms)

    @property
    def elapsed_ms(self) -> float:
        return self._elapsed_ms


__all__ = [
    "Histogram",
    "Metrics",
    "metrics",
    "Timer",
    "AsyncTimer",
]
