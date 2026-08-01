"""Foreshadowing CRUD round-trip."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

import monitor_data.tools.mongodb_tools.foreshadowing as fs_mod
from monitor_data.tools.mongodb_tools.foreshadowing import (
    mongodb_create_foreshadowing,
    mongodb_list_open_foreshadowing,
    mongodb_mark_foreshadowing_paid,
)
from monitor_data.schemas.foreshadowing import ForeshadowingCreate


class _FakeForeshadowingCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def insert_one(self, doc: dict) -> None:
        doc["_id"] = doc.get("foreshadowing_id")
        self.docs.append(doc)

    def find(self, query: dict) -> list[dict]:
        out: list[dict] = []
        for d in self.docs:
            ok = True
            for k, v in query.items():
                if d.get(k) != v:
                    ok = False
                    break
            if ok:
                out.append(d)
        return out

    def update_one(self, query: dict, update: dict) -> None:
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                d.update(update.get("$set", {}))
                return


class _FakeMongoClient:
    def __init__(self) -> None:
        self.fs = _FakeForeshadowingCollection()

    def __getitem__(self, name: str) -> _FakeForeshadowingCollection:
        return self.fs


@pytest.fixture
def fake_mongo(monkeypatch: pytest.MonkeyPatch) -> _FakeMongoClient:
    client = _FakeMongoClient()
    monkeypatch.setattr(fs_mod, "get_mongodb_client", lambda: client)
    return client


def test_create_and_list_open(fake_mongo: _FakeMongoClient) -> None:
    scene = uuid4()
    story = uuid4()
    resp = mongodb_create_foreshadowing(
        ForeshadowingCreate(
            scene_id=scene, story_id=story, kind="plant",
            summary="The captain's eye twitches", planted_by_turn=3, target_turn=10,
        )
    )
    assert resp.summary == "The captain's eye twitches"
    assert resp.status == "open"
    items = mongodb_list_open_foreshadowing(scene, story, limit=5)
    assert len(items) == 1
    assert items[0].foreshadowing_id == resp.foreshadowing_id


def test_mark_paid_removes_from_open(fake_mongo: _FakeMongoClient) -> None:
    scene = uuid4()
    story = uuid4()
    resp = mongodb_create_foreshadowing(
        ForeshadowingCreate(
            scene_id=scene, story_id=story, kind="plant",
            summary="x", planted_by_turn=0, target_turn=0,
        )
    )
    updated = mongodb_mark_foreshadowing_paid(resp.foreshadowing_id, paid_at_turn=5)
    assert updated is not None
    assert updated.status == "paid"
    assert mongodb_list_open_foreshadowing(scene, story) == []


def test_list_filters_other_scenes(fake_mongo: _FakeMongoClient) -> None:
    s1 = uuid4()
    s2 = uuid4()
    story = uuid4()
    mongodb_create_foreshadowing(
        ForeshadowingCreate(scene_id=s1, story_id=story, kind="plant",
                           summary="a", planted_by_turn=0, target_turn=0)
    )
    mongodb_create_foreshadowing(
        ForeshadowingCreate(scene_id=s2, story_id=story, kind="plant",
                           summary="b", planted_by_turn=0, target_turn=0)
    )
    assert len(mongodb_list_open_foreshadowing(s1, story, limit=5)) == 1
    assert len(mongodb_list_open_foreshadowing(s2, story, limit=5)) == 1


def test_list_caps_results(fake_mongo: _FakeMongoClient) -> None:
    scene = uuid4()
    story = uuid4()
    for i in range(7):
        mongodb_create_foreshadowing(
            ForeshadowingCreate(scene_id=scene, story_id=story, kind="plant",
                               summary=f"plant {i}", planted_by_turn=0, target_turn=0)
        )
    assert len(mongodb_list_open_foreshadowing(scene, story, limit=3)) == 3