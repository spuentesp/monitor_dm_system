"""CanonKeeper's fact branch carries the witness record (join Task 5).

The proposals stamped with cast witnesses at narration time must reach the
``neo4j_create_fact`` call verbatim — until then committed facts lose their
witness record and the who-knows-what filter cannot enforce scene secrecy.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.asyncio
async def test_commit_fact_branch_passes_witnesses_and_properties(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    mock_call_tool = AsyncMock(return_value="{}")
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    monkeypatch.setattr(keeper, "_check_tool_error", MagicMock())
    monkeypatch.setattr(keeper, "_store_neo4j_id_on_proposal", MagicMock())

    witness_a = str(uuid4())
    witness_b = str(uuid4())
    proposal = {
        "universe_id": str(uuid4()),
        "payload": {
            "statement": "the ledger vanished",
            "fact_type": "occurrence",
            "witnesses": [witness_a, witness_b],
            "properties": {"told_to": [witness_b], "scene_kind": "heist"},
        },
    }
    await keeper._commit_fact_branch(MagicMock(), "pid", proposal, [], None)

    mock_call_tool.assert_called_once()
    tool_name = mock_call_tool.call_args[0][0]
    assert tool_name == "neo4j_create_fact"
    params = mock_call_tool.call_args[0][1]["params"]
    assert params["witnesses"] == [witness_a, witness_b]
    assert params["properties"] == {"told_to": [witness_b], "scene_kind": "heist"}
    assert params["statement"] == "the ledger vanished"


@pytest.mark.asyncio
async def test_commit_fact_branch_falls_back_to_the_proposal_witnesses(monkeypatch: pytest.MonkeyPatch):
    """The narration path stamps the proposal top level too — read either."""
    keeper = CanonKeeper()
    mock_call_tool = AsyncMock(return_value="{}")
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    monkeypatch.setattr(keeper, "_check_tool_error", MagicMock())
    monkeypatch.setattr(keeper, "_store_neo4j_id_on_proposal", MagicMock())

    witness = str(uuid4())
    proposal = {
        "universe_id": str(uuid4()),
        "witnesses": [witness],
        "payload": {"statement": "the door is sealed", "fact_type": "state"},
    }
    await keeper._commit_fact_branch(MagicMock(), "pid", proposal, [], None)

    params = mock_call_tool.call_args[0][1]["params"]
    assert params["witnesses"] == [witness]
    assert params["properties"] is None
