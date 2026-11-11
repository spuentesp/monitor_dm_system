"""
Tests for SessionIngestAgent — G03 entry-correction MCP pass-throughs (CF-1).

The agent is a thin forwarder to the data-layer session-entry tools: these
tests assert the tool name, the arguments, and that MCP error strings are
surfaced as ValueError (BaseAgent.call_tool returns tool failures as text).

Run:
    uv run pytest packages/agents/tests/test_session_ingest_agent.py -q
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from monitor_agents.ingestion.session_ingest import SessionIngestAgent


def _agent() -> SessionIngestAgent:
    agent = SessionIngestAgent(agent_id="test-session-ingest")
    return agent


class TestEntryPassThroughs:
    @pytest.mark.asyncio
    async def test_update_entry_forwards_tool_and_args(self):
        agent = _agent()
        entry_id = str(uuid4())
        agent.call_tool = AsyncMock(  # type: ignore[method-assign]
            return_value={"id": entry_id, "content": "corrected", "struck": False}
        )

        result = await agent.update_entry(entry_id, "corrected")

        agent.call_tool.assert_awaited_once_with(
            "mongodb_update_session_entry",
            {"entry_id": entry_id, "text": "corrected"},
        )
        assert result["content"] == "corrected"

    @pytest.mark.asyncio
    async def test_strike_entry_is_soft_and_records_retracted_ids(self):
        agent = _agent()
        entry_id = str(uuid4())
        proposal_ids = [str(uuid4()), str(uuid4())]
        agent.call_tool = AsyncMock(  # type: ignore[method-assign]
            return_value={"id": entry_id, "struck": True, "struck_proposal_ids": proposal_ids}
        )

        result = await agent.strike_entry(entry_id, retracted_proposal_ids=proposal_ids)

        agent.call_tool.assert_awaited_once_with(
            "mongodb_delete_session_entry",
            {
                "entry_id": entry_id,
                "soft": True,
                "reason": "struck at the table",
                "retracted_proposal_ids": proposal_ids,
            },
        )
        assert result["struck"] is True
        assert result["struck_proposal_ids"] == proposal_ids

    @pytest.mark.asyncio
    async def test_restore_entry_returns_restored_proposal_ids(self):
        agent = _agent()
        entry_id = str(uuid4())
        proposal_id = str(uuid4())
        agent.call_tool = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "id": entry_id,
                "struck": False,
                "restored_proposal_ids": [proposal_id],
            }
        )

        result = await agent.restore_entry(entry_id)

        agent.call_tool.assert_awaited_once_with(
            "mongodb_restore_session_entry",
            {"entry_id": entry_id},
        )
        assert result["restored_proposal_ids"] == [proposal_id]

    @pytest.mark.asyncio
    async def test_get_entry_returns_none_when_missing(self):
        agent = _agent()
        agent.call_tool = AsyncMock(return_value=None)  # type: ignore[method-assign]

        assert await agent.get_entry(str(uuid4())) is None

    @pytest.mark.asyncio
    async def test_mcp_error_string_raises_value_error(self):
        """A tool failure arrives as text — it must not be swallowed."""
        agent = _agent()
        entry_id = str(uuid4())
        agent.call_tool = AsyncMock(  # type: ignore[method-assign]
            return_value=f"Error executing tool: Session entry {entry_id} not found"
        )

        with pytest.raises(ValueError, match="not found"):
            await agent.update_entry(entry_id, "text")
