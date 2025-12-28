"""
Middleware for MONITOR Data Layer.

AUTHORITY ENFORCEMENT:
The auth middleware ensures that only authorized agents can call certain tools.
This is the ENFORCEMENT POINT for the authority matrix.

AUTHORITY MATRIX:
| Tool Pattern           | Allowed Agents                    |
|------------------------|-----------------------------------|
| neo4j_create_*         | CanonKeeper                       |
| neo4j_update_*         | CanonKeeper                       |
| neo4j_get_*, neo4j_query_* | * (all agents)               |
| mongodb_create_scene   | Orchestrator                      |
| mongodb_append_turn    | Narrator, Orchestrator            |
| mongodb_*_proposal     | Resolver, Narrator, CanonKeeper   |
| qdrant_*               | Indexer, ContextAssembly (read)   |
| composite_canonize_*   | CanonKeeper                       |

VALIDATION:
The validation middleware ensures all requests conform to Pydantic schemas
before reaching database clients.

See: docs/architecture/AGENT_ORCHESTRATION.md for full authority matrix
"""

from monitor_data.middleware.auth import (
    require_authority,
    check_authority,
    get_allowed_agents,
    AuthorizationError,
    AUTHORITY_MATRIX,
)

# from monitor_data.middleware.validation import validate_request

__all__ = [
    "require_authority",
    "check_authority",
    "get_allowed_agents",
    "AuthorizationError",
    "AUTHORITY_MATRIX",
    # "validate_request",
]
