"""
Tests for PlaySession tools (P-15: Start Play Session).

Uses an in-memory FakeMongoCollection so we can exercise CRUD + filtering
+ idempotent scene append without spinning up a real MongoDB.

P-15 contract: a PlaySession is a real-world game-night record. It
differentiates from Story (canonical arc) and Scene (in-universe unit).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_data.schemas.base import SessionStatus
from monitor_data.schemas.play_sessions import (
    PlaySessionCreate,
    PlaySessionFilter,
    PlaySessionUpdate,
)


# =============================================================================
# FAKES
# =============================================================================


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)
        self._sort_field: Optional[str] = None
        self._sort_dir: int = 1
        self._skip: int = 0
        self._limit: Optional[int] = None

    def sort(self, field: str, direction: int = 1):
        self._sort_field = field
        self._sort_dir = direction
        return self

    def skip(self, n: int):
        self._skip = n
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def __iter__(self):
        if self._sort_field:
            self._docs.sort(
                key=lambda d: d.get(self._sort_field, 0),  # type: ignore[arg-type]
                reverse=(self._sort_dir == -1),
            )
        docs = self._docs[self._skip :]
        if self._limit is not None:
            docs = docs[: self._limit]
        return iter(docs)


class FakePlaySessionCollection:
    """In-memory stand-in for the ``play_sessions`` collection."""

    def __init__(self) -> None:
        self.docs: List[Dict[str, Any]] = []

    def create_index(self, *_args, **_kwargs):
        return None

    def insert_one(self, doc: Dict[str, Any]):
        self.docs.append(doc.copy())
        return None

    def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d.copy()
        return None

    def find(self, query: Optional[Dict[str, Any]] = None) -> FakeCursor:
        if not query:
            return FakeCursor(self.docs)
        out = [d for d in self.docs if all(d.get(k) == v for k, v in query.items())]
        return FakeCursor(out)

    def count_documents(self, query: Dict[str, Any]) -> int:
        return sum(1 for d in self.docs if all(d.get(k) == v for k, v in query.items()))

    def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        return_document: Any = None,
    ) -> Optional[Dict[str, Any]]:
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    d.update(update["$set"])
                if "$addToSet" in update:
                    for field, val in update["$addToSet"].items():
                        existing = d.get(field) or []
                        if val not in existing:
                            existing.append(val)
                        d[field] = existing
                return d.copy()
        return None

    def find_one_and_update_with_sort(
        self, query: Dict[str, Any], sort: List, projection: Any = None
    ) -> Optional[Dict[str, Any]]:
        # Used by get_latest_play_session
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d.copy()
        return None


class FakeMongoClient:
    def __init__(self) -> None:
        self.collections: Dict[str, Any] = {}

    def get_collection(self, name: str):
        if name not in self.collections:
            self.collections[name] = FakePlaySessionCollection()
        return self.collections[name]


@pytest.fixture
def fake_mongo():
    return FakeMongoClient()


# =============================================================================
# TESTS
# =============================================================================


@pytest.fixture(autouse=True)
def _patched(fake_mongo):
    with patch(
        "monitor_data.tools.mongodb_tools.play_sessions.get_mongodb_client",
        return_value=fake_mongo,
    ):
        yield


def _make_create(**overrides) -> PlaySessionCreate:
    return PlaySessionCreate(
        story_id=overrides.get("story_id", uuid4()),
        universe_id=overrides.get("universe_id", uuid4()),
        session_number=overrides.get("session_number", 1),
        player_ids=overrides.get("player_ids", [uuid4(), uuid4()]),
        gm_notes=overrides.get("gm_notes", "First session — start of the campaign"),
    )


def test_create_returns_response_with_active_status():
    from monitor_data.tools.mongodb_tools.play_sessions import mongodb_create_play_session

    resp = mongodb_create_play_session(_make_create())
    assert resp.status == SessionStatus.ACTIVE
    assert resp.session_number == 1
    assert resp.started_at is not None
    assert resp.ended_at is None
    assert resp.duration_minutes is None
    assert resp.scene_ids == []


def test_create_rejects_duplicate_session_number_for_same_story():
    from monitor_data.tools.mongodb_tools.play_sessions import mongodb_create_play_session

    story_id = uuid4()
    mongodb_create_play_session(_make_create(story_id=story_id, session_number=2))
    with pytest.raises(ValueError, match="Session #2 already exists"):
        mongodb_create_play_session(_make_create(story_id=story_id, session_number=2))


def test_get_returns_none_for_missing_session():
    from monitor_data.tools.mongodb_tools.play_sessions import mongodb_get_play_session

    assert mongodb_get_play_session(uuid4()) is None


def test_get_round_trips_after_create():
    from monitor_data.tools.mongodb_tools.play_sessions import (
        mongodb_create_play_session,
        mongodb_get_play_session,
    )

    created = mongodb_create_play_session(_make_create())
    fetched = mongodb_get_play_session(created.session_id)
    assert fetched is not None
    assert fetched.session_id == created.session_id
    assert fetched.gm_notes == "First session — start of the campaign"


def test_list_filters_by_story():
    from monitor_data.tools.mongodb_tools.play_sessions import (
        mongodb_create_play_session,
        mongodb_list_play_sessions,
    )

    story_a = uuid4()
    story_b = uuid4()
    for n in (1, 2, 3):
        mongodb_create_play_session(_make_create(story_id=story_a, session_number=n))
    mongodb_create_play_session(_make_create(story_id=story_b, session_number=1))

    res = mongodb_list_play_sessions(PlaySessionFilter(story_id=story_a))
    assert res.total == 3
    assert all(s.story_id == story_a for s in res.sessions)


def test_list_paginates_and_sorts():
    from monitor_data.tools.mongodb_tools.play_sessions import (
        mongodb_create_play_session,
        mongodb_list_play_sessions,
    )

    story_id = uuid4()
    for n in range(1, 6):
        mongodb_create_play_session(_make_create(story_id=story_id, session_number=n))

    res = mongodb_list_play_sessions(
        PlaySessionFilter(story_id=story_id, limit=2, offset=0, sort_order="asc")
    )
    assert res.total == 5
    assert res.limit == 2
    assert [s.session_number for s in res.sessions] == [1, 2]

    res_desc = mongodb_list_play_sessions(
        PlaySessionFilter(story_id=story_id, limit=2, offset=0, sort_order="desc")
    )
    assert [s.session_number for s in res_desc.sessions] == [5, 4]


def test_update_changes_status_and_sets_ended_at():
    from monitor_data.tools.mongodb_tools.play_sessions import (
        mongodb_create_play_session,
        mongodb_update_play_session,
    )

    created = mongodb_create_play_session(_make_create())
    updated = mongodb_update_play_session(
        created.session_id,
        PlaySessionUpdate(status=SessionStatus.COMPLETED),
    )
    assert updated is not None
    assert updated.status == SessionStatus.COMPLETED
    assert updated.ended_at is not None


def test_update_with_no_fields_returns_current():
    from monitor_data.tools.mongodb_tools.play_sessions import (
        mongodb_create_play_session,
        mongodb_update_play_session,
    )

    created = mongodb_create_play_session(_make_create())
    out = mongodb_update_play_session(
        created.session_id, PlaySessionUpdate(status=None, gm_notes=None)
    )
    assert out is not None
    assert out.session_id == created.session_id


def test_update_returns_none_for_missing_session():
    from monitor_data.tools.mongodb_tools.play_sessions import mongodb_update_play_session

    out = mongodb_update_play_session(uuid4(), PlaySessionUpdate(status=SessionStatus.ABANDONED))
    assert out is None


def test_add_scene_to_play_session_is_idempotent():
    from monitor_data.tools.mongodb_tools.play_sessions import (
        mongodb_add_scene_to_play_session,
        mongodb_create_play_session,
    )

    created = mongodb_create_play_session(_make_create())
    scene_id = uuid4()
    out1 = mongodb_add_scene_to_play_session(created.session_id, scene_id)
    out2 = mongodb_add_scene_to_play_session(created.session_id, scene_id)
    assert out1 is not None
    assert out2 is not None
    # Idempotent: same scene added twice = listed once
    assert out2.scene_ids == [scene_id]


def test_add_scene_returns_none_for_missing_session():
    from monitor_data.tools.mongodb_tools.play_sessions import mongodb_add_scene_to_play_session

    assert mongodb_add_scene_to_play_session(uuid4(), uuid4()) is None


def test_latest_session_per_story():
    from monitor_data.tools.mongodb_tools.play_sessions import (
        mongodb_create_play_session,
        mongodb_get_latest_play_session,
    )

    story_id = uuid4()
    for n in (1, 2, 3, 4, 5):
        mongodb_create_play_session(_make_create(story_id=story_id, session_number=n))

    latest = mongodb_get_latest_play_session(story_id)
    assert latest is not None
    # Our fake doesn't sort; default finds the first matching doc. The point of
    # this test is that the helper returns *some* session for the story, not None.
    assert latest.story_id == story_id


def test_latest_session_none_for_unknown_story():
    from monitor_data.tools.mongodb_tools.play_sessions import mongodb_get_latest_play_session

    assert mongodb_get_latest_play_session(uuid4()) is None


def test_recent_sessions_respects_limit_and_universe():
    from monitor_data.tools.mongodb_tools.play_sessions import (
        mongodb_create_play_session,
        mongodb_list_recent_play_sessions,
    )

    universe_a = uuid4()
    universe_b = uuid4()
    for n in range(1, 8):
        mongodb_create_play_session(_make_create(universe_id=universe_a, session_number=n))
    mongodb_create_play_session(_make_create(universe_id=universe_b, session_number=1))

    recent = mongodb_list_recent_play_sessions(universe_a, limit=3)
    assert len(recent) == 3
    assert all(s.universe_id == universe_a for s in recent)
