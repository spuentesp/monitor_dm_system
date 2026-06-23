"""
Unit tests for ConversationLoop nodes, state schema, and graph construction.

Uses unittest.mock only — no live databases.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.graph import END

from monitor_agents.loops.conversation_loop import (
    ConversationState,
    build_conversation_graph,
    close_session,
    generate_npc_responses,
    load_npc_context,
    process_player_turn,
    route_after_npc_response,
)
from monitor_data.schemas.conversations import ConversationMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(**overrides: Any) -> ConversationState:
    """Build a minimal ConversationState for testing."""
    defaults: Dict[str, Any] = {
        "conversation_id": uuid4(),
        "universe_id": uuid4(),
        "mode": ConversationMode.DIRECT,
        "npc_ids": [],
        "npc_contexts": {},
        "turns": [],
        "current_player_input": None,
        "current_npc_responses": [],
        "pending_proposals": [],
        "is_complete": False,
        "turns_count": 0,
        "max_turns": 100,
    }
    defaults.update(overrides)
    return ConversationState(**defaults)


# ===========================================================================
# ConversationState schema
# ===========================================================================


class TestConversationState:
    def test_default_is_complete_false(self):
        state = _state()
        assert state.is_complete is False

    def test_default_turns_count_zero(self):
        state = _state()
        assert state.turns_count == 0

    def test_default_max_turns_one_hundred(self):
        state = _state()
        assert state.max_turns == 100

    def test_default_lists_empty(self):
        state = _state()
        assert state.turns == []
        assert state.npc_ids == []
        assert state.pending_proposals == []
        assert state.current_npc_responses == []

    def test_mode_direct_accepted(self):
        state = _state(mode=ConversationMode.DIRECT)
        assert state.mode == ConversationMode.DIRECT

    def test_mode_actor_accepted(self):
        state = _state(mode=ConversationMode.ACTOR)
        assert state.mode == ConversationMode.ACTOR


# ===========================================================================
# route_after_npc_response
# ===========================================================================


class TestRouteAfterNpcResponse:
    def test_is_complete_routes_to_close(self):
        state = _state(is_complete=True)
        assert route_after_npc_response(state) == "close"

    def test_turns_at_max_routes_to_close(self):
        state = _state(turns_count=100, max_turns=100)
        assert route_after_npc_response(state) == "close"

    def test_turns_exceeds_max_routes_to_close(self):
        state = _state(turns_count=150, max_turns=100)
        assert route_after_npc_response(state) == "close"

    def test_normal_turn_routes_to_end(self):
        state = _state(turns_count=5, max_turns=100, is_complete=False)
        assert route_after_npc_response(state) == END

    def test_zero_turns_is_not_complete(self):
        state = _state(turns_count=0, is_complete=False)
        assert route_after_npc_response(state) == END


# ===========================================================================
# build_conversation_graph
# ===========================================================================


class TestBuildConversationGraph:
    def test_returns_state_graph(self):
        from langgraph.graph import StateGraph

        g = build_conversation_graph()
        assert isinstance(g, StateGraph)

    def test_expected_nodes_present(self):
        g = build_conversation_graph()
        expected = {
            "open_session",
            "load_npc_context",
            "process_player_turn",
            "generate_npc_responses",
            "close_session",
        }
        assert expected.issubset(set(g.nodes.keys()))

    def test_graph_compiles_without_error(self):
        g = build_conversation_graph()
        compiled = g.compile()
        assert compiled is not None


# ===========================================================================
# process_player_turn
# ===========================================================================


class TestProcessPlayerTurn:
    @pytest.mark.asyncio
    async def test_no_input_returns_empty_dict(self):
        state = _state(current_player_input=None)
        result = await process_player_turn(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_appends_player_turn(self):
        state = _state(
            current_player_input="Hello there!",
            player_entity_id=uuid4(),
        )

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            result = await process_player_turn(state)

        assert "turns" in result
        turns = result["turns"]
        assert len(turns) == 1
        assert turns[0]["speaker_role"] == "player"
        assert turns[0]["text"] == "Hello there!"

    @pytest.mark.asyncio
    async def test_clears_current_npc_responses(self):
        state = _state(
            current_player_input="Attack!",
            current_npc_responses=[{"npc_id": "x", "text": "old response"}],
        )

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            result = await process_player_turn(state)

        assert result["current_npc_responses"] == []

    @pytest.mark.asyncio
    async def test_calls_mongodb_append_turn(self):
        conv_id = uuid4()
        state = _state(
            conversation_id=conv_id,
            current_player_input="Hello",
        )

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            await process_player_turn(state)

        mock_agent.call_tool.assert_awaited_once()
        call_args = mock_agent.call_tool.call_args
        assert call_args[0][0] == "mongodb_append_conversation_turn"
        assert call_args[0][1]["conversation_id"] == str(conv_id)


# ===========================================================================
# load_npc_context
# ===========================================================================


class TestLoadNpcContext:
    @pytest.mark.asyncio
    async def test_bounded_concurrency_for_npc_preload(self):
        npc_ids = [uuid4() for _ in range(10)]
        state = _state(mode=ConversationMode.DIRECT, npc_ids=npc_ids)

        active = 0
        max_active = 0

        async def fake_load_npc_data(npc_id: UUID, include_secrets: bool = False):  # noqa: ARG001
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)
            active -= 1
            return {
                "name": f"NPC {npc_id}",
                "role": "npc",
                "profile": {},
                "facts": [],
            }

        mock_agent = MagicMock()
        mock_agent._load_npc_data = AsyncMock(side_effect=fake_load_npc_data)

        with (
            patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent),
            patch(
                "monitor_agents.context_assembly.ContextAssembly._fetch_runtime_profile",
                new=AsyncMock(return_value={}),
            ),
        ):
            result = await load_npc_context(state)

        assert len(result["npc_contexts"]) == len(npc_ids)
        assert max_active <= 4


# ===========================================================================
# generate_npc_responses
# ===========================================================================


class TestGenerateNpcResponses:
    @pytest.mark.asyncio
    async def test_no_player_input_returns_empty(self):
        state = _state(current_player_input=None)
        result = await generate_npc_responses(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_direct_mode_calls_respond_direct(self):
        npc_id = uuid4()
        state = _state(
            mode=ConversationMode.DIRECT,
            npc_ids=[npc_id],
            current_player_input="What do you know?",
            npc_contexts={str(npc_id): {"name": "Aldric", "role": "innkeeper"}},
        )

        mock_agent = MagicMock()
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "I know many things.",
                "emotional_state_after": "neutral",
                "proposals": [],
            }
        )

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            result = await generate_npc_responses(state)

        mock_agent.respond_direct.assert_awaited_once()
        assert len(result["current_npc_responses"]) == 1
        assert result["current_npc_responses"][0]["text"] == "I know many things."
        assert (
            mock_agent.respond_direct.await_args.kwargs["npc_data"]
            == state.npc_contexts[str(npc_id)]
        )

    @pytest.mark.asyncio
    async def test_direct_mode_forwards_source_profile(self):
        npc_id = uuid4()
        source_profile = {
            "canon_signal_terms": ["Prince", "Primogen"],
            "confidence_by_field": {"canon_signal_terms": 0.9},
        }
        state = _state(
            mode=ConversationMode.DIRECT,
            npc_ids=[npc_id],
            current_player_input="What does the Prince want?",
            npc_contexts={str(npc_id): {"name": "Aldric", "role": "herald"}},
            source_profile=source_profile,
        )

        mock_agent = MagicMock()
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "The Prince has many demands.",
                "emotional_state_after": "neutral",
                "proposals": [],
            }
        )

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            await generate_npc_responses(state)

        kwargs = mock_agent.respond_direct.await_args.kwargs
        assert kwargs["source_profile"] == source_profile

    @pytest.mark.asyncio
    async def test_actor_mode_calls_respond_actor(self):
        npc_id = uuid4()
        state = _state(
            mode=ConversationMode.ACTOR,
            npc_ids=[npc_id],
            current_player_input="What motivates this character?",
            npc_contexts={str(npc_id): {"name": "Elara", "role": "wizard"}},
        )

        mock_agent = MagicMock()
        mock_agent.respond_actor = AsyncMock(
            return_value={
                "actor_response": "She wants power.",
                "canon_insight": "hidden ambition",
                "proposals": [],
            }
        )

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            result = await generate_npc_responses(state)

        mock_agent.respond_actor.assert_awaited_once()
        assert result["current_npc_responses"][0]["text"] == "She wants power."
        assert result["current_npc_responses"][0]["canon_insight"] == "hidden ambition"
        assert (
            mock_agent.respond_actor.await_args.kwargs["npc_data"]
            == state.npc_contexts[str(npc_id)]
        )

    @pytest.mark.asyncio
    async def test_increments_turns_count(self):
        npc_id = uuid4()
        state = _state(
            mode=ConversationMode.DIRECT,
            npc_ids=[npc_id],
            turns_count=3,
            current_player_input="hello",
            npc_contexts={str(npc_id): {"name": "Guard"}},
        )

        mock_agent = MagicMock()
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "Halt!",
                "emotional_state_after": "hostile",
                "proposals": [],
            }
        )

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            result = await generate_npc_responses(state)

        assert result["turns_count"] == 4

    @pytest.mark.asyncio
    async def test_resets_current_player_input_to_none(self):
        npc_id = uuid4()
        state = _state(
            mode=ConversationMode.DIRECT,
            npc_ids=[npc_id],
            current_player_input="hi",
            npc_contexts={str(npc_id): {"name": "Guard"}},
        )

        mock_agent = MagicMock()
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "...",
                "emotional_state_after": "neutral",
                "proposals": [],
            }
        )

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            result = await generate_npc_responses(state)

        assert result["current_player_input"] is None

    @pytest.mark.asyncio
    async def test_accumulates_proposals(self):
        npc_id = uuid4()
        existing_proposal = {"change_type": "fact", "content": {"old": "info"}}
        new_proposal = {"change_type": "entity", "content": {"name": "New NPC"}}

        state = _state(
            mode=ConversationMode.DIRECT,
            npc_ids=[npc_id],
            pending_proposals=[existing_proposal],
            current_player_input="Tell me",
            npc_contexts={str(npc_id): {"name": "Bard"}},
        )

        mock_agent = MagicMock()
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "Once upon a time...",
                "emotional_state_after": "happy",
                "proposals": [new_proposal],
            }
        )

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            result = await generate_npc_responses(state)

        assert len(result["pending_proposals"]) == 2
        assert existing_proposal in result["pending_proposals"]
        assert new_proposal in result["pending_proposals"]


# ===========================================================================
# close_session
# ===========================================================================


class TestCloseSession:
    @pytest.mark.asyncio
    async def test_calls_mongodb_update_conversation_status(self):
        conv_id = uuid4()
        state = _state(conversation_id=conv_id)

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            await close_session(state)

        # First call should update conversation status
        first_call = mock_agent.call_tool.call_args_list[0]
        assert first_call[0][0] == "mongodb_update_conversation"
        assert first_call[0][1]["conversation_id"] == str(conv_id)
        assert first_call[0][1]["params"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_no_proposals_skips_create_proposed_change(self):
        state = _state(pending_proposals=[])

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            await close_session(state)

        # Only the update_conversation call should have happened
        all_tool_names = [c[0][0] for c in mock_agent.call_tool.call_args_list]
        assert "mongodb_create_proposed_change" not in all_tool_names

    @pytest.mark.asyncio
    async def test_stages_each_proposal_as_proposed_change(self):
        proposals = [
            {"change_type": "entity", "content": {"name": "Dragon"}, "confidence": 0.9},
            {"change_type": "fact", "content": {"text": "Dragon guards cave"}, "confidence": 0.7},
        ]
        state = _state(pending_proposals=proposals, scene_id=uuid4(), story_id=uuid4())

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            await close_session(state)

        stage_calls = [
            c
            for c in mock_agent.call_tool.call_args_list
            if c[0][0] == "mongodb_create_proposed_change"
        ]
        assert len(stage_calls) == 2

    @pytest.mark.asyncio
    async def test_proposal_change_type_passed_to_create(self):
        proposals = [
            {
                "change_type": "state_change",
                "content": {"entity_id": str(uuid4())},
                "confidence": 0.8,
            }
        ]
        scene_id = uuid4()
        story_id = uuid4()
        state = _state(pending_proposals=proposals, scene_id=scene_id, story_id=story_id)

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        with patch("monitor_agents.npc_voice.NPCVoice", return_value=mock_agent):
            await close_session(state)

        stage_calls = [
            c
            for c in mock_agent.call_tool.call_args_list
            if c[0][0] == "mongodb_create_proposed_change"
        ]
        assert len(stage_calls) == 1
        payload = stage_calls[0][0][1]
        assert payload["params"]["change_type"] == "state_change"
        assert payload["params"]["scene_id"] == str(scene_id)
        assert payload["params"]["story_id"] == str(story_id)
        assert payload["params"]["evidence"][0]["type"] == "snippet"
