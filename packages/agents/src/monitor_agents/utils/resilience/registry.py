"""Process-wide circuit breaker registry for MONITOR services.

Provides named circuit breakers for each external service
(Neo4j, MongoDB, Qdrant, OpenSearch, Postgres, LLM) so that
agents can opt-in to resilience on a per-service basis.

Usage:
    from monitor_agents.utils.resilience import get_breaker

    neo4j_breaker = get_breaker("neo4j")
    result = await neo4j_breaker.call(neo4j_query, cypher, params=params)
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

from monitor_agents.utils.resilience import CircuitBreaker

logger = logging.getLogger(__name__)

# Service-specific defaults tuned for the MONITOR deployment.
_SERVICE_DEFAULTS: Dict[str, Dict[str, float]] = {
    "neo4j": {"failure_threshold": 3, "reset_timeout": 30.0},
    "mongodb": {"failure_threshold": 5, "reset_timeout": 20.0},
    "qdrant": {"failure_threshold": 3, "reset_timeout": 30.0},
    "opensearch": {"failure_threshold": 3, "reset_timeout": 30.0},
    "postgres": {"failure_threshold": 3, "reset_timeout": 30.0},
    "llm": {"failure_threshold": 5, "reset_timeout": 15.0},
    "mcp": {"failure_threshold": 5, "reset_timeout": 15.0},
}

_breakers: Dict[str, CircuitBreaker] = {}
_lock = threading.Lock()


def get_breaker(name: str) -> CircuitBreaker:
    """Return the singleton CircuitBreaker for the given service name.

    Creates a new breaker with service-tuned defaults the first time a
    name is requested. Thread-safe.
    """
    with _lock:
        if name not in _breakers:
            defaults = _SERVICE_DEFAULTS.get(name, {"failure_threshold": 3, "reset_timeout": 30.0})
            _breakers[name] = CircuitBreaker(name=name, **defaults)
            logger.debug(
                "Created circuit breaker for service=%s with defaults=%s",
                name,
                defaults,
            )
        return _breakers[name]


def reset_all() -> None:
    """Reset every registered breaker back to CLOSED. Test helper."""
    with _lock:
        for breaker in _breakers.values():
            breaker.reset()


def list_registered() -> list[str]:
    """Return the names of all breakers created so far."""
    with _lock:
        return list(_breakers.keys())


def configure_breaker(name: str, **kwargs) -> CircuitBreaker:
    """Override the defaults for a service and return its breaker.

    Useful for tests that want a tighter failure threshold.
    """
    with _lock:
        _breakers[name] = CircuitBreaker(name=name, **kwargs)
        return _breakers[name]


def unregister(name: str) -> Optional[CircuitBreaker]:
    """Remove and return a breaker by name (test helper)."""
    with _lock:
        return _breakers.pop(name, None)
