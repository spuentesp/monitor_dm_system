"""
Property-based tests for scene state invariants.

Tests that scene state transitions follow the valid FSM:
  ACTIVE → FINALIZING → (COMPLETED)
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from uuid import uuid4

from monitor_data.schemas.scenes import SceneCreate, SceneUpdate
from monitor_data.schemas.base import SceneStatus


class TestSceneStatusFSM:
    def test_status_values(self):
        assert SceneStatus.ACTIVE.value == "active"
        assert SceneStatus.FINALIZING.value == "finalizing"

    def test_valid_transitions(self):
        s = SceneCreate(story_id=uuid4(), universe_id=uuid4(), title="Test Scene")
        assert s.status == SceneStatus.ACTIVE

        u = SceneUpdate(status=SceneStatus.FINALIZING)
        assert u.status == SceneStatus.FINALIZING


class TestSceneCreate:
    @given(
        title=st.text(min_size=1, max_size=100),
        purpose=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=50)
    def test_scene_create_with_title(self, title, purpose):
        s = SceneCreate(story_id=uuid4(), universe_id=uuid4(), title=title, purpose=purpose)
        assert s.title.strip() == title.strip()
        assert s.status == SceneStatus.ACTIVE

    @given(title=st.text(min_size=201, max_size=500))
    @settings(max_examples=30)
    def test_title_too_long_fails(self, title):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SceneCreate(story_id=uuid4(), universe_id=uuid4(), title=title)
