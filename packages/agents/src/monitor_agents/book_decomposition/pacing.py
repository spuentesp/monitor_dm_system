"""Keep a long extraction run inside what the provider and plan allow.

Three kinds of failure need three different responses:
- An exhausted plan or a bad key won't recover soon, so the whole run stops and can resume.
- A temporary rate limit recovers, so every caller pauses together, with growing backoff.
- A spending budget stops the run before the plan is used up.

`classify_llm_error` treats a plan usage limit as a retryable rate limit, which suits a single
gameplay turn. A batch job would burn hours retrying it, so this module tells them apart.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum

import structlog

from monitor_agents.book_decomposition.extractor import (
    CONTENT_ERRORS,
    ExtractorResult,
    WindowExtractor,
    failed_call_usage,
)
from monitor_agents.book_decomposition.windows import Window
from monitor_agents.llm_errors import LLMErrorClass, classify_llm_error

log = structlog.get_logger()

_INITIAL_BACKOFF_SECONDS = 15.0
_MAX_BACKOFF_SECONDS = 300.0
_RUN_ENDING_TEXT = (
    "hit your usage limit",
    "reached your 5-hour usage limit",
    "usage limit reached",
    "usage limit exceeded",
    "insufficient balance",
    "insufficient_balance",
)
# MiniMax's plan-limit codes, in the forms it reports them. The wording varies; the codes don't.
_RUN_ENDING_CODE = re.compile(r'(?:\(|status_code"?\s*[:=]\s*)(?:2056|2067)\b')
_RUN_ENDING_CLASSES = (LLMErrorClass.QUOTA, LLMErrorClass.AUTH)


class StopKind(StrEnum):
    QUOTA = "quota"  # Used up or refused. Comes back on its own.
    BUDGET = "budget"  # This run's spending limit. Only a person should raise it.
    OTHER = "other"


class RunStopped(Exception):
    """The run must stop now. Finished work is saved, and the same command resumes it."""


def ends_the_run(exc: BaseException) -> bool:
    """True when retrying can't help: the plan is used up or the key is bad."""
    # These carry the model's output, which is book text and could contain any phrase.
    if isinstance(exc, CONTENT_ERRORS):
        return False
    message = str(exc)
    if any(text in message.casefold() for text in _RUN_ENDING_TEXT):
        return True
    if _RUN_ENDING_CODE.search(message):
        return True
    return classify_llm_error(exc).error_class in _RUN_ENDING_CLASSES


class RunGuard:
    """Shared by every concurrent call in a run: paces, backs off, and enforces the budget."""

    def __init__(
        self,
        *,
        max_output_tokens: int | None = None,
        requests_per_minute: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.max_output_tokens = max_output_tokens
        self._interval = 60.0 / requests_per_minute if requests_per_minute else 0.0
        self._clock = clock
        self._sleep = sleep
        self._next_slot = 0.0
        self._paused_until = 0.0
        self._backoff = _INITIAL_BACKOFF_SECONDS
        self.stopped_reason: str | None = None
        self.stop_kind: StopKind | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests = 0
        self.rate_limit_pauses = 0

    @property
    def stopped(self) -> bool:
        return self.stopped_reason is not None

    def stop(self, reason: str, kind: StopKind = StopKind.OTHER) -> None:
        if self.stopped_reason is None:
            self.stopped_reason = reason
            self.stop_kind = kind
            log.warning("book_run_stopped", reason=reason, kind=kind.value)

    def resume(self) -> None:
        """Clear a stop, once waiting has given the provider time to recover."""
        self.stopped_reason = None
        self.stop_kind = None

    def _raise_if_stopped(self) -> None:
        if self.stopped_reason is not None:
            raise RunStopped(self.stopped_reason)

    async def acquire(self) -> None:
        """Wait for a turn to call the provider. Raises RunStopped if the run has ended."""
        while True:
            self._raise_if_stopped()
            now = self._clock()
            start = max(now, self._next_slot)
            if self._paused_until > start:
                # Wait out the pause, then take a slot based on the new time. A newer pause set
                # during the wait still applies; this one is over either way.
                waited_for = self._paused_until
                await self._sleep(waited_for - now)
                if self._paused_until == waited_for:
                    self._paused_until = 0.0
                continue
            self._next_slot = start + self._interval
            if start > now:
                await self._sleep(start - now)
            self._raise_if_stopped()
            self.requests += 1
            return

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Count a successful call's usage, and stop the run if it's over budget."""
        self._backoff = _INITIAL_BACKOFF_SECONDS
        self._charge(input_tokens, output_tokens)

    def _charge(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if self.max_output_tokens and self.output_tokens >= self.max_output_tokens:
            self.stop(
                f"Output token budget reached ({self.output_tokens:,} of {self.max_output_tokens:,})",
                StopKind.BUDGET,
            )

    def on_error(self, exc: BaseException) -> None:
        """Respond to a failed call: stop the run, pause everyone, or do nothing."""
        if ends_the_run(exc):
            self.stop(f"Provider refused the request: {str(exc)[:200]}", StopKind.QUOTA)
            return
        if isinstance(exc, CONTENT_ERRORS):
            return
        if classify_llm_error(exc).error_class == LLMErrorClass.RATE_LIMIT:
            self._paused_until = max(self._paused_until, self._clock() + self._backoff)
            log.warning("book_run_rate_limited", pause_seconds=self._backoff)
            self._backoff = min(self._backoff * 2, _MAX_BACKOFF_SECONDS)
            self.rate_limit_pauses += 1

    async def call(self, make_call: Callable[[], Awaitable[object]]) -> object:
        """Run one provider call under this guard."""
        await self.acquire()
        try:
            return await make_call()
        except RunStopped:
            raise
        except Exception as exc:  # noqa: BLE001  # reason: classified here, then re-raised to the caller
            # A failed call can be the most expensive kind: a cut-off answer uses the full limit.
            self._charge(*failed_call_usage(exc))
            self.on_error(exc)
            self._raise_if_stopped()
            raise


class GuardedExtractor:
    """A WindowExtractor that goes through a RunGuard."""

    def __init__(self, inner: WindowExtractor, guard: RunGuard) -> None:
        self._inner = inner
        self._guard = guard

    async def __call__(self, window: Window) -> ExtractorResult:
        async def make_call() -> ExtractorResult:
            return await self._inner(window)

        result = await self._guard.call(make_call)
        assert isinstance(result, ExtractorResult)  # noqa: S101
        self._guard.record(result.input_tokens, result.output_tokens)
        return result
