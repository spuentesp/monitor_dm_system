"""
Authority enforcement middleware for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only
CALLED BY: MCP server (server.py)

This is the ENFORCEMENT POINT for the authority matrix.
Only authorized agents can call certain tools (primarily write operations).
"""

from typing import List


# =============================================================================
# AUTHORITY MATRIX
# =============================================================================

# Maps tool names to list of allowed agent types
# If a tool is not in this dict, it's accessible by all agents (default open)
# Empty list [] means no agent can call it (reserved/internal)
# ["*"] means all agents can call it (explicit open)
# Specific agent names restrict access to those agents only

AUTHORITY_MATRIX = {
    # =========================================================================
    # NEO4J OPERATIONS - Universe & Multiverse
    # =========================================================================
    "neo4j_create_multiverse": ["CanonKeeper"],
    "neo4j_get_multiverse": ["*"],
    "neo4j_create_universe": ["CanonKeeper"],
    "neo4j_get_universe": ["*"],
    "neo4j_list_universes": ["*"],
    "neo4j_update_universe": ["CanonKeeper"],
    "neo4j_delete_universe": ["CanonKeeper"],
    "neo4j_ensure_omniverse": ["CanonKeeper"],
    # =========================================================================
    # NEO4J OPERATIONS - Entities (DL-2)
    # =========================================================================
    "neo4j_create_entity": ["CanonKeeper"],
    "neo4j_get_entity": ["*"],
    "neo4j_list_entities": ["*"],
    "neo4j_update_entity": ["CanonKeeper"],
    "neo4j_delete_entity": ["CanonKeeper"],
    "neo4j_set_state_tags": ["CanonKeeper"],
    # =========================================================================
    # NEO4J OPERATIONS - Relationships
    # =========================================================================
    "neo4j_create_relationship": ["CanonKeeper"],
    "neo4j_get_relationships": ["*"],
    "neo4j_delete_relationship": ["CanonKeeper"],
    # =========================================================================
    # NEO4J OPERATIONS - Facts & Events
    # =========================================================================
    "neo4j_create_fact": ["CanonKeeper"],
    "neo4j_get_fact": ["*"],
    "neo4j_list_facts": ["*"],
    "neo4j_update_fact": ["CanonKeeper"],
    "neo4j_delete_fact": ["CanonKeeper"],
    "neo4j_create_event": ["CanonKeeper"],
    "neo4j_get_event": ["*"],
    "neo4j_list_events": ["*"],
    # =========================================================================
    # NEO4J OPERATIONS - Stories
    # =========================================================================
    "neo4j_create_story": ["CanonKeeper", "Orchestrator"],
    "neo4j_get_story": ["*"],
    "neo4j_list_stories": ["*"],
    "neo4j_update_story": ["CanonKeeper"],
    # =========================================================================
    # NEO4J OPERATIONS - Sources
    # =========================================================================
    "neo4j_create_source": ["CanonKeeper"],
    "neo4j_get_source": ["*"],
    "neo4j_list_sources": ["*"],
    "neo4j_link_evidence": ["CanonKeeper"],
    # =========================================================================
    # NEO4J OPERATIONS - Axioms
    # =========================================================================
    "neo4j_create_axiom": ["CanonKeeper"],
    "neo4j_get_axiom": ["*"],
    "neo4j_list_axioms": ["*"],
    # =========================================================================
    # NEO4J OPERATIONS - Plot Threads
    # =========================================================================
    "neo4j_create_plot_thread": ["CanonKeeper"],
    "neo4j_update_plot_thread": ["CanonKeeper"],
    "neo4j_list_plot_threads": ["*"],
    # =========================================================================
    # MONGODB OPERATIONS - Scenes
    # =========================================================================
    "mongodb_create_scene": ["CanonKeeper", "Narrator"],
    "mongodb_get_scene": ["*"],
    "mongodb_update_scene": ["CanonKeeper", "Narrator"],
    "mongodb_list_scenes": ["*"],
    # =========================================================================
    # MONGODB OPERATIONS - Turns
    # =========================================================================
    "mongodb_append_turn": ["*"],
    "mongodb_get_turns": ["*"],
    "mongodb_undo_turn": ["Orchestrator"],
    # =========================================================================
    # MONGODB OPERATIONS - Proposals (Legacy - kept for backward compatibility)
    # =========================================================================
    "mongodb_create_proposal": ["Narrator", "Resolver", "CanonKeeper"],
    "mongodb_get_proposals": ["*"],
    "mongodb_update_proposal": ["CanonKeeper"],
    "mongodb_list_pending_proposals": ["*"],
    # =========================================================================
    # MONGODB OPERATIONS - Proposed Changes (DL-5)
    # =========================================================================
    "mongodb_create_proposed_change": ["*"],
    "mongodb_get_proposed_change": ["*"],
    "mongodb_list_proposed_changes": ["*"],
    "mongodb_update_proposed_change": ["CanonKeeper"],
    # =========================================================================
    # MONGODB OPERATIONS - Resolutions
    # =========================================================================
    "mongodb_create_resolution": ["Resolver"],
    "mongodb_get_resolution": ["*"],
    # =========================================================================
    # MONGODB OPERATIONS - Memories
    # =========================================================================
    "mongodb_create_memory": ["MemoryManager"],
    "mongodb_get_memories": ["*"],
    "mongodb_update_memory": ["MemoryManager"],
    "mongodb_search_memories": ["*"],
    # =========================================================================
    # MONGODB OPERATIONS - Character Sheets
    # =========================================================================
    "mongodb_create_character_sheet": ["Orchestrator"],
    "mongodb_get_character_sheet": ["*"],
    "mongodb_update_character_sheet": ["Orchestrator", "CanonKeeper"],
    # =========================================================================
    # MONGODB OPERATIONS - Documents
    # =========================================================================
    "mongodb_create_document": ["Indexer"],
    "mongodb_get_document": ["*"],
    "mongodb_list_documents": ["*"],
    "mongodb_update_document_status": ["Indexer"],
    # =========================================================================
    # MONGODB OPERATIONS - Snippets
    # =========================================================================
    "mongodb_create_snippets": ["Indexer"],
    "mongodb_get_snippets": ["*"],
    # =========================================================================
    # MONGODB OPERATIONS - Story Outlines
    # =========================================================================
    "mongodb_create_story_outline": ["Orchestrator"],
    "mongodb_get_story_outline": ["*"],
    "mongodb_update_story_outline": ["Orchestrator"],
    # =========================================================================
    # QDRANT OPERATIONS - Vectors
    # =========================================================================
    "qdrant_embed_scene": ["Indexer"],
    "qdrant_embed_memory": ["Indexer"],
    "qdrant_embed_snippet": ["Indexer"],
    "qdrant_search": ["*"],
    "qdrant_search_memories": ["*"],
    "qdrant_delete_vectors": ["Indexer"],
    # =========================================================================
    # COMPOSITE OPERATIONS
    # =========================================================================
    "composite_get_entity_full": ["*"],
    "composite_get_scene_context": ["*"],
    # =========================================================================
    # UTILITY OPERATIONS
    # =========================================================================
    "dice_roll": ["*"],
}


