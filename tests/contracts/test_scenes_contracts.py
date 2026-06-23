"""
Contract tests for Scene and Turn schemas.

Covers:
- TurnCreate: append a turn (with entity_id validation when speaker=ENTITY)
- TurnResponse: full turn data
- SceneCreate / SceneUpdate / SceneResponse
- SceneFilter: list filter with sorting
- SceneListResponse: paginated
- SceneStatus enum
- Speaker enum
- TemporalMode enum

Use Cases: P-1, P-2 (Scene system)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

import pytest

from monitor_data.schemas.scenes import (
    TurnCreate,
    TurnResponse,
    SceneCreate,
    SceneUpdate,
    SceneResponse,
    SceneFilter,
    SceneListResponse,
)
from monitor_data.schemas.base import (
    Speaker,
    TemporalMode,
    SceneStatus,
)


# =============================================================================
# Enums (just verify values exist)
# =============================================================================


class TestSpeakerEnum:
    def test_values(self):
        assert Speaker.USER.value == "user"
        assert Speaker.GM.value == "gm"
        assert Speaker.ENTITY.value == "entity"


class TestTemporalModeEnum:
    def test_values(self):
        assert TemporalMode.PRESENT.value == "present"
        assert TemporalMode.FLASHBACK.value == "flashback"
        assert TemporalMode.FLASH_FORWARD.value == "flash_forward"
        assert TemporalMode.DREAM.value == "dream"


class TestSceneStatusEnum:
    def test_values(self):
        assert SceneStatus.ACTIVE.value == "active"
        assert SceneStatus.FINALIZING.value == "finalizing"
        assert SceneStatus.COMPLETED.value == "completed"


# =============================================================================
# TurnCreate
# =============================================================================


class TestTurnCreate:
    def test_user_turn(self):
        t = TurnCreate(speaker=Speaker.USER, text="I attack the dragon")
        assert t.entity_id is None
        assert t.resolution_ref is None

    def test_gm_turn(self):
        t = TurnCreate(speaker=Speaker.GM, text="The dragon roars.")
        assert t.speaker == Speaker.GM

    def test_entity_turn(self):
        t = TurnCreate(
            speaker=Speaker.ENTITY,
            entity_id=uuid4(),
            text="I am Gandalf.",
        )
        assert t.entity_id is not None

    def test_entity_with_entity_id(self):
        """Entity speaker must have entity_id (positive test)."""
        t = TurnCreate(
            speaker=Speaker.ENTITY,
            entity_id=uuid4(),
            text="NPC speaking",
        )
        assert t.entity_id is not None

    def test_empty_text_fails(self):
        with pytest.raises(Exception):
            TurnCreate(speaker=Speaker.USER, text="")

    def test_with_resolution(self):
        t = TurnCreate(
            speaker=Speaker.GM,
            text="Resolution",
            resolution_ref=uuid4(),
        )
        assert t.resolution_ref is not None


# =============================================================================
# TurnResponse
# =============================================================================


class TestTurnResponse:
    def test_minimal(self):
        t = TurnResponse(
            turn_id=uuid4(),
            speaker=Speaker.USER,
            text="Hello",
            timestamp=datetime.utcnow(),
        )
        assert t.entity_id is None

    def test_entity_turn(self):
        t = TurnResponse(
            turn_id=uuid4(),
            speaker=Speaker.ENTITY,
            entity_id=uuid4(),
            text="Greetings",
            timestamp=datetime.utcnow(),
            resolution_ref=uuid4(),
        )
        assert t.resolution_ref is not None


# =============================================================================
# SceneCreate
# =============================================================================


class TestSceneCreate:
    def test_minimal(self):
        s = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="The Battle",
        )
        assert s.temporal_mode == TemporalMode.PRESENT  # default
        assert s.status == SceneStatus.ACTIVE  # default
        assert s.purpose == ""  # default
        assert s.participating_entities == []  # default

    def test_with_timeline(self):
        s = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="The Fall",
            narrative_order=5,
            time_ref=datetime(2024, 6, 1),
            time_description="The day of the eclipse",
        )
        assert s.narrative_order == 5

    def test_flashback(self):
        s = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="15 years ago",
            temporal_mode=TemporalMode.FLASHBACK,
            parent_scene_id=uuid4(),
        )
        assert s.temporal_mode == TemporalMode.FLASHBACK
        assert s.parent_scene_id is not None

    def test_with_location_and_participants(self):
        s = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Tavern meeting",
            location_ref=uuid4(),
            participating_entities=[uuid4(), uuid4(), uuid4()],
        )
        assert len(s.participating_entities) == 3


# =============================================================================
# SceneUpdate
# =============================================================================


class TestSceneUpdate:
    def test_empty(self):
        u = SceneUpdate()
        assert u.title is None

    def test_status_transition(self):
        u = SceneUpdate(status=SceneStatus.COMPLETED, summary="Battle resolved")
        assert u.status == SceneStatus.COMPLETED


# =============================================================================
# SceneResponse
# =============================================================================


class TestSceneResponse:
    def test_minimal(self):
        s = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="x",
            purpose="",
            status=SceneStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert s.turns == []  # default
        assert s.temporal_mode == TemporalMode.PRESENT  # default
        assert s.summary == ""  # default

    def test_with_turns(self):
        turn = TurnResponse(
            turn_id=uuid4(),
            speaker=Speaker.USER,
            text="Hi",
            timestamp=datetime.utcnow(),
        )
        s = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="x",
            purpose="",
            status=SceneStatus.COMPLETED,
            turns=[turn],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        assert len(s.turns) == 1
        assert s.completed_at is not None


# =============================================================================
# SceneFilter
# =============================================================================


class TestSceneFilter:
    def test_defaults(self):
        f = SceneFilter()
        assert f.limit == 50
        assert f.sort_by == "created_at"
        assert f.sort_order == "desc"

    def test_with_filters(self):
        f = SceneFilter(
            story_id=uuid4(),
            status=SceneStatus.COMPLETED,
            limit=100,
        )
        assert f.status == SceneStatus.COMPLETED

    def test_invalid_sort_order_fails(self):
        with pytest.raises(Exception):
            SceneFilter(sort_order="invalid")

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            SceneFilter(limit=0)
        with pytest.raises(Exception):
            SceneFilter(limit=2000)  # > 1000


# =============================================================================
# SceneListResponse
# =============================================================================


class TestSceneListResponse:
    def test_empty(self):
        r = SceneListResponse(scenes=[], total=0, limit=50, offset=0)
        assert r.scenes == []
