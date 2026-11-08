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


def _mock_client() -> tuple[MongoDBClient, dict[str, MagicMock]]:
    """A MongoDBClient wired to a dict-like mock DB (one MagicMock per name)."""
    client = MongoDBClient.__new__(MongoDBClient)
    cols: dict[str, MagicMock] = {}
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: cols.setdefault(name, MagicMock())
    client._client = MagicMock()  # pretend connected so get_database() returns _db
    client._db = db
    return client, cols


@pytest.mark.asyncio
async def test_create_indexes_provisions_text_indexes():
    """Full-text indexes (the OpenSearch replacement) exist on narrative collections."""
    client, cols = _mock_client()
    await client._create_indexes()

    text = "text"
    expected = {
        "scenes": [("title", text), ("purpose", text), ("summary", text)],
        "snippets": [("text", text), ("section", text)],
        "knowledge_packs": [("name", text), ("description", text), ("intro_text", text)],
        "chat_messages": [("text", text), ("entity_name", text)],
        "lorebook_entries": [("content", text), ("comment", text)],
        "gm_notes": [("content", text)],
    }
    for coll_name, keys in expected.items():
        assert coll_name in cols, f"{coll_name} indexes were never created"
        index_keys = [c.args[0] for c in cols[coll_name].create_index.call_args_list]
        assert keys in index_keys, f"{coll_name} missing text index on {keys}"


@pytest.mark.asyncio
async def test_create_indexes_provisions_lorebook_and_gm_notes_lookups():
    client, cols = _mock_client()
    await client._create_indexes()

    lore_calls = cols["lorebook_entries"].create_index.call_args_list
    assert any(c.args[0] == [("id", 1)] and c.kwargs.get("unique") for c in lore_calls)
    assert any(c.args[0] == [("character_id", 1), ("is_active", 1)] for c in lore_calls)

    gm_calls = cols["gm_notes"].create_index.call_args_list
    assert any(c.args[0] == [("universe_id", 1)] and c.kwargs.get("unique") for c in gm_calls)


@pytest.mark.asyncio
async def test_ensure_indexes_for_prefix_applies_same_spec():
    """A world prefix (e.g. 'lotr_') gets the full index set incl. text indexes."""
    client, cols = _mock_client()
    await client.ensure_indexes_for_prefix("lotr_")

    assert "lotr_scenes" in cols
    scene_keys = [c.args[0] for c in cols["lotr_scenes"].create_index.call_args_list]
    assert [("scene_id", 1)] in scene_keys
    assert any(k == [("title", "text"), ("purpose", "text"), ("summary", "text")] for k in scene_keys)
    assert "lotr_knowledge_packs" in cols
    pack_keys = [c.args[0] for c in cols["lotr_knowledge_packs"].create_index.call_args_list]
    assert any(k and k[0][1] == "text" for k in pack_keys)
    # Default (unprefixed) collections must NOT be touched by the prefix call.
    assert "scenes" not in cols


@pytest.mark.asyncio
async def test_ensure_indexes_for_prefix_empty_is_noop():
    client, cols = _mock_client()
    await client.ensure_indexes_for_prefix("")
    await client.ensure_indexes_for_prefix("   ")
    assert cols == {}
