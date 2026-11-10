"""
Tests for the story ledger tools (DL-4 / ST-1).

The ledger is the campaign's memory: one append-only entry per finished
scene. These tests pin that entries are appended and never overwritten,
that they keep their order, and that reading them back returns them in the
order they were written.

Run:
    cd /path/to/monitor_dm_system && pytest packages/data-layer/tests/test_story_ledger_tools.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

from monitor_data.schemas.stories import (
    StoryLedgerEntryCreate,
    StoryLedgerStateChange,
)


class FakeCollection:
    """In-memory stand-in for a MongoDB collection."""

    def __init__(self) -> None:
        self.docs: list[dict] = []

    def insert_one(self, doc: dict) -> Mock:
        self.docs.append(dict(doc))
        return Mock(inserted_id=doc.get("entry_id"))

    def count_documents(self, query: dict) -> int:
        return len([doc for doc in self.docs if doc.get("story_id") == query.get("story_id")])

    def find(self, query: dict) -> list[dict]:
        return [dict(doc) for doc in self.docs if doc.get("story_id") == query.get("story_id")]


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def get_collection(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


def _entry(story_id, **overrides) -> StoryLedgerEntryCreate:
    payload = {
        "story_id": story_id,
        "universe_id": uuid4(),
        "scene_id": uuid4(),
        "scene_index": 1,
        "summary": "The party crossed the drowned road and found the vault door sealed.",
        "state_changes": [StoryLedgerStateChange(who="Ilse", what="opened the vault map", where="the drowned road")],
        "open_questions": ["Who sealed the vault?"],
        "start_time": datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
        "end_time": datetime(1012, 3, 1, 11, 0, tzinfo=UTC),
        "world_moves": ["The miller moved his grain"],
    }
    payload.update(overrides)
    return StoryLedgerEntryCreate(**payload)


class TestStoryLedgerAppend:
    def test_the_entry_is_stored_with_its_position(self):
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_append_story_ledger_entry,
        )

        client = FakeClient()
        story_id = uuid4()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            entry = mongodb_append_story_ledger_entry(_entry(story_id))

        assert entry.sequence == 1
        assert str(entry.story_id) == str(story_id)
        assert entry.state_changes[0].who == "Ilse"
        assert entry.open_questions == ["Who sealed the vault?"]
        assert entry.world_moves == ["The miller moved his grain"]

    def test_entries_are_appended_and_never_overwritten(self):
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_append_story_ledger_entry,
        )

        client = FakeClient()
        story_id = uuid4()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            first = mongodb_append_story_ledger_entry(_entry(story_id, scene_index=1))
            second = mongodb_append_story_ledger_entry(_entry(story_id, scene_index=2))

        stored = client.get_collection("story_ledger").docs
        assert len(stored) == 2
        assert first.entry_id != second.entry_id
        assert first.sequence == 1
        assert second.sequence == 2

    def test_another_story_has_its_own_ledger(self):
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_append_story_ledger_entry,
        )

        client = FakeClient()
        mine, theirs = uuid4(), uuid4()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            mongodb_append_story_ledger_entry(_entry(mine))
            mongodb_append_story_ledger_entry(_entry(theirs))

        stored = client.get_collection("story_ledger").docs
        assert len([doc for doc in stored if doc["story_id"] == str(mine)]) == 1
        assert len([doc for doc in stored if doc["story_id"] == str(theirs)]) == 1


class TestStoryLedgerList:
    def test_entries_come_back_oldest_first(self):
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_append_story_ledger_entry,
            mongodb_list_story_ledger_entries,
        )

        client = FakeClient()
        story_id = uuid4()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            mongodb_append_story_ledger_entry(_entry(story_id, scene_index=1))
            mongodb_append_story_ledger_entry(_entry(story_id, scene_index=2))
            mongodb_append_story_ledger_entry(_entry(story_id, scene_index=3))

            entries = mongodb_list_story_ledger_entries(story_id)

        assert [entry.sequence for entry in entries] == [1, 2, 3]
        assert [entry.scene_index for entry in entries] == [1, 2, 3]

    def test_the_limit_keeps_the_newest_entries(self):
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_append_story_ledger_entry,
            mongodb_list_story_ledger_entries,
        )

        client = FakeClient()
        story_id = uuid4()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            for index in range(1, 5):
                mongodb_append_story_ledger_entry(_entry(story_id, scene_index=index))

            entries = mongodb_list_story_ledger_entries(story_id, limit=2)

        assert [entry.scene_index for entry in entries] == [3, 4]

    def test_an_empty_ledger_is_empty(self):
        from monitor_data.tools.mongodb_tools.stories import (
            mongodb_list_story_ledger_entries,
        )

        client = FakeClient()
        with patch(
            "monitor_data.tools.mongodb_tools.stories.get_mongodb_client",
            return_value=client,
        ):
            entries = mongodb_list_story_ledger_entries(uuid4())

        assert entries == []
