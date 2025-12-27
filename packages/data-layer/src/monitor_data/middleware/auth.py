"""
Authority enforcement middleware for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only

This module enforces the authority matrix, ensuring only authorized agents
can call specific tools.
"""

from typing import Callable, Optional


# ============================================================================
# Authority Matrix
# ============================================================================
# This matrix defines which agent types can call which tools.
# - "*" means all agents can call the tool
# - List of agent names means only those agents can call the tool

AUTHORITY_MATRIX: dict[str, list[str]] = {
    # ========================================================================
    # Neo4j Universe Operations
    # ========================================================================
    "neo4j_create_universe": ["CanonKeeper"],
    "neo4j_get_universe": ["*"],
    "neo4j_update_universe": ["CanonKeeper"],
    "neo4j_list_universes": ["*"],
    "neo4j_delete_universe": ["CanonKeeper"],
    
    "neo4j_create_multiverse": ["CanonKeeper"],
    "neo4j_get_multiverse": ["*"],
    "neo4j_update_multiverse": ["CanonKeeper"],
    "neo4j_list_multiverses": ["*"],
    "neo4j_delete_multiverse": ["CanonKeeper"],
    
    # ========================================================================
    # Neo4j Entity Operations (to be added in DL-2)
    # ========================================================================
    # "neo4j_create_entity": ["CanonKeeper"],
    # "neo4j_get_entity": ["*"],
    # "neo4j_update_entity": ["CanonKeeper"],
    # "neo4j_list_entities": ["*"],
    # "neo4j_delete_entity": ["CanonKeeper"],
    
    # ========================================================================
    # Neo4j Fact/Event Operations (to be added in DL-3)
    # ========================================================================
    # "neo4j_create_fact": ["CanonKeeper"],
    # "neo4j_create_event": ["CanonKeeper"],
    # "neo4j_get_fact": ["*"],
    # "neo4j_update_fact": ["CanonKeeper"],
    # "neo4j_list_facts": ["*"],
    # "neo4j_delete_fact": ["CanonKeeper"],
    
    # ========================================================================
    # MongoDB Operations (to be added in future use cases)
    # ========================================================================
    # "mongodb_create_scene": ["Orchestrator"],
    # "mongodb_append_turn": ["Narrator", "Orchestrator"],
    # "mongodb_create_proposed_change": ["Resolver", "Narrator", "CanonKeeper"],
    # "mongodb_get_proposed_change": ["*"],
    # "mongodb_list_proposed_changes": ["*"],
    # "mongodb_update_proposed_change": ["Resolver", "Narrator", "CanonKeeper"],
    
    # ========================================================================
    # Qdrant Operations (to be added in future use cases)
    # ========================================================================
    # "qdrant_upsert": ["Indexer"],
    # "qdrant_search": ["*"],
    # "qdrant_delete": ["Indexer"],
    
    # ========================================================================
    # Composite Operations (to be added in future use cases)
    # ========================================================================
    # "composite_canonize_scene": ["CanonKeeper"],
    # "composite_assemble_context": ["*"],
}


class AuthorizationError(Exception):
    """Raised when an agent attempts to call a tool without authorization."""
    pass


def check_authority(tool_name: str, agent_type: Optional[str]) -> bool:
    """
    Check if an agent has authority to call a tool.
    
    Args:
        tool_name: Name of the tool being called
        agent_type: Type of agent making the call (e.g., "CanonKeeper", "Narrator")
        
    Returns:
        True if authorized, False otherwise
    """
    if tool_name not in AUTHORITY_MATRIX:
        # Tool not registered - deny by default
        return False
    
    allowed_agents = AUTHORITY_MATRIX[tool_name]
    
    # "*" means all agents are allowed
    if "*" in allowed_agents:
        return True
    
    # Check if agent_type is in the allowed list
    return agent_type in allowed_agents


def require_authority(tool_name: str) -> Callable:
    """
    Decorator to enforce authority checks on tool functions.
    
    Args:
        tool_name: Name of the tool being protected
        
    Returns:
        Decorator function
        
    Usage:
        @require_authority("neo4j_create_universe")
        def create_universe(agent_type: str, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(agent_type: Optional[str] = None, *args, **kwargs):
            if not check_authority(tool_name, agent_type):
                raise AuthorizationError(
                    f"Agent '{agent_type}' is not authorized to call '{tool_name}'. "
                    f"Allowed agents: {AUTHORITY_MATRIX.get(tool_name, [])}"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator
