"""Behavior tests for WorldBuildingLoop choreography (Phase 2).

Exercises pure logic only — no LLM, no DB.

Covers:
- WorldBuildingState defaults
- format_response appends "Added to your world" footer when committed > 0
- format_response appends error footer when errors present
- format_response increments turns_count
- load_world_context detects first-turn vs continuation correctly
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_state(**overrides) -> Any:
    """Build a minimal WorldBuildingState."""
    from monitor_agents.loops.world_building_loop import WorldBuildingState

    base: dict[str, Any] = {
        "session_id": "test-session",
    }
    base.update(overrides)
    return WorldBuildingState(**base)


# =============================================================================
# WorldBuildingState defaults
# =============================================================================


class TestWorldBuildingStateDefaults:
    def test_minimal_construction(self):
        state = _make_state()
        assert state.session_id == "test-session"
        assert state.universe_id is None
        assert state.multiverse_id is None
        assert state.conversation_history == []
        assert state.current_user_input == ""
        assert state.world_summary == {}
        assert state.world_profile == {}
        assert state.coverage_summary == ""
        assert state.known_open_questions == []
        assert state.priority_gaps == []
        assert state.response_text == ""
        assert state.extracted_proposals == []
        assert state.committed_count == 0
        assert state.commit_errors == []
        assert state.turns_count == 0
        assert state.is_first_turn is True

    def test_explicit_overrides(self):
        uid = uuid4()
        mid = uuid4()
        state = _make_state(
            universe_id=uid,
            multiverse_id=mid,
            current_user_input="Tell me about your world",
            turns_count=2,
            is_first_turn=False,
        )
        assert state.universe_id == uid
        assert state.multiverse_id == mid
        assert state.current_user_input == "Tell me about your world"
        assert state.turns_count == 2
        assert state.is_first_turn is False

    def test_with_proposals(self):
        state = _make_state(
            extracted_proposals=[
                {"proposal_type": "axiom", "payload": {"statement": "Magic is rare"}},
            ],
            committed_count=1,
        )
        assert len(state.extracted_proposals) == 1
        assert state.committed_count == 1


# =============================================================================
# format_response
# =============================================================================


class TestFormatResponse:
    @pytest.mark.asyncio
    async def test_no_committed_no_errors_returns_response_with_incremented_turns(self):
        from monitor_agents.loops.world_building_loop import format_response

        state = _make_state(
            response_text="Hello traveler.",
            committed_count=0,
            commit_errors=[],
            turns_count=3,
        )
        result = await format_response(state)
        assert "Hello traveler." in result["response_text"]
        assert "Added to your world" not in result["response_text"]
        assert result["turns_count"] == 4  # incremented from 3

    @pytest.mark.asyncio
    async def test_committed_count_appends_added_footer(self):
        from monitor_agents.loops.world_building_loop import format_response

        state = _make_state(
            response_text="Done!",
            extracted_proposals=[
                {"proposal_type": "axiom", "payload": {"statement": "Magic is rare"}},
                {"proposal_type": "entity", "payload": {"name": "Bartholomew"}},
            ],
            committed_count=2,
        )
        result = await format_response(state)
        text = result["response_text"]
        assert "Added to your world" in text
        assert "Axiom" in text
        assert "Bartholomew" in text

    @pytest.mark.asyncio
    async def test_committed_count_uses_payload_statement_fallback(self):
        from monitor_agents.loops.world_building_loop import format_response

        state = _make_state(
            response_text="Done!",
            extracted_proposals=[
                {
                    "proposal_type": "fact",
                    "payload": {"statement": "The king was murdered in 1247"},
                },
            ],
            committed_count=1,
        )
        result = await format_response(state)
        text = result["response_text"]
        assert "Fact" in text
        assert "king was murdered" in text

    @pytest.mark.asyncio
    async def test_errors_append_retry_footer(self):
        from monitor_agents.loops.world_building_loop import format_response

        state = _make_state(
            response_text="Done!",
            committed_count=0,
            commit_errors=["err1", "err2", "err3"],
        )
        result = await format_response(state)
        text = result["response_text"]
        assert "could not be added" in text
        assert "3 element(s)" in text
        assert "retry on next turn" in text

    @pytest.mark.asyncio
    async def test_committed_but_no_extracted_proposals(self):
        """Edge case: committed_count > 0 but proposals list is empty."""
        from monitor_agents.loops.world_building_loop import format_response

        state = _make_state(
            response_text="Done!",
            extracted_proposals=[],
            committed_count=1,
        )
        result = await format_response(state)
        # No footer should be added because there are no proposals to display
        assert "Added to your world" not in result["response_text"]


# =============================================================================
# load_world_context — first-turn detection
# =============================================================================


class TestLoadWorldContextFirstTurn:
    @pytest.mark.asyncio
    async def test_first_turn_detected_when_no_history(self):
        from monitor_agents.loops.world_building_loop import load_world_context

        state = _make_state(turns_count=0, conversation_history=[])
        with patch("monitor_agents.world_architect.agent.WorldArchitect") as MockArchitect:
            mock_instance = MockArchitect.return_value
            mock_instance._load_world_state = AsyncMock(return_value={})
            result = await load_world_context(state)

        assert result["is_first_turn"] is True
        assert result["world_summary"] == {}

    @pytest.mark.asyncio
    async def test_first_turn_false_when_history_exists(self):
        from monitor_agents.loops.world_building_loop import load_world_context

        state = _make_state(
            turns_count=2,
            conversation_history=[{"role": "user", "content": "hi"}],
        )
        with patch("monitor_agents.world_architect.agent.WorldArchitect") as MockArchitect:
            mock_instance = MockArchitect.return_value
            mock_instance._load_world_state = AsyncMock(return_value={"name": "Test"})
            result = await load_world_context(state)

        assert result["is_first_turn"] is False
        assert result["world_summary"] == {"name": "Test"}

    @pytest.mark.asyncio
    async def test_first_turn_false_when_turns_count_positive_no_history(self):
        from monitor_agents.loops.world_building_loop import load_world_context

        # Edge case: turns_count>0 but no history. Should still be NOT first.
        state = _make_state(turns_count=1, conversation_history=[])
        with patch("monitor_agents.world_architect.agent.WorldArchitect") as MockArchitect:
            mock_instance = MockArchitect.return_value
            mock_instance._load_world_state = AsyncMock(return_value={})
            result = await load_world_context(state)

        assert result["is_first_turn"] is False

    @pytest.mark.asyncio
    async def test_universe_id_passed_to_architect(self):
        from monitor_agents.loops.world_building_loop import load_world_context

        uid = uuid4()
        state = _make_state(universe_id=uid, turns_count=0, conversation_history=[])
        with patch("monitor_agents.world_architect.agent.WorldArchitect") as MockArchitect:
            mock_instance = MockArchitect.return_value
            mock_instance._load_world_state = AsyncMock(return_value={"x": 1})
            await load_world_context(state)
            mock_instance._load_world_state.assert_awaited_once_with(uid)
