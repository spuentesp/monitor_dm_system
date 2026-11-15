"""Unit tests for the interrupted-correction scan tools (auto-reconciler).

The reconciler sweeps for proposals whose knowledge-correction accept
started (``knowledge_retraction_checkpoint``) but never recorded the
verdict (``knowledge_correction_applied``). Stalled corrections carry
``knowledge_reconciliation_error`` and must not be swept again.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from monitor_data.db.mongodb import MongoDBClient
from monitor_data.tools.mongodb_tools.proposals import (
    mongodb_find_interrupted_corrections,
    mongodb_mark_correction_stalled,
)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch):
    import mongomock
    from monitor_data.db import mongodb as mongodb_module
    from monitor_data.tools.mongodb_tools import proposals as proposals_module

    client = mongomock.MongoClient()
    db = client["monitor"]
    db.create_collection("proposed_changes")

    holder = MongoDBClient()
    holder._client = client
    holder._db = db
    holder._indexes_created = True

    monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: holder)
    monkeypatch.setattr(proposals_module, "get_mongodb_client", lambda: holder)
    return db


def _doc(store, *, status="pending", checkpoint=True, applied=False, stalled=False) -> str:
    proposal_id = str(uuid4())
    doc = {"proposal_id": proposal_id, "status": status, "content": {}}
    if checkpoint:
        doc["knowledge_retraction_checkpoint"] = {"memory_id": "m"}
    if applied:
        doc["knowledge_correction_applied"] = True
    if stalled:
        doc["knowledge_reconciliation_error"] = "moved under us"
    store["proposed_changes"].insert_one(doc)
    return proposal_id


def test_finds_only_unfinished_checkpointed_accepts(store):
    expected = _doc(store)
    _doc(store, checkpoint=False)
    _doc(store, applied=True)
    _doc(store, status="accepted")
    _doc(store, stalled=True)
    found = [d["proposal_id"] for d in mongodb_find_interrupted_corrections()]
    assert found == [expected]


def test_limit_is_honoured(store):
    for _ in range(3):
        _doc(store)
    assert len(mongodb_find_interrupted_corrections(limit=2)) == 2


def test_mark_stalled_excludes_the_correction_from_future_sweeps(store):
    proposal_id = _doc(store)
    mongodb_mark_correction_stalled(uuid4(), "no-op for an unknown proposal")
    assert len(mongodb_find_interrupted_corrections()) == 1
    from uuid import UUID

    mongodb_mark_correction_stalled(UUID(proposal_id), "The attribution changed")
    assert mongodb_find_interrupted_corrections() == []
