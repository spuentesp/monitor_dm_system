"""Streaming send: live token delivery through send_message_stream (Phase 7).

The fake loop's ``step`` invokes the token callback with delays and events —
no live LM, no databases. These tests assert:
- the first token reaches the consumer before generation finishes,
- only the reply text is streamed and "done" carries the emotional /
  relationship read,
- deferred memory writes are flushed after the last chunk,
- the fallback path (the model cannot stream) replays the completed reply in
  word chunks — the pre-streaming behavior,
- a client disconnect stops generation and never flushes a half reply as a
  memory.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_ui.routers import character_conversation as cc

REPLY_TEXT = "We don't get trouble here."
EMOTION = "guarded"
SNAPSHOT = {"stance": "guarded", "trust": -0.1}


def _reply(text: str = REPLY_TEXT) -> dict[str, Any]:
    return {
        "text": text,
        "emotional_state": EMOTION,
        "relationship_snapshot": SNAPSHOT,
    }


class FakeLoop:
    """Stand-in for ConversationLoop driven by a scripted step()."""

    def __init__(self, step_impl: Any, order: list[str] | None = None) -> None:
        self.state = SimpleNamespace(
            turns=[],
            pending_proposals=[],
            lorebook_overrides={},
            include_cross_incarnation=False,
        )
        self._closed = False
        self.step = AsyncMock(side_effect=step_impl)
        self.flush_memory_writes = AsyncMock(return_value=1)
        if order is not None:
            self.flush_memory_writes = AsyncMock(side_effect=self._record_flush(order))

    @staticmethod
    def _record_flush(order: list[str]) -> Any:
        async def _flush() -> int:
            order.append("flush")
            return 1

        return _flush


async def _collect(stream: Any, order: list[str] | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    async for event in stream:
        events.append(event)
        if order is not None:
            order.append(f"event:{event['type']}")
    return events


class TestLiveTokenDelivery:
    def setup_method(self) -> None:
        cc._LOOPS.clear()

    async def test_first_token_reaches_the_consumer_before_generation_finishes(self) -> None:
        proceed = asyncio.Event()
        finished = asyncio.Event()

        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            await token_callback("Well ")
            await proceed.wait()
            await token_callback("met.")
            finished.set()
            return [_reply("Well met.")]

        cc._cache_loop("conv-live", FakeLoop(step_impl))
        stream = await cc.send_message_stream("conv-live", "hi")

        first = await stream.__anext__()
        assert first == {"type": "token", "text": "Well "}
        # Generation is still running when the first token is delivered.
        assert not finished.is_set()

        proceed.set()
        rest = await _collect(stream)
        assert finished.is_set()
        assert [e["type"] for e in rest] == ["token", "done"]
        assert rest[0]["text"] == "met."

    async def test_only_reply_text_is_streamed_and_done_carries_the_read(self) -> None:
        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            for piece in ("We don't ", "get ", "trouble ", "here."):
                await token_callback(piece)
            return [_reply()]

        cc._cache_loop("conv-text", FakeLoop(step_impl))
        events = await _collect(await cc.send_message_stream("conv-text", "hi"))

        assert [e["type"] for e in events] == ["token"] * 4 + ["done"]
        assert "".join(e["text"] for e in events if e["type"] == "token") == REPLY_TEXT
        done = events[-1]
        assert done["text"] == REPLY_TEXT
        assert done["emotional_state"] == EMOTION
        assert done["relationship_snapshot"] == SNAPSHOT
        assert done["conversation_id"] == "conv-text"
        # Nothing but reply text: no extra keys on the token events.
        assert all(set(e) == {"type", "text"} for e in events if e["type"] == "token")

    async def test_step_receives_deferred_writes_and_the_token_callback(self) -> None:
        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            await token_callback("Hi.")
            return [_reply("Hi.")]

        loop = FakeLoop(step_impl)
        cc._cache_loop("conv-wire", loop)
        await _collect(await cc.send_message_stream("conv-wire", "hello"))

        loop.step.assert_awaited_once()
        kwargs = loop.step.await_args.kwargs
        assert kwargs["defer_memory_writes"] is True
        assert callable(kwargs["token_callback"])

    async def test_memory_writes_happen_after_the_last_chunk(self) -> None:
        order: list[str] = []

        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            await token_callback("We don't ")
            await token_callback("get trouble here.")
            return [_reply()]

        cc._cache_loop("conv-order", FakeLoop(step_impl, order=order))
        events = await _collect(await cc.send_message_stream("conv-order", "hi"), order=order)

        assert [e["type"] for e in events] == ["token", "token", "done"]
        # The flush runs after the done event was delivered to the consumer.
        assert order == ["event:token", "event:token", "event:done", "flush"]

    async def test_loop_closed_during_stream_is_evicted(self) -> None:
        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            await token_callback("Hi.")
            loop = cc.get_loop("conv-closed")
            loop._closed = True
            return [_reply("Hi.")]

        cc._cache_loop("conv-closed", FakeLoop(step_impl))
        await _collect(await cc.send_message_stream("conv-closed", "hi"))
        assert cc.get_loop("conv-closed") is None


class TestFallbackReplay:
    def setup_method(self) -> None:
        cc._LOOPS.clear()

    async def test_non_streaming_model_replays_the_reply_in_word_chunks(self) -> None:
        """When the model cannot stream, the pre-streaming behavior holds."""

        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            # token_callback deliberately unused: no live tokens produced.
            return [_reply()]

        cc._cache_loop("conv-fb", FakeLoop(step_impl))
        events = await _collect(await cc.send_message_stream("conv-fb", "hi"))

        tokens = [e["text"] for e in events if e["type"] == "token"]
        assert len(tokens) > 1  # word chunks, exactly like before streaming
        assert "".join(tokens) == REPLY_TEXT
        assert events[-1]["type"] == "done"
        assert events[-1]["text"] == REPLY_TEXT

    async def test_empty_reply_still_ends_with_done(self) -> None:
        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            return []

        cc._cache_loop("conv-empty", FakeLoop(step_impl))
        events = await _collect(await cc.send_message_stream("conv-empty", "hi"))
        assert [e["type"] for e in events] == ["done"]
        assert events[0]["text"] == ""


class TestDisconnect:
    def setup_method(self) -> None:
        cc._LOOPS.clear()

    async def test_disconnect_stops_generation_and_writes_no_half_reply_memory(self) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()
        release = asyncio.Event()

        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            await token_callback("Hal")
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            await token_callback("f a complete reply.")
            return [_reply("Half a complete reply.")]

        loop = FakeLoop(step_impl)
        cc._cache_loop("conv-disc", loop)
        stream = await cc.send_message_stream("conv-disc", "hi")

        first = await stream.__anext__()
        assert first == {"type": "token", "text": "Hal"}
        assert started.is_set()

        await stream.aclose()
        await asyncio.wait_for(cancelled.wait(), timeout=2.0)
        # Generation stopped mid-reply: no flush — a half reply is never
        # written as a memory (the deferred buffer only holds complete
        # exchanges, and it is not flushed here).
        loop.flush_memory_writes.assert_not_awaited()
        release.set()

    async def test_disconnect_after_a_completed_reply_still_remembers_it(self) -> None:
        """The exchange happened as a whole — the old invariant is kept."""
        completed = asyncio.Event()

        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            await token_callback("Well met.")
            completed.set()
            return [_reply("Well met.")]

        loop = FakeLoop(step_impl)
        cc._cache_loop("conv-disc2", loop)
        stream = await cc.send_message_stream("conv-disc2", "hi")

        # Take the first token, then drop the client before "done".
        await stream.__anext__()
        await asyncio.wait_for(completed.wait(), timeout=2.0)
        await stream.aclose()

        for _ in range(50):
            if loop.flush_memory_writes.await_count:
                break
            await asyncio.sleep(0.01)
        loop.flush_memory_writes.assert_awaited_once()


class TestGenerationErrors:
    def setup_method(self) -> None:
        cc._LOOPS.clear()

    async def test_step_error_propagates_to_the_consumer(self) -> None:
        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            raise RuntimeError("boom")

        cc._cache_loop("conv-err", FakeLoop(step_impl))
        stream = await cc.send_message_stream("conv-err", "hi")
        with pytest.raises(RuntimeError, match="boom"):
            await stream.__anext__()

    async def test_step_error_persists_the_turn_snapshot(self) -> None:
        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            raise RuntimeError("boom")

        loop = FakeLoop(step_impl)
        loop.state.turns = [{"turn_index": 0, "speaker_role": "player", "text": "hi"}]
        cc._cache_loop("conv-err2", loop)
        mongo = MagicMock()

        with patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo):
            stream = await cc.send_message_stream("conv-err2", "hi")
            with pytest.raises(RuntimeError):
                await stream.__anext__()

        mongo.get_collection.return_value.update_one.assert_called_once()
        args = mongo.get_collection.return_value.update_one.call_args.args
        assert args[0] == {"conversation_id": "conv-err2"}
        assert args[1] == {"$set": {"turns": [{"turn_index": 0, "speaker_role": "player", "text": "hi"}]}}

    async def test_closed_conversation_maps_to_keyerror(self) -> None:
        from monitor_agents.loops.conversation_loop import ConversationClosedError

        async def step_impl(text: str, *, defer_memory_writes: bool = False, token_callback: Any = None) -> Any:
            raise ConversationClosedError("closed")

        cc._cache_loop("conv-closed2", FakeLoop(step_impl))
        stream = await cc.send_message_stream("conv-closed2", "hi")
        with pytest.raises(KeyError):
            await stream.__anext__()
        assert cc.get_loop("conv-closed2") is None
