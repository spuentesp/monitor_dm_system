"""
Commit handlers for CanonKeeper.

Provides a registration system for entity-type-specific commit handlers,
following the Open/Closed Principle.
"""

from monitor_agents.handlers.registry import (
    CommitHandlerAdapter,
    CommitHandlerRegistry,
    commit_handler,
    get_handler_registry,
    reset_handler_registry,
)

__all__ = [
    "CommitHandlerAdapter",
    "CommitHandlerRegistry",
    "commit_handler",
    "get_handler_registry",
    "reset_handler_registry",
]
