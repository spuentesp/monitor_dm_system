"""
Neo4j tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only

MCP tools for interacting with Neo4j canonical graph database.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from monitor_data.db.neo4j import Neo4jClient
from monitor_data.middleware.auth import AuthorizationError, check_authority
from monitor_data.schemas.base import CanonLevel, ErrorResponse
from monitor_data.schemas.universe import (
    ListUniversesRequest,
    ListUniversesResponse,
    UniverseCreate,
    UniverseResponse,
    UniverseUpdate,
)


# ============================================================================
# Global Neo4j Client Instance
# ============================================================================

_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    """Get or create the global Neo4j client instance."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
        _neo4j_client.connect()
    return _neo4j_client


# ============================================================================
# Universe CRUD Operations
# ============================================================================


def neo4j_create_universe(
    agent_type: str,
    data: UniverseCreate,
) -> UniverseResponse | ErrorResponse:
    """
    Create a new Universe node in Neo4j.
    
    Authority: CanonKeeper only
    
    Args:
        agent_type: Type of agent making the request
        data: Universe creation data
        
    Returns:
        UniverseResponse on success, ErrorResponse on failure
    """
    # Check authority
    if not check_authority("neo4j_create_universe", agent_type):
        return ErrorResponse(
            error=f"Agent '{agent_type}' is not authorized to create universes",
            code="UNAUTHORIZED",
            details={"tool": "neo4j_create_universe", "agent": agent_type}
        )
    
    try:
        client = get_neo4j_client()
        
        # Generate UUID for the new universe
        universe_id = uuid4()
        created_at = datetime.now(timezone.utc)
        
        # First verify that the multiverse exists
        verify_query = """
        MATCH (m:Multiverse {id: $multiverse_id})
        RETURN m
        """
        result = client.execute_read(verify_query, {"multiverse_id": str(data.multiverse_id)})
        
        if not result:
            return ErrorResponse(
                error=f"Multiverse with id {data.multiverse_id} does not exist",
                code="NOT_FOUND",
                details={"multiverse_id": str(data.multiverse_id)}
            )
        
        # Create the Universe node and relationship
        create_query = """
        MATCH (m:Multiverse {id: $multiverse_id})
        CREATE (u:Universe {
            id: $id,
            multiverse_id: $multiverse_id,
            name: $name,
            description: $description,
            genre: $genre,
            tone: $tone,
            tech_level: $tech_level,
            canon_level: $canon_level,
            authority: $authority,
            created_at: datetime($created_at)
        })
        CREATE (m)-[:CONTAINS]->(u)
        RETURN u
        """
        
        params = {
            "id": str(universe_id),
            "multiverse_id": str(data.multiverse_id),
            "name": data.name,
            "description": data.description,
            "genre": data.genre or "",
            "tone": data.tone or "",
            "tech_level": data.tech_level or "",
            "canon_level": CanonLevel.CANON.value,
            "authority": data.authority.value,
            "created_at": created_at.isoformat(),
        }
        
        result = client.execute_write(create_query, params)
        
        if not result:
            return ErrorResponse(
                error="Failed to create universe",
                code="CREATE_FAILED",
                details={"multiverse_id": str(data.multiverse_id)}
            )
        
        # Return the created universe
        return UniverseResponse(
            id=universe_id,
            multiverse_id=data.multiverse_id,
            name=data.name,
            description=data.description,
            genre=data.genre,
            tone=data.tone,
            tech_level=data.tech_level,
            canon_level=CanonLevel.CANON,
            authority=data.authority,
            created_at=created_at,
        )
        
    except Exception as e:
        return ErrorResponse(
            error=str(e),
            code="INTERNAL_ERROR",
            details={"exception": type(e).__name__}
        )


