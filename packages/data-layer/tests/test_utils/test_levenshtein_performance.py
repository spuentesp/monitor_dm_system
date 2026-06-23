"""
Performance benchmarks for Levenshtein ratio after rapidfuzz migration (Paso 1).

LAYER: 1 (data-layer)
CRITERIO DE ÉXITO: rapidfuzz ≥10x más rápido que la implementación pure-Python
para strings de 100+ caracteres.
"""

import time
import pytest

from monitor_data.tools.ingest_tools.delta_detection import _levenshtein_ratio


# ---------------------------------------------------------------------------
# Performance threshold (CRITERIO DE ÉXITO)
# ---------------------------------------------------------------------------

MIN_SPEEDUP_FACTOR = 10
STRING_LENGTH = 100
WARMUP_ITERATIONS = 100
BENCHMARK_ITERATIONS = 1000


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def long_similar_strings() -> tuple[str, str]:
    """Two strings of ~120 chars with ~10% difference."""
    s1 = (
        "The ancient kingdom of Eldoria stood for a thousand years, "
        "its towers reaching toward the heavens like stone fingers."
    )
    s2 = (
        "The ancient kingdom of Eldoria stood for a thousand years, "
        "its spires reaching toward the heavens like iron fingers."
    )
    return s1, s2


@pytest.fixture
def long_different_strings() -> tuple[str, str]:
    """Two strings of ~120 chars with no shared words."""
    s1 = (
        "The ancient kingdom of Eldoria stood for a thousand years, "
        "its towers reaching toward the heavens like stone fingers."
    )
    s2 = (
        "Meanwhile in the distant future, quantum computers processed "
        "vast amounts of data while humanity explored the outer planets."
    )
    return s1, s2


# ---------------------------------------------------------------------------
# Pure-Python reference (same algorithm as the original Wagner-Fischer)
# ---------------------------------------------------------------------------


def _pure_python_levenshtein_ratio(s1: str, s2: str) -> float:
    """Original Wagner-Fischer implementation for baseline comparison."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len1, len2 = len(s1), len(s2)
    prev = list(range(len2 + 1))
    curr = [0] * (len2 + 1)

    for i in range(1, len1 + 1):
        curr[0] = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + cost,
            )
        prev, curr = curr, prev

    distance = prev[len2]
    max_len = max(len1, len2)
    return 1.0 - (distance / max_len) if max_len > 0 else 1.0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLevenshteinPerformance:
    """Verify rapidfuzz achieves ≥10x speedup over pure-Python."""

    def test_speedup_similar_strings(self, long_similar_strings: tuple[str, str]) -> None:
        """Benchmark: similar long strings (~10% diff)."""
        s1, s2 = long_similar_strings
        assert len(s1) >= STRING_LENGTH, f"Fixture too short: {len(s1)} chars"

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            _levenshtein_ratio(s1, s2)
            _pure_python_levenshtein_ratio(s1, s2)

        # Benchmark rapidfuzz
        t0 = time.perf_counter()
        for _ in range(BENCHMARK_ITERATIONS):
            _levenshtein_ratio(s1, s2)
        rapidfuzz_time = time.perf_counter() - t0

        # Benchmark pure Python
        t0 = time.perf_counter()
        for _ in range(BENCHMARK_ITERATIONS):
            _pure_python_levenshtein_ratio(s1, s2)
        pure_time = time.perf_counter() - t0

        speedup = pure_time / rapidfuzz_time if rapidfuzz_time > 0 else float("inf")
        print(f"\n  Similar strings ({len(s1)} chars):")
        print(
            f"    rapidfuzz: {rapidfuzz_time:.4f}s ({rapidfuzz_time / BENCHMARK_ITERATIONS * 1000:.3f}ms/call)"
        )
        print(
            f"    pure-Python: {pure_time:.4f}s ({pure_time / BENCHMARK_ITERATIONS * 1000:.3f}ms/call)"
        )
        print(f"    speedup: {speedup:.1f}x")

        assert speedup >= MIN_SPEEDUP_FACTOR, (
            f"Speedup {speedup:.1f}x below minimum {MIN_SPEEDUP_FACTOR}x for similar strings"
        )

    def test_speedup_different_strings(self, long_different_strings: tuple[str, str]) -> None:
        """Benchmark: completely different long strings."""
        s1, s2 = long_different_strings
        assert len(s1) >= STRING_LENGTH, f"Fixture too short: {len(s1)} chars"

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            _levenshtein_ratio(s1, s2)
            _pure_python_levenshtein_ratio(s1, s2)

        # Benchmark rapidfuzz
        t0 = time.perf_counter()
        for _ in range(BENCHMARK_ITERATIONS):
            _levenshtein_ratio(s1, s2)
        rapidfuzz_time = time.perf_counter() - t0

        # Benchmark pure Python
        t0 = time.perf_counter()
        for _ in range(BENCHMARK_ITERATIONS):
            _pure_python_levenshtein_ratio(s1, s2)
        pure_time = time.perf_counter() - t0

        speedup = pure_time / rapidfuzz_time if rapidfuzz_time > 0 else float("inf")
        print(f"\n  Different strings ({len(s1)} chars):")
        print(
            f"    rapidfuzz: {rapidfuzz_time:.4f}s ({rapidfuzz_time / BENCHMARK_ITERATIONS * 1000:.3f}ms/call)"
        )
        print(
            f"    pure-Python: {pure_time:.4f}s ({pure_time / BENCHMARK_ITERATIONS * 1000:.3f}ms/call)"
        )
        print(f"    speedup: {speedup:.1f}x")

        assert speedup >= MIN_SPEEDUP_FACTOR, (
            f"Speedup {speedup:.1f}x below minimum {MIN_SPEEDUP_FACTOR}x for different strings"
        )

    def test_rapidfuzz_is_faster_than_pure(self) -> None:
        """Sanity check: rapidfuzz should be faster on non-trivial different input."""
        s1 = "hello world " * 10
        s2 = "hallo world " * 10  # 1 char different per repetition

        t0 = time.perf_counter()
        _levenshtein_ratio(s1, s2)
        rf_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        _pure_python_levenshtein_ratio(s1, s2)
        py_time = time.perf_counter() - t0

        assert rf_time <= py_time, "rapidfuzz should not be slower than pure Python"
