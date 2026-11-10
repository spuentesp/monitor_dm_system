"""Live token streaming for the direct NPC voice (light RP, Phase 7).

The direct voice's LM completion is a structured record (DSPy ChatAdapter
format: ``[[ ## npc_response ## ]]`` then the remaining output fields). This
module streams that completion and emits ONLY the spoken reply text — field
names, markers, the other fields, reasoning and JSON fallback output never
reach the player.

Wiring: the caller (``NPCVoice.respond_direct``, driven by ConversationLoop's
streaming send) registers its token callback with :func:`voice_stream_scope`
around the voice module call. ``dspy_runtime.CachedDSPyLM`` routes
``npc_voice`` completions through :func:`try_stream_voice_reply` when a
callback is registered. When the provider or model cannot stream, the caller
falls back to the standard non-streaming LM call — with a log line, never
silently.

LAYER: 2 (agents)
IMPORTS FROM: external libs only (litellm, structlog)
"""

from __future__ import annotations

import structlog

import asyncio
import contextvars
import re
from contextlib import contextmanager
from typing import Any, Awaitable, Callable, Iterator, NamedTuple

import litellm

log = structlog.get_logger()

# One spoken-reply token/delta. Async so the sink can hand off to an event
# loop queue without blocking the LM's worker thread.
TokenCallback = Callable[[str], Awaitable[None]]


class VoiceStreamSink(NamedTuple):
    """Where reply tokens go, and the event loop that owns the callback."""

    callback: TokenCallback
    loop: asyncio.AbstractEventLoop | None


# Visible to the LM call inside asyncio.to_thread (contextvars are copied into
# the worker thread), so no plumbing through DSPy internals is needed.
voice_stream_var: contextvars.ContextVar[VoiceStreamSink | None] = contextvars.ContextVar("voice_stream", default=None)

_REPLY_FIELD = "npc_response"
# Line-anchored like ChatAdapter's own parse: a marker only starts a field at
# the beginning of a line (leading spaces allowed).
_FIELD_MARKER_RE = re.compile(r"(?m)^[ \t]*\[\[ ## (\w+) ## \]\]")
# Longest field-marker line (plus its leading newlines) that can still grow
# into ``[[ ## emotional_state_after ## ]]``. While the tail of the reply
# value could still be the start of a marker, it stays withheld from the
# stream — markers and other fields must never leak.
_HOLD_BACK = 40


class _ReplyFieldExtractor:
    """Incrementally extract the spoken reply from a streaming completion.

    Only the value of the ``npc_response`` field is emitted. Preamble,
    field markers, the trailing fields and any JSON fallback shape produce
    no output at all.
    """

    def __init__(self) -> None:
        self._value_start: int | None = None
        self._emitted = 0
        self._done = False

    def feed(self, full_text: str) -> str:
        """Return the next reply-text delta from the accumulated completion."""
        if self._done:
            return ""
        if self._value_start is None:
            self._locate_value(full_text)
        start = self._value_start
        if start is None:
            return ""
        value = full_text[start:]
        closing = _FIELD_MARKER_RE.search(full_text, start)
        if closing is not None:
            self._done = True
            region = full_text[start : closing.start()]
        else:
            hold = max(0, len(value) - _HOLD_BACK)
            if hold <= self._emitted:
                return ""
            region = value[:hold]
        return self._take(region, final=self._done)

    def finish(self, full_text: str) -> str:
        """Flush the held-back tail once the completion ends."""
        if self._done or self._value_start is None:
            return ""
        self._done = True
        value = full_text[self._value_start :]
        # A trailing "[[" is a field marker that never finished arriving —
        # drop it rather than leak it. It cannot span the emitted boundary:
        # feed() withholds a tail longer than any marker line.
        cut = value.find("[[", self._emitted)
        region = value[:cut] if cut != -1 else value
        return self._take(region, final=True)

    def _locate_value(self, full_text: str) -> int | None:
        for match in _FIELD_MARKER_RE.finditer(full_text):
            name = match.group(1)
            if name == _REPLY_FIELD:
                self._value_start = match.end()
                return self._value_start
            if name == "completed":
                # The reply field never arrived — give up for good.
                self._done = True
                return None
        return None

    def _take(self, region: str, *, final: bool) -> str:
        delta = region[self._emitted :]
        first = self._emitted == 0
        self._emitted = len(region)
        if first:
            # ChatAdapter.parse strips the field value — mirror that on the
            # first emission only (later deltas are mid-content).
            delta = delta.lstrip()
        if final:
            delta = delta.rstrip()
        return delta


