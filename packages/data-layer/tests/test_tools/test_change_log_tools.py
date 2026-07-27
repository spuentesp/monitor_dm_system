"""Hermetic unit tests for the append-only ChangeLog mongodb tools (T-064).

The schema is covered by tests/contracts/test_change_log_contracts.py; this
file covers the *tool* functions (append / list / builder) with a mocked
MongoDB client.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from monitor_data.schemas.change_log import (
    ChangeLogFilter,
    ChangeSubjectType,
    ChangeType,
)
from monitor_data.tools.mongodb_tools.change_log import (
    make_change_log_entry,
    mongodb_append_change_log,
    mongodb_list_change_log,
)

_MODULE = "monitor_data.tools.mongodb_tools.change_log.get_mongodb_client"


def test_make_change_log_entry_defaults():
    sid = uuid4()
    entry = make_change_log_entry(subject_type=ChangeSubjectType.ENTITY, subject_id=sid)
    assert entry.subject_type == ChangeSubjectType.ENTITY
    assert entry.subject_id == sid
    assert entry.change_type == ChangeType.CREATED
    assert entry.author == "CanonKeeper"
    assert entry.authority.value == "system"
    assert entry.change_id is not None


@patch(_MODULE)
def test_append_inserts_serialized_doc(mock_client):
    coll = MagicMock()
    mock_client.return_value.get_collection.return_value = coll

    entry = make_change_log_entry(
        subject_type=ChangeSubjectType.FACT,
        subject_id=uuid4(),
        reason="canonized by test",
    )
    mongodb_append_change_log(entry)

    coll.insert_one.assert_called_once()
    doc = coll.insert_one.call_args[0][0]
    assert doc["subject_type"] == "fact"
    assert doc["change_type"] == "created"
    assert doc["reason"] == "canonized by test"
    # UUIDs serialized to strings for Mongo.
    assert isinstance(doc["subject_id"], str)
    assert isinstance(doc["change_id"], str)


@patch(_MODULE)
def test_append_is_best_effort_and_never_raises(mock_client):
    # Auditing must never break a canon commit — a client failure is swallowed.
    mock_client.return_value.get_collection.side_effect = RuntimeError("mongo down")
    entry = make_change_log_entry(subject_type=ChangeSubjectType.AXIOM, subject_id=uuid4())
    mongodb_append_change_log(entry)  # must not raise


@patch(_MODULE)
def test_list_builds_query_and_parses(mock_client):
    coll = MagicMock()
    mock_client.return_value.get_collection.return_value = coll
    coll.count_documents.return_value = 1

    now = datetime.now(UTC)
    doc = {
        "change_id": str(uuid4()),
        "subject_type": "entity",
        "subject_id": str(uuid4()),
        "change_type": "created",
        "timestamp": now,
        "author": "CanonKeeper",
        "authority": "system",
    }
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = [doc]
    coll.find.return_value = cursor

    uid = uuid4()
    resp = mongodb_list_change_log(ChangeLogFilter(subject_type=ChangeSubjectType.ENTITY, subject_id=uid, limit=10))

    assert resp.total == 1
    assert len(resp.entries) == 1
    assert resp.entries[0].subject_type == ChangeSubjectType.ENTITY
    # subject_type + subject_id became query filters.
    query = coll.find.call_args[0][0]
    assert query["subject_type"] == "entity"
    assert query["subject_id"] == str(uid)
    # desc sort by default.
    cursor.sort.assert_called_once_with("timestamp", -1)
