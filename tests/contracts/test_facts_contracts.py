"""
Contract tests for Fact and Event schemas.

Covers:
- FactType enum: state, relationship, attribute, occurrence
- SimulationScope enum: local, regional, global
- FactStatus enum: active, superseded, tombstoned
- FactCreate / FactUpdate / FactResponse / FactFilter
- EventCreate / EventResponse / EventFilter

Use Cases: DL-19 (Fact system), DL-20 (Events)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

import pytest

from monitor_data.schemas.facts import (
    FactType,
    SimulationScope,
    FactStatus,
    FactCreate,
    FactUpdate,
    FactResponse,
    FactFilter,
    EventCreate,
    EventResponse,
    EventFilter,
)
from monitor_data.schemas.base import (
    CanonLevel,
    KnowledgeScope,
    Authority,
    HistoricalEventScope,
    LoreEventStatus,
)


# =============================================================================
# Enums
# =============================================================================


class TestFactTypeEnum:
    def test_all_values(self):
        assert FactType.STATE.value == "state"
        assert FactType.RELATIONSHIP.value == "relationship"
        assert FactType.ATTRIBUTE.value == "attribute"
        assert FactType.OCCURRENCE.value == "occurrence"


class TestSimulationScopeEnum:
    def test_all_values(self):
        assert SimulationScope.LOCAL.value == "local"
        assert SimulationScope.REGIONAL.value == "regional"
        assert SimulationScope.GLOBAL.value == "global"


class TestFactStatusEnum:
    def test_all_values(self):
        assert FactStatus.ACTIVE.value == "active"
        assert FactStatus.SUPERSEDED.value == "superseded"
        assert FactStatus.TOMBSTONED.value == "tombstoned"


# =============================================================================
# FactCreate
# =============================================================================


class TestFactCreate:
    def test_minimal(self):
        f = FactCreate(
            universe_id=uuid4(),
            statement="The king is alive",
        )
        assert f.fact_type == FactType.STATE  # default
        assert f.magnitude == 1  # default
        assert f.scope == SimulationScope.LOCAL  # default
        assert f.canon_level == CanonLevel.PROPOSED  # default
        assert f.knowledge_scope == KnowledgeScope.WORLD  # default
        assert f.confidence == 1.0  # default
        assert f.authority == Authority.SYSTEM  # default
        assert f.status == FactStatus.ACTIVE  # default

    def test_full(self):
        f = FactCreate(
            universe_id=uuid4(),
            statement="The dragon is dead",
            fact_type=FactType.OCCURRENCE,
            magnitude=10,
            scope=SimulationScope.GLOBAL,
            time_ref=datetime.utcnow(),
            duration=86400,
            properties={"killer": "Knight"},
            entity_ids=[uuid4()],
            source_ids=[uuid4()],
            scene_ids=[uuid4()],
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
            confidence=0.95,
            authority=Authority.GM,
        )
        assert f.magnitude == 10
        assert f.properties["killer"] == "Knight"

    def test_magnitude_bounds(self):
        with pytest.raises(Exception):
            FactCreate(
                universe_id=uuid4(),
                statement="x",
                magnitude=11,  # > 10
            )
        with pytest.raises(Exception):
            FactCreate(
                universe_id=uuid4(),
                statement="x",
                magnitude=0,  # < 1
            )

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            FactCreate(
                universe_id=uuid4(),
                statement="x",
                confidence=1.5,
            )

    def test_with_replaces(self):
        f = FactCreate(
            universe_id=uuid4(),
            statement="Updated fact",
            replaces=uuid4(),
        )
        assert f.replaces is not None

    def test_empty_statement_fails(self):
        with pytest.raises(Exception):
            FactCreate(universe_id=uuid4(), statement="")  # min_length=1


# =============================================================================
# FactUpdate
# =============================================================================


class TestFactUpdate:
    def test_empty(self):
        u = FactUpdate()
        assert u.statement is None
        assert u.status is None

    def test_partial(self):
        u = FactUpdate(
            statement="Updated statement",
            status=FactStatus.SUPERSEDED,
            confidence=0.5,
        )
        assert u.statement == "Updated statement"
        assert u.status == FactStatus.SUPERSEDED


# =============================================================================
# FactResponse
# =============================================================================


class TestFactResponse:
    def test_minimal(self):
        f = FactResponse(
            id=uuid4(),
            universe_id=uuid4(),
            statement="x",
            fact_type=FactType.STATE,
            canon_level=CanonLevel.PROPOSED,
            knowledge_scope=KnowledgeScope.WORLD,
            confidence=0.9,
            authority=Authority.SYSTEM,
            status=FactStatus.ACTIVE,
            created_at=datetime.utcnow(),
            replaces=None,
            properties=None,
        )
        assert f.entity_ids == []  # default
        assert f.scene_ids == []  # default

    def test_with_relations(self):
        eid = uuid4()
        f = FactResponse(
            id=uuid4(),
            universe_id=uuid4(),
            statement="x",
            fact_type=FactType.RELATIONSHIP,
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.FACTION,
            confidence=1.0,
            authority=Authority.GM,
            status=FactStatus.ACTIVE,
            created_at=datetime.utcnow(),
            replaces=None,
            properties={"k": "v"},
            entity_ids=[eid],
        )
        assert eid in f.entity_ids
        assert f.properties["k"] == "v"


# =============================================================================
# FactFilter
# =============================================================================


class TestFactFilter:
    def test_defaults(self):
        f = FactFilter()
        assert f.min_magnitude == 1  # default
        assert f.status == FactStatus.ACTIVE  # default
        assert f.limit == 30  # default
        assert f.offset == 0  # default

    def test_with_filters(self):
        f = FactFilter(
            universe_id=uuid4(),
            entity_id=uuid4(),
            fact_type=FactType.STATE,
            min_magnitude=5,
            scope=SimulationScope.REGIONAL,
        )
        assert f.min_magnitude == 5

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            FactFilter(limit=0)
        with pytest.raises(Exception):
            FactFilter(limit=200)  # > 100


# =============================================================================
# EventCreate
# =============================================================================


class TestEventCreate:
    def test_minimal(self):
        e = EventCreate(
            universe_id=uuid4(),
            title="The Battle of Helm's Deep",
            start_time=datetime(2024, 1, 1),
        )
        assert e.magnitude == 5  # default
        assert e.scope == SimulationScope.LOCAL  # default
        assert e.scene_id is None

    def test_with_relations(self):
        e = EventCreate(
            universe_id=uuid4(),
            title="The Sundering",
            description="A cataclysmic event",
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 12, 31),
            scope=SimulationScope.GLOBAL,
            timeline_after=[uuid4()],
            timeline_before=[uuid4()],
            causes=[uuid4()],
        )
        assert e.scope == SimulationScope.GLOBAL


# =============================================================================
# EventResponse
# =============================================================================


class TestEventResponse:
    def test_minimal(self):
        e = EventResponse(
            id=uuid4(),
            universe_id=uuid4(),
            title="x",
            start_time=datetime(2024, 1, 1),
            canon_level=CanonLevel.PROPOSED,
            knowledge_scope=KnowledgeScope.WORLD,
            confidence=1.0,
            authority=Authority.SOURCE,
            created_at=datetime.utcnow(),
        )
        assert e.causes == []  # default
        assert e.timeline_before == []  # default


# =============================================================================
# EventFilter
# =============================================================================


class TestEventFilter:
    def test_defaults(self):
        f = EventFilter()
        assert f.min_magnitude == 1  # default
        assert f.limit == 30  # default
        assert f.offset == 0  # default

    def test_with_filters(self):
        f = EventFilter(
            universe_id=uuid4(),
            scope=SimulationScope.REGIONAL,
            min_magnitude=5,
        )
        assert f.min_magnitude == 5

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            EventFilter(limit=0)
        with pytest.raises(Exception):
            EventFilter(limit=200)  # > 100
