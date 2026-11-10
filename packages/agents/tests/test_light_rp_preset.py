"""
Light RP preset, persona/agency, and deferred memory writes (Phase 7).

Uses unittest.mock only — no live databases. The wiring tests assert the
real callee (NPCVoice methods) is invoked with the expected arguments.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from monitor_data.schemas.conversations import ConversationMode

from monitor_agents.cast import AGENCY_RULE
from monitor_agents.loops.conversation_loop import (
    ConversationLoop,
    ConversationState,
    _flush_memory_writes,
    _make_voice_agent,
    _persona_prompt_block,
    close_session,
    get_preset,
)


def _state(**overrides: Any) -> ConversationState:
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
# LightPreset (task 2)
# ===========================================================================


class TestLightPreset:
    def test_named_preset_declares_light_rp(self):
        preset = get_preset("light")
        assert preset.name == "light"
        assert preset.dice is False
        assert preset.gm_verdict is False
        assert preset.canonization_prompts is False
        assert preset.stage_canon_proposals is False
        assert preset.model_tier in ("light", "standard")

    def test_unknown_preset_raises(self):
        with pytest.raises(KeyError):
            get_preset("hardcore")

    def test_loop_applies_preset(self):
        loop = ConversationLoop(
            conversation_id=uuid4(),
            universe_id=uuid4(),
            mode=ConversationMode.DIRECT,
            npc_ids=[uuid4()],
            preset="light",
        )
        assert loop.state.preset_name == "light"
        assert loop.state.model_tier == "light"
        assert loop.state.stage_canon_proposals is False

    def test_loop_without_preset_keeps_canon_staging(self):
        loop = ConversationLoop(
            conversation_id=uuid4(),
            universe_id=uuid4(),
            mode=ConversationMode.DIRECT,
            npc_ids=[uuid4()],
        )
        assert loop.state.preset_name == ""
        assert loop.state.stage_canon_proposals is True


class TestCloseWithoutCanonization:
    async def test_light_close_stages_no_proposals_but_completes(self):
        state = _state(
            stage_canon_proposals=False,
            pending_proposals=[{"change_type": "relationship", "content": {}}],
        )
        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock(return_value={})
        with (
            patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent),
            patch(
                "monitor_agents.loops.conversation_loop._extract_episodic_memories",
                new_callable=AsyncMock,
            ) as extract,
        ):
            result = await close_session(state)

        assert result["is_complete"] is True
        assert result["pending_proposals"] == []
        extract.assert_not_awaited()
        tool_names = [call.args[0] for call in mock_agent.call_tool.await_args_list]
        assert "mongodb_create_proposed_change" not in tool_names
        assert "mongodb_update_conversation" in tool_names

    async def test_close_flushes_leftover_deferred_writes(self):
        buffered = {"npc_id": uuid4(), "player_said": "hi", "npc_said": "hey", "conversation_id": uuid4()}
        state = _state(stage_canon_proposals=False, deferred_memory_writes=[buffered])
        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock(return_value={})
        with (
            patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent),
            patch(
                "monitor_agents.loops.conversation_loop._flush_memory_writes",
                new_callable=AsyncMock,
            ) as flush,
        ):
            await close_session(state)
        flush.assert_awaited_once_with([buffered])
        assert state.deferred_memory_writes == []


# ===========================================================================
# Persona + the Phase 4 agency rule (task 4)
# ===========================================================================


class TestPersonaAndAgency:
    def test_block_carries_persona_and_the_real_cast_rule(self):
        state = _state(
            player_entity_id=uuid4(),
            player_name="Mira",
            player_persona="Mira — a smuggler with a soft spot for strays.",
        )
        block = _persona_prompt_block(state, uuid4(), "Wisp")
        assert "Mira — a smuggler with a soft spot for strays." in block
        # The single source of the rule is monitor_agents.cast — reused, not copied.
        assert AGENCY_RULE in block
        assert "[PLAYER-CONTROLLED] Mira" in block
        assert "(SPEAKING NOW)" in block
        assert "[GM-CONTROLLED] Wisp" in block

    def test_block_without_persona_still_states_the_rule(self):
        state = _state(player_entity_id=uuid4())
        block = _persona_prompt_block(state, uuid4(), "Wisp")
        assert AGENCY_RULE in block
        assert "[GM-CONTROLLED] Wisp" in block

    async def test_respond_direct_receives_the_composed_block(self):
        npc_id = uuid4()
        player_id = uuid4()
        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock(return_value={})
        mock_agent.respond_direct = AsyncMock(
            return_value={
                "npc_response": "Well met.",
                "emotional_state_after": "calm",
                "relationship_delta": "none",
                "social_read": {},
                "relationship_snapshot": {},
                "proposals": [],
            }
        )
        state = _state(
            npc_ids=[npc_id],
            player_entity_id=player_id,
            player_name="Mira",
            player_persona="Mira — a smuggler with a soft spot for strays.",
            npc_contexts={str(npc_id): {"name": "Wisp", "role": "guide", "profile": {}, "facts": []}},
            current_player_input="Hello!",
            turns=[{"turn_index": 0, "speaker_role": "player", "text": "Hello!"}],
        )
        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            from monitor_agents.loops.conversation_loop import generate_npc_responses

            await generate_npc_responses(state)

        mock_agent.respond_direct.assert_awaited_once()
        kwargs = mock_agent.respond_direct.await_args.kwargs
        assert kwargs["npc_id"] == npc_id
        assert kwargs["player_said"] == "Hello!"
        assert "Mira — a smuggler with a soft spot for strays." in kwargs["player_persona"]
        assert AGENCY_RULE in kwargs["player_persona"]


# ===========================================================================
# Model tier (task 2 preset knob)
# ===========================================================================


class TestModelTier:
    def test_light_tier_keeps_the_default_voice_module(self):
        agent, writer = _make_voice_agent("light")
        assert type(agent._direct_module).__name__ == "NPCDirectVoiceModule"
        assert writer is None

    def test_standard_tier_installs_the_tiered_module(self):
        agent, _ = _make_voice_agent("standard")
        assert type(agent._direct_module).__name__ == "_TieredDirectVoiceModule"

    def test_tiered_module_runs_under_standard(self):
        import contextlib as _ctx

        from monitor_data.schemas.llm_config import ModelRole

        agent, _ = _make_voice_agent("standard")
        module = agent._direct_module
        module.speak = MagicMock(return_value="prediction")
        with patch(
            "monitor_agents.dspy_runtime.dspy_context_for",
            side_effect=lambda *a, **k: _ctx.nullcontext(),
        ) as mock_ctx:
            module.forward(npc_name="Wisp")
        module.speak.assert_called_once_with(npc_name="Wisp")
        mock_ctx.assert_called_once_with("npc_voice", ModelRole.STANDARD)


# ===========================================================================
# Deferred memory writes (task 3: writes happen after the stream completes)
# ===========================================================================


class TestDeferredMemoryWrites:
    async def test_deferring_agent_buffers_the_write(self):
        agent, writer = _make_voice_agent("light", defer_memory_writes=True)
        assert writer is not None
        await agent._write_npc_memory(
            npc_id=uuid4(),
            player_said="hi",
            npc_said="hey",
            conversation_id=uuid4(),
            emotional_state_after="calm",
            relationship_delta="none",
            scene_id=None,
            story_id=None,
            universe_id=uuid4(),
        )
        assert len(writer.calls) == 1
        assert writer.calls[0]["player_said"] == "hi"

    async def test_flush_invokes_the_real_write_with_expected_arguments(self):
        npc_id = uuid4()
        conv_id = uuid4()
        universe_id = uuid4()
        buffered = {
            "npc_id": npc_id,
            "player_said": "hi",
            "npc_said": "hey",
            "conversation_id": conv_id,
            "emotional_state_after": "calm",
            "relationship_delta": "trust:+0.1",
            "scene_id": None,
            "story_id": None,
            "universe_id": universe_id,
        }
        with patch(
            "monitor_agents.npc_voice.agent.NPCVoice._write_npc_memory",
            new_callable=AsyncMock,
        ) as real_write:
            flushed = await _flush_memory_writes([buffered])

        assert flushed == 1
        # The real callee is invoked with exactly what respond_direct would pass.
        real_write.assert_awaited_once()
        assert real_write.await_args.kwargs == buffered

    async def test_step_defers_then_flush_runs_the_real_write(self):
        npc_id = uuid4()
        mock_agent = MagicMock()
        mock_agent.call_tool = AsyncMock(return_value={})

        async def _respond(**kwargs: Any) -> dict[str, Any]:
            await mock_agent._write_npc_memory(
                npc_id=npc_id,
                player_said=kwargs["player_said"],
                npc_said="Hey.",
                conversation_id=kwargs["conversation_id"],
                emotional_state_after="calm",
                relationship_delta="none",
                scene_id=None,
                story_id=None,
                universe_id=kwargs["universe_id"],
            )
            return {
                "npc_response": "Hey.",
                "emotional_state_after": "calm",
                "relationship_delta": "none",
                "social_read": {},
                "relationship_snapshot": {},
                "proposals": [],
            }

        mock_agent.respond_direct = AsyncMock(side_effect=_respond)
        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            loop = ConversationLoop(
                conversation_id=uuid4(),
                universe_id=uuid4(),
                mode=ConversationMode.DIRECT,
                npc_ids=[npc_id],
                preset="light",
            )
            loop.state.npc_contexts = {str(npc_id): {"name": "Wisp", "role": "guide", "profile": {}, "facts": []}}
            responses = await loop.step("Hi.", defer_memory_writes=True)

        assert responses[0]["text"] == "Hey."
        assert len(loop.state.deferred_memory_writes) == 1

        with patch(
            "monitor_agents.npc_voice.agent.NPCVoice._write_npc_memory",
            new_callable=AsyncMock,
        ) as real_write:
            flushed = await loop.flush_memory_writes()

        assert flushed == 1
        real_write.assert_awaited_once()
        assert real_write.await_args.kwargs["player_said"] == "Hi."
        assert loop.state.deferred_memory_writes == []
