from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.asyncio
async def test_batch_contradiction_check_empty_context():
    keeper = CanonKeeper()
    keeper._fetch_canon_facts = AsyncMock(return_value=[])
    keeper._fetch_canon_axioms = AsyncMock(return_value=[])

    result = await keeper._batch_contradiction_check(
        [{"proposal_id": str(uuid4()), "content": {"statement": "test"}}], uuid4()
    )
    assert result == {}


@pytest.mark.asyncio
async def test_batch_contradiction_check_empty_candidates():
    keeper = CanonKeeper()
    keeper._fetch_canon_facts = AsyncMock(return_value=[{"statement": "fact1"}])
    keeper._fetch_canon_axioms = AsyncMock(return_value=[{"statement": "axiom1"}])

    result = await keeper._batch_contradiction_check([{"proposal_id": str(uuid4()), "content": {}}], uuid4())
    assert result == {}


@pytest.mark.asyncio
async def test_batch_contradiction_check_success(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    keeper._fetch_canon_facts = AsyncMock(return_value=[{"statement": "fact1"}])
    keeper._fetch_canon_axioms = AsyncMock(return_value=[{"statement": "axiom1"}])

    pid1 = str(uuid4())
    pid2 = str(uuid4())

    # Mix of dict and string content
    proposals = [
        {"proposal_id": pid1, "content": {"statement": "test1"}},
        {"proposal_id": pid2, "content": json.dumps({"statement": "test2"})},
    ]

    mock_module = MagicMock()
    # Assume 1-based indexing returns index 2 as rejected
    mock_module.forward.return_value = {2: "Because I said so"}

    def mock_init(*args, **kwargs):
        pass

    monkeypatch.setattr("monitor_agents.canonkeeper.verification.BatchContradictionModule.__init__", mock_init)
    monkeypatch.setattr("monitor_agents.canonkeeper.verification.BatchContradictionModule.forward", mock_module.forward)

    result = await keeper._batch_contradiction_check(proposals, uuid4())

    assert result == {pid2: "Because I said so"}
    assert mock_module.forward.call_count == 1