@contextmanager
def voice_stream_scope(callback: TokenCallback | None) -> Iterator[None]:
    """Register ``callback`` as the reply-token sink for the enclosed call.

    Captures the running event loop so the LM's worker thread can dispatch
    tokens back to it. ``callback=None`` registers nothing (non-streaming).
    """
    if callback is None:
        yield
        return
    try:
        loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    token = voice_stream_var.set(VoiceStreamSink(callback=callback, loop=loop))
    try:
        yield
    finally:
        voice_stream_var.reset(token)


def _log_callback_failure(done: Any) -> None:
    try:
        exc = done.exception()
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _log_callback_failure)
        return
    if exc is not None:
        log.warning("voice_stream_callback_failed", exc_info=exc)


def _dispatch_token(sink: VoiceStreamSink, text: str) -> None:
    """Deliver one token to the sink's callback without blocking the caller."""
    try:
        loop = asyncio.get_running_loop()
        waiter: Any = loop.create_task(sink.callback(text))
    except RuntimeError:
        target = sink.loop
        if target is None or not target.is_running():
            log.debug("voice_stream_token_dropped", reason="no running event loop")
            return
        waiter = asyncio.run_coroutine_threadsafe(sink.callback(text), target)
    waiter.add_done_callback(_log_callback_failure)


def _delta_text(chunk: Any) -> str:
    choices = getattr(chunk, "choices", None)
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    return str(getattr(delta, "content", "") or "")


def try_stream_voice_reply(
    model: str,
    messages: list[dict[str, Any]],
    lm_kwargs: dict[str, Any],
) -> list[str] | None:
    """Stream the direct-voice call, emitting the spoken reply as it generates.

    Returns ``[full_text]`` (what the DSPy adapter parses) when the stream
    completed, or ``None`` when streaming is unavailable — no sink registered,
    the provider refused/could not stream, or the stream came back empty —
    so the caller falls back to the standard non-streaming LM call. The
    fallback is logged; it is never silent.
    """
    sink = voice_stream_var.get()
    if sink is None:
        return None
    kwargs = dict(lm_kwargs)
    kwargs.pop("stream", None)
    try:
        response = litellm.completion(model=model, messages=messages, stream=True, **kwargs)
    except Exception:  # noqa: BLE001  # reason: documented fallback: streaming unavailable (in try_stream_voice_reply)
        log.warning("npc_voice_streaming_unavailable", fallback="non-streaming", exc_info=True)
        return None

    full_text = ""
    extractor = _ReplyFieldExtractor()
    try:
        for chunk in response:
            text = _delta_text(chunk)
            if not text:
                continue
            full_text += text
            delta = extractor.feed(full_text)
            if delta:
                _dispatch_token(sink, delta)
        final = extractor.finish(full_text)
        if final:
            _dispatch_token(sink, final)
    except Exception:  # noqa: BLE001  # reason: documented fallback: streaming broke mid-flight (in try_stream_voice_reply)
        log.warning("npc_voice_streaming_unavailable", fallback="non-streaming", exc_info=True)
        return None

    if not full_text.strip():
        log.warning("npc_voice_streaming_unavailable", fallback="non-streaming", detail="empty stream")
        return None
    return [full_text]
