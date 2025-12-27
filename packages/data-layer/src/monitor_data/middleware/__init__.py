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
| neo4j_delete_*         | CanonKeeper                       |
| neo4j_get_*, neo4j_list_* | * (all agents)               |
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
    AUTHORITY_MATRIX,
    AuthorizationError,
    check_authority,
    require_authority,
)

__all__ = [
    "AUTHORITY_MATRIX",
    "AuthorizationError",
    "check_authority",
    "require_authority",
]

# from monitor_data.middleware.validation import validate_request
