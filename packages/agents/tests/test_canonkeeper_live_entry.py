"""
Tests for CanonKeeper.check_live_entry — advisory live contradiction checks (P1.1).

check_live_entry assembles its own canon context (facts + axioms via MCP) and
delegates to verify_fact. It is read-only: no proposals, no Neo4j writes, and
at most one LLM call (the DSPy ContradictionModule inside verify_fact).

Covers:
- empty canon / empty entry → no alert, no LLM call
- contradiction found → explanation propagated, context built from axioms + facts
- ContradictionModule raising → heuristic fallback engaged

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_canonkeeper_live_entry.py -v
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper
from tests.conftest import FakeMCPClient


def _keeper_with_mcp(fake_mcp: FakeMCPClient) -> CanonKeeper:
    """CanonKeeper whose MCP calls route to the fake client."""
    keeper = CanonKeeper(agent_id="test-live-entry")
    keeper.call_tool = fake_mcp.call_tool  # type: ignore[assignment]
    return keeper


class TestCheckLiveEntry:
    @pytest.mark.asyncio
    async def test_empty_canon_returns_no_alert_and_no_llm_call(self):
        """No canon context → early exit, ContradictionModule never built."""
        fake_mcp = FakeMCPClient()
        fake_mcp.add_response("neo4j_list_facts", {}, [])
        fake_mcp.add_response("neo4j_list_axioms", {}, [])
        keeper = _keeper_with_mcp(fake_mcp)

        with patch("monitor_agents.canonkeeper.verification.ContradictionModule") as mock_module_cls:
            result = await keeper.check_live_entry(uuid4(), "The king is alive and well")

        assert result["has_contradiction"] is False
        assert result["explanation"] == ""
        mock_module_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_entry_returns_no_alert_and_skips_mcp(self):
        """Blank entry → early exit before any MCP fetch."""
        fake_mcp = FakeMCPClient()
        keeper = _keeper_with_mcp(fake_mcp)

        with patch("monitor_agents.canonkeeper.verification.ContradictionModule") as mock_module_cls:
            result = await keeper.check_live_entry(uuid4(), "   ")

        assert result["has_contradiction"] is False
        mock_module_cls.assert_not_called()
        assert fake_mcp._call_tool_call_count == 0

    @pytest.mark.asyncio
    async def test_contradiction_found_propagates_explanation(self):
        """LLM verdict is returned verbatim; context mirrors _check_contradiction."""
        fake_mcp = FakeMCPClient()
        fake_mcp.add_response("neo4j_list_facts", {}, [{"statement": "The king is dead"}])
        fake_mcp.add_response("neo4j_list_axioms", {}, [{"statement": "Magic is forbidden"}])
        keeper = _keeper_with_mcp(fake_mcp)

        mock_result = {
            "has_contradiction": True,
            "explanation": "The king cannot greet anyone: canon says he is dead.",
        }
        with patch("monitor_agents.canonkeeper.verification.ContradictionModule") as mock_module_cls:
            mock_module = mock_module_cls.return_value
            mock_module.forward.return_value = mock_result

            result = await keeper.check_live_entry(uuid4(), "The king greeted the party")

        assert result["has_contradiction"] is True
        assert "king" in result["explanation"].lower()

        # Context was assembled from axioms + facts, same shape as _check_contradiction.
        forward_kwargs = mock_module.forward.call_args.kwargs
        assert "Axiom: Magic is forbidden" in forward_kwargs["context"]
        assert "Fact: The king is dead" in forward_kwargs["context"]
        assert forward_kwargs["new_fact"] == "The king greeted the party"

    @pytest.mark.asyncio
    async def test_module_failure_engages_heuristic_fallback(self):
        """ContradictionModule raising → verify_fact's heuristic fallback decides."""
        fake_mcp = FakeMCPClient()
        fake_mcp.add_response("neo4j_list_facts", {}, [{"statement": "The king is dead"}])
        fake_mcp.add_response("neo4j_list_axioms", {}, [])
        keeper = _keeper_with_mcp(fake_mcp)

        with patch("monitor_agents.canonkeeper.verification.ContradictionModule") as mock_module_cls:
            mock_module = mock_module_cls.return_value
            mock_module.forward.side_effect = Exception("LLM unavailable")

            result = await keeper.check_live_entry(uuid4(), "The king is not dead")

        # Heuristic negation check catches "is not dead" vs "is dead".
        assert result["has_contradiction"] is True
        assert "king" in result["explanation"].lower()
