"""Unit tests for ConversationLoop.trim_last_exchange (UX-6 rewind).

The trim API must remove the last exchange from the loop's in-memory state
AND its persisted turn history, without ending the conversation. Uses
unittest.mock only — no live databases.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from monitor_data.schemas.conversations import ConversationMode

from monitor_agents.loops.conversation_loop import (
    ConversationClosedError,
    ConversationLoop,
    ConversationState,
)

NPC_ID = uuid4()


def _loop(**overrides: Any) -> ConversationLoop:
    return ConversationLoop(
        conversation_id=overrides.get("conversation_id", uuid4()),
        universe_id=overrides.get("universe_id", uuid4()),
        mode=overrides.get("mode", ConversationMode.DIRECT),
        npc_ids=overrides.get("npc_ids", [NPC_ID]),
    )


def _seed_exchangeable_state(loop: ConversationLoop) -> dict[str, Any]:
    """Put one completed exchange on the loop; return the pre-step expectations."""
    greeting = {"turn_index": 0, "speaker_role": "npc", "text": "Hello."}
    prior_proposal = {"change_type": "fact", "content": {"old": "info"}}
    loop.state.turns = [greeting]
    loop.state.turns_count = 1
    loop.state.pending_proposals = [prior_proposal]
    loop.state.npc_contexts = {str(NPC_ID): {"name": "Mira", "profile": {"current_emotional_state": "calm"}}}
    loop.state.lorebook_overrides = {"entry-a": True}
    return {
        "turns": [greeting],
        "turns_count": 1,
        "pending_proposals": [prior_proposal],
        "emotion": "calm",
        "overrides": {"entry-a": True},
    }


@contextmanager
def _patch_turn_nodes(*, extra_proposal: dict[str, Any] | None = None):
    """Patch process/generate so one step appends a full exchange."""

    async def fake_process(state: ConversationState) -> dict[str, Any]:
        return {
            "turns": [
                *state.turns,
                {"turn_index": len(state.turns), "speaker_role": "player", "text": state.current_player_input},
            ]
        }

    async def fake_generate(state: ConversationState) -> dict[str, Any]:
        # In-place mutation of the social context, mirroring the worst case
        # the snapshot has to survive (the real nodes replace the dict, but
        # a copy must protect against either style).
        state.npc_contexts[str(NPC_ID)]["profile"]["current_emotional_state"] = "furious"
        proposals = [*state.pending_proposals]
        if extra_proposal is not None:
            proposals = [*proposals, extra_proposal]
        update: dict[str, Any] = {
            "current_npc_responses": [{"npc_id": str(NPC_ID), "npc_name": "Mira", "text": "…"}],
            "npc_contexts": state.npc_contexts,
            "turns": [
                *state.turns,
                {
                    "turn_index": len(state.turns),
                    "speaker_role": "npc",
                    "entity_id": str(NPC_ID),
                    "entity_name": "Mira",
                    "text": "…",
                },
            ],
            "pending_proposals": proposals,
            "turns_count": state.turns_count + 1,
            "current_player_input": None,
        }
        # The real node only buffers writes when the caller asked to defer.
        if state.defer_memory_writes:
            update["deferred_memory_writes"] = [*state.deferred_memory_writes, {"npc_id": str(NPC_ID)}]
        return update

    with (
        patch("monitor_agents.loops.conversation_loop.process_player_turn", new=fake_process),
        patch("monitor_agents.loops.conversation_loop.generate_npc_responses", new=fake_generate),
    ):
        yield


@contextmanager
def _patch_trim_tool(return_value: Any = None, side_effect: Exception | None = None):
    """Patch NPCVoice so trim's persisted-history call is observable.

    Yields the fake agent; its ``call_tool`` records every invocation.
    """
    agent = MagicMock()
    agent.call_tool = AsyncMock(return_value=return_value, side_effect=side_effect)
    with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=agent):
        yield agent


class TestTrimLastExchange:
    @pytest.mark.asyncio
    async def test_trim_restores_state_to_before_the_exchange(self):
        loop = _loop()
        expected = _seed_exchangeable_state(loop)

        with (
            _patch_turn_nodes(extra_proposal={"change_type": "relationship", "content": {}}),
            _patch_trim_tool(return_value={"conversation_id": str(loop.state.conversation_id)}) as voice,
        ):
            await loop.step("I knock.")
            assert loop.state.turns_count == 2  # exchange really applied
            removed = await loop.trim_last_exchange()

        assert removed == 2  # player line + NPC reply
        assert loop.state.turns == expected["turns"]
        assert loop.state.turns_count == expected["turns_count"]
        assert loop.state.pending_proposals == expected["pending_proposals"]
        assert loop.state.npc_contexts[str(NPC_ID)]["profile"]["current_emotional_state"] == expected["emotion"]
        assert loop.state.lorebook_overrides == expected["overrides"]
        assert loop.state.deferred_memory_writes == []
        assert loop.state.current_player_input is None
        # The conversation stays open — nothing closed or completed it.
        assert loop._closed is False
        assert loop.state.is_complete is False
        voice.call_tool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_trim_calls_persisted_history_tool_with_keep_turns(self):
        loop = _loop()
        _seed_exchangeable_state(loop)

        with _patch_turn_nodes(), _patch_trim_tool(return_value={"ok": True}) as voice:
            await loop.step("Hello again.")
            await loop.trim_last_exchange()

        name, args = voice.call_tool.await_args.args
        assert name == "mongodb_trim_conversation_turns"
        assert args == {"conversation_id": str(loop.state.conversation_id), "keep_turns": 1}

    @pytest.mark.asyncio
    async def test_trim_twice_walks_back_two_exchanges(self):
        loop = _loop()
        expected = _seed_exchangeable_state(loop)

        with _patch_turn_nodes(), _patch_trim_tool(return_value=None) as voice:
            await loop.step("First.")
            await loop.step("Second.")
            assert loop.state.turns_count == 3
            assert await loop.trim_last_exchange() == 2
            assert loop.state.turns_count == 2
            assert await loop.trim_last_exchange() == 2
            assert loop.state.turns_count == expected["turns_count"]
            # Nothing left to undo: the third call is a no-op.
            assert await loop.trim_last_exchange() == 0

        assert voice.call_tool.await_count == 2

    @pytest.mark.asyncio
    async def test_trim_on_fresh_loop_returns_zero_without_tool_call(self):
        loop = _loop()
        with _patch_trim_tool() as voice:
            assert await loop.trim_last_exchange() == 0

        voice.call_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trim_refuses_after_the_conversation_closed(self):
        loop = _loop()
        _seed_exchangeable_state(loop)

        with _patch_turn_nodes(), _patch_trim_tool():
            await loop.step("Final words.")
        loop._closed = True
        with _patch_trim_tool() as voice:
            assert await loop.trim_last_exchange() == 0
        voice.call_tool.assert_not_awaited()
        assert loop.state.turns_count == 2  # untouched

    @pytest.mark.asyncio
    async def test_failed_step_leaves_no_snapshot_to_trim(self):
        loop = _loop()
        _seed_exchangeable_state(loop)

        async def fake_process(state: ConversationState) -> dict[str, Any]:
            return {
                "turns": [
                    *state.turns,
                    {"speaker_role": "player", "text": state.current_player_input},
                ]
            }

        async def fake_generate(state: ConversationState) -> dict[str, Any]:
            raise RuntimeError("provider exploded")

        with (
            patch("monitor_agents.loops.conversation_loop.process_player_turn", new=fake_process),
            patch("monitor_agents.loops.conversation_loop.generate_npc_responses", new=fake_generate),
            _patch_trim_tool() as voice,
        ):
            with pytest.raises(RuntimeError, match="provider exploded"):
                await loop.step("Hi.")
            # The failed step rolled its own turn list back; trim has no
            # snapshot for it, so a rewind cannot pop a healthy exchange.
            assert await loop.trim_last_exchange() == 0

        assert loop.state.turns_count == 1
        voice.call_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_conversation_still_steps_after_a_trim(self):
        loop = _loop()
        _seed_exchangeable_state(loop)

        with _patch_turn_nodes(), _patch_trim_tool(return_value=None):
            await loop.step("Undo me.")
            await loop.trim_last_exchange()
            responses = await loop.step("And again.")

        assert responses[0]["text"] == "…"
        assert loop.state.turns_count == 2
        assert loop._closed is False

    @pytest.mark.asyncio
    async def test_persisted_trim_failure_does_not_break_the_in_memory_trim(self):
        loop = _loop()
        expected = _seed_exchangeable_state(loop)

        with _patch_turn_nodes(), _patch_trim_tool(side_effect=ValueError("mongo down")):
            await loop.step("Hello.")
            removed = await loop.trim_last_exchange()

        assert removed == 2
        assert loop.state.turns == expected["turns"]
        assert loop.state.turns_count == expected["turns_count"]

    @pytest.mark.asyncio
    async def test_tool_execution_error_text_is_logged_not_raised(self):
        """BaseAgent.call_tool returns tool failures as text, not exceptions."""
        loop = _loop()
        _seed_exchangeable_state(loop)

        with _patch_turn_nodes(), _patch_trim_tool(return_value="Error executing tool: boom"):
            await loop.step("Hello.")
            removed = await loop.trim_last_exchange()

        assert removed == 2
        assert loop.state.turns_count == 1

    @pytest.mark.asyncio
    async def test_trim_drops_buffered_memory_writes_of_the_exchange(self):
        """defer_memory_writes buffers the exchange's writes; trim discards them."""
        loop = _loop()
        _seed_exchangeable_state(loop)
        loop.state.deferred_memory_writes = [{"npc_id": "earlier-exchange"}]

        with _patch_turn_nodes(), _patch_trim_tool(return_value=None):
            await loop.step("With defer.", defer_memory_writes=True)
            # The step buffered this exchange's writes behind the earlier ones.
            assert loop.state.deferred_memory_writes == [
                {"npc_id": "earlier-exchange"},
                {"npc_id": str(NPC_ID)},
            ]
            await loop.trim_last_exchange()

        assert loop.state.deferred_memory_writes == [{"npc_id": "earlier-exchange"}]


