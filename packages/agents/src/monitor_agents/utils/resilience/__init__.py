"""Resilience utilities for MONITOR Agents.

Provides:
- CircuitBreaker: prevents cascading failures when external services
  (Neo4j, MongoDB, Qdrant, OpenSearch, Postgres) are unhealthy.
- LLMFallbackChain: graceful degradation for LLM calls.
- with_circuit_breaker: decorator for async service calls.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries only
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

__all__ = [
    "CircuitState",
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "with_circuit_breaker",
    "LLMFallbackChain",
    "FallbackExhausted",
    "get_breaker",
    "reset_all",
    "list_registered",
    "configure_breaker",
    "unregister",
]


class CircuitState(str, Enum):
    """States of a circuit breaker."""

    CLOSED = "closed"  # Normal operation, calls pass through
    OPEN = "open"  # Service is down, calls fail fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerOpen(Exception):
    """Raised when a circuit breaker is open and rejects a call."""


class FallbackExhausted(Exception):
    """Raised when every fallback in a chain has failed."""


class CircuitBreaker:
    """Circuit breaker for async service calls.

    State machine:
        CLOSED   --(N consecutive failures)--> OPEN
        OPEN     --(after reset_timeout)----> HALF_OPEN
        HALF_OPEN --(success)----------------> CLOSED
        HALF_OPEN --(failure)----------------> OPEN

    Usage:
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout=30.0)

        async def safe_call():
            return await breaker.call(some_async_fn, arg1, kw=val)
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        reset_timeout: float = 30.0,
        expected_exceptions: tuple = (Exception,),
        name: str = "default",
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if reset_timeout < 0:
            raise ValueError("reset_timeout must be >= 0")
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.expected_exceptions = expected_exceptions
        self.name = name

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._success_count: int = 0
        self._half_open_in_flight: int = 0

    # ---- public API --------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Return current state, transitioning OPEN -> HALF_OPEN if timer expired."""
        self._maybe_transition_to_half_open()
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def reset(self) -> None:
        """Force the breaker back to CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_in_flight = 0
        self._last_failure_time = 0.0

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Invoke ``func`` through the breaker.

        Raises:
            CircuitBreakerOpen: if the breaker is open and rejects the call.
        """
        self._maybe_transition_to_half_open()

        if self._state == CircuitState.OPEN:
            raise CircuitBreakerOpen(f"Circuit '{self.name}' is OPEN; failing fast")

        if self._state == CircuitState.HALF_OPEN:
            # Only one probe at a time
            if self._half_open_in_flight > 0:
                raise CircuitBreakerOpen(f"Circuit '{self.name}' HALF_OPEN with probe in flight")
            self._half_open_in_flight += 1

        try:
            result = await func(*args, **kwargs)
        except self.expected_exceptions as exc:
            self._record_failure(exc)
            raise
        except Exception as exc:
            # Unexpected — still record failure for safety
            self._record_failure(exc)
            raise

        self._record_success()
        return result

    # ---- internal ---------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        if (
            self._state == CircuitState.OPEN
            and (time.monotonic() - self._last_failure_time) >= self.reset_timeout
        ):
            logger.info(
                "Circuit '%s' transitioning OPEN -> HALF_OPEN after %.1fs",
                self.name,
                self.reset_timeout,
            )
            self._state = CircuitState.HALF_OPEN
            self._half_open_in_flight = 0
            self._success_count = 0

    def _record_failure(self, exc: BaseException) -> None:
        if self._state == CircuitState.HALF_OPEN:
            # Failure during probe -> back to OPEN
            logger.warning("Circuit '%s' probe failed (%s) -> OPEN", self.name, exc)
            self._state = CircuitState.OPEN
            self._half_open_in_flight = 0
            self._last_failure_time = time.monotonic()
            return

        # CLOSED
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            logger.warning(
                "Circuit '%s' reached %d failures -> OPEN",
                self.name,
                self._failure_count,
            )
            self._state = CircuitState.OPEN

    def _record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
            # One success closes the circuit
            logger.info("Circuit '%s' probe succeeded -> CLOSED", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            return

        # CLOSED
        self._failure_count = 0


def with_circuit_breaker(
    breaker: CircuitBreaker,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator: wrap an async function in a CircuitBreaker."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await breaker.call(func, *args, **kwargs)

        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return wrapper

    return decorator


class LLMFallbackChain:
    """Try multiple LLM providers/models in order until one succeeds.

    Used by the BaseAgent when the primary LLM is unavailable — the
    next provider in the chain is attempted instead. If all fail,
    FallbackExhausted is raised.

    Usage:
        chain = LLMFallbackChain([
            ("anthropic", "claude-3-5-sonnet", anthropic_call),
            ("openai", "gpt-4o", openai_call),
        ])
        result = await chain.invoke(prompt)
    """

    def __init__(self, fallbacks: list) -> None:
        if not fallbacks:
            raise ValueError("fallbacks must be non-empty")
        for entry in fallbacks:
            if len(entry) != 3:
                raise ValueError("Each fallback must be a (provider, model, callable) tuple")
        self.fallbacks = list(fallbacks)

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Try each fallback in order; return the first success."""
        last_error: Optional[BaseException] = None
        for provider, model, func in self.fallbacks:
            try:
                logger.info(
                    "LLM fallback: trying provider=%s model=%s",
                    provider,
                    model,
                )
                return await func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("LLM fallback %s/%s failed: %s", provider, model, exc)
        raise FallbackExhausted(f"All {len(self.fallbacks)} LLM fallbacks failed") from last_error


# Re-export the registry helpers so callers can `from ...resilience import get_breaker`
from monitor_agents.utils.resilience.registry import (  # noqa: E402
    get_breaker,
    reset_all,
    list_registered,
    configure_breaker,
    unregister,
)
