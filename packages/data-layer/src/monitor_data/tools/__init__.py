"""
MCP Tools for MONITOR Data Layer.

These tools are exposed via the MCP server for agents to call.
Each tool enforces authority checks before executing.

TOOL CATEGORIES:
- neo4j_tools:     41 operations (entities, facts, events, queries)
- mongodb_tools:   18 operations (scenes, turns, proposals, memories)
- qdrant_tools:    3 operations (embed, search, delete)
- composite_tools: 2 operations (context assembly, canonization)

AUTHORITY ENFORCEMENT:
Tools check the calling agent's type before executing.
Example: neo4j_create_fact() only allows agent_type="CanonKeeper"

See: docs/architecture/MCP_TRANSPORT.md for full tool specifications
See: docs/architecture/AGENT_ORCHESTRATION.md for authority matrix
"""

from monitor_data.tools.neo4j_tools import (
    neo4j_create_multiverse,
    neo4j_get_multiverse,
    neo4j_create_universe,
    neo4j_get_universe,
    neo4j_list_universes,
    neo4j_update_universe,
    neo4j_delete_universe,
    neo4j_ensure_omniverse,
)

from monitor_data.tools.qdrant_tools import (
    qdrant_upsert,
    qdrant_upsert_batch,
    qdrant_search,
    qdrant_delete,
    qdrant_delete_by_filter,
    qdrant_get_collection_info,
    qdrant_create_collection,
)

# from monitor_data.tools.mongodb_tools import *
# from monitor_data.tools.composite_tools import *

__all__ = [
    # Neo4j Universe/Multiverse tools
    "neo4j_create_multiverse",
    "neo4j_get_multiverse",
    "neo4j_create_universe",
    "neo4j_get_universe",
    "neo4j_list_universes",
    "neo4j_update_universe",
    "neo4j_delete_universe",
    "neo4j_ensure_omniverse",
    # Qdrant vector tools
    "qdrant_upsert",
    "qdrant_upsert_batch",
    "qdrant_search",
    "qdrant_delete",
    "qdrant_delete_by_filter",
    "qdrant_get_collection_info",
    "qdrant_create_collection",
]
