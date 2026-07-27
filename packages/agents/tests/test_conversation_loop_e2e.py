"""
ConversationLoop orchestration e2e — live DB.

Regression coverage for the ConversationLoop.start() / step() / finish()
orchestration bug fixed earlier this session. The bug: step() re-invoked the
compiled graph from its fixed entry point (open_session) and never reached
process_player_turn / generate_npc_responses, so every player turn came back
empty and the NPC wasn't acknowledged.

This test is gated behind ``RUN_INTEGRATION=1`` (see root conftest.py) and
drives the loop against the real MongoDB + Neo4j stack with a mocked DSPy
module so the LLM is never actually called.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from unittest.mock import patch
from uuid import UUID

import pytest

from monitor_agents.loops.conversation_loop import ConversationLoop, ConversationMode
from monitor_agents.npc_voice.agent import NPCDirectResponse, NPCVoice

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration

SKIP_REASON = "Set RUN_INTEGRATION=1 (or RUN_E2E=1) to run live-DB tests"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _stub_dspy_direct():
    """Patch NPCVoice's DSPy direct-voice module so the LLM is never called."""

    class _Mod:
        def __call__(self, **_kwargs):
            return NPCDirectResponse(
                npc_response="We don't get much trouble here.",
                emotional_state_after="guarded",
                relationship_delta="trust:+0.1",
            )

    _orig_init = NPCVoice.__init__

    def _patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        self._direct_module = _Mod()

    with patch.object(NPCVoice, "__init__", _patched_init):
        yield


async def _assemble_npc() -> tuple[UUID, UUID]:
    """Provision a real CharacterEntity + NPCProfile. Returns (universe_id, entity_id)."""
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.npc_profiles import NPCProfileCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_npc_profile
    from monitor_data.tools.neo4j_tools.entities import neo4j_create_entity

    from monitor_agents.canonkeeper.agent import CanonKeeper

    keeper = CanonKeeper()
    mv = await keeper.create_multiverse(
        {
            "name": "LoopE2E Multiverse",
            "system_name": "Freeform",
            "description": "ephemeral e2e fixture",
        }
    )
    u = await keeper.create_universe(
        {
            "multiverse_id": str(mv["id"]),
            "name": "LoopE2E Universe",
            "genre": "Freeform",
            "description": "ephemeral",
            "tone": "neutral",
        }
    )
    universe_uuid = u["id"] if isinstance(u, dict) else u.id
    entity = neo4j_create_entity(
        EntityCreate(
            universe_id=universe_uuid,
            name="Aldric",
            entity_type="character",
            sub_type="npc",
            is_archetype=False,
            description="LoopE2E NPC",
            properties={"role": "innkeeper"},
        )
    )
    mongodb_create_npc_profile(
        NPCProfileCreate(
            entity_id=entity.id,
            speech_style="clipped",
            current_emotional_state="guarded",
        )
    )
    return universe_uuid, entity.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_step_returns_nonempty_responses_for_each_player_input():
    """Regression: step() must return non-empty responses on each call.

    The pre-fix bug had step() re-invoking open_session from the compiled
    graph entry point, ending at load_npc_context before reaching
    process_player_turn / generate_npc_responses — so every step() came
    back with empty current_npc_responses. This test pins the contract.
    """
    universe_id, entity_id = await _assemble_npc()

    with _stub_dspy_direct():
        loop = await ConversationLoop.start(
            universe_id=universe_id,
            mode=ConversationMode.DIRECT,
            npc_ids=[entity_id],
        )

        responses_1 = await loop.step("Evening.")
        responses_2 = await loop.step("Who are you?")

        assert responses_1, "first step() returned no responses (regression)"
        assert responses_2, "second step() returned no responses (regression)"
        assert all(r.get("text") for r in responses_1 + responses_2), "step() returned a response with empty text"

        await loop.finish()
        assert loop.state.conversation_id is not None
        assert loop.state.is_complete is True


async def test_finish_marks_loop_closed_and_idempotent():
    """After finish(), the loop must be marked closed; a second finish() is a no-op.

    Before the fix, finish() was the graph re-invocation that ended at
    load_npc_context — the close_session node was never reached, the
    conversation stayed open in MongoDB, and proposals were never staged.
    """
    universe_id, entity_id = await _assemble_npc()

    with _stub_dspy_direct():
        loop = await ConversationLoop.start(
            universe_id=universe_id,
            mode=ConversationMode.DIRECT,
            npc_ids=[entity_id],
        )
        await loop.step("hi")

        # First finish — must mark closed + stage proposals (none in this canned case).
        await loop.finish()
        assert getattr(loop, "_closed", False) is True

        # Second finish — must be a no-op (no exception, no further side effects).
        result = await loop.finish()
        # Whatever the second call returns, it must not have crashed.
        assert isinstance(result, list)
        assert loop._closed is True
