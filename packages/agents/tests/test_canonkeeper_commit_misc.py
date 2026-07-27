from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.asyncio
async def test_commit_spatial_topology_missing_locations(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call_tool = AsyncMock()
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    
    proposal = {"payload": {"from_location": "", "to_location": "B"}}
    await keeper._commit_spatial_topology(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_call_tool.assert_not_called()
    
@pytest.mark.asyncio
async def test_commit_spatial_topology_unresolved(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_resolve = AsyncMock(return_value=None)
    monkeypatch.setattr(keeper, "_resolve_name_to_uuid", mock_resolve)
    mock_call_tool = AsyncMock()
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    
    proposal = {"payload": {"from_location": "A", "to_location": "B"}}
    await keeper._commit_spatial_topology(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_call_tool.assert_not_called()

@pytest.mark.asyncio
async def test_commit_spatial_topology_success(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    uid_a = str(uuid4())
    uid_b = str(uuid4())
    
    async def mock_resolve(name, universe_id):
        if name == "A":
            return uid_a
        if name == "B":
            return uid_b
        return None
        
    monkeypatch.setattr(keeper, "_resolve_name_to_uuid", mock_resolve)
    
    mock_call_tool = AsyncMock(return_value="{}")
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    monkeypatch.setattr(keeper, "_check_tool_error", MagicMock())
    
    proposal = {"payload": {"from_location": "A", "to_location": "B", "description": "test"}}
    await keeper._commit_spatial_topology(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_call_tool.assert_called_once()
    args = mock_call_tool.call_args[0][1]["params"]
    assert args["from_entity_id"] == uid_a
    assert args["to_entity_id"] == uid_b
    assert args["properties"]["description"] == "test"

@pytest.mark.asyncio
async def test_commit_create_agenda(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call_tool = AsyncMock()
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    
    proposal = {"payload": {"title": "My Agenda"}}
    await keeper._commit_create_agenda(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_call_tool.assert_called_once()
    assert mock_call_tool.call_args[0][0] == "neo4j_create_agenda"
