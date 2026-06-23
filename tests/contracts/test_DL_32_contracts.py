"""
Contract tests for PlotThread schemas.

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)
"""

import pytest
from pydantic import ValidationError
from monitor_data.schemas.plot_threads import (
    PlotThreadCategory, PlotThreadUrgency, ExtractedPlotThread, PlotThreadDetectionResult,
)


class TestPlotThreadCategory:
    def test_values(self):
        assert PlotThreadCategory.PROMISE.value == "promise"
        assert PlotThreadCategory.THREAT.value == "threat"
        assert PlotThreadCategory.MYSTERY.value == "mystery"
        assert PlotThreadCategory.CONSEQUENCE.value == "consequence"
        assert PlotThreadCategory.RELATIONSHIP.value == "relationship"
        assert PlotThreadCategory.WORLD_EVENT.value == "world_event"


class TestPlotThreadUrgency:
    def test_values(self):
        assert PlotThreadUrgency.LOW.value == "low"
        assert PlotThreadUrgency.MEDIUM.value == "medium"
        assert PlotThreadUrgency.HIGH.value == "high"
        assert PlotThreadUrgency.CRITICAL.value == "critical"


class TestExtractedPlotThread:
    def test_minimal(self):
        t = ExtractedPlotThread(title="Missing Sword", description="Where did the sword go?")
        assert t.category == PlotThreadCategory.MYSTERY
        assert t.urgency == PlotThreadUrgency.MEDIUM
        assert t.confidence == 0.7
        assert t.entity_names == []

    def test_full(self):
        t = ExtractedPlotThread(
            title="King's Promise",
            description="The king promised to reward the party",
            category=PlotThreadCategory.PROMISE,
            urgency=PlotThreadUrgency.HIGH,
            entity_names=["King", "Party"],
            confidence=0.9,
        )
        assert t.urgency == PlotThreadUrgency.HIGH

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ExtractedPlotThread(title="X", description="Y", confidence=1.1)
        with pytest.raises(ValidationError):
            ExtractedPlotThread(title="X", description="Y", confidence=-0.1)


class TestPlotThreadDetectionResult:
    def test_empty(self):
        r = PlotThreadDetectionResult()
        r.compute_totals()
        assert r.total_detected == 0

    def test_with_threads(self):
        t = ExtractedPlotThread(title="T1", description="desc", urgency=PlotThreadUrgency.CRITICAL)
        r = PlotThreadDetectionResult(threads=[t])
        r.compute_totals()
        assert r.total_detected == 1
        assert r.high_urgency_count == 1