class TestSnapshotStack:
    @pytest.mark.asyncio
    async def test_snapshot_is_pushed_only_for_completed_steps(self):
        loop = _loop()
        _seed_exchangeable_state(loop)

        async def fake_process(state: ConversationState) -> dict[str, Any]:
            return {}

        async def fake_generate(state: ConversationState) -> dict[str, Any]:
            raise RuntimeError("nope")

        with (
            patch("monitor_agents.loops.conversation_loop.process_player_turn", new=fake_process),
            patch("monitor_agents.loops.conversation_loop.generate_npc_responses", new=fake_generate),
        ):
            with pytest.raises(RuntimeError):
                await loop.step("Hi.")

        assert loop._exchange_snapshots == []

    @pytest.mark.asyncio
    async def test_closed_conversation_refuses_to_step_but_trims_nothing(self):
        loop = _loop()
        _seed_exchangeable_state(loop)
        loop.state.is_complete = True

        with pytest.raises(ConversationClosedError):
            await loop.step("Hi.")
        assert await loop.trim_last_exchange() == 0


def test_snapshot_captures_npc_context_by_copy():
    """The snapshot must not alias the live npc_contexts dict."""
    loop = _loop()
    loop.state.npc_contexts = {str(NPC_ID): {"name": "Mira", "profile": {"current_emotional_state": "calm"}}}
    snapshot = loop._snapshot_exchange()
    loop.state.npc_contexts[str(NPC_ID)]["profile"]["current_emotional_state"] = "enraged"
    assert snapshot["npc_contexts"][str(NPC_ID)]["profile"]["current_emotional_state"] == "calm"
