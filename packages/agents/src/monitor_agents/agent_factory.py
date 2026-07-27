"""
Agent factory for MONITOR loops.

DIP: Centralizes agent instantiation so loops don't directly import
agent classes. Swapping implementations (e.g., for testing) requires
only changing this file.

LAYER: 2 (agents)
CALLED BY: scene_loop, story_loop, combat_loop, world_building_loop
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_agents.context_assembly.agent import ContextAssembly
    from monitor_agents.extraction.agent import ExtractionAgent
    from monitor_agents.narrator.agent import Narrator
    from monitor_agents.resolver import Resolver
    from monitor_agents.world_architect.world_rules_agent import WorldRulesAgent
    from monitor_agents.story.agent import StoryAgent

# Registry mapping class names to their module paths
AGENT_REGISTRY = {
    "ContextAssembly": "monitor_agents.context_assembly.agent",
    "Resolver": "monitor_agents.resolver",
    "Narrator": "monitor_agents.narrator.agent",
    "CanonKeeper": "monitor_agents.canonkeeper.agent",
    "ExtractionAgent": "monitor_agents.extraction.agent",
    "WorldRulesAgent": "monitor_agents.world_architect.world_rules_agent",
    "StoryAgent": "monitor_agents.story.agent",
}


class AgentFactory:
    """
    Creates agent instances for use in loop nodes.

    All agents are stateless — state lives in databases, not agents.
    This factory exists purely to centralize instantiation and make
    it easy to inject fakes/mocks in tests.
    """

    def _create_agent(self, class_name: str, agent_id: str) -> Any:
        module_path = AGENT_REGISTRY[class_name]
        module = importlib.import_module(module_path)
        agent_class = getattr(module, class_name)
        return agent_class(agent_id=agent_id)

    def create_context_assembly(self, agent_id: str = "context-assembly-1") -> ContextAssembly:
        return cast('ContextAssembly', self._create_agent("ContextAssembly", agent_id))

    def create_resolver(self, agent_id: str = "resolver-1") -> Resolver:
        return cast('Resolver', self._create_agent("Resolver", agent_id))

    def create_narrator(self, agent_id: str = "narrator-1") -> Narrator:
        return cast('Narrator', self._create_agent("Narrator", agent_id))

    def create_canonkeeper(self, agent_id: str = "canonkeeper-1") -> CanonKeeper:
        return cast('CanonKeeper', self._create_agent("CanonKeeper", agent_id))

    def create_extractor(self, agent_id: str = "extractor-1") -> ExtractionAgent:
        return cast('ExtractionAgent', self._create_agent("ExtractionAgent", agent_id))

    def create_world_rules(self, agent_id: str = "worldrules-1") -> WorldRulesAgent:
        return cast('WorldRulesAgent', self._create_agent("WorldRulesAgent", agent_id))

    def create_story_agent(self, agent_id: str = "story-1") -> StoryAgent:
        return cast('StoryAgent', self._create_agent("StoryAgent", agent_id))


# ----------------------------------------------------------------------
# Singleton instance for use across all loops
# ----------------------------------------------------------------------
_default_factory: AgentFactory | None = None


def get_agent_factory() -> AgentFactory:
    """Return the shared agent factory (lazy-initialized)."""
    global _default_factory
    if _default_factory is None:
        _default_factory = AgentFactory()
    return _default_factory


def set_agent_factory(factory: AgentFactory | None) -> None:
    """Install a custom factory (tests inject fakes through this seam)."""
    global _default_factory
    _default_factory = factory


def reset_agent_factory() -> None:
    """Reset the factory (useful for tests to ensure clean state)."""
    global _default_factory
    _default_factory = None
