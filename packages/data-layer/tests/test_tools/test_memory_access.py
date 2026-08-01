"""Memory access_count batch + forget_stale_memories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

import monitor_data.tools.mongodb_tools.memories as mem_mod
from monitor_data.tools.mongodb_tools.memories import (
    mongodb_increment_memory_access,
    mongodb_forget_stale_memories,
)


class _FakeMemoriesCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.update_calls: list[dict] = []
        self.delete_calls: list[dict] = []

    def update_many(self, query: dict, update: dict) -> None:
        self.update_calls.append({"query": query, "update": update})
        ids = (query.get("memory_id") or {}).get("$in") or []
        for d in self.docs:
            if d.get("memory_id") in ids:
                d["access_count"] = d.get("access_count", 0) + update.get("$inc", {}).get(
                    "access_count", 0
                )

    def delete_many(self, query: dict):
        self.delete_calls.append(query)
        before = len(self.docs)
        kept = []
        for d in self.docs:
            scalar_match = all(
                d.get(k) == v for k, v in query.items()
                if not k.startswith("$") and not isinstance(v, dict)
            )
            if not scalar_match:
                kept.append(d)
                continue
            if "importance" in query and isinstance(query["importance"], dict):
                if "$lte" in query["importance"] and d.get("importance") > query["importance"]["$lte"]:
                    kept.append(d)
                    continue
            if "access_count" in query and isinstance(query["access_count"], dict):
                if "$lte" in query["access_count"] and d.get("access_count") > query["access_count"]["$lte"]:
                    kept.append(d)
                    continue
            if "created_at" in query and isinstance(query["created_at"], dict):
                cutoff = query["created_at"].get("$lt")
                raw = d.get("created_at")
                if cutoff and raw:
                    try:
                        d_val = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
                    except ValueError:
                        d_val = raw
                    if d_val >= cutoff:
                        kept.append(d)
                        continue
        self.docs = kept
        return type("R", (), {"deleted_count": before - len(kept)})()


class _FakeMongoClient:
    def __init__(self) -> None:
        self.mem = _FakeMemoriesCollection()

    def get_collection(self, name: str) -> _FakeMemoriesCollection:
        return self.mem


@pytest.fixture
def fake_mongo(monkeypatch: pytest.MonkeyPatch) -> _FakeMongoClient:
    client = _FakeMongoClient()
    monkeypatch.setattr(mem_mod, "get_mongodb_client", lambda: client)
    return client


def test_increment_batches(fake_mongo: _FakeMongoClient) -> None:
    ids = [str(uuid4()), str(uuid4()), str(uuid4())]
    for i in ids:
        fake_mongo.mem.docs.append({"memory_id": i, "access_count": 0})
    mongodb_increment_memory_access([uuid4(), uuid4()])
    # Two of the three docs match (we only added three IDs but pass two UUIDs to increment)
    assert len(fake_mongo.mem.update_calls) == 1
    upd = fake_mongo.mem.update_calls[0]
    assert upd["update"]["$inc"]["access_count"] == 1
    assert "$in" in upd["query"]["memory_id"]


def test_increment_empty_returns_zero(fake_mongo: _FakeMongoClient) -> None:
    assert mongodb_increment_memory_access([]) == 0
    assert fake_mongo.mem.update_calls == []


def test_forget_deletes_only_stale_low_value(fake_mongo: _FakeMongoClient) -> None:
    story_uuid = uuid4()
    story = str(story_uuid)
    old_ts = (datetime.now(UTC) - timedelta(days=365)).isoformat()
    fake_mongo.mem.docs.extend([
        # stale + low importance + never recalled -> delete
        {"memory_id": str(uuid4()), "story_id": story, "importance": 0.05,
         "access_count": 0, "created_at": old_ts},
        # high importance -> keep
        {"memory_id": str(uuid4()), "story_id": story, "importance": 0.5,
         "access_count": 0, "created_at": old_ts},
        # recalled -> keep
        {"memory_id": str(uuid4()), "story_id": story, "importance": 0.05,
         "access_count": 3, "created_at": old_ts},
    ])
    n = mongodb_forget_stale_memories(
        story_id=story_uuid, min_age_scenes=10, max_importance=0.1, max_access_count=0
    )
    assert n == 1
    assert len(fake_mongo.mem.docs) == 2


def test_forget_no_match_returns_zero(fake_mongo: _FakeMongoClient) -> None:
    assert mongodb_forget_stale_memories(story_id=uuid4()) == 0