def neo4j_get_universe(
    agent_type: str,
    universe_id: UUID,
) -> UniverseResponse | ErrorResponse:
    """
    Get a Universe by ID.
    
    Authority: All agents (read-only)
    
    Args:
        agent_type: Type of agent making the request
        universe_id: ID of the universe to retrieve
        
    Returns:
        UniverseResponse on success, ErrorResponse on failure
    """
    # Check authority
    if not check_authority("neo4j_get_universe", agent_type):
        return ErrorResponse(
            error=f"Agent '{agent_type}' is not authorized to read universes",
            code="UNAUTHORIZED",
            details={"tool": "neo4j_get_universe", "agent": agent_type}
        )
    
    try:
        client = get_neo4j_client()
        
        query = """
        MATCH (u:Universe {id: $universe_id})
        RETURN u
        """
        
        result = client.execute_read(query, {"universe_id": str(universe_id)})
        
        if not result:
            return ErrorResponse(
                error=f"Universe with id {universe_id} not found",
                code="NOT_FOUND",
                details={"universe_id": str(universe_id)}
            )
        
        node = result[0]["u"]
        
        return UniverseResponse(
            id=UUID(node["id"]),
            multiverse_id=UUID(node["multiverse_id"]),
            name=node["name"],
            description=node["description"],
            genre=node.get("genre") or None,
            tone=node.get("tone") or None,
            tech_level=node.get("tech_level") or None,
            canon_level=CanonLevel(node["canon_level"]),
            authority=node["authority"],
            created_at=datetime.fromisoformat(str(node["created_at"]).replace("Z", "+00:00")),
        )
        
    except Exception as e:
        return ErrorResponse(
            error=str(e),
            code="INTERNAL_ERROR",
            details={"exception": type(e).__name__}
        )


def neo4j_update_universe(
    agent_type: str,
    universe_id: UUID,
    data: UniverseUpdate,
) -> UniverseResponse | ErrorResponse:
    """
    Update a Universe's mutable fields.
    
    Authority: CanonKeeper only
    
    Args:
        agent_type: Type of agent making the request
        universe_id: ID of the universe to update
        data: Universe update data
        
    Returns:
        UniverseResponse on success, ErrorResponse on failure
    """
    # Check authority
    if not check_authority("neo4j_update_universe", agent_type):
        return ErrorResponse(
            error=f"Agent '{agent_type}' is not authorized to update universes",
            code="UNAUTHORIZED",
            details={"tool": "neo4j_update_universe", "agent": agent_type}
        )
    
    try:
        client = get_neo4j_client()
        
        # Build SET clause dynamically based on provided fields
        set_clauses = []
        params = {"universe_id": str(universe_id)}
        
        if data.name is not None:
            set_clauses.append("u.name = $name")
            params["name"] = data.name
        
        if data.description is not None:
            set_clauses.append("u.description = $description")
            params["description"] = data.description
        
        if data.genre is not None:
            set_clauses.append("u.genre = $genre")
            params["genre"] = data.genre
        
        if data.tone is not None:
            set_clauses.append("u.tone = $tone")
            params["tone"] = data.tone
        
        if data.tech_level is not None:
            set_clauses.append("u.tech_level = $tech_level")
            params["tech_level"] = data.tech_level
        
        if not set_clauses:
            # No fields to update
            return neo4j_get_universe(agent_type, universe_id)
        
        query = f"""
        MATCH (u:Universe {{id: $universe_id}})
        SET {', '.join(set_clauses)}
        RETURN u
        """
        
        result = client.execute_write(query, params)
        
        if not result:
            return ErrorResponse(
                error=f"Universe with id {universe_id} not found",
                code="NOT_FOUND",
                details={"universe_id": str(universe_id)}
            )
        
        node = result[0]["u"]
        
        return UniverseResponse(
            id=UUID(node["id"]),
            multiverse_id=UUID(node["multiverse_id"]),
            name=node["name"],
            description=node["description"],
            genre=node.get("genre") or None,
            tone=node.get("tone") or None,
            tech_level=node.get("tech_level") or None,
            canon_level=CanonLevel(node["canon_level"]),
            authority=node["authority"],
            created_at=datetime.fromisoformat(str(node["created_at"]).replace("Z", "+00:00")),
        )
        
    except Exception as e:
        return ErrorResponse(
            error=str(e),
            code="INTERNAL_ERROR",
            details={"exception": type(e).__name__}
        )


