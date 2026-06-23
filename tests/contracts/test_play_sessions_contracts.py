"""Contract tests for the PlaySession schemas.

Verifies that play_sessions Pydantic models:
- instantiate with valid data,
- enforce required fields and length / range constraints,
- enforce SessionStatus enum membership and sort_order pattern.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from monitor_data.schemas.base import SessionStatus
from monitor_data.schemas.play_sessions import (
    PlaySessionAddScene,
    PlaySessionCreate,
    PlaySessionFilter,
    PlaySessionListResponse,
    PlaySessionResponse,
    PlaySessionUpdate,
)
from pydantic import ValidationError


pytestmark = pytest.mark.unit


# =============================================================================
# PlaySessionCreate
# =============================================================================


class TestPlaySessionCreate:
    def test_minimal(self):
        s = PlaySessionCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            session_number=1,
        )
        assert s.player_ids == []
        assert s.gm_notes is None

    def test_full(self):
        s = PlaySessionCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            session_number=5,
            player_ids=[uuid4(), uuid4()],
            gm_notes="session prep",
        )
        assert len(s.player_ids) == 2
        assert s.gm_notes == "session prep"

    def test_session_number_min(self):
        with pytest.raises(ValidationError):
            PlaySessionCreate(
                story_id=uuid4(), universe_id=uuid4(), session_number=0
            )

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            PlaySessionCreate()  # type: ignore[call-arg]

    def test_gm_notes_too_long(self):
        with pytest.raises(ValidationError):
            PlaySessionCreate(
                story_id=uuid4(),
                universe_id=uuid4(),
                session_number=1,
                gm_notes="x" * 5001,
            )


# =============================================================================
# PlaySessionUpdate
# =============================================================================


class TestPlaySessionUpdate:
    def test_empty(self):
        u = PlaySessionUpdate()
        assert u.status is None
        assert u.ended_at is None
        assert u.gm_notes is None
        assert u.player_notes is None
        assert u.summary is None
        assert u.xp_awarded is None
        assert u.scene_ids is None

    def test_partial(self):
        now = datetime.now(timezone.utc)
        u = PlaySessionUpdate(status=SessionStatus.COMPLETED, ended_at=now, xp_awarded=500)
        assert u.status == SessionStatus.COMPLETED
        assert u.xp_awarded == 500

    def test_xp_negative(self):
        with pytest.raises(ValidationError):
            PlaySessionUpdate(xp_awarded=-1)

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            PlaySessionUpdate(status="bogus")  # type: ignore[arg-type]

    def test_summary_too_long(self):
        with pytest.raises(ValidationError):
            PlaySessionUpdate(summary="x" * 5001)


# =============================================================================
# PlaySessionAddScene
# =============================================================================


class TestPlaySessionAddScene:
    def test_minimal(self):
        sid = uuid4()
        scene = uuid4()
        a = PlaySessionAddScene(session_id=sid, scene_id=scene)
        assert a.session_id == sid
        assert a.scene_id == scene

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            PlaySessionAddScene()  # type: ignore[call-arg]


# =============================================================================
# PlaySessionResponse
# =============================================================================


class TestPlaySessionResponse:
    def _kwargs(self, **overrides):
        now = datetime.now(timezone.utc)
        base = {
            "session_id": uuid4(),
            "story_id": uuid4(),
            "universe_id": uuid4(),
            "session_number": 1,
            "status": SessionStatus.ACTIVE,
            "player_ids": [],
            "scene_ids": [],
            "started_at": now,
            "created_at": now,
            "updated_at": now,
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        r = PlaySessionResponse(**self._kwargs())
        assert r.gm_notes is None
        assert r.player_notes is None
        assert r.summary is None
        assert r.xp_awarded is None
        assert r.ended_at is None
        assert r.duration_minutes is None
        assert r.narrative_id is None

    def test_full(self):
        now = datetime.now(timezone.utc)
        r = PlaySessionResponse(
            **self._kwargs(
                status=SessionStatus.COMPLETED,
                ended_at=now,
                duration_minutes=180,
                gm_notes="notes",
                summary="adventurers saved the town",
                xp_awarded=1000,
                narrative_id=uuid4(),
            )
        )
        assert r.duration_minutes == 180
        assert r.xp_awarded == 1000

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            PlaySessionResponse()  # type: ignore[call-arg]


# =============================================================================
# PlaySessionFilter
# =============================================================================


class TestPlaySessionFilter:
    def test_defaults(self):
        f = PlaySessionFilter()
        assert f.story_id is None
        assert f.universe_id is None
        assert f.status is None
        assert f.limit == 50
        assert f.offset == 0
        assert f.sort_order == "asc"

    def test_with_values(self):
        f = PlaySessionFilter(
            story_id=uuid4(),
            status=SessionStatus.COMPLETED,
            sort_order="desc",
            limit=100,
        )
        assert f.status == SessionStatus.COMPLETED
        assert f.sort_order == "desc"

    def test_invalid_sort_order(self):
        with pytest.raises(ValidationError):
            PlaySessionFilter(sort_order="random")

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            PlaySessionFilter(limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            PlaySessionFilter(limit=201)

    def test_offset_min(self):
        with pytest.raises(ValidationError):
            PlaySessionFilter(offset=-1)


# =============================================================================
# PlaySessionListResponse
# =============================================================================


class TestPlaySessionListResponse:
    def test_empty(self):
        r = PlaySessionListResponse(sessions=[], total=0, limit=50, offset=0)
        assert r.sessions == []
        assert r.total == 0

    def test_with_session(self):
        now = datetime.now(timezone.utc)
        s = PlaySessionResponse(
            session_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            session_number=1,
            status=SessionStatus.ACTIVE,
            player_ids=[],
            scene_ids=[],
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        r = PlaySessionListResponse(sessions=[s], total=1, limit=50, offset=0)
        assert len(r.sessions) == 1
