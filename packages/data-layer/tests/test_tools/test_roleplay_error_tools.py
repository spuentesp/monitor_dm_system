from datetime import UTC, datetime
from uuid import uuid4

import pytest

from monitor_data.schemas.roleplay_errors import (
    RoleplayError,
    RoleplayErrorCategory,
    RoleplayErrorFilter,
    RoleplayErrorSource,
)
from monitor_data.tools.mongodb_tools.roleplay_errors import (
    mongodb_list_roleplay_errors,
    mongodb_record_roleplay_error,
)


class _FakeRoleplayErrorsCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(doc)

    def count_documents(self, query):
        return len(self._match(query))

    def find(self, query):
        return _FakeCursor(self._match(query))

    def _match(self, query):
        results = []
        for doc in self.docs:
            match = True
            for key, value in query.items():
                if key == "occurred_at" and isinstance(value, dict):
                    if "$gte" in value and doc["occurred_at"] < value["$gte"]:
                        match = False
                    if "$lte" in value and doc["occurred_at"] > value["$lte"]:
                        match = False
                elif doc.get(key) != value:
                    match = False
            if match:
                results.append(doc)
        return results


class _FakeCursor:
    def __init__(self, results):
        self.results = list(results)

    def sort(self, key, direction):
        self.results = sorted(self.results, key=lambda d: d.get(key), reverse=(direction == -1))
        return self

    def skip(self, offset):
        self.results = self.results[offset:]
        return self

    def limit(self, limit):
        self.results = self.results[:limit]
        return self

    def __iter__(self):
        return iter(self.results)


class _FakeMongo:
    def __init__(self):
        self.collection = _FakeRoleplayErrorsCollection()

    def get_collection(self, name):
        assert name == "roleplay_errors"
        return self.collection


def test_record_roleplay_error_round_trips(monkeypatch):
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.roleplay_errors.get_mongodb_client",
        lambda: fake_mongo,
    )

    scene_id = uuid4()
    story_id = uuid4()
    params = RoleplayError(
        source=RoleplayErrorSource.SCENE_LOOP,
        category=RoleplayErrorCategory.MEMORY_PERSIST_NOT_FOUND,
        message="Entity not found",
        fatal=False,
        scene_id=scene_id,
        story_id=story_id,
    )

    result = mongodb_record_roleplay_error(params)

    assert result.source == RoleplayErrorSource.SCENE_LOOP
    assert result.category == RoleplayErrorCategory.MEMORY_PERSIST_NOT_FOUND
    assert result.message == "Entity not found"
    assert result.scene_id == scene_id
    assert result.story_id == story_id
    assert len(fake_mongo.collection.docs) == 1


def test_list_roleplay_errors_filters_by_category(monkeypatch):
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.roleplay_errors.get_mongodb_client",
        lambda: fake_mongo,
    )

    mongodb_record_roleplay_error(
        RoleplayError(
            source=RoleplayErrorSource.SCENE_LOOP,
            category=RoleplayErrorCategory.MEMORY_PERSIST_NOT_FOUND,
            message="err1",
        )
    )
    mongodb_record_roleplay_error(
        RoleplayError(
            source=RoleplayErrorSource.GM_AGENT,
            category=RoleplayErrorCategory.GM_DECISION_FAILED,
            message="err2",
        )
    )

    result = mongodb_list_roleplay_errors(RoleplayErrorFilter(category=RoleplayErrorCategory.GM_DECISION_FAILED))

    assert result.total == 1
    assert len(result.errors) == 1
    assert result.errors[0].message == "err2"


def test_list_roleplay_errors_filters_by_scene_and_fatal(monkeypatch):
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.roleplay_errors.get_mongodb_client",
        lambda: fake_mongo,
    )

    scene_id = uuid4()
    other_scene_id = uuid4()
    mongodb_record_roleplay_error(
        RoleplayError(
            source=RoleplayErrorSource.RESOLVER,
            category=RoleplayErrorCategory.RESOLVER_CHECK_FAILED,
            message="fatal one",
            fatal=True,
            scene_id=scene_id,
        )
    )
    mongodb_record_roleplay_error(
        RoleplayError(
            source=RoleplayErrorSource.RESOLVER,
            category=RoleplayErrorCategory.RESOLVER_CHECK_FAILED,
            message="non-fatal, other scene",
            fatal=False,
            scene_id=other_scene_id,
        )
    )

    result = mongodb_list_roleplay_errors(RoleplayErrorFilter(scene_id=scene_id, fatal=True))

    assert result.total == 1
    assert result.errors[0].message == "fatal one"


def test_convert_roleplay_error_doc_raises_on_malformed_doc(monkeypatch):
    """Regression guard: no legacy-coercion path for a malformed record —
    a bad category value must raise loudly, not be silently swallowed
    (the exact failure mode that caused a real crash in the ingestion
    module's two-shapes-for-one-field last_error handling)."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.roleplay_errors.get_mongodb_client",
        lambda: fake_mongo,
    )
    fake_mongo.collection.docs.append(
        {
            "error_id": str(uuid4()),
            "occurred_at": datetime.now(UTC),
            "source": "scene_loop",
            "category": "not_a_real_category",
            "llm_error_class": None,
            "message": "boom",
            "detail": None,
            "fatal": False,
            "universe_id": None,
            "story_id": None,
            "scene_id": None,
            "conversation_id": None,
            "turn_id": None,
            "entity_id": None,
        }
    )

    with pytest.raises(ValueError):
        mongodb_list_roleplay_errors(RoleplayErrorFilter())
