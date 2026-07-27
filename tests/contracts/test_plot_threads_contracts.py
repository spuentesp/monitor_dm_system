"""
Contract tests for Plot Threads schemas (M-29 dangling threads).

Covers:
- PlotThreadCategory enum: 6 narrative thread kinds
- PlotThreadUrgency enum: 4 urgency levels
- ExtractedPlotThread: thread extracted from text
- PlotThreadDetectionResult: detection run result with compute_totals()

Use Cases: M-29 (Plot thread detection)
"""

from __future__ import annotations

import pytest
from monitor_data.schemas.plot_threads import (
    ExtractedPlotThread,
    PlotThreadCategory,
    PlotThreadDetectionResult,
    PlotThreadUrgency,
)

# =============================================================================
# Enums
# =============================================================================


class TestPlotThreadCategoryEnum:
    def test_all_values(self):
        assert PlotThreadCategory.PROMISE.value == "promise"
        assert PlotThreadCategory.THREAT.value == "threat"
        assert PlotThreadCategory.MYSTERY.value == "mystery"
        assert PlotThreadCategory.CONSEQUENCE.value == "consequence"
        assert PlotThreadCategory.RELATIONSHIP.value == "relationship"
        assert PlotThreadCategory.WORLD_EVENT.value == "world_event"


class TestPlotThreadUrgencyEnum:
    def test_all_values(self):
        assert PlotThreadUrgency.LOW.value == "low"
        assert PlotThreadUrgency.MEDIUM.value == "medium"
        assert PlotThreadUrgency.HIGH.value == "high"
        assert PlotThreadUrgency.CRITICAL.value == "critical"


# =============================================================================
# ExtractedPlotThread
# =============================================================================


class TestExtractedPlotThread:
    def test_minimal(self):
        t = ExtractedPlotThread(
            title="The hidden heir",
            description="Someone is the rightful heir to the throne",
        )
        assert t.title == "The hidden heir"
        assert t.category == PlotThreadCategory.MYSTERY  # default
        assert t.urgency == PlotThreadUrgency.MEDIUM  # default
        assert t.confidence == 0.7  # default
        assert t.entity_names == []
        assert t.tags == []

    def test_threat_high_urgency(self):
        t = ExtractedPlotThread(
            title="The dragon awakens",
            description="The dragon stirs beneath the mountain",
            category=PlotThreadCategory.THREAT,
            urgency=PlotThreadUrgency.CRITICAL,
        )
        assert t.urgency == PlotThreadUrgency.CRITICAL
        assert t.category == PlotThreadCategory.THREAT

    def test_with_entities(self):
        t = ExtractedPlotThread(
            title="The promise to the elves",
            description="The king owes the elves a great debt",
            category=PlotThreadCategory.PROMISE,
            urgency=PlotThreadUrgency.HIGH,
            entity_names=["King Arthur", "Queen Titania"],
            source_hint="p. 234",
        )
        assert "King Arthur" in t.entity_names
        assert t.source_hint == "p. 234"

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            ExtractedPlotThread(
                title="X",
                description="X",
                confidence=1.5,  # > 1.0
            )
        with pytest.raises(Exception):
            ExtractedPlotThread(
                title="X",
                description="X",
                confidence=-0.1,  # < 0.0
            )

    def test_with_tags(self):
        t = ExtractedPlotThread(
            title="Lost artifact",
            description="Where is the Orb of Power?",
            tags=["artifact", "mystery", "main-quest"],
        )
        assert "main-quest" in t.tags


# =============================================================================
# PlotThreadDetectionResult
# =============================================================================


class TestPlotThreadDetectionResult:
    def test_empty(self):
        result = PlotThreadDetectionResult()
        assert result.threads == []
        assert result.total_detected == 0
        assert result.high_urgency_count == 0

    def test_with_threads(self):
        threads = [
            ExtractedPlotThread(
                title="Low thread",
                description="...",
                urgency=PlotThreadUrgency.LOW,
            ),
            ExtractedPlotThread(
                title="Critical thread",
                description="...",
                urgency=PlotThreadUrgency.CRITICAL,
            ),
            ExtractedPlotThread(
                title="High thread",
                description="...",
                urgency=PlotThreadUrgency.HIGH,
            ),
        ]
        result = PlotThreadDetectionResult(threads=threads)
        result.compute_totals()
        assert result.total_detected == 3
        assert result.high_urgency_count == 2  # HIGH + CRITICAL
