"""Player-persona threading: loop state → NPCVoice → DSPy voice module."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.loops import conversation_loop as cl


def _null_dspy_context():
    return patch(
        "monitor_agents.npc_voice.npc_voice.dspy_context_for",
        lambda *a, **kw: contextlib.nullcontext(),
    )


class TestDirectVoiceModulePersona:
    def test_forward_passes_player_persona(self):
        from monitor_agents.npc_voice.npc_voice import NPCDirectVoiceModule

        module = NPCDirectVoiceModule()
        captured: dict = {}

        class _FakeSpeak:
            def __call__(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace()

        module.speak = _FakeSpeak()
        with _null_dspy_context():
            module.forward(
                npc_name="Maeve",
                npc_role="innkeeper",
                personality_summary="wary",
                current_emotional_state="calm",
                relevant_memories="[]",
                known_facts="[]",
                active_triggers="[]",
                conversation_history="",
                profile_context="",
                player_said="Hello.",
                player_persona="Kael — a wandering sellsword",
            )
        assert captured["player_persona"] == "Kael — a wandering sellsword"

    def test_forward_defaults_persona_empty(self):
        from monitor_agents.npc_voice.npc_voice import NPCDirectVoiceModule

        module = NPCDirectVoiceModule()
        captured: dict = {}

        class _FakeSpeak:
            def __call__(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace()

        module.speak = _FakeSpeak()
        with _null_dspy_context():
            module.forward(
                npc_name="Maeve",
                npc_role="innkeeper",
                personality_summary="wary",
                current_emotional_state="calm",
                relevant_memories="[]",
                known_facts="[]",
                active_triggers="[]",
                conversation_history="",
                profile_context="",
                player_said="Hello.",
            )
        assert captured["player_persona"] == ""


class TestConversationLoopPersona:
    def _state(self, persona: str) -> cl.ConversationState:
        npc_id = uuid.uuid4()
        return cl.ConversationState(
            conversation_id=uuid.uuid4(),
            universe_id=uuid.uuid4(),
            mode=cl.ConversationMode.DIRECT,
            npc_ids=[npc_id],
            current_player_input="Hello.",
            npc_contexts={str(npc_id): {"name": "Maeve"}},
            player_persona=persona,
        )

    def test_persona_threaded_into_respond_direct(self):
        state = self._state("Kael — a wandering sellsword")

        fake_voice = AsyncMock()
        fake_voice.respond_direct = AsyncMock(
            return_value={
                "npc_response": '"A sellsword, hm?"',
                "emotional_state_after": "curious",
                "proposals": [],
            }
        )

        with pytest.MonkeyPatch.context() as mp:
            import monitor_agents.npc_voice.agent as npc_agent_mod

            mp.setattr(npc_agent_mod, "NPCVoice", lambda: fake_voice)
            out = asyncio.run(cl.generate_npc_responses(state))

        assert fake_voice.respond_direct.await_args.kwargs["player_persona"] == (
            "Kael — a wandering sellsword"
        )
        assert out["current_npc_responses"][0]["text"] == '"A sellsword, hm?"'

    def test_empty_persona_passed_as_empty(self):
        state = self._state("")

        fake_voice = AsyncMock()
        fake_voice.respond_direct = AsyncMock(
            return_value={
                "npc_response": '"Yes?"',
                "emotional_state_after": "neutral",
                "proposals": [],
            }
        )

        with pytest.MonkeyPatch.context() as mp:
            import monitor_agents.npc_voice.agent as npc_agent_mod

            mp.setattr(npc_agent_mod, "NPCVoice", lambda: fake_voice)
            asyncio.run(cl.generate_npc_responses(state))

        assert fake_voice.respond_direct.await_args.kwargs["player_persona"] == ""

    def test_loop_init_accepts_persona(self):
        loop = cl.ConversationLoop(
            conversation_id=uuid.uuid4(),
            universe_id=uuid.uuid4(),
            mode=cl.ConversationMode.DIRECT,
            npc_ids=[uuid.uuid4()],
            player_persona="Kael — sellsword",
        )
        assert loop.state.player_persona == "Kael — sellsword"
