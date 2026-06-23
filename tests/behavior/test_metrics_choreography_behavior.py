"""Behavior tests for the metrics utility (Phase 5.2 - Observability).

Covers:
- Histogram observations, quantiles, mean, stddev
- Metrics counters, gauges, tagged counters
- Thread-safety
- Timer / AsyncTimer context managers
- Snapshot shape
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# Histogram
# =============================================================================


class TestHistogram:
    def test_empty(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        assert h.count() == 0
        assert h.mean() == 0.0
        assert h.min() == 0.0
        assert h.max() == 0.0
        assert h.quantile(0.5) == 0.0

    def test_single_observation(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        h.observe(42.0)
        assert h.count() == 1
        assert h.mean() == 42.0
        assert h.min() == 42.0
        assert h.max() == 42.0

    def test_multiple_observations(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
            h.observe(v)
        assert h.count() == 5
        assert h.mean() == 30.0
        assert h.min() == 10.0
        assert h.max() == 50.0

    def test_quantile_p50_median(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        for v in range(1, 101):
            h.observe(float(v))
        # 1..100, median should be 50 (or close)
        p50 = h.quantile(0.5)
        assert 48.0 <= p50 <= 52.0

    def test_quantile_p99_high(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        for v in range(1, 101):
            h.observe(float(v))
        p99 = h.quantile(0.99)
        assert p99 >= 90.0

    def test_quantile_invalid_q(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        with pytest.raises(ValueError):
            h.quantile(1.5)
        with pytest.raises(ValueError):
            h.quantile(-0.1)

    def test_stddev_zero_for_single_sample(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        h.observe(5.0)
        assert h.stddev() == 0.0

    def test_stddev_positive_for_distribution(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            h.observe(v)
        # Population stddev ~1.414, sample stddev ~1.581
        assert h.stddev() > 0.0

    def test_snapshot_includes_quantiles(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        h.observe(1.0)
        snap = h.snapshot()
        assert "mean" in snap
        assert "p50" in snap
        assert "p95" in snap
        assert "p99" in snap
        assert "stddev" in snap
        assert "count" in snap
        assert "min" in snap
        assert "max" in snap

    def test_reservoir_sampling_respects_max(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram(max_size=10)
        for v in range(100):
            h.observe(float(v))
        assert h.count() == 10

    def test_reset(self):
        from monitor_agents.utils.metrics import Histogram

        h = Histogram()
        h.observe(1.0)
        h.reset()
        assert h.count() == 0


# =============================================================================
# Metrics — counters
# =============================================================================


class TestMetricsCounters:
    def setup_method(self):
        from monitor_agents.utils.metrics import Metrics

        # Use a fresh Metrics per test (not the global singleton)
        self.m = Metrics()

    def test_default_zero(self):
        assert self.m.get_counter("nope") == 0.0

    def test_incr_default_one(self):
        self.m.incr("scenes.completed")
        self.m.incr("scenes.completed")
        assert self.m.get_counter("scenes.completed") == 2.0

    def test_incr_explicit_value(self):
        self.m.incr("turns", 5)
        assert self.m.get_counter("turns") == 5.0

    def test_incr_negative_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            self.m.incr("x", -1)

    def test_tagged_counter(self):
        self.m.incr("llm.calls", 1, tags={"model": "claude", "result": "success"})
        self.m.incr("llm.calls", 1, tags={"model": "claude", "result": "success"})
        self.m.incr("llm.calls", 1, tags={"model": "claude", "result": "failure"})

        assert (
            self.m.get_tagged_counter(
                "llm.calls", tags={"model": "claude", "result": "success"}
            )
            == 2.0
        )
        assert (
            self.m.get_tagged_counter(
                "llm.calls", tags={"model": "claude", "result": "failure"}
            )
            == 1.0
        )

    def test_tag_order_does_not_matter(self):
        self.m.incr("x", 1, tags={"a": "1", "b": "2"})
        # Reverse order
        assert self.m.get_tagged_counter("x", tags={"b": "2", "a": "1"}) == 1.0


# =============================================================================
# Metrics — gauges
# =============================================================================


class TestMetricsGauges:
    def setup_method(self):
        from monitor_agents.utils.metrics import Metrics

        self.m = Metrics()

    def test_default_none(self):
        assert self.m.get_gauge("never_set") is None

    def test_set_and_get(self):
        self.m.set_gauge("neo4j.healthy", 1)
        self.m.set_gauge("queue.depth", 42)
        assert self.m.get_gauge("neo4j.healthy") == 1.0
        assert self.m.get_gauge("queue.depth") == 42.0

    def test_set_overwrites(self):
        self.m.set_gauge("x", 1)
        self.m.set_gauge("x", 99)
        assert self.m.get_gauge("x") == 99.0

    def test_set_float(self):
        self.m.set_gauge("cpu_pct", 73.5)
        assert self.m.get_gauge("cpu_pct") == 73.5


# =============================================================================
# Metrics — histograms
# =============================================================================


class TestMetricsHistograms:
    def setup_method(self):
        from monitor_agents.utils.metrics import Metrics

        self.m = Metrics()

    def test_observe_creates(self):
        self.m.observe("llm.latency_ms", 100.0)
        hist = self.m.get_histogram("llm.latency_ms")
        assert hist is not None
        assert hist.count() == 1

    def test_multiple_observations(self):
        for v in [10.0, 20.0, 30.0]:
            self.m.observe("latency", v)
        assert self.m.get_histogram("latency").count() == 3

    def test_snapshot_includes_histogram(self):
        self.m.observe("a", 1.0)
        snap = self.m.snapshot()
        assert "histograms" in snap
        assert "a" in snap["histograms"]
        assert snap["histograms"]["a"]["count"] == 1.0


# =============================================================================
# Metrics — snapshot
# =============================================================================


class TestMetricsSnapshot:
    def test_shape(self):
        from monitor_agents.utils.metrics import Metrics

        m = Metrics()
        m.incr("a", 5)
        m.set_gauge("b", 10)
        m.observe("c", 1.0)
        snap = m.snapshot()

        assert "counters" in snap
        assert "gauges" in snap
        assert "histograms" in snap
        assert "tagged_counters" in snap
        assert snap["counters"]["a"] == 5.0
        assert snap["gauges"]["b"] == 10.0
        assert "c" in snap["histograms"]

    def test_reset_clears_all(self):
        from monitor_agents.utils.metrics import Metrics

        m = Metrics()
        m.incr("a", 5)
        m.set_gauge("b", 10)
        m.observe("c", 1.0)
        m.reset()
        snap = m.snapshot()
        assert snap["counters"] == {}
        assert snap["gauges"] == {}
        assert snap["histograms"] == {}


# =============================================================================
# Thread-safety
# =============================================================================


class TestMetricsThreadSafety:
    def test_concurrent_incr(self):
        from monitor_agents.utils.metrics import Metrics

        m = Metrics()
        n_threads = 10
        n_per_thread = 1000

        def worker():
            for _ in range(n_per_thread):
                m.incr("shared")

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert m.get_counter("shared") == n_threads * n_per_thread


# =============================================================================
# Timer (sync)
# =============================================================================


class TestTimer:
    def test_records_duration(self):
        from monitor_agents.utils.metrics import metrics, Timer

        metrics.reset()
        with Timer("test.timer"):
            sum(range(1000))  # small work

        hist = metrics.get_histogram("test.timer")
        assert hist is not None
        assert hist.count() == 1
        assert hist.mean() > 0.0

    def test_elapsed_ms_property(self):
        from monitor_agents.utils.metrics import Timer

        with Timer("dummy") as t:
            pass
        assert t.elapsed_ms >= 0.0


# =============================================================================
# AsyncTimer
# =============================================================================


class TestAsyncTimer:
    def test_records_duration(self):
        from monitor_agents.utils.metrics import metrics, AsyncTimer

        metrics.reset()

        async def do_work():
            await asyncio.sleep(0.01)
            async with AsyncTimer("test.async_timer"):
                await asyncio.sleep(0.01)

        asyncio.run(do_work())
        hist = metrics.get_histogram("test.async_timer")
        assert hist is not None
        assert hist.count() == 1
        # Sleep was ~10ms, allow slack
        assert hist.mean() > 5.0

    def test_records_failure(self):
        from monitor_agents.utils.metrics import metrics, AsyncTimer

        metrics.reset()

        async def fail():
            try:
                async with AsyncTimer("x"):
                    raise RuntimeError("boom")
            except RuntimeError:
                pass

        asyncio.run(fail())
        # Even on exception, the observation is recorded
        assert metrics.get_histogram("x").count() == 1


# =============================================================================
# Singleton `metrics`
# =============================================================================


class TestGlobalSingleton:
    def test_singleton_is_metrics_instance(self):
        from monitor_agents.utils.metrics import Metrics, metrics

        assert isinstance(metrics, Metrics)

    def test_singleton_is_shared(self):
        from monitor_agents.utils.metrics import metrics

        # mutate singleton, observe change
        metrics.reset()
        metrics.incr("shared.singleton")
        assert metrics.get_counter("shared.singleton") == 1.0