def neo4j_list_universes(
    agent_type: str,
    request: Optional[ListUniversesRequest] = None,
) -> ListUniversesResponse | ErrorResponse:
    """
    List universes with optional filtering and pagination.
    
    Authority: All agents (read-only)
    
    Args:
        agent_type: Type of agent making the request
        request: List request with filters and pagination
        
    Returns:
        ListUniversesResponse on success, ErrorResponse on failure
    """
    # Check authority
    if not check_authority("neo4j_list_universes", agent_type):
        return ErrorResponse(
            error=f"Agent '{agent_type}' is not authorized to list universes",
            code="UNAUTHORIZED",
            details={"tool": "neo4j_list_universes", "agent": agent_type}
        )
    
    try:
        client = get_neo4j_client()
        
        # Use defaults if request is None
        if request is None:
            request = ListUniversesRequest()
        
        # Build WHERE clause
        where_clauses = []
        params: dict = {
            "limit": request.limit,
            "offset": request.offset,
        }
        
        if request.multiverse_id is not None:
            where_clauses.append("u.multiverse_id = $multiverse_id")
            params["multiverse_id"] = str(request.multiverse_id)
        
        if request.canon_level is not None:
            where_clauses.append("u.canon_level = $canon_level")
            params["canon_level"] = request.canon_level.value
        
        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        # Count total
        count_query = f"""
        MATCH (u:Universe)
        {where_clause}
        RETURN count(u) as total
        """
        
        count_result = client.execute_read(count_query, params)
        total = count_result[0]["total"] if count_result else 0
        
        # Get paginated results
        query = f"""
        MATCH (u:Universe)
        {where_clause}
        RETURN u
        ORDER BY u.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        
        result = client.execute_read(query, params)
        
        universes = []
        for record in result:
            node = record["u"]
            universes.append(
                UniverseResponse(
                    id=UUID(node["id"]),
                    multiverse_id=UUID(node["multiverse_id"]),
                    name=node["name"],
                    description=node["description"],
                    genre=node.get("genre") or None,
                    tone=node.get("tone") or None,
                    tech_level=node.get("tech_level") or None,
                    canon_level=CanonLevel(node["canon_level"]),
                    authority=node["authority"],
                    created_at=datetime.fromisoformat(str(node["created_at"]).replace("Z", "+00:00")),
                )
            )
        
        return ListUniversesResponse(
            universes=universes,
            total=total,
        )
        
    except Exception as e:
        return ErrorResponse(
            error=str(e),
            code="INTERNAL_ERROR",
            details={"exception": type(e).__name__}
        )


def neo4j_delete_universe(
    agent_type: str,
    universe_id: UUID,
    force: bool = False,
) -> dict | ErrorResponse:
    """
    Delete a Universe node.
    
    Authority: CanonKeeper only
    
    Args:
        agent_type: Type of agent making the request
        universe_id: ID of the universe to delete
        force: If True, cascade delete all dependent data
        
    Returns:
        Success dict on success, ErrorResponse on failure
    """
    # Check authority
    if not check_authority("neo4j_delete_universe", agent_type):
        return ErrorResponse(
            error=f"Agent '{agent_type}' is not authorized to delete universes",
            code="UNAUTHORIZED",
            details={"tool": "neo4j_delete_universe", "agent": agent_type}
        )
    
    try:
        client = get_neo4j_client()
        
        if not force:
            # Check for dependent data
            check_query = """
            MATCH (u:Universe {id: $universe_id})
            OPTIONAL MATCH (u)-[r]->(dependent)
            WHERE NOT dependent:Multiverse
            RETURN count(dependent) as dependents
            """
            
            result = client.execute_read(check_query, {"universe_id": str(universe_id)})
            
            if result and result[0]["dependents"] > 0:
                return ErrorResponse(
                    error=f"Universe has dependent data. Use force=true to cascade delete.",
                    code="HAS_DEPENDENTS",
                    details={
                        "universe_id": str(universe_id),
                        "dependents": result[0]["dependents"]
                    }
                )
        
        # Delete the universe (and dependents if force=True)
        if force:
            delete_query = """
            MATCH (u:Universe {id: $universe_id})
            OPTIONAL MATCH (u)-[*]->(dependent)
            DETACH DELETE u, dependent
            RETURN count(u) as deleted
            """
        else:
            delete_query = """
            MATCH (u:Universe {id: $universe_id})
            DETACH DELETE u
            RETURN count(u) as deleted
            """
        
        result = client.execute_write(delete_query, {"universe_id": str(universe_id)})
        
        if not result or result[0]["deleted"] == 0:
            return ErrorResponse(
                error=f"Universe with id {universe_id} not found",
                code="NOT_FOUND",
                details={"universe_id": str(universe_id)}
            )
        
        return {
            "success": True,
            "universe_id": str(universe_id),
            "message": "Universe deleted successfully"
        }
        
    except Exception as e:
        return ErrorResponse(
            error=str(e),
            code="INTERNAL_ERROR",
            details={"exception": type(e).__name__}
        )