def check_authority(tool_name: str, agent_type: str) -> bool:
    """
    Check if an agent has authority to call a tool.

    Args:
        tool_name: Name of the tool being called
        agent_type: Type of the calling agent (e.g., "CanonKeeper", "Narrator")

    Returns:
        True if agent has authority, False otherwise

    Examples:
        >>> check_authority("neo4j_create_universe", "CanonKeeper")
        True
        >>> check_authority("neo4j_create_universe", "Narrator")
        False
        >>> check_authority("neo4j_get_universe", "Narrator")
        True
    """
    # If tool not in matrix, default to open access
    if tool_name not in AUTHORITY_MATRIX:
        return True

    allowed_agents = AUTHORITY_MATRIX[tool_name]

    # Empty list means no access (reserved/internal)
    if not allowed_agents:
        return False

    # ["*"] means all agents allowed
    if "*" in allowed_agents:
        return True

    # Check if agent_type is in the allowed list
    return agent_type in allowed_agents


def get_allowed_agents(tool_name: str) -> List[str]:
    """
    Get list of agents allowed to call a tool.

    Args:
        tool_name: Name of the tool

    Returns:
        List of allowed agent types, or ["*"] if open to all

    Examples:
        >>> get_allowed_agents("neo4j_create_universe")
        ['CanonKeeper']
        >>> get_allowed_agents("neo4j_get_universe")
        ['*']
    """
    return AUTHORITY_MATRIX.get(tool_name, ["*"])


class AuthorizationError(Exception):
    """Raised when an agent attempts an unauthorized operation."""

    def __init__(self, tool_name: str, agent_type: str, allowed_agents: List[str]):
        self.tool_name = tool_name
        self.agent_type = agent_type
        self.allowed_agents = allowed_agents
        super().__init__(
            f"Agent '{agent_type}' is not authorized to call '{tool_name}'. "
            f"Allowed agents: {', '.join(allowed_agents)}"
        )


def require_authority(tool_name: str, agent_type: str) -> None:
    """
    Enforce authority check, raising an exception if unauthorized.

    Args:
        tool_name: Name of the tool being called
        agent_type: Type of the calling agent

    Raises:
        AuthorizationError: If agent lacks authority

    Examples:
        >>> require_authority("neo4j_create_universe", "CanonKeeper")  # OK
        >>> require_authority("neo4j_create_universe", "Narrator")  # Raises
        Traceback (most recent call last):
            ...
        AuthorizationError: Agent 'Narrator' is not authorized...
    """
    if not check_authority(tool_name, agent_type):
        allowed = get_allowed_agents(tool_name)
        raise AuthorizationError(tool_name, agent_type, allowed)
