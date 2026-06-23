"""
API endpoint tests for story operations.

Tests story schemas and route structure without real DB connections.
"""

from __future__ import annotations

from uuid import uuid4
from datetime import datetime, timezone

from monitor_data.schemas.base import StoryStatus, StoryType


class TestStoryRoutesExist:
    def test_story_router_exists(self):
        from monitor_ui.routers.stories import router

        assert router is not None


class TestStoryCreateSchema:
    def test_minimal(self):
        from monitor_data.schemas.stories import StoryCreate

        s = StoryCreate(universe_id=uuid4(), title="Test Story")
        assert s.title == "Test Story"
        assert s.story_type == StoryType.CAMPAIGN
        assert s.status == StoryStatus.PLANNED

    def test_with_pcs(self):
        from monitor_data.schemas.stories import StoryCreate

        pc_ids = [uuid4(), uuid4()]
        s = StoryCreate(universe_id=uuid4(), title="Test", pc_ids=pc_ids)
        assert len(s.pc_ids) == 2


class TestStoryResponseSchema:
    def test_response_fields(self):
        from monitor_data.schemas.stories import StoryResponse

        now = datetime.now(timezone.utc)
        r = StoryResponse(
            id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            theme="",
            premise="",
            story_type=StoryType.CAMPAIGN,
            status=StoryStatus.PLANNED,
            created_at=now,
            pc_ids=[],
            game_system_id=None,
        )
        assert r.story_type == StoryType.CAMPAIGN


class TestStoryFilter:
    def test_filter_defaults(self):
        from monitor_data.schemas.stories import StoryFilter

        f = StoryFilter()
        assert f.limit == 50
        assert f.offset == 0


class TestBrowseRoutes:
    """T-072 browse endpoints: list stories / scenes / turns / threads."""

    def _route_paths(self, router):
        return {getattr(r, "path", "") for r in router.routes}

    def test_list_and_drilldown_routes_exist(self):
        from monitor_ui.routers.stories import router, scenes_router

        paths = self._route_paths(router)
        assert "" in paths  # GET /api/stories
        assert "/{story_id}/scenes" in paths
        assert "/{story_id}/threads" in paths
        assert "/scenes/{scene_id}/turns" in self._route_paths(scenes_router)

    def test_list_stories_maps_neo4j_records(self, monkeypatch):
        import asyncio

        from monitor_data.schemas.stories import StoryListResponse, StoryResponse
        from monitor_ui.routers import stories as stories_mod

        record = StoryResponse(
            id=uuid4(),
            universe_id=uuid4(),
            title="The Sunken Vault",
            theme="mystery",
            premise="Something stirs under Ironwatch.",
            story_type=StoryType.CAMPAIGN,
            status=StoryStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            pc_ids=[],
            game_system_id=None,
            scene_count=3,
        )

        from monitor_data.tools import neo4j_tools

        monkeypatch.setattr(
            neo4j_tools,
            "neo4j_list_stories",
            lambda params: StoryListResponse(
                stories=[record], total=1, limit=params.limit, offset=params.offset
            ),
        )

        out = asyncio.get_event_loop().run_until_complete(
            stories_mod.list_stories(universe_id=str(record.universe_id))
        )
        assert out.total == 1
        assert out.stories[0].title == "The Sunken Vault"
        assert out.stories[0].scene_count == 3
        assert out.stories[0].status == "active"
