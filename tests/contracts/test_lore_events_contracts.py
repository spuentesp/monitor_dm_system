"""
Contract tests for LoreEvent schemas.

Covers:
- LoreEventCreate: create historical event
- LoreEventUpdate: partial update
- LoreEventResponse: full response
- LoreEventFilter: list filter
- LoreEventListResponse: paginated list
- HistoricalEventScope enum
- LoreEventStatus enum

Use Cases: DL-3 (Lore event timeline)
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import uuid4

import pytest

from monitor_data.schemas.lore_events import (
    LoreEventCreate,
    LoreEventUpdate,
    LoreEventResponse,
    LoreEventFilter,
    LoreEventListResponse,
)
from monitor_data.schemas.base import (
    HistoricalEventScope,
    LoreEventStatus,
    Authority,
    CanonLevel,
)


# =============================================================================
# Enums
# =============================================================================


class TestHistoricalEventScopeEnum:
    def test_all_values(self):
        assert HistoricalEventScope.COSMIC.value == "cosmic"
        assert HistoricalEventScope.GLOBAL.value == "global"
        assert HistoricalEventScope.REGIONAL.value == "regional"
        assert HistoricalEventScope.LOCAL.value == "local"
        assert HistoricalEventScope.PERSONAL.value == "personal"


class TestLoreEventStatusEnum:
    def test_all_values(self):
        assert LoreEventStatus.CLOSED.value == "closed"
        assert LoreEventStatus.OPEN.value == "open"


# =============================================================================
# LoreEventCreate
# =============================================================================


class TestLoreEventCreate:
    def test_minimal(self):
        e = LoreEventCreate(
            universe_id=uuid4(),
            title="The War of the Ring",
        )
        assert e.title == "The War of the Ring"
        assert e.scope == HistoricalEventScope.GLOBAL  # default
        assert e.event_status == LoreEventStatus.CLOSED  # default
        assert e.canon_level == CanonLevel.PROPOSED  # default
        assert e.authority == Authority.SOURCE  # default
        assert e.confidence == 1.0  # default

    def test_with_timeline(self):
        e = LoreEventCreate(
            universe_id=uuid4(),
            title="The Sundering",
            description="A cataclysmic event",
            era="M31",
            start_time_ref=datetime(2024, 1, 1),
            end_time_ref=datetime(2024, 12, 31),
            duration_description="One year",
        )
        assert e.era == "M31"
        assert e.start_time_ref is not None
        assert e.duration_description == "One year"

    def test_with_relations(self):
        e = LoreEventCreate(
            universe_id=uuid4(),
            title="The Battle of Helm's Deep",
            entity_ids=[uuid4(), uuid4()],
            caused_by_ids=[uuid4()],
            led_to_ids=[uuid4(), uuid4()],
            source_ids=[uuid4()],
        )
        assert len(e.entity_ids) == 2
        assert len(e.led_to_ids) == 2

    def test_with_open_status(self):
        e = LoreEventCreate(
            universe_id=uuid4(),
            title="The Slow Corruption",
            event_status=LoreEventStatus.OPEN,
            scope=HistoricalEventScope.COSMIC,
        )
        assert e.event_status == LoreEventStatus.OPEN
        assert e.scope == HistoricalEventScope.COSMIC

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            LoreEventCreate(
                universe_id=uuid4(),
                title="x",
                confidence=1.5,
            )


# =============================================================================
# LoreEventUpdate
# =============================================================================


class TestLoreEventUpdate:
    def test_empty(self):
        u = LoreEventUpdate()
        assert u.title is None
        assert u.description is None

    def test_partial(self):
        u = LoreEventUpdate(
            title="Updated title",
            event_status=LoreEventStatus.OPEN,
            confidence=0.7,
        )
        assert u.title == "Updated title"
        assert u.event_status == LoreEventStatus.OPEN


# =============================================================================
# LoreEventResponse
# =============================================================================


class TestLoreEventResponse:
    def test_minimal(self):
        e = LoreEventResponse(
            id=uuid4(),
            universe_id=uuid4(),
            title="x",
            description="",
            scope=HistoricalEventScope.GLOBAL,
            event_status=LoreEventStatus.CLOSED,
            canon_level=CanonLevel.PROPOSED,
            confidence=0.9,
            authority=Authority.SOURCE,
            created_at=datetime.now(),
        )
        assert e.source_ids == []
        assert e.entity_ids == []


# =============================================================================
# LoreEventFilter
# =============================================================================


class TestLoreEventFilter:
    def test_defaults(self):
        f = LoreEventFilter()
        assert f.limit == 50
        assert f.offset == 0

    def test_with_filters(self):
        f = LoreEventFilter(
            universe_id=uuid4(),
            scope=HistoricalEventScope.GLOBAL,
            event_status=LoreEventStatus.OPEN,
            era="M31",
        )
        assert f.universe_id is not None
        assert f.scope == HistoricalEventScope.GLOBAL
        assert f.era == "M31"

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            LoreEventFilter(limit=0)
        with pytest.raises(Exception):
            LoreEventFilter(limit=300)  # > 200


# =============================================================================
# LoreEventListResponse
# =============================================================================


class TestLoreEventListResponse:
    def test_empty(self):
        r = LoreEventListResponse(events=[], total=0, limit=50, offset=0)
        assert r.events == []
        assert r.total == 0
