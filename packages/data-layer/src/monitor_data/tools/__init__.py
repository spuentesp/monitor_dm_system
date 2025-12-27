"""
MCP Tools for MONITOR Data Layer.

These tools are exposed via the MCP server for agents to call.
Each tool enforces authority checks before executing.

TOOL CATEGORIES:
- neo4j_tools:     Universe/Multiverse operations + entities, facts, events (to be expanded)
- mongodb_tools:   18 operations (scenes, turns, proposals, memories) (to be added)
- qdrant_tools:    3 operations (embed, search, delete) (to be added)
- composite_tools: 2 operations (context assembly, canonization) (to be added)

AUTHORITY ENFORCEMENT:
Tools check the calling agent's type before executing.
Example: neo4j_create_fact() only allows agent_type="CanonKeeper"

See: docs/architecture/MCP_TRANSPORT.md for full tool specifications
See: docs/architecture/AGENT_ORCHESTRATION.md for authority matrix
"""

from monitor_data.tools.neo4j_tools import (
    neo4j_create_universe,
    neo4j_delete_universe,
    neo4j_get_universe,
    neo4j_list_universes,
    neo4j_update_universe,
)

__all__ = [
    "neo4j_create_universe",
    "neo4j_delete_universe",
    "neo4j_get_universe",
    "neo4j_list_universes",
    "neo4j_update_universe",
]

# from monitor_data.tools.mongodb_tools import *
# from monitor_data.tools.qdrant_tools import *
# from monitor_data.tools.composite_tools import *
