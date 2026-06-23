"""
Agent factory for MONITOR loops.

DIP: Centralizes agent instantiation so loops don't directly import
agent classes. Swapping implementations (e.g., for testing) requires
only changing this file.

LAYER: 2 (agents)
CALLED BY: scene_loop, story_loop, combat_loop, world_building_loop
"""

from __future__ import annotations

from typing import Optional

from monitor_agents.canonkeeper import CanonKeeper
from monitor_agents.context_assembly import ContextAssembly
from monitor_agents.narrator import Narrator
from monitor_agents.resolver import Resolver


class AgentFactory:
    """
    Creates agent instances for use in loop nodes.

    All agents are stateless — state lives in databases, not agents.
    This factory exists purely to centralize instantiation and make
    it easy to inject fakes/mocks in tests.
    """

    def create_context_assembly(self, agent_id: str = "context-assembly-1") -> ContextAssembly:
        return ContextAssembly(agent_id=agent_id)

    def create_resolver(self, agent_id: str = "resolver-1") -> Resolver:
        return Resolver(agent_id=agent_id)

    def create_narrator(self, agent_id: str = "narrator-1") -> Narrator:
        return Narrator(agent_id=agent_id)

    def create_canonkeeper(self, agent_id: str = "canonkeeper-1") -> CanonKeeper:
        return CanonKeeper(agent_id=agent_id)


# ----------------------------------------------------------------------
# Singleton instance for use across all loops
# ----------------------------------------------------------------------
_default_factory: Optional[AgentFactory] = None


def get_agent_factory() -> AgentFactory:
    """Return the shared agent factory (lazy-initialized)."""
    global _default_factory
    if _default_factory is None:
        _default_factory = AgentFactory()
    return _default_factory


def set_agent_factory(factory: Optional[AgentFactory]) -> None:
    """Install a custom factory (tests inject fakes through this seam)."""
    global _default_factory
    _default_factory = factory


def reset_agent_factory() -> None:
    """Reset the factory (useful for tests to ensure clean state)."""
    global _default_factory
    _default_factory = None
