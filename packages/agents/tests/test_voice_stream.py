"""Live token streaming for the direct NPC voice (Phase 7, task 3).

A fake streaming LM yields tokens with delays. These tests assert:
- the first token reaches the callback before the LM stream finishes,
- only the spoken reply text is streamed (no field names, markers, other
  fields, reasoning or JSON),
- the fallback path when the provider/model cannot stream (logged, not
  silent) and the reply arrives through the non-streaming call,
- respond_direct wires the callback through the real voice module and the
  real dspy_runtime gate, for the LIGHT and the STANDARD tier variants,
- a cancelled voice call buffers no memory write (no half reply remembered),
- ConversationLoop forwards the callback to the real NPCVoice.respond_direct.

Uses unittest.mock only — no live databases and no real LM.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from monitor_data.schemas.conversations import ConversationMode
from monitor_data.schemas.llm_config import LLMProviderType

from monitor_agents import dspy_runtime, voice_stream
from monitor_agents.loops.conversation_loop import (
    ConversationLoop,
    _make_voice_agent,
    generate_npc_responses,
)
from monitor_agents.npc_voice.agent import NPCVoice

# =============================================================================
# Fake streaming LM
# =============================================================================

REPLY_TEXT = "Well met, traveler. The road is long and the night is cold."
EMOTION_AFTER = "curious"
DELTA = "trust:+0.1"

COMPLETION = (
    "[[ ## npc_response ## ]]\n"
    f"{REPLY_TEXT}\n"
    "\n"
    "[[ ## emotional_state_after ## ]]\n"
    f"{EMOTION_AFTER}\n"
    "\n"
    "[[ ## relationship_delta ## ]]\n"
    f"{DELTA}\n"
    "\n"
    "[[ ## completed ## ]]\n"
)


class FakeDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.delta = FakeDelta(content)


class FakeChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [FakeChoice(content)]


def split_awkwardly(text: str, size: int = 7) -> list[str]:
    """Split mid-word and mid-marker so chunk boundaries cannot hide bugs."""
    return [text[i : i + size] for i in range(0, len(text), size)]


def make_fake_completion(
    pieces: list[str],
    *,
    delay: float = 0.0,
    finished_at: dict[str, float] | None = None,
    fail_after: int | None = None,
):
    """Build a replacement for litellm.completion that streams ``pieces``."""

    def _completion(**kwargs: Any) -> Any:
        assert kwargs.get("stream") is True

        def _gen() -> Any:
            for i, piece in enumerate(pieces):
                if fail_after is not None and i >= fail_after:
                    raise RuntimeError("stream broke")
                if delay:
                    time.sleep(delay)
                yield FakeChunk(piece)
            if finished_at is not None:
                finished_at["at"] = time.monotonic()

        return _gen()

    return _completion


async def _wait_for(predicate: Any, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached in time")


class _FakeClient:
    def __init__(self) -> None:
        self.model = "gpt-test"
        self.provider = LLMProviderType.OPENAI
        self.params: dict[str, Any] = {}
        self.api_key = "fake-key"
        self.base_url = None


def _stub_call_tool(sample_npc_data: dict[str, Any]) -> Any:
    async def mock_call_tool(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "neo4j_get_entity":
            return {
                "name": sample_npc_data["name"],
                "universe_id": "uni-test",
                "properties": {"role": sample_npc_data["role"]},
            }
        if tool_name == "mongodb_get_npc_profile":
            return sample_npc_data["profile"]
        if tool_name == "neo4j_list_facts":
            return [{"statement": f} for f in sample_npc_data["facts"]]
        if tool_name == "qdrant_search_memories":
            return [{"text": "I saw you defend the market from bandits"}]
        return {}

    return mock_call_tool


def _sample_npc_data() -> dict[str, Any]:
    return {
        "name": "Commander Aldric",
        "role": "city guard captain",
        "profile": {"speech_style": "terse", "current_emotional_state": "guarded", "triggers": []},
        "facts": [],
    }


# =============================================================================
# Reply-field extraction
# =============================================================================


class TestReplyFieldExtractor:
    def test_streams_only_the_reply_text(self):
        ex = voice_stream._ReplyFieldExtractor()
        out = "".join(ex.feed(COMPLETION[:i]) for i in range(1, len(COMPLETION) + 1))
        out += ex.finish(COMPLETION)
        assert out == REPLY_TEXT

    def test_never_emits_markers_field_names_or_other_fields(self):
        ex = voice_stream._ReplyFieldExtractor()
        out = "".join(ex.feed(COMPLETION[:i]) for i in range(1, len(COMPLETION) + 1))
        out += ex.finish(COMPLETION)
        for leak in ("[[", "##", "npc_response", "emotional_state_after", "relationship_delta", EMOTION_AFTER, DELTA):
            assert leak not in out

    def test_preamble_before_the_reply_marker_is_not_streamed(self):
        text = "Hmm, let me think about [[ ## reasoning ## ]] hmm.\n" + COMPLETION
        ex = voice_stream._ReplyFieldExtractor()
        out = "".join(ex.feed(text[:i]) for i in range(1, len(text) + 1))
        assert out == REPLY_TEXT
        assert "Hmm" not in out

    def test_json_fallback_output_streams_nothing(self):
        text = '{"npc_response": "Well met.", "emotional_state_after": "calm", "relationship_delta": "none"}'
        ex = voice_stream._ReplyFieldExtractor()
        out = "".join(ex.feed(text[:i]) for i in range(1, len(text) + 1))
        out += ex.finish(text)
        assert out == ""

    def test_completed_before_reply_marker_aborts(self):
        text = "[[ ## completed ## ]]\n" + COMPLETION
        ex = voice_stream._ReplyFieldExtractor()
        out = "".join(ex.feed(text[:i]) for i in range(1, len(text) + 1))
        out += ex.finish(text)
        assert out == ""

    def test_held_back_tail_is_flushed_at_finish(self):
        # A short reply never crosses the hold-back window while open.
        text = "[[ ## npc_response ## ]]\nHi.\n"
        ex = voice_stream._ReplyFieldExtractor()
        out = "".join(ex.feed(text[:i]) for i in range(1, len(text) + 1))
        assert out == ""  # held back while no closing marker has arrived
        assert ex.finish(text) == "Hi."

    def test_partial_marker_tail_never_leaks(self):
        text = "[[ ## npc_response ## ]]\nWell met.\n\n[[ ## emotional_sta"
        ex = voice_stream._ReplyFieldExtractor()
        out = "".join(ex.feed(text[:i]) for i in range(1, len(text) + 1))
        out += ex.finish(text)
        assert out == "Well met."

    def test_interior_whitespace_is_preserved(self):
        text = "[[ ## npc_response ## ]]\nWell   met,\ntraveler.\n\n[[ ## completed ## ]]\n"
        ex = voice_stream._ReplyFieldExtractor()
        out = "".join(ex.feed(text[:i]) for i in range(1, len(text) + 1))
        out += ex.finish(text)
        assert out == "Well   met,\ntraveler."


# =============================================================================
# try_stream_voice_reply
# =============================================================================


class TestTryStreamVoiceReply:
    @pytest.mark.asyncio
    async def test_no_sink_skips_streaming_entirely(self, monkeypatch: pytest.MonkeyPatch) -> None:
        completion = Mock(side_effect=AssertionError("must not be called"))
        monkeypatch.setattr(voice_stream.litellm, "completion", completion)
        assert voice_stream.voice_stream_var.get() is None
        assert voice_stream.try_stream_voice_reply("openai/gpt-test", [{"role": "user", "content": "hi"}], {}) is None
        completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_token_arrives_before_the_lm_finishes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events: list[tuple[float, str]] = []
        finished_at: dict[str, float] = {}

        async def cb(text: str) -> None:
            events.append((time.monotonic(), text))

        monkeypatch.setattr(
            voice_stream.litellm,
            "completion",
            make_fake_completion(split_awkwardly(COMPLETION), delay=0.02, finished_at=finished_at),
        )
        with voice_stream.voice_stream_scope(cb):
            result = await asyncio.to_thread(
                voice_stream.try_stream_voice_reply, "openai/gpt-test", [{"role": "user", "content": "hi"}], {}
            )

        assert result == [COMPLETION]
        await _wait_for(lambda: "".join(t for _, t in events) == REPLY_TEXT)
        assert finished_at["at"] > 0
        assert events[0][0] < finished_at["at"], "first token must precede the end of the LM stream"

    @pytest.mark.asyncio
    async def test_streams_only_reply_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        got: list[str] = []

        async def cb(text: str) -> None:
            got.append(text)

        monkeypatch.setattr(
            voice_stream.litellm, "completion", make_fake_completion(split_awkwardly(COMPLETION, size=11))
        )
        with voice_stream.voice_stream_scope(cb):
            await asyncio.to_thread(
                voice_stream.try_stream_voice_reply, "openai/gpt-test", [{"role": "user", "content": "hi"}], {}
            )

        await _wait_for(lambda: "".join(got) == REPLY_TEXT)
        joined = "".join(got)
        assert joined == REPLY_TEXT
        assert "[[" not in joined
        assert "emotional_state_after" not in joined

    @pytest.mark.asyncio
    async def test_provider_cannot_stream_falls_back_with_a_log_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(**kwargs: Any) -> Any:
            raise RuntimeError("streaming not supported")

        monkeypatch.setattr(voice_stream.litellm, "completion", boom)
        mock_log = MagicMock()
        monkeypatch.setattr(voice_stream, "log", mock_log)

        async def cb(text: str) -> None:  # pragma: no cover - must never run
            raise AssertionError("no tokens may be emitted")

        with voice_stream.voice_stream_scope(cb):
            result = await asyncio.to_thread(
                voice_stream.try_stream_voice_reply, "openai/gpt-test", [{"role": "user", "content": "hi"}], {}
            )

        assert result is None  # the caller falls back to the non-streaming call
        mock_log.warning.assert_called_once()
        assert "npc_voice_streaming_unavailable" in str(mock_log.warning.call_args.args)

    @pytest.mark.asyncio
    async def test_mid_stream_failure_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            voice_stream.litellm,
            "completion",
            make_fake_completion(split_awkwardly(COMPLETION), fail_after=3),
        )
        mock_log = MagicMock()
        monkeypatch.setattr(voice_stream, "log", mock_log)

        async def cb(text: str) -> None:
            pass

        with voice_stream.voice_stream_scope(cb):
            result = await asyncio.to_thread(
                voice_stream.try_stream_voice_reply, "openai/gpt-test", [{"role": "user", "content": "hi"}], {}
            )

        assert result is None
        mock_log.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_stream_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(voice_stream.litellm, "completion", make_fake_completion([]))
        mock_log = MagicMock()
        monkeypatch.setattr(voice_stream, "log", mock_log)

        async def cb(text: str) -> None:  # pragma: no cover - must never run
            raise AssertionError("no tokens may be emitted")

        with voice_stream.voice_stream_scope(cb):
            result = await asyncio.to_thread(
                voice_stream.try_stream_voice_reply, "openai/gpt-test", [{"role": "user", "content": "hi"}], {}
            )

        assert result is None
        mock_log.warning.assert_called_once()


# =============================================================================
# respond_direct wiring (real module + real dspy_runtime gate)
# =============================================================================


class TestRespondDirectStreaming:
    @pytest.mark.asyncio
    async def test_light_tier_streams_reply_only_and_returns_the_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        npc_data = _sample_npc_data()
        agent = NPCVoice()
        agent.call_tool = _stub_call_tool(npc_data)  # type: ignore[method-assign]

        async def _fake_resolve(node_name: str, role: Any = None) -> Any:
            assert node_name == "npc_voice"
            return _FakeClient()

        monkeypatch.setattr(dspy_runtime, "_resolve_client", _fake_resolve)
        finished_at: dict[str, float] = {}
        monkeypatch.setattr(
            voice_stream.litellm,
            "completion",
            make_fake_completion(split_awkwardly(COMPLETION), delay=0.02, finished_at=finished_at),
        )

        events: list[tuple[float, str]] = []

        async def cb(text: str) -> None:
            events.append((time.monotonic(), text))

        started = time.monotonic()
        result = await agent.respond_direct(
            conversation_id=uuid4(),
            npc_id=uuid4(),
            player_said="Commander, I need your help.",
            npc_data=npc_data,
            universe_id=uuid4(),
            token_callback=cb,
        )

        assert result["npc_response"] == REPLY_TEXT
        assert result["emotional_state_after"] == EMOTION_AFTER
        assert result["relationship_delta"] == DELTA

        await _wait_for(lambda: "".join(t for _, t in events) == REPLY_TEXT)
        joined = "".join(t for _, t in events)
        assert joined == REPLY_TEXT
        assert "[[" not in joined and "relationship_delta" not in joined
        assert events[0][0] < finished_at["at"], "first token must precede the end of the LM stream"
        assert finished_at["at"] >= started

    @pytest.mark.asyncio
    async def test_standard_tier_variant_streams_and_defers_memory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        npc_data = _sample_npc_data()
        agent, writer = _make_voice_agent("standard", defer_memory_writes=True)
        assert writer is not None
        agent.call_tool = _stub_call_tool(npc_data)  # type: ignore[method-assign]

        async def _fake_resolve(node_name: str, role: Any = None) -> Any:
            return _FakeClient()

        monkeypatch.setattr(dspy_runtime, "_resolve_client", _fake_resolve)
        monkeypatch.setattr(voice_stream.litellm, "completion", make_fake_completion(split_awkwardly(COMPLETION)))

        got: list[str] = []

        async def cb(text: str) -> None:
            got.append(text)

        result = await agent.respond_direct(
            conversation_id=uuid4(),
            npc_id=uuid4(),
            player_said="Well?",
            npc_data=npc_data,
            universe_id=uuid4(),
            token_callback=cb,
        )

        await _wait_for(lambda: "".join(got) == REPLY_TEXT)
        assert "".join(got) == REPLY_TEXT
        assert result["npc_response"] == REPLY_TEXT
        # The deferred writer buffered the memory write; it is flushed only
        # after the stream completes (by the streaming send / close_session).
        assert len(writer.calls) == 1
        assert writer.calls[0]["npc_said"] == REPLY_TEXT

    @pytest.mark.asyncio
    async def test_without_callback_the_voice_registers_no_sink(self) -> None:
        seen: list[Any] = []
        agent = NPCVoice()
        agent.call_tool = _stub_call_tool(_sample_npc_data())  # type: ignore[method-assign]

        def _capture(**kwargs: Any) -> Any:
            seen.append(voice_stream.voice_stream_var.get())
            pred = MagicMock()
            pred.npc_response = "Hi."
            pred.emotional_state_after = "calm"
            pred.relationship_delta = "none"
            return pred

        agent._direct_module = Mock(side_effect=_capture)  # type: ignore[method-assign]
        await agent.respond_direct(
            conversation_id=uuid4(),
            npc_id=uuid4(),
            player_said="hello",
            npc_data=_sample_npc_data(),
            universe_id=uuid4(),
        )
        assert seen == [None]

    @pytest.mark.asyncio
    async def test_cancelled_voice_call_writes_no_memory(self) -> None:
        """A half reply is never written as a memory (disconnect path)."""
        npc_data = _sample_npc_data()
        agent = NPCVoice()
        agent.call_tool = _stub_call_tool(npc_data)  # type: ignore[method-assign]
        agent._write_npc_memory = AsyncMock()  # type: ignore[method-assign]
        release = threading.Event()
        entered = threading.Event()

        def _blocking(**kwargs: Any) -> Any:
            entered.set()
            release.wait(timeout=5.0)
            pred = MagicMock()
            pred.npc_response = REPLY_TEXT
            pred.emotional_state_after = EMOTION_AFTER
            pred.relationship_delta = DELTA
            return pred

        agent._direct_module = Mock(side_effect=_blocking)  # type: ignore[method-assign]

        async def cb(text: str) -> None:
            pass

        task = asyncio.create_task(
            agent.respond_direct(
                conversation_id=uuid4(),
                npc_id=uuid4(),
                player_said="hello",
                npc_data=npc_data,
                universe_id=uuid4(),
                token_callback=cb,
            )
        )
        await asyncio.to_thread(entered.wait, 2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        await asyncio.sleep(0.01)
        agent._write_npc_memory.assert_not_awaited()


# =============================================================================
# ConversationLoop → respond_direct forwarding
# =============================================================================


class TestLoopForwardsTheTokenCallback:
    @pytest.mark.asyncio
    async def test_generate_npc_responses_forwards_callback(self) -> None:
        npc_id = uuid4()
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
        state = _loop_state(npc_id)

        async def cb(text: str) -> None:
            pass

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            await generate_npc_responses(state, token_callback=cb)

        assert mock_agent.respond_direct.await_args.kwargs["token_callback"] is cb

    @pytest.mark.asyncio
    async def test_multi_npc_conversations_stream_nothing(self) -> None:
        ids = [uuid4(), uuid4()]
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
        state = _loop_state(*ids)

        async def cb(text: str) -> None:  # pragma: no cover - must never run
            raise AssertionError("multi-NPC turns do not stream")

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            await generate_npc_responses(state, token_callback=cb)

        assert mock_agent.respond_direct.await_args.kwargs["token_callback"] is None

    @pytest.mark.asyncio
    async def test_step_passes_the_callback_through(self) -> None:
        npc_id = uuid4()
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

        async def cb(text: str) -> None:
            pass

        with patch("monitor_agents.npc_voice.agent.NPCVoice", return_value=mock_agent):
            loop = ConversationLoop(
                conversation_id=uuid4(),
                universe_id=uuid4(),
                mode=ConversationMode.DIRECT,
                npc_ids=[npc_id],
                preset="light",
            )
            loop.state.npc_contexts = {str(npc_id): {"name": "Wisp", "role": "guide", "profile": {}, "facts": []}}
            responses = await loop.step("Hi.", defer_memory_writes=True, token_callback=cb)

        assert responses[0]["text"] == "Well met."
        assert mock_agent.respond_direct.await_args.kwargs["token_callback"] is cb


def _loop_state(*npc_ids: Any) -> Any:
    from monitor_agents.loops.conversation_loop import ConversationState

    return ConversationState(
        conversation_id=uuid4(),
        universe_id=uuid4(),
        mode=ConversationMode.DIRECT,
        npc_ids=list(npc_ids),
        npc_contexts={
            str(nid): {"name": f"NPC-{i}", "role": "guide", "profile": {}, "facts": []} for i, nid in enumerate(npc_ids)
        },
        current_player_input="Hello!",
        turns=[{"turn_index": 0, "speaker_role": "player", "text": "Hello!"}],
    )
