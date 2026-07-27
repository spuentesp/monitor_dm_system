"""
Tests for CaptureInsightAgent.analyze_entry — per-entry capture insights (P1.2).

analyze_entry fetches canonical entity names and open threads via MCP, then
runs the DSPy CaptureEntryModule (mocked here — prompt construction and result
mapping are asserted, not canned text). LLM failure yields an empty insight so
logging is never blocked.

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_capture_insights.py -v
"""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_agents.ingestion.capture_insights import CaptureInsight, CaptureInsightAgent
from tests.conftest import FakeMCPClient


def _agent_with_mcp(fake_mcp: FakeMCPClient) -> CaptureInsightAgent:
    """CaptureInsightAgent whose MCP calls route to the fake client."""
    agent = CaptureInsightAgent(agent_id="test-capture-insights")
    agent.call_tool = fake_mcp.call_tool  # type: ignore[assignment]
    return agent


class TestAnalyzeEntry:
    @pytest.mark.asyncio
    async def test_prompt_construction_and_result_mapping(self):
        """Module receives entry + canon context; prediction maps to CaptureInsight."""
        fake_mcp = FakeMCPClient()
        fake_mcp.add_response(
            "neo4j_list_entities",
            {},
            {"entities": [{"name": "Mira"}, {"name": "The Sunken Chapel"}, {"name": None}]},
        )
        fake_mcp.add_response(
            "neo4j_list_plot_threads",
            {},
            {"threads": [{"title": "The sealed door"}, {"title": "Missing caravan"}]},
        )
        agent = _agent_with_mcp(fake_mcp)

        prediction = SimpleNamespace(
            participants=["Mira"],
            locations=["The Sunken Chapel"],
            candidate_facts=["the key is now with Mira"],
            advances_thread="The sealed door",
        )
        with (
            patch("monitor_agents.ingestion.session_ingest.CaptureEntryModule") as mock_module_cls,
            patch(
                "monitor_agents.dspy_runtime.dspy_context_for",
                lambda *a, **kw: nullcontext(),
            ),
        ):
            mock_module = mock_module_cls.return_value
            mock_module.forward.return_value = prediction

            insight = await agent.analyze_entry(uuid4(), "Mira pocketed the key beneath the chapel")

        # Result mapping
        assert insight.participants == ["Mira"]
        assert insight.locations == ["The Sunken Chapel"]
        assert insight.candidate_facts == ["the key is now with Mira"]
        assert insight.advances_thread == "The sealed door"

        # Prompt construction: canon context flows into the module call
        forward_kwargs = mock_module.forward.call_args.kwargs
        assert forward_kwargs["entry_text"] == "Mira pocketed the key beneath the chapel"
        assert forward_kwargs["known_entities"] == ["Mira", "The Sunken Chapel"]
        assert forward_kwargs["open_threads"] == ["The sealed door", "Missing caravan"]

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty_insight(self):
        """Module raising → structlog warning + empty insight, never an exception."""
        fake_mcp = FakeMCPClient()
        fake_mcp.add_response("neo4j_list_entities", {}, {"entities": [{"name": "Mira"}]})
        fake_mcp.add_response("neo4j_list_plot_threads", {}, {"threads": []})
        agent = _agent_with_mcp(fake_mcp)

        with (
            patch("monitor_agents.ingestion.session_ingest.CaptureEntryModule") as mock_module_cls,
            patch(
                "monitor_agents.dspy_runtime.dspy_context_for",
                lambda *a, **kw: nullcontext(),
            ),
        ):
            mock_module_cls.return_value.forward.side_effect = Exception("LLM unavailable")

            insight = await agent.analyze_entry(uuid4(), "The party moved on")

        assert insight == CaptureInsight()
        assert insight.participants == []
        assert insight.locations == []
        assert insight.candidate_facts == []
        assert insight.advances_thread == ""

    @pytest.mark.asyncio
    async def test_empty_canon_context_still_calls_module(self):
        """No entities/threads known → empty context lists, module still runs."""
        fake_mcp = FakeMCPClient()
        fake_mcp.add_response("neo4j_list_entities", {}, {"entities": []})
        fake_mcp.add_response("neo4j_list_plot_threads", {}, {"threads": []})
        agent = _agent_with_mcp(fake_mcp)

        prediction = SimpleNamespace(
            participants=[],
            locations=["the chapel"],
            candidate_facts=[],
            advances_thread="",
        )
        with (
            patch("monitor_agents.ingestion.session_ingest.CaptureEntryModule") as mock_module_cls,
            patch(
                "monitor_agents.dspy_runtime.dspy_context_for",
                lambda *a, **kw: nullcontext(),
            ),
        ):
            mock_module = mock_module_cls.return_value
            mock_module.forward.return_value = prediction

            insight = await agent.analyze_entry(uuid4(), "The party reached the chapel")

        forward_kwargs = mock_module.forward.call_args.kwargs
        assert forward_kwargs["known_entities"] == []
        assert forward_kwargs["open_threads"] == []
        assert insight.locations == ["the chapel"]
        assert insight.advances_thread == ""
