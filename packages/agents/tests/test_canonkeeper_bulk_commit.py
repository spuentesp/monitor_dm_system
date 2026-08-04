from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


def _proposal_doc(source: str, status: str = "pending", pid: str = "") -> dict[str, Any]:
    if not pid:
        pid = str(uuid4())
    return {
        "proposal_id": pid,
        "change_type": "fact",
        "proposal_type": "create_lore_fact",
        "content": {"statement": "The moon is hollow"},
        "status": status,
        "source": source,
    }


@pytest.mark.asyncio
async def test_bulk_commit_proposals_empty():
    keeper = CanonKeeper()
    result = await keeper.bulk_commit_proposals([])
    assert result == {"committed": 0, "rejected": 0, "errors": []}


@pytest.mark.asyncio
async def test_bulk_commit_proposals_success(monkeypatch: pytest.MonkeyPatch):
    from monitor_data.db import mongodb as mongodb_module

    proposals_coll = MagicMock()
    client = MagicMock()
    client.get_collection.return_value = proposals_coll
    monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: client)

    keeper = CanonKeeper()
    monkeypatch.setattr(keeper, "_commit_to_neo4j", AsyncMock())

    pid = str(uuid4())
    proposal = _proposal_doc("source1", pid=pid)

    result = await keeper.bulk_commit_proposals([proposal], contradiction_check=False)

    assert result == {"committed": 1, "rejected": 0, "errors": []}
    proposals_coll.update_one.assert_called_once_with({"proposal_id": pid}, {"$set": {"status": "committed"}})


@pytest.mark.asyncio
async def test_bulk_commit_proposals_with_rejections(monkeypatch: pytest.MonkeyPatch):
    from monitor_data.db import mongodb as mongodb_module

    proposals_coll = MagicMock()
    client = MagicMock()
    client.get_collection.return_value = proposals_coll
    monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: client)

    keeper = CanonKeeper()

    pid1 = str(uuid4())
    pid2 = str(uuid4())
    proposal1 = _proposal_doc("source1", pid=pid1)
    proposal2 = _proposal_doc("source2", pid=pid2)

    # Mock contradiction check to reject pid1
    async def mock_check(ordered, universe_id):
        return {pid1: "Conflicts with canon"}

    monkeypatch.setattr(keeper, "_batch_contradiction_check", mock_check)
    monkeypatch.setattr(keeper, "_commit_to_neo4j", AsyncMock())

    result = await keeper.bulk_commit_proposals([proposal1, proposal2], contradiction_check=True, universe_id=uuid4())

    assert result["committed"] == 1
    assert result["rejected"] == 1

    # pid1 should be rejected
    proposals_coll.update_one.assert_any_call(
        {"proposal_id": pid1}, {"$set": {"status": "rejected", "rejection_reason": "Conflicts with canon"}}
    )

    # pid2 should be committed
    proposals_coll.update_one.assert_any_call({"proposal_id": pid2}, {"$set": {"status": "committed"}})
