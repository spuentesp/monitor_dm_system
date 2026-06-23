"""
Contract tests for LoreEvent schemas.

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)

pytest --test-run-type=unit tests/contracts/test_DL_30_contracts.py
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from monitor_data.schemas.base import (
    HistoricalEventScope,
    LoreEventStatus,
    Authority,
    CanonLevel,
)
from monitor_data.schemas.lore_events import (
    LoreEventCreate,
    LoreEventUpdate,
    LoreEventResponse,
    LoreEventFilter,
    LoreEventListResponse,
)


class TestLoreEventCreate:
    def test_minimal(self):
        e = LoreEventCreate(universe_id=uuid4(), title="The Fall of Cadia")
        assert e.title == "The Fall of Cadia"
        assert e.scope == HistoricalEventScope.GLOBAL
        assert e.event_status == LoreEventStatus.CLOSED
        assert e.description == ""
        assert e.canon_level == CanonLevel.PROPOSED
        assert e.authority == Authority.SOURCE

    def test_full(self):
        now = datetime.now(timezone.utc)
        e = LoreEventCreate(
            universe_id=uuid4(),
            title="The Horus Heresy",
            description="Massive civil war",
            era="M31",
            start_time_ref=now,
            scope=HistoricalEventScope.COSMIC,
            event_status=LoreEventStatus.CLOSED,
            source_ids=[uuid4()],
            entity_ids=[uuid4()],
            canon_level=CanonLevel.CANON,
            confidence=0.95,
            authority=Authority.GM,
        )
        assert e.scope == HistoricalEventScope.COSMIC
        assert e.authority == Authority.GM

    def test_title_min_length_1(self):
        with pytest.raises(ValidationError):
            LoreEventCreate(universe_id=uuid4(), title="")


class TestLoreEventUpdate:
    def test_empty(self):
        u = LoreEventUpdate()
        assert u.title is None


class TestLoreEventResponse:
    def test_minimal(self):
        now = datetime.now(timezone.utc)
        r = LoreEventResponse(
            id=uuid4(),
            universe_id=uuid4(),
            title="Fall of Cadia",
            description="",
            scope=HistoricalEventScope.GLOBAL,
            event_status=LoreEventStatus.CLOSED,
            canon_level=CanonLevel.CANON,
            confidence=1.0,
            authority=Authority.GM,
            created_at=now,
        )
        assert r.title == "Fall of Cadia"


class TestLoreEventFilter:
    def test_defaults(self):
        f = LoreEventFilter()
        assert f.limit == 50
        assert f.offset == 0


class TestLoreEventListResponse:
    def test_valid(self):
        r = LoreEventListResponse(events=[], total=0, limit=50, offset=0)
        assert r.total == 0


class TestHistoricalEventScopeEnum:
    def test_values(self):
        assert HistoricalEventScope.COSMIC.value == "cosmic"
        assert HistoricalEventScope.GLOBAL.value == "global"
        assert HistoricalEventScope.REGIONAL.value == "regional"
        assert HistoricalEventScope.LOCAL.value == "local"
        assert HistoricalEventScope.PERSONAL.value == "personal"


class TestLoreEventStatusEnum:
    def test_values(self):
        assert LoreEventStatus.OPEN.value == "open"
        assert LoreEventStatus.CLOSED.value == "closed"
