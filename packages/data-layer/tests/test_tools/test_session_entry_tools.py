"""Unit tests for Session Recorder entry tools (CF-1 / G03 strike & edit).

Covers soft-delete semantics (strike keeps an audit trail; hard delete is
rejected in v1), in-place editing, the undo/restore path, struck filtering in
lists, and Redis message-cache invalidation on every write.

Run:
    uv run pytest packages/data-layer/tests/test_tools/test_session_entry_tools.py -q
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from monitor_data.tools.mongodb_tools import (
    STRIKE_REASON,
    mongodb_delete_session_entry,
    mongodb_get_session_entry,
    mongodb_list_session_entries,
    mongodb_restore_session_entry,
    mongodb_update_session_entry,
)


class _FakeCollection:
    """Minimal Mongo collection stand-in for the ``chat_messages`` docs."""

    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs: dict[str, dict[str, Any]] = {d["id"]: dict(d) for d in (docs or [])}
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def find_one(self, query: dict[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        key = next(iter(query))
        doc = self.docs.get(str(query[key]))
        return dict(doc) if doc else None

    def find(self, query: dict[str, Any], *_args: Any, sort: Any = None, **_kwargs: Any) -> Any:
        rows = [dict(d) for d in self.docs.values()]
        if "session_id" in query:
            rows = [r for r in rows if r.get("session_id") == query["session_id"]]
        if "struck" in query and isinstance(query["struck"], dict) and "$ne" in query["struck"]:
            rows = [r for r in rows if r.get("struck") != query["struck"]["$ne"]]
        rows.sort(key=lambda r: str(r.get("timestamp") or ""))
        return iter(rows)

    def update_one(self, flt: dict[str, Any], update: dict[str, Any]) -> None:
        self.updates.append((flt, update))
        key = next(iter(flt))
        doc = self.docs.get(str(flt[key]))
        if doc is None:
            return
        if "$set" in update:
            doc.update(update["$set"])
        if "$unset" in update:
            for field in update["$unset"]:
                doc.pop(field, None)


@pytest.fixture
def entry_doc() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "session_id": "rec-1",
        "role": "player",
        "content": "Mira pocketed the key",
        "timestamp": "2026-11-10T20:00:00+00:00",
        "metadata": {},
    }


@pytest.fixture
def fake_coll(entry_doc: dict[str, Any]) -> _FakeCollection:
    return _FakeCollection([entry_doc])


@pytest.fixture
def mongo(fake_coll: _FakeCollection) -> Mock:
    client = Mock()
    client.get_collection.return_value = fake_coll
    return client


@pytest.fixture
def redis() -> Mock:
    client = Mock()
    client.delete.return_value = 1
    return client


def _patched(mongo: Mock, redis: Mock):
    return (
        patch(
            "monitor_data.tools.mongodb_tools.session_entries.get_mongodb_client",
            return_value=mongo,
        ),
        patch("monitor_data.db.redis.get_redis_client", return_value=redis),
    )


# =============================================================================
# Reads
# =============================================================================


def test_get_session_entry_returns_public_doc(mongo: Mock, redis: Mock, entry_doc: dict[str, Any]):
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        result = mongodb_get_session_entry(entry_doc["id"])

    assert result is not None
    assert result["id"] == entry_doc["id"]
    assert result["content"] == "Mira pocketed the key"
    assert result["struck"] is False
    assert result["struck_proposal_ids"] == []
    assert "_id" not in result


def test_get_session_entry_missing_returns_none(mongo: Mock, redis: Mock):
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        assert mongodb_get_session_entry(str(uuid4())) is None


def test_list_excludes_struck_by_default(mongo: Mock, redis: Mock, entry_doc: dict[str, Any]):
    struck = {**entry_doc, "id": str(uuid4()), "content": "wrong take", "struck": True}
    mongo.get_collection.return_value = _FakeCollection([entry_doc, struck])
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        rows = mongodb_list_session_entries("rec-1")

    assert [r["id"] for r in rows] == [entry_doc["id"]]


def test_list_include_struck_returns_audit_rows(mongo: Mock, redis: Mock, entry_doc: dict[str, Any]):
    struck = {**entry_doc, "id": str(uuid4()), "content": "wrong take", "struck": True}
    mongo.get_collection.return_value = _FakeCollection([entry_doc, struck])
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        rows = mongodb_list_session_entries("rec-1", include_struck=True)

    assert len(rows) == 2
    assert any(r["struck"] for r in rows)


# =============================================================================
# Edit
# =============================================================================


def test_update_sets_content_and_edited_at(mongo: Mock, redis: Mock, entry_doc: dict[str, Any]):
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        result = mongodb_update_session_entry(entry_doc["id"], "  Mira pocketed the chapel key  ")

    assert result["content"] == "Mira pocketed the chapel key"
    assert result["edited_at"]
    # Cache invalidation keeps the recorder's next read fresh.
    redis.delete.assert_called_once_with("chat_messages:rec-1")


def test_update_missing_entry_raises(mongo: Mock, redis: Mock):
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        with pytest.raises(ValueError, match="not found"):
            mongodb_update_session_entry(str(uuid4()), "text")


def test_update_empty_text_raises(mongo: Mock, redis: Mock, entry_doc: dict[str, Any]):
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        with pytest.raises(ValueError, match="text must not be empty"):
            mongodb_update_session_entry(entry_doc["id"], "   ")


def test_update_struck_entry_raises(mongo: Mock, redis: Mock, entry_doc: dict[str, Any]):
    struck = {**entry_doc, "struck": True}
    mongo.get_collection.return_value = _FakeCollection([struck])
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        with pytest.raises(ValueError, match="struck"):
            mongodb_update_session_entry(entry_doc["id"], "sneaky edit")


# =============================================================================
# Strike (soft delete)
# =============================================================================


def test_delete_soft_marks_struck_with_audit_trail(
    mongo: Mock, redis: Mock, entry_doc: dict[str, Any], fake_coll: _FakeCollection
):
    mongo_patch, redis_patch = _patched(mongo, redis)
    proposal_ids = [str(uuid4()), str(uuid4())]
    with mongo_patch, redis_patch:
        result = mongodb_delete_session_entry(
            entry_doc["id"],
            soft=True,
            retracted_proposal_ids=proposal_ids,
        )

    assert result["struck"] is True
    assert result["struck_at"]
    assert result["struck_reason"] == STRIKE_REASON
    assert result["struck_proposal_ids"] == proposal_ids
    # The doc itself is kept — CF-8 and the audit list need the history.
    assert fake_coll.docs[entry_doc["id"]]["content"] == "Mira pocketed the key"
    redis.delete.assert_called_once_with("chat_messages:rec-1")


def test_delete_hard_rejected_in_v1(mongo: Mock, redis: Mock, entry_doc: dict[str, Any]):
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        with pytest.raises(ValueError, match="not supported in v1"):
            mongodb_delete_session_entry(entry_doc["id"], soft=False)


def test_delete_missing_entry_raises(mongo: Mock, redis: Mock):
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        with pytest.raises(ValueError, match="not found"):
            mongodb_delete_session_entry(str(uuid4()))


# =============================================================================
# Restore (the one undo)
# =============================================================================


def test_restore_clears_strike_and_returns_retracted_ids(mongo: Mock, redis: Mock, entry_doc: dict[str, Any]):
    proposal_ids = [str(uuid4())]
    struck = {
        **entry_doc,
        "struck": True,
        "struck_at": "2026-11-10T20:05:00+00:00",
        "struck_reason": STRIKE_REASON,
        "struck_proposal_ids": proposal_ids,
    }
    mongo.get_collection.return_value = _FakeCollection([struck])
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        result = mongodb_restore_session_entry(entry_doc["id"])

    assert result["struck"] is False
    assert result["struck_at"] is None
    assert result["restored_proposal_ids"] == proposal_ids
    redis.delete.assert_called_once_with("chat_messages:rec-1")


def test_restore_missing_entry_raises(mongo: Mock, redis: Mock):
    mongo_patch, redis_patch = _patched(mongo, redis)
    with mongo_patch, redis_patch:
        with pytest.raises(ValueError, match="not found"):
            mongodb_restore_session_entry(str(uuid4()))
