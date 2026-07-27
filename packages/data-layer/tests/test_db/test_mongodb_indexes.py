"""Hermetic test that MongoDBClient._create_indexes provisions the change_log
collection's indexes (R5). The append-only audit trail is queried by subject
history, type/author/transaction filters, and sorted by timestamp."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from monitor_data.db.mongodb import MongoDBClient


@pytest.mark.asyncio
async def test_create_indexes_provisions_change_log():
    client = MongoDBClient.__new__(MongoDBClient)
    # Dict-like mock DB: each collection name yields its own MagicMock.
    cols: dict[str, MagicMock] = {}
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: cols.setdefault(name, MagicMock())
    client._db = db

    await client._create_indexes()

    assert "change_log" in cols, "change_log indexes were never created"
    calls = cols["change_log"].create_index.call_args_list
    index_keys = [c.args[0] for c in calls]

    # change_id is the unique primary key.
    assert any(k == [("change_id", 1)] for k in index_keys)
    unique_call = next(c for c in calls if c.args[0] == [("change_id", 1)])
    assert unique_call.kwargs.get("unique") is True

    # Entity-history (subject_id + timestamp desc) and timestamp sort indexes.
    assert any(k == [("subject_id", 1), ("timestamp", -1)] for k in index_keys)
    assert any(k == [("timestamp", -1)] for k in index_keys)
    # Filter indexes.
    assert any(k == [("subject_type", 1)] for k in index_keys)
    assert any(k == [("transaction_id", 1)] for k in index_keys)
