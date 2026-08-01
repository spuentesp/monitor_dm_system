"""
Unit tests for ConversationLoop nodes, state schema, and graph construction.

Uses unittest.mock only — no live databases.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.graph import END
from monitor_data.schemas.conversations import ConversationMode

from monitor_agents.loops.conversation_loop import (
    ConversationLoop,
    ConversationState,
    build_conversation_graph,
    close_session,
    generate_npc_responses,
    load_npc_context,
    open_session,
    process_player_turn,
    route_after_npc_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(**overrides: Any) -> ConversationState:
    """Build a minimal ConversationState for testing."""
    defaults: dict[str, Any] = {
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
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

        async def fake_load_npc_data(npc_id: UUID, include_secrets: bool = False):
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
            patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent),
            patch(
                "monitor_agents.context_assembly.agent.ContextAssembly._fetch_runtime_profile",
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            result = await generate_npc_responses(state)

        mock_agent.respond_direct.assert_awaited_once()
        assert len(result["current_npc_responses"]) == 1
        assert result["current_npc_responses"][0]["text"] == "I know many things."
        assert mock_agent.respond_direct.await_args.kwargs["npc_data"] == state.npc_contexts[str(npc_id)]

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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            await generate_npc_responses(state)

        kwargs = mock_agent.respond_direct.await_args.kwargs
        assert kwargs["source_profile"] == source_profile

    @pytest.mark.asyncio
    async def test_direct_mode_scans_lorebook_and_forwards_context(self):
        """Light-RP sessions carry lorebook_character_ids — the turn must scan
        entries and hand matched contents to NPCVoice as lorebook_context."""
        npc_id = uuid4()
        state = _state(
            mode=ConversationMode.DIRECT,
            npc_ids=[npc_id],
            current_player_input="Tell me about alchefire.",
            npc_contexts={str(npc_id): {"name": "Mira", "role": "alchemist"}},
            lorebook_character_ids=["char-1"],
        )

        mock_agent = MagicMock()

        async def _call_tool(name: str, params: dict) -> object:
            if name == "mongodb_get_scan_config":
                return {}
            if name == "mongodb_scan_lorebook":
                return {"before": ["Alchefire burns blue without heat."], "after": [], "depth": []}
            raise AssertionError(f"unexpected tool call: {name}")

        mock_agent.call_tool = AsyncMock(side_effect=_call_tool)
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "Alchefire? That's my secret.",
                "emotional_state_after": "guarded",
                "proposals": [],
            }
        )

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            await generate_npc_responses(state)

        kwargs = mock_agent.respond_direct.await_args.kwargs
        assert kwargs["lorebook_context"] == ["Alchefire burns blue without heat."]

    @pytest.mark.asyncio
    async def test_direct_mode_lorebook_scan_failure_still_responds(self):
        """A failing lorebook scan must not break the turn."""
        npc_id = uuid4()
        state = _state(
            mode=ConversationMode.DIRECT,
            npc_ids=[npc_id],
            current_player_input="Hello.",
            npc_contexts={str(npc_id): {"name": "Mira", "role": "alchemist"}},
            lorebook_character_ids=["char-1"],
        )

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock(side_effect=RuntimeError("mongo down"))
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "Well met.",
                "emotional_state_after": "neutral",
                "proposals": [],
            }
        )

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            result = await generate_npc_responses(state)

        assert result["current_npc_responses"][0]["text"] == "Well met."
        assert mock_agent.respond_direct.await_args.kwargs["lorebook_context"] == []

    @pytest.mark.asyncio
    async def test_direct_mode_without_lorebook_ids_skips_scan(self):
        npc_id = uuid4()
        state = _state(
            mode=ConversationMode.DIRECT,
            npc_ids=[npc_id],
            current_player_input="Hello.",
            npc_contexts={str(npc_id): {"name": "Mira", "role": "alchemist"}},
        )

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "Well met.",
                "emotional_state_after": "neutral",
                "proposals": [],
            }
        )

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            await generate_npc_responses(state)

        mock_agent.call_tool.assert_not_called()
        assert mock_agent.respond_direct.await_args.kwargs["lorebook_context"] == []

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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            result = await generate_npc_responses(state)

        mock_agent.respond_actor.assert_awaited_once()
        assert result["current_npc_responses"][0]["text"] == "She wants power."
        assert result["current_npc_responses"][0]["canon_insight"] == "hidden ambition"
        assert mock_agent.respond_actor.await_args.kwargs["npc_data"] == state.npc_contexts[str(npc_id)]

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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            await close_session(state)

        stage_calls = [c for c in mock_agent.call_tool.call_args_list if c[0][0] == "mongodb_create_proposed_change"]
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

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            await close_session(state)

        stage_calls = [c for c in mock_agent.call_tool.call_args_list if c[0][0] == "mongodb_create_proposed_change"]
        assert len(stage_calls) == 1
        payload = stage_calls[0][0][1]
        assert payload["params"]["change_type"] == "state_change"
        assert payload["params"]["scene_id"] == str(scene_id)
        assert payload["params"]["story_id"] == str(story_id)
        assert payload["params"]["evidence"][0]["type"] == "snippet"

    @pytest.mark.asyncio
    async def test_episodic_memories_staged_as_event_proposals(self):
        """End-of-chat distills salient moments from the transcript and stages
        them as event proposals — previously only state/relationship changes
        were staged, so sessions left no narrative trace for CanonKeeper."""
        npc_id = uuid4()
        state = _state(
            pending_proposals=[],
            npc_ids=[npc_id],
            npc_contexts={str(npc_id): {"name": "Kessa", "role": "captain"}},
            turns=[
                {"turn_index": 0, "speaker_role": "player", "entity_name": "Player", "text": "You're a fraud."},
                {"turn_index": 1, "speaker_role": "npc", "entity_name": "Kessa", "text": "Say that again."},
                {"turn_index": 2, "speaker_role": "player", "entity_name": "Player", "text": "I'm sorry."},
            ],
        )

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        fake_extractor = MagicMock()
        fake_extractor.forward = MagicMock(
            return_value=[
                {"text": "Aldric insulted Kessa, then apologized.", "importance": 8, "emotional_valence": -0.2}
            ]
        )

        with (
            patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent),
            patch(
                "monitor_agents.extraction.memory_extraction.MemoryExtractor",
                return_value=fake_extractor,
            ),
        ):
            await close_session(state)

        stage_calls = [c for c in mock_agent.call_tool.call_args_list if c[0][0] == "mongodb_create_proposed_change"]
        assert len(stage_calls) == 1
        params = stage_calls[0][0][1]["params"]
        assert params["change_type"] == "event"
        assert params["content"]["description"] == "Aldric insulted Kessa, then apologized."
        assert params["content"]["importance"] == 0.8
        assert params["content"]["source"] == "episodic_extraction"

    @pytest.mark.asyncio
    async def test_episodic_extraction_failure_does_not_block_close(self):
        npc_id = uuid4()
        state = _state(
            pending_proposals=[],
            npc_ids=[npc_id],
            turns=[
                {"turn_index": 0, "speaker_role": "player", "text": "hi"},
                {"turn_index": 1, "speaker_role": "npc", "text": "well met"},
            ],
        )

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()

        with (
            patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent),
            patch(
                "monitor_agents.extraction.memory_extraction.MemoryExtractor",
                side_effect=RuntimeError("llm down"),
            ),
        ):
            result = await close_session(state)

        # Session still closed; no episodic proposals staged.
        assert result == {"pending_proposals": []}
        stage_calls = [c for c in mock_agent.call_tool.call_args_list if c[0][0] == "mongodb_create_proposed_change"]
        assert stage_calls == []


# ===========================================================================
# redistill_episodic_proposals — rebuild episodic proposals from a transcript
# ===========================================================================


class TestRedistillEpisodicProposals:
    @pytest.mark.asyncio
    async def test_builds_state_from_doc_and_stages(self):
        from monitor_agents.loops.conversation_loop import redistill_episodic_proposals

        npc_id = uuid4()
        universe_id = uuid4()
        doc = {
            "conversation_id": str(uuid4()),
            "universe_id": str(universe_id),
            "mode": "direct",
            "npc_ids": [str(npc_id)],
            "turns": [
                {"turn_index": 0, "speaker_role": "player", "entity_name": "Player", "text": "join me"},
                {"turn_index": 1, "speaker_role": "npc", "entity_name": "Kessa", "text": "aye"},
            ],
        }

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()
        fake_extractor = MagicMock()
        fake_extractor.forward = MagicMock(
            return_value=[{"text": "Kessa accepted the helm.", "importance": 9, "emotional_valence": 0.4}]
        )

        with (
            patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent),
            patch(
                "monitor_agents.extraction.memory_extraction.MemoryExtractor",
                return_value=fake_extractor,
            ),
        ):
            staged = await redistill_episodic_proposals(doc)

        assert len(staged) == 1
        stage_calls = [c for c in mock_agent.call_tool.call_args_list if c[0][0] == "mongodb_create_proposed_change"]
        assert len(stage_calls) == 1
        params = stage_calls[0][0][1]["params"]
        assert params["change_type"] == "event"
        assert params["universe_id"] == str(universe_id)
        assert params["content"]["description"] == "Kessa accepted the helm."
        assert params["evidence"][0]["ref_id"] == doc["conversation_id"]

    @pytest.mark.asyncio
    async def test_empty_extraction_stages_nothing(self):
        from monitor_agents.loops.conversation_loop import redistill_episodic_proposals

        doc = {
            "conversation_id": str(uuid4()),
            "universe_id": str(uuid4()),
            "mode": "direct",
            "npc_ids": [str(uuid4())],
            "turns": [
                {"turn_index": 0, "speaker_role": "player", "text": "hi"},
                {"turn_index": 1, "speaker_role": "npc", "text": "yo"},
            ],
        }

        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock()
        fake_extractor = MagicMock()
        fake_extractor.forward = MagicMock(return_value=[])

        with (
            patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent),
            patch(
                "monitor_agents.extraction.memory_extraction.MemoryExtractor",
                return_value=fake_extractor,
            ),
        ):
            staged = await redistill_episodic_proposals(doc)

        assert staged == []
        stage_calls = [c for c in mock_agent.call_tool.call_args_list if c[0][0] == "mongodb_create_proposed_change"]
        assert stage_calls == []

    @pytest.mark.asyncio
    async def test_short_transcript_stages_nothing(self):
        from monitor_agents.loops.conversation_loop import redistill_episodic_proposals

        doc = {
            "conversation_id": str(uuid4()),
            "universe_id": str(uuid4()),
            "mode": "direct",
            "npc_ids": [str(uuid4())],
            "turns": [{"turn_index": 0, "speaker_role": "player", "text": "hi"}],
        }

        staged = await redistill_episodic_proposals(doc)
        assert staged == []


# ===========================================================================
# open_session — params wrapping + conversation_id adoption
# ===========================================================================


class TestOpenSession:
    @pytest.mark.asyncio
    async def test_wraps_create_args_in_params(self):
        state = _state()
        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock(return_value={"conversation_id": str(uuid4())})

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            await open_session(state)

        call = mock_agent.call_tool.call_args
        assert call[0][0] == "mongodb_create_conversation"
        # The tool takes a single `params` model — args must be wrapped.
        assert "params" in call[0][1]
        assert call[0][1]["params"]["mode"] == state.mode.value

    @pytest.mark.asyncio
    async def test_adopts_persisted_conversation_id(self):
        persisted = uuid4()
        state = _state(conversation_id=uuid4())
        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock(return_value={"conversation_id": str(persisted)})

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            result = await open_session(state)

        # The create tool mints its own id; the loop must adopt it so later
        # append/persist/close target the real session.
        assert result == {"conversation_id": persisted}

    @pytest.mark.asyncio
    async def test_no_persisted_id_returns_empty(self):
        state = _state()
        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock(return_value={})

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            result = await open_session(state)

        assert result == {}


# ===========================================================================
# ConversationLoop.step / finish — mid-session orchestration
#
# Regression coverage: the compiled graph has a single fixed entry point
# (open_session), so re-invoking it per turn never reached response
# generation. step()/finish() must drive the mid-session nodes directly.
# ===========================================================================


def _loop(**overrides) -> ConversationLoop:
    return ConversationLoop(
        conversation_id=overrides.get("conversation_id", uuid4()),
        universe_id=overrides.get("universe_id", uuid4()),
        mode=overrides.get("mode", ConversationMode.DIRECT),
        npc_ids=overrides.get("npc_ids", [uuid4()]),
    )


class TestConversationLoopStep:
    @pytest.mark.asyncio
    async def test_step_returns_generated_responses(self):
        loop = _loop()
        responses = [{"npc_id": "x", "npc_name": "Maeve", "text": "We don't get trouble here."}]

        async def fake_process(state):
            return {}

        async def fake_generate(state):
            return {
                "current_npc_responses": responses,
                "turns_count": state.turns_count + 1,
                "current_player_input": None,
            }

        with (
            patch("monitor_agents.loops.conversation_loop.process_player_turn", new=fake_process),
            patch(
                "monitor_agents.loops.conversation_loop.generate_npc_responses",
                new=fake_generate,
            ),
        ):
            out = await loop.step("Evening.")

        assert out == responses
        assert loop.state.turns_count == 1

    @pytest.mark.asyncio
    async def test_step_does_not_auto_close_before_max_turns(self):
        loop = _loop()
        closed = {"called": False}

        async def fake_process(state):
            return {}

        async def fake_generate(state):
            return {"current_npc_responses": [], "turns_count": 1, "current_player_input": None}

        async def fake_close(state):
            closed["called"] = True
            return {}

        with (
            patch("monitor_agents.loops.conversation_loop.process_player_turn", new=fake_process),
            patch(
                "monitor_agents.loops.conversation_loop.generate_npc_responses",
                new=fake_generate,
            ),
            patch("monitor_agents.loops.conversation_loop.close_session", new=fake_close),
        ):
            await loop.step("hi")

        assert closed["called"] is False


class TestConversationLoopFinish:
    @pytest.mark.asyncio
    async def test_finish_closes_session_and_returns_proposals(self):
        loop = _loop()
        loop.state = ConversationState(
            **{
                **loop.state.model_dump(),
                "pending_proposals": [{"change_type": "fact", "content": {}}],
            }
        )
        closed = {"called": False}

        async def fake_close(state):
            closed["called"] = True
            return {}

        with patch("monitor_agents.loops.conversation_loop.close_session", new=fake_close):
            props = await loop.finish()

        assert closed["called"] is True
        assert loop.state.is_complete is True
        assert len(props) == 1

    @pytest.mark.asyncio
    async def test_finish_is_idempotent_after_step_close(self):
        loop = _loop()
        close_count = {"n": 0}

        async def fake_close(state):
            close_count["n"] += 1
            return {}

        # Simulate the loop already having closed during step().
        loop._closed = True

        with patch("monitor_agents.loops.conversation_loop.close_session", new=fake_close):
            await loop.finish()

        assert close_count["n"] == 0
