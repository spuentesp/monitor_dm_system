from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.asyncio
async def test_replace_fact_error_on_create(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    mock_create = AsyncMock(return_value={"error": "db offline"})
    monkeypatch.setattr(keeper, "create_fact", mock_create)

    old_id = uuid4()
    result = await keeper.replace_fact(old_id, {"statement": "new"})

    assert result == {"error": "db offline"}
    assert mock_create.call_args[0][0]["replaces"] == str(old_id)


@pytest.mark.asyncio
async def test_replace_fact_success(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    new_id = str(uuid4())
    mock_create = AsyncMock(return_value={"id": new_id})
    monkeypatch.setattr(keeper, "create_fact", mock_create)

    mock_call_tool = AsyncMock()
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    mock_track = AsyncMock()
    monkeypatch.setattr(keeper, "_track_fact_replacement", mock_track)

    old_id = uuid4()
    scene_id = uuid4()
    result = await keeper.replace_fact(old_id, {"statement": "new"}, scene_id=scene_id, reason="test")

    assert result["old_fact_id"] == str(old_id)
    assert result["new_fact_id"] == new_id
    assert result["scene_id"] == str(scene_id)
    assert result["reason"] == "test"
    assert "replacement_time" in result

    mock_call_tool.assert_called_once()
    assert mock_call_tool.call_args[0][0] == "neo4j_update_fact"
    updates = mock_call_tool.call_args[0][1]["updates"]
    assert updates["replaced_by"] == new_id
    assert updates["replaced_reason"] == "test"

    mock_track.assert_called_once()


@pytest.mark.asyncio
async def test_replace_fact_tombstone_error(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    new_id = str(uuid4())
    mock_create = AsyncMock(return_value={"id": new_id})
    monkeypatch.setattr(keeper, "create_fact", mock_create)

    mock_call_tool = AsyncMock(side_effect=Exception("DB Error"))
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    mock_track = AsyncMock()
    monkeypatch.setattr(keeper, "_track_fact_replacement", mock_track)

    old_id = uuid4()
    # It should still return success but log the error
    result = await keeper.replace_fact(old_id, {"statement": "new"})

    assert result["old_fact_id"] == str(old_id)
    assert result["new_fact_id"] == new_id
    mock_track.assert_called_once()
