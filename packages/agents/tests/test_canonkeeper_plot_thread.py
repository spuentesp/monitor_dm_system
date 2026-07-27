from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.asyncio
async def test_commit_plot_thread_no_story_id(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call = AsyncMock(return_value=json.dumps({"stories": []}))
    monkeypatch.setattr(keeper, "call_tool", mock_call)
    
    mock_mark = MagicMock()
    monkeypatch.setattr(keeper, "_mark_runtime_activation_status", mock_mark)
    
    proposal = {"universe_id": "test", "payload": {"title": "test"}}
    await keeper._commit_plot_thread(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_mark.assert_called_once()
    assert mock_mark.call_args[0][2] == "unresolved"

@pytest.mark.asyncio
async def test_commit_plot_thread_with_story_fallback(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call = AsyncMock(side_effect=[
        json.dumps({"stories": [{"story_id": "s1"}]}),
        "{}"
    ])
    monkeypatch.setattr(keeper, "call_tool", mock_call)
    
    mock_check = MagicMock()
    monkeypatch.setattr(keeper, "_check_tool_error", mock_check)
    mock_store = MagicMock()
    monkeypatch.setattr(keeper, "_store_runtime_ref_on_proposal", mock_store)
    
    proposal = {"universe_id": "test", "payload": {"title": "test"}}
    await keeper._commit_plot_thread(MagicMock(), "pid", proposal, [], MagicMock())
    
    assert mock_call.call_count == 2
    mock_store.assert_called_once()

@pytest.mark.asyncio
async def test_commit_plot_thread_with_story_id(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call = AsyncMock(return_value="{}")
    monkeypatch.setattr(keeper, "call_tool", mock_call)
    
    mock_check = MagicMock()
    monkeypatch.setattr(keeper, "_check_tool_error", mock_check)
    mock_store = MagicMock()
    monkeypatch.setattr(keeper, "_store_runtime_ref_on_proposal", mock_store)
    
    proposal = {"story_id": "s1", "payload": {"title": "test"}}
    await keeper._commit_plot_thread(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_call.assert_called_once()
    assert mock_call.call_args[0][0] == "neo4j_create_plot_thread"
    mock_store.assert_called_once()
