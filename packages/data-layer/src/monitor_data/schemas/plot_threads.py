"""
Pydantic schemas for dangling plot thread detection (EPIC 2, EPIC 6).

LAYER: 1 (data-layer)

A DanglingPlotThread is an open narrative thread extracted from source text
or session notes — a promise, threat, unresolved question, or foreshadowed
event that hasn't been resolved yet.

EPIC 2 requires: "Detect dangling plot threads"
EPIC 6 requires: "Detect unresolved consequences"

Thread categories:
    PROMISE       — A character promised to do something (unfulfilled)
    THREAT        — A looming danger that hasn't materialized
    MYSTERY       — An open question or unsolved puzzle
    CONSEQUENCE   — An action taken whose outcome hasn't been determined
    RELATIONSHIP  — A tension or bond between characters that's unresolved
    WORLD_EVENT   — A timeline event that's been set up but not resolved

Resolution status:
    OPEN          — Mentioned but no progress
    ADVANCED      — Partially addressed
    RESOLVED      — Fully closed out
    ABANDONED     — Dropped and unlikely to return
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PlotThreadCategory(str, Enum):
    """What kind of narrative thread this is."""

    PROMISE = "promise"
    THREAT = "threat"
    MYSTERY = "mystery"
    CONSEQUENCE = "consequence"
    RELATIONSHIP = "relationship"
    WORLD_EVENT = "world_event"


class PlotThreadUrgency(str, Enum):
    """How urgently this thread needs resolution."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExtractedPlotThread(BaseModel):
    """
    A dangling plot thread extracted from source text during ingestion.

    Stored on the KnowledgePack alongside axioms, lore facts, etc.
    When applied → becomes a PlotThread node/edge for tracking.
    """

    title: str = Field(
        max_length=300,
        description="Short descriptive title for this thread",
    )
    description: str = Field(
        max_length=2000,
        description="What the thread is about, why it's unresolved",
    )
    category: PlotThreadCategory = Field(
        default=PlotThreadCategory.MYSTERY,
        description="What kind of narrative thread",
    )
    urgency: PlotThreadUrgency = Field(
        default=PlotThreadUrgency.MEDIUM,
        description="How urgently this needs resolution",
    )
    entity_names: List[str] = Field(
        default_factory=list,
        description="Characters/factions/locations involved",
    )
    source_hint: Optional[str] = Field(
        None,
        max_length=200,
        description="Where in the source this thread appears (page/section)",
    )
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)


class PlotThreadDetectionResult(BaseModel):
    """Result of running plot thread detection on a source."""

    threads: List[ExtractedPlotThread] = Field(default_factory=list)
    total_detected: int = Field(default=0)
    high_urgency_count: int = Field(default=0)

    def compute_totals(self) -> None:
        self.total_detected = len(self.threads)
        self.high_urgency_count = sum(
            1
            for t in self.threads
            if t.urgency in (PlotThreadUrgency.HIGH, PlotThreadUrgency.CRITICAL)
        )
