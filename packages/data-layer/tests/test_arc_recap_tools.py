"""
Tests for the arc-recap tools (CF-12).

An arc recap is one MongoDB document per story, upserted on every refresh:
saving twice for the same story must leave exactly one document (idempotent
persistence) with a stable recap_id and an updated watermark, and reads
must return None for a story that has no recap yet.

Run:
    cd /path/to/monitor_dm_system && pytest packages/data-layer/tests/test_arc_recap_tools.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

from monitor_data.schemas.arc_recaps import ArcRecapCreate, ArcRecapDetail


class FakeCollection:
    """In-memory stand-in for the arc_recaps MongoDB collection."""

    def __init__(self) -> None:
        self.docs: list[dict] = []

    def _find(self, query: dict) -> dict | None:
        for doc in self.docs:
            if doc.get("story_id") == query.get("story_id"):
                return doc
        return None

    def find_one(self, query: dict) -> dict | None:
        doc = self._find(query)
        return dict(doc) if doc is not None else None

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> Mock:
        existing = self._find(query)
        if existing is None:
            assert upsert, "update_one without upsert must match an existing doc"
            self.docs.append(dict(update["$set"]))
        else:
            existing.update(update["$set"])
        return Mock(matched_count=1, modified_count=1)


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def get_collection(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


def _params(story_id, **overrides) -> ArcRecapCreate:
    payload = {
        "story_id": story_id,
        "universe_id": uuid4(),
        "recap_markdown": "## Major Arcs\n- The vault opened.\n",
        "detail": ArcRecapDetail.STANDARD,
        "scene_count": 3,
        "scenes_watermark": "1012-03-05T11:00:00+00:00",
        "last_scene_id": uuid4(),
    }
    payload.update(overrides)
    return ArcRecapCreate(**payload)


class TestArcRecapTools:
    def test_save_then_get_round_trips(self):
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_get_arc_recap,
            mongodb_save_arc_recap,
        )

        client = FakeClient()
        story_id = uuid4()
        params = _params(story_id)
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            saved = mongodb_save_arc_recap(params)
            loaded = mongodb_get_arc_recap(story_id)

        assert loaded is not None
        assert loaded.recap_id == saved.recap_id
        assert loaded.story_id == story_id
        assert loaded.recap_markdown == params.recap_markdown
        assert loaded.detail == ArcRecapDetail.STANDARD
        assert loaded.scene_count == 3
        assert loaded.scenes_watermark == "1012-03-05T11:00:00+00:00"
        assert loaded.last_scene_id == params.last_scene_id
        assert isinstance(loaded.generated_at, datetime)

    def test_get_returns_none_when_no_recap(self):
        from monitor_data.tools.mongodb_tools.stories import mongodb_get_arc_recap

        client = FakeClient()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            assert mongodb_get_arc_recap(uuid4()) is None

    def test_resave_is_idempotent_one_doc_per_story(self):
        """Refreshing the recap upserts in place: one doc, stable recap_id,
        updated content and watermark."""
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_get_arc_recap,
            mongodb_save_arc_recap,
        )

        client = FakeClient()
        story_id = uuid4()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            first = mongodb_save_arc_recap(_params(story_id, scene_count=3))
            second = mongodb_save_arc_recap(
                _params(
                    story_id,
                    recap_markdown="## Major Arcs\n- The vault opened.\n- The king fell.\n",
                    detail=ArcRecapDetail.DETAILED,
                    scene_count=5,
                    scenes_watermark="1012-04-02T09:30:00+00:00",
                )
            )
            loaded = mongodb_get_arc_recap(story_id)

        collection = client.collections["arc_recaps"]
        assert len(collection.docs) == 1
        assert second.recap_id == first.recap_id
        assert loaded is not None
        assert loaded.recap_markdown.endswith("The king fell.\n")
        assert loaded.detail == ArcRecapDetail.DETAILED
        assert loaded.scene_count == 5
        assert loaded.scenes_watermark == "1012-04-02T09:30:00+00:00"
        assert loaded.generated_at >= first.generated_at

    def test_recaps_are_scoped_per_story(self):
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_get_arc_recap,
            mongodb_save_arc_recap,
        )

        client = FakeClient()
        story_a, story_b = uuid4(), uuid4()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            mongodb_save_arc_recap(_params(story_a, recap_markdown="recap A"))
            mongodb_save_arc_recap(_params(story_b, recap_markdown="recap B"))
            a = mongodb_get_arc_recap(story_a)
            b = mongodb_get_arc_recap(story_b)

        assert len(client.collections["arc_recaps"].docs) == 2
        assert a is not None and a.recap_markdown == "recap A"
        assert b is not None and b.recap_markdown == "recap B"

    def test_tools_are_exported_and_registered(self):
        """The facade re-exports the tools so the MCP server auto-discovers them."""
        import monitor_data.tools.mongodb_tools as facade

        assert callable(facade.mongodb_save_arc_recap)
        assert callable(facade.mongodb_get_arc_recap)
        assert "mongodb_save_arc_recap" in facade.__all__
        assert "mongodb_get_arc_recap" in facade.__all__

    def test_authority_matrix_entries(self):
        from monitor_data.middleware.auth import check_authority

        assert check_authority("mongodb_save_arc_recap", "RecapAgent")
        assert check_authority("mongodb_save_arc_recap", "CanonKeeper")
        assert not check_authority("mongodb_save_arc_recap", "Narrator")
        assert check_authority("mongodb_get_arc_recap", "Narrator")

    def test_save_stamps_generated_at_utc(self):
        from monitor_data.tools.mongodb_tools.stories import mongodb_save_arc_recap

        client = FakeClient()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            saved = mongodb_save_arc_recap(_params(uuid4()))

        assert saved.generated_at.tzinfo is UTC
