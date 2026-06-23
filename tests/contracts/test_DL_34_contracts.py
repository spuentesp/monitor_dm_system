"""
Contract tests for key schemas: stories, story_outlines, tone_profiles, tone_libraries.

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError

from monitor_data.schemas.base import StoryStatus, StoryType, Authority, CanonLevel
from monitor_data.schemas.stories import StoryCreate, StoryUpdate, StoryResponse, StoryFilter


class TestStoryType:
    def test_values(self):
        assert StoryType.CAMPAIGN.value == "campaign"
        assert StoryType.ARC.value == "arc"
        assert StoryType.EPISODE.value == "episode"
        assert StoryType.ONE_SHOT.value == "one_shot"


class TestStoryStatus:
    def test_values(self):
        assert StoryStatus.PLANNED.value == "planned"
        assert StoryStatus.ACTIVE.value == "active"
        assert StoryStatus.COMPLETED.value == "completed"
        assert StoryStatus.ABANDONED.value == "abandoned"


class TestStoryCreate:
    def test_minimal(self):
        s = StoryCreate(universe_id=uuid4(), title="The Lost Mines")
        assert s.title == "The Lost Mines"
        assert s.story_type == StoryType.CAMPAIGN
        assert s.status == StoryStatus.PLANNED

    def test_title_required(self):
        with pytest.raises(ValidationError):
            StoryCreate(universe_id=uuid4(), title="")


class TestStoryUpdate:
    def test_empty(self):
        u = StoryUpdate()
        assert u.title is None


class TestStoryResponse:
    def test_minimal(self):
        now = datetime.now(timezone.utc)
        r = StoryResponse(
            id=uuid4(), universe_id=uuid4(), title="Test", theme="", premise="",
            story_type=StoryType.CAMPAIGN, status=StoryStatus.PLANNED,
            created_at=now, pc_ids=[], game_system_id=None,
        )
        assert r.title == "Test"


class TestStoryFilter:
    def test_defaults(self):
        f = StoryFilter()
        assert f.limit == 50
        assert f.offset == 0
