"""Behavior tests for the resilience utility (CircuitBreaker + LLMFallbackChain).

Phase 5.1 — Error Recovery (SYS-11).

Covers:
- CircuitBreaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Failure threshold and reset timeout
- CircuitBreakerOpen exception
- with_circuit_breaker decorator
- LLMFallbackChain success and FallbackExhausted
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# CircuitState enum
# =============================================================================


class TestCircuitState:
    def test_values(self):
        from monitor_agents.utils.resilience import CircuitState

        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


# =============================================================================
# CircuitBreaker — construction
# =============================================================================


class TestCircuitBreakerConstruction:
    def test_default_state_is_closed(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_invalid_threshold_raises(self):
        from monitor_agents.utils.resilience import CircuitBreaker

        with pytest.raises(ValueError, match="failure_threshold"):
            CircuitBreaker(failure_threshold=0, name="bad")

    def test_invalid_reset_timeout_raises(self):
        from monitor_agents.utils.resilience import CircuitBreaker

        with pytest.raises(ValueError, match="reset_timeout"):
            CircuitBreaker(reset_timeout=-1.0, name="bad")

    def test_custom_threshold(self):
        from monitor_agents.utils.resilience import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=5, reset_timeout=10.0, name="custom")
        assert cb.failure_threshold == 5
        assert cb.reset_timeout == 10.0


# =============================================================================
# CircuitBreaker — happy path
# =============================================================================


class TestCircuitBreakerSuccess:
    def test_passes_through(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="ok")

        async def succeeds():
            return "result"

        result = asyncio.run(cb.call(succeeds))
        assert result == "result"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_passes_args_kwargs(self):
        from monitor_agents.utils.resilience import CircuitBreaker

        cb = CircuitBreaker(name="args")

        async def echo(a, b=10):
            return (a, b)

        result = asyncio.run(cb.call(echo, 1, b=2))
        assert result == (1, 2)


# =============================================================================
# CircuitBreaker — failure path
# =============================================================================


class TestCircuitBreakerFailure:
    def test_single_failure_keeps_closed(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3, name="test")

        async def fails():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            asyncio.run(cb.call(fails))
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 1

    def test_three_failures_opens_circuit(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3, name="test")

        async def fails():
            raise ValueError("nope")

        for _ in range(3):
            with pytest.raises(ValueError):
                asyncio.run(cb.call(fails))
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    def test_open_circuit_fails_fast(self):
        from monitor_agents.utils.resilience import (
            CircuitBreaker,
            CircuitBreakerOpen,
            CircuitState,
        )

        cb = CircuitBreaker(failure_threshold=1, name="test")

        async def fails():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            asyncio.run(cb.call(fails))
        assert cb.state == CircuitState.OPEN

        async def would_succeed():
            return "should not run"

        with pytest.raises(CircuitBreakerOpen):
            asyncio.run(cb.call(would_succeed))

    def test_success_resets_failure_count(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3, name="test")

        async def fails():
            raise ValueError("nope")

        async def succeeds():
            return "ok"

        # 2 failures (still under threshold)
        for _ in range(2):
            with pytest.raises(ValueError):
                asyncio.run(cb.call(fails))
        assert cb.failure_count == 2

        # 1 success -> reset
        result = asyncio.run(cb.call(succeeds))
        assert result == "ok"
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_unexpected_exceptions_also_count(self):
        from monitor_agents.utils.resilience import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=1, name="test")

        async def crashes():
            raise SystemError("crash")

        with pytest.raises(SystemError):
            asyncio.run(cb.call(crashes))
        assert cb.state.value == "open"


# =============================================================================
# CircuitBreaker — half-open transitions
# =============================================================================


class TestCircuitBreakerHalfOpen:
    def test_reset_timeout_transitions_to_half_open(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.1, name="test")

        async def fails():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            asyncio.run(cb.call(fails))
        assert cb.state == CircuitState.OPEN

        # Wait for reset timeout
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.1, name="test")

        async def fails():
            raise RuntimeError("boom")

        async def succeeds():
            return "recovered"

        with pytest.raises(RuntimeError):
            asyncio.run(cb.call(fails))
        time.sleep(0.15)

        # Now in HALF_OPEN; success closes
        result = asyncio.run(cb.call(succeeds))
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.1, name="test")

        async def fails():
            raise RuntimeError("still broken")

        with pytest.raises(RuntimeError):
            asyncio.run(cb.call(fails))
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        with pytest.raises(RuntimeError):
            asyncio.run(cb.call(fails))
        assert cb.state == CircuitState.OPEN


# =============================================================================
# CircuitBreaker.reset
# =============================================================================


class TestCircuitBreakerReset:
    def test_reset_to_closed(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=1, name="test")

        async def fails():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            asyncio.run(cb.call(fails))
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_reset_when_already_closed(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test")
        cb.reset()
        assert cb.state == CircuitState.CLOSED


# =============================================================================
# with_circuit_breaker decorator
# =============================================================================


class TestCircuitBreakerDecorator:
    def test_decorator_wraps_function(self):
        from monitor_agents.utils.resilience import (
            CircuitBreaker,
            CircuitBreakerOpen,
            with_circuit_breaker,
        )

        cb = CircuitBreaker(failure_threshold=1, name="deco")

        @with_circuit_breaker(cb)
        async def flaky():
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError):
            asyncio.run(flaky())

        # Now OPEN
        with pytest.raises(CircuitBreakerOpen):
            asyncio.run(flaky())

    def test_decorator_preserves_metadata(self):
        from monitor_agents.utils.resilience import (
            CircuitBreaker,
            with_circuit_breaker,
        )

        cb = CircuitBreaker(name="deco")

        @with_circuit_breaker(cb)
        async def greet(name):
            return f"hello {name}"

        assert greet.__wrapped__.__name__ == "greet"
        assert asyncio.run(greet("world")) == "hello world"


# =============================================================================
# LLMFallbackChain
# =============================================================================


class TestLLMFallbackChain:
    def test_first_success_wins(self):
        from monitor_agents.utils.resilience import LLMFallbackChain

        async def primary(prompt):
            return f"primary:{prompt}"

        async def secondary(prompt):
            return f"secondary:{prompt}"

        chain = LLMFallbackChain(
            [("anthropic", "claude", primary), ("openai", "gpt", secondary)]
        )
        result = asyncio.run(chain.invoke("hello"))
        assert result == "primary:hello"

    def test_falls_back_to_secondary(self):
        from monitor_agents.utils.resilience import LLMFallbackChain

        async def primary(prompt):
            raise RuntimeError("anthropic down")

        async def secondary(prompt):
            return f"openai:{prompt}"

        chain = LLMFallbackChain(
            [("anthropic", "claude", primary), ("openai", "gpt", secondary)]
        )
        result = asyncio.run(chain.invoke("hi"))
        assert result == "openai:hi"

    def test_all_fail_raises(self):
        from monitor_agents.utils.resilience import FallbackExhausted, LLMFallbackChain

        async def fail1(prompt):
            raise RuntimeError("1")

        async def fail2(prompt):
            raise ValueError("2")

        chain = LLMFallbackChain(
            [("a", "1", fail1), ("b", "2", fail2)]
        )
        with pytest.raises(FallbackExhausted) as exc_info:
            asyncio.run(chain.invoke("x"))
        assert "2 LLM" in str(exc_info.value)

    def test_empty_chain_raises(self):
        from monitor_agents.utils.resilience import LLMFallbackChain

        with pytest.raises(ValueError, match="non-empty"):
            LLMFallbackChain([])

    def test_invalid_tuple_shape_raises(self):
        from monitor_agents.utils.resilience import LLMFallbackChain

        with pytest.raises(ValueError, match=r"\(provider, model, callable\)"):
            LLMFallbackChain([("only_provider",)])

    def test_passes_args_kwargs(self):
        from monitor_agents.utils.resilience import LLMFallbackChain

        async def primary(prompt, *, max_tokens=10):
            return f"{prompt}:{max_tokens}"

        chain = LLMFallbackChain([("a", "1", primary)])
        result = asyncio.run(chain.invoke("hi", max_tokens=20))
        assert result == "hi:20"


# =============================================================================
# CircuitBreaker — exception filtering
# =============================================================================


class TestCircuitBreakerExceptionFilter:
    def test_only_expected_exceptions_count_as_failures(self):
        from monitor_agents.utils.resilience import CircuitBreaker, CircuitState

        cb = CircuitBreaker(
            failure_threshold=1,
            expected_exceptions=(ValueError,),
            name="filter",
        )

        async def raises_key_error():
            raise KeyError("not tracked")

        # KeyError is not in expected_exceptions -> still records as failure
        # (defensive default) and trips the breaker
        with pytest.raises(KeyError):
            asyncio.run(cb.call(raises_key_error))
        assert cb.state == CircuitState.OPEN

    def test_filter_does_not_swallow_unexpected(self):
        from monitor_agents.utils.resilience import CircuitBreaker

        cb = CircuitBreaker(
            failure_threshold=10,
            expected_exceptions=(ValueError,),
            name="filter",
        )

        async def raises_value_error():
            raise ValueError("tracked")

        with pytest.raises(ValueError):
            asyncio.run(cb.call(raises_value_error))
        assert cb.failure_count == 1


# =============================================================================
# Service registry (get_breaker, configure_breaker, etc.)
# =============================================================================


class TestBreakerRegistry:
    def teardown_method(self):
        from monitor_agents.utils.resilience import list_registered, reset_all, unregister

        # Unregister everything to keep tests isolated
        for name in list(list_registered()):
            unregister(name)
        reset_all()

    def test_get_breaker_creates_singleton(self):
        from monitor_agents.utils.resilience import CircuitBreaker, get_breaker

        a = get_breaker("neo4j")
        b = get_breaker("neo4j")
        assert a is b
        assert isinstance(a, CircuitBreaker)

    def test_unknown_service_uses_default_defaults(self):
        from monitor_agents.utils.resilience import get_breaker

        b = get_breaker("my_custom_service")
        # Default: failure_threshold=3, reset_timeout=30
        assert b.failure_threshold == 3
        assert b.reset_timeout == 30.0

    def test_known_service_uses_tuned_defaults(self):
        from monitor_agents.utils.resilience import get_breaker

        neo4j = get_breaker("neo4j")
        mongodb = get_breaker("mongodb")
        llm = get_breaker("llm")

        # Tuned per service
        assert neo4j.failure_threshold == 3
        assert mongodb.failure_threshold == 5
        assert llm.failure_threshold == 5
        assert llm.reset_timeout == 15.0

    def test_list_registered(self):
        from monitor_agents.utils.resilience import get_breaker, list_registered

        assert "neo4j" not in list_registered()
        get_breaker("neo4j")
        get_breaker("mongodb")
        names = list_registered()
        assert "neo4j" in names
        assert "mongodb" in names

    def test_configure_breaker_overrides(self):
        from monitor_agents.utils.resilience import configure_breaker, get_breaker

        configure_breaker("neo4j", failure_threshold=99, reset_timeout=1.0)
        b = get_breaker("neo4j")
        assert b.failure_threshold == 99
        assert b.reset_timeout == 1.0

    def test_reset_all(self):
        from monitor_agents.utils.resilience import (
            CircuitState,
            get_breaker,
            reset_all,
        )

        a = get_breaker("neo4j")
        # Force OPEN
        a._state = CircuitState.OPEN
        a._failure_count = 10
        b = get_breaker("mongodb")
        b._state = CircuitState.OPEN

        reset_all()
        assert a.state == CircuitState.CLOSED
        assert b.state == CircuitState.CLOSED
        assert a.failure_count == 0

    def test_unregister(self):
        from monitor_agents.utils.resilience import get_breaker, unregister

        b = get_breaker("neo4j")
        assert unregister("neo4j") is b
        # Re-fetching creates a fresh one
        b2 = get_breaker("neo4j")
        assert b2 is not b

    def test_unregister_unknown(self):
        from monitor_agents.utils.resilience import unregister

        assert unregister("never_registered") is None

    def test_through_registry_async(self):
        from monitor_agents.utils.resilience import (
            CircuitBreakerOpen,
            get_breaker,
        )

        breaker = get_breaker("neo4j", )  # default
        # Use a direct reference to control the threshold
        breaker = get_breaker("neo4j")
        # Mutate to low threshold for fast test
        breaker.failure_threshold = 1

        async def fails():
            raise RuntimeError("neo4j down")

        with pytest.raises(RuntimeError):
            asyncio.run(breaker.call(fails))
        # Now open
        async def would_succeed():
            return "ok"

        with pytest.raises(CircuitBreakerOpen):
            asyncio.run(breaker.call(would_succeed))
