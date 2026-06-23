"""
Commit handler registry for CanonKeeper.

遵循 Open/Closed Principle: 添加新实体类型无需修改 CanonKeeper 类本身，
只需注册新的 handler 即可。

Usage:
    from monitor_agents.handlers.registry import commit_handler, get_handler

    @commit_handler("custom_entity")
    async def handle_custom(proposals_coll, proposal_id, proposal, source_id_strs, verdict, agent):
        ...
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Handler signature: (proposals_coll, proposal_id, proposal, source_id_strs, verdict, agent)
CommitHandler = Callable[
    [Any, str, Dict[str, Any], Optional[List[str]], BaseModel, Any],  # agent is BaseAgent
    Awaitable[None],
]


class CommitHandlerRegistry:
    """
    Registry for proposal commit handlers.

    Allows handlers to be registered dynamically rather than hard-coded
    in a static dict. Follows Open/Closed Principle.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, CommitHandler] = {}

    def register(self, type_key: str, handler: CommitHandler) -> None:
        """Register a handler for a given type key."""
        if type_key in self._handlers:
            logger.warning(
                "Overwriting existing handler for type_key '%s'",
                type_key,
            )
        self._handlers[type_key] = handler
        logger.debug("Registered commit handler for type_key: %s", type_key)

    def get(self, type_key: str) -> Optional[CommitHandler]:
        """Get handler for a type key, returns None if not found."""
        return self._handlers.get(type_key)

    def get_handler_name(self, type_key: str) -> Optional[str]:
        """
        Get the handler name for a type key.
        Returns the function name for debugging.
        """
        handler = self._handlers.get(type_key)
        return handler.__name__ if handler else None

    def list_types(self) -> List[str]:
        """List all registered type keys."""
        return list(self._handlers.keys())


# Global registry instance
_registry: Optional[CommitHandlerRegistry] = None


def get_handler_registry() -> CommitHandlerRegistry:
    """Get the global handler registry (singleton)."""
    global _registry
    if _registry is None:
        _registry = CommitHandlerRegistry()
        _register_builtin_handlers()
    return _registry


def reset_handler_registry() -> None:
    """Reset the registry (for testing)."""
    global _registry
    _registry = None


def commit_handler(type_key: str) -> Callable[[CommitHandler], CommitHandler]:
    """
    Decorator to register a commit handler for a type key.

    Usage:
        @commit_handler("custom_entity")
        async def handle_custom(proposals_coll, proposal_id, proposal, source_id_strs, verdict, agent):
            await agent.call_tool("neo4j_create_entity", {...})
    """

    def decorator(func: CommitHandler) -> CommitHandler:
        registry = get_handler_registry()
        registry.register(type_key, func)
        return func

    return decorator


def _register_builtin_handlers() -> None:
    """
    Register built-in handlers from CanonKeeper.

    This is called once on first access to ensure backward compatibility.
    The actual handler methods live in CanonKeeper class and are wrapped here.
    """
    # Import here to avoid circular imports

    # Map of type_key -> method name on CanonKeeper
    _BUILTIN_HANDLERS = {
        "multiverse": "_commit_multiverse",
        "universe": "_commit_universe",
        "entity": "_commit_entity",
        "character": "_commit_entity",
        "location": "_commit_entity",
        "item": "_commit_entity",
        "faction": "_commit_entity",
        "concept": "_commit_entity",
        "create_entity_archetype": "_commit_entity",
        "entity_archetype": "_commit_entity",
        "axiom": "_commit_axiom",
        "create_axiom": "_commit_axiom",
        "world_truth": "_commit_axiom",
        "update_agenda_clock": "_commit_update_agenda_clock",
        "create_agenda": "_commit_create_agenda",
        "spatial_topology": "_commit_spatial_topology",
        "create_random_table": "_commit_random_table",
        "create_tone_profile": "_commit_tone_profile",
        "create_character_profile": "_commit_character_profile",
        "create_generation_template": "_commit_generation_template",
        "relationship": "_commit_relationship",
        "fact": "_commit_fact",
        "event": "_commit_fact",
        "create_lore_fact": "_commit_fact",
        "lore_fact": "_commit_fact",
        "create_plot_thread": "_commit_plot_thread",
        "entity_relationship": "_commit_entity_relationship",
        "state_update": "_commit_state_change",
        "state_change": "_commit_state_change",
    }

    # Note: The actual handler methods are instance methods on CanonKeeper.
    # This registry just provides a way to look them up by type key.
    # The dispatch happens in CanonKeeper._commit_to_neo4j().
    for type_key, method_name in _BUILTIN_HANDLERS.items():
        # We store a placeholder that references the method name
        # The actual call dispatches through CanonKeeper
        pass  # Handlers are registered via CanonKeeper._COMMIT_HANDLERS for now


class CommitHandlerAdapter:
    """
    Adapter that wraps a CanonKeeper instance to work with the registry.

    This allows the existing CanonKeeper handler methods to be used
    through the registry interface.
    """

    def __init__(self, agent: Any) -> None:
        self._agent = agent

    async def execute(
        self,
        type_key: str,
        proposals_coll: Any,
        proposal_id: str,
        proposal: Dict[str, Any],
        source_id_strs: Optional[List[str]],
        verdict: BaseModel,
    ) -> None:
        """Execute the handler for the given type key."""
        registry = get_handler_registry()
        handler = registry.get(type_key)

        if handler is None:
            # Fall back to CanonKeeper's built-in dispatch
            await self._fallback_dispatch(
                type_key, proposals_coll, proposal_id, proposal, source_id_strs, verdict
            )
            return

        await handler(proposals_coll, proposal_id, proposal, source_id_strs, verdict, self._agent)

    async def _fallback_dispatch(
        self,
        type_key: str,
        proposals_coll: Any,
        proposal_id: str,
        proposal: Dict[str, Any],
        source_id_strs: Optional[List[str]],
        verdict: BaseModel,
    ) -> None:
        """Fallback to CanonKeeper's internal _COMMIT_HANDLERS dispatch."""
        # This maintains backward compatibility
        from monitor_agents.canonkeeper import CanonKeeper

        if isinstance(self._agent, CanonKeeper):
            handler_name = self._agent._COMMIT_HANDLERS.get(type_key)
            if handler_name:
                handler = getattr(self._agent, handler_name)
                await handler(proposals_coll, proposal_id, proposal, source_id_strs, verdict)
            else:
                logger.warning("Unknown type_key '%s' in fallback dispatch", type_key)
        else:
            logger.error("Cannot fallback dispatch for non-CanonKeeper agent")
