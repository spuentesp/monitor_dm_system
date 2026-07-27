"""
Tests for the Simulacrum agent.

Covers:
- SimulacrumAgent initialization and DSPy module setup
- run_world_tick: agenda fetching, council execution, proposal generation
- Error handling: empty agendas, DSPy failures, JSON parsing

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_simulacrum.py -v
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


# Helper: patch dspy_context_for to avoid real LLM/PostgreSQL calls
@pytest.fixture
def mock_dspy_context():
    """Patch dspy_context_for to return a no-op context manager."""
    with patch("monitor_agents.simulacrum.agent.dspy_context_for", return_value=nullcontext()):
        yield


# =============================================================================
# Initialization
# =============================================================================


class TestSimulacrumInit:
    def test_agent_initializes_with_default_id(self):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        assert agent.agent_type == "Simulacrum"
        assert agent.agent_id == "simulacrum-1"

    def test_agent_initializes_with_custom_id(self):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent(agent_id="sim-42")
        assert agent.agent_id == "sim-42"

    def test_agent_has_three_dspy_modules(self):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        assert hasattr(agent, "_opportunist")
        assert hasattr(agent, "_realist")
        assert hasattr(agent, "_reconciler")


# =============================================================================
# run_world_tick — empty agendas
# =============================================================================


class TestRunWorldTickEmptyAgendas:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_agendas(self):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        agent.call_tool = AsyncMock(return_value=None)

        result = await agent.run_world_tick(
            universe_id=uuid4(),
            current_time=datetime(2025, 1, 1, tzinfo=UTC),
            recent_high_impact_events=[],
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_agendas_is_empty_list(self):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        agent.call_tool = AsyncMock(return_value=[])

        result = await agent.run_world_tick(
            universe_id=uuid4(),
            current_time=datetime(2025, 1, 1, tzinfo=UTC),
            recent_high_impact_events=[],
        )

        assert result == []


# =============================================================================
# run_world_tick — council execution with mocked DSPy
# =============================================================================


class TestRunWorldTickCouncil:
    @pytest.mark.asyncio
    async def test_generates_clock_advance_proposal(self, mock_dspy_context):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        agent.call_tool = AsyncMock(
            return_value=[
                {
                    "id": "agenda-1",
                    "title": "Conquer the North",
                    "description": "Military campaign",
                    "agenda_type": "military",
                    "owner_name": "Northern Army",
                    "current_segments": 3,
                    "total_segments": 10,
                }
            ]
        )

        # Mock the DSPy modules
        opp_mock = MagicMock()
        opp_mock.return_value = MagicMock(proposed_move="Advance troops", reasoning="Good opportunity")
        real_mock = MagicMock()
        real_mock.return_value = MagicMock(proposed_move="Hold position", reasoning="Too risky")
        reconciler_mock = MagicMock()
        reconciler_mock.return_value = MagicMock(
            clock_tick=2,
            summary="Army advances cautiously",
            final_decision="Advance 2 segments",
            change_type="update_agenda",
            reasoning="Balanced approach",
        )

        agent._opportunist = opp_mock
        agent._realist = real_mock
        agent._reconciler = reconciler_mock

        result = await agent.run_world_tick(
            universe_id=uuid4(),
            current_time=datetime(2025, 1, 1, tzinfo=UTC),
            recent_high_impact_events=[{"type": "battle", "outcome": "victory"}],
        )

        assert len(result) >= 1
        proposal = result[0]
        assert proposal["change_type"] == "mechanic"
        assert proposal["proposal_type"] == "update_agenda_clock"
        assert "Conquer the North" in proposal["summary"]
        assert proposal["content"]["tick"] == 2

    @pytest.mark.asyncio
    async def test_generates_fact_proposal_for_create_fact(self, mock_dspy_context):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        agent.call_tool = AsyncMock(
            return_value=[
                {
                    "id": "agenda-2",
                    "title": "Spread Rumors",
                    "description": "Disinformation campaign",
                    "agenda_type": "social",
                    "owner_name": "Shadow Network",
                    "current_segments": 1,
                    "total_segments": 5,
                }
            ]
        )

        opp_mock = MagicMock()
        opp_mock.return_value = MagicMock(proposed_move="Spread rumors", reasoning="Effective")
        real_mock = MagicMock()
        real_mock.return_value = MagicMock(proposed_move="Wait", reasoning="Premature")
        reconciler_mock = MagicMock()
        reconciler_mock.return_value = MagicMock(
            clock_tick=1,
            summary="Rumors spread",
            final_decision="Begin disinformation",
            change_type="create_fact",
            reasoning="Timing is right",
        )

        agent._opportunist = opp_mock
        agent._realist = real_mock
        agent._reconciler = reconciler_mock

        result = await agent.run_world_tick(
            universe_id=uuid4(),
            current_time=datetime(2025, 1, 1, tzinfo=UTC),
            recent_high_impact_events=[],
        )

        # Should have both a clock-advance and a fact proposal
        assert len(result) >= 1
        fact_proposals = [p for p in result if p["change_type"] == "create_fact"]
        assert len(fact_proposals) >= 1
        assert "Shadow Network" in fact_proposals[0]["content"]["statement"]

    @pytest.mark.asyncio
    async def test_skips_agenda_on_dspy_failure(self, mock_dspy_context):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        agent.call_tool = AsyncMock(
            return_value=[
                {
                    "id": "agenda-err",
                    "title": "Failing Agenda",
                    "description": "Will cause DSPy error",
                    "agenda_type": "test",
                    "owner_name": "Test Faction",
                    "current_segments": 0,
                    "total_segments": 1,
                }
            ]
        )

        # Mock DSPy to raise an exception
        agent._opportunist = MagicMock(side_effect=Exception("DSPy failed"))
        agent._realist = MagicMock()
        agent._reconciler = MagicMock()

        result = await agent.run_world_tick(
            universe_id=uuid4(),
            current_time=datetime(2025, 1, 1, tzinfo=UTC),
            recent_high_impact_events=[],
        )

        # Should return empty list (agenda was skipped, not crashed)
        assert result == []

    @pytest.mark.asyncio
    async def test_zero_clock_tick_produces_no_clock_proposal(self, mock_dspy_context):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        agent.call_tool = AsyncMock(
            return_value=[
                {
                    "id": "agenda-0",
                    "title": "Waiting Game",
                    "description": "No progress",
                    "agenda_type": "passive",
                    "owner_name": "Patient Faction",
                    "current_segments": 0,
                    "total_segments": 1,
                }
            ]
        )

        opp_mock = MagicMock()
        opp_mock.return_value = MagicMock(proposed_move="Wait", reasoning="No action")
        real_mock = MagicMock()
        real_mock.return_value = MagicMock(proposed_move="Wait", reasoning="Agree")
        reconciler_mock = MagicMock()
        reconciler_mock.return_value = MagicMock(
            clock_tick=0,
            summary="No progress",
            final_decision="Hold",
            change_type="none",
            reasoning="Consensus to wait",
        )

        agent._opportunist = opp_mock
        agent._realist = real_mock
        agent._reconciler = reconciler_mock

        result = await agent.run_world_tick(
            universe_id=uuid4(),
            current_time=datetime(2025, 1, 1, tzinfo=UTC),
            recent_high_impact_events=[],
        )

        # No clock-advance proposal when tick is 0
        clock_proposals = [p for p in result if p.get("proposal_type") == "update_agenda_clock"]
        assert len(clock_proposals) == 0


# =============================================================================
# run — base method
# =============================================================================


class TestSimulacrumRun:
    @pytest.mark.asyncio
    async def test_run_returns_none(self):
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        agent = SimulacrumAgent()
        result = await agent.run()
        assert result is None
