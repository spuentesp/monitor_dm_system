"""
Neo4j MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose Neo4j operations via the MCP server.
All write operations require CanonKeeper authority (enforced by middleware).
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.universe import (
    UniverseCreate,
    UniverseUpdate,
    UniverseResponse,
    UniverseFilter,
    MultiverseCreate,
    MultiverseResponse,
)


# =============================================================================
# MULTIVERSE OPERATIONS
# =============================================================================


def neo4j_create_multiverse(params: MultiverseCreate) -> MultiverseResponse:
    """
    Create a new Multiverse node.

    Authority: CanonKeeper only
    Use Case: DL-1 (prerequisite for universes)

    Args:
        params: Multiverse creation parameters

    Returns:
        MultiverseResponse with created multiverse data

    Raises:
        ValueError: If omniverse_id doesn't exist
    """
    client = get_neo4j_client()

    # Verify omniverse exists
    verify_query = """
    MATCH (o:Omniverse {id: $omniverse_id})
    RETURN o.id as id
    """
    result = client.execute_read(
        verify_query, {"omniverse_id": str(params.omniverse_id)}
    )
    if not result:
        raise ValueError(f"Omniverse {params.omniverse_id} not found")

    # Create multiverse
    multiverse_id = uuid4()
    create_query = """
    MATCH (o:Omniverse {id: $omniverse_id})
    CREATE (m:Multiverse {
        id: $id,
        omniverse_id: $omniverse_id,
        name: $name,
        system_name: $system_name,
        description: $description,
        created_at: datetime($created_at)
    })
    CREATE (o)-[:CONTAINS]->(m)
    RETURN m
    """
    created_at = datetime.now(timezone.utc)
    client.execute_write(
        create_query,
        {
            "id": str(multiverse_id),
            "omniverse_id": str(params.omniverse_id),
            "name": params.name,
            "system_name": params.system_name,
            "description": params.description,
            "created_at": created_at.isoformat(),
        },
    )

    return MultiverseResponse(
        id=multiverse_id,
        omniverse_id=params.omniverse_id,
        name=params.name,
        system_name=params.system_name,
        description=params.description,
        created_at=created_at,
    )


def neo4j_get_multiverse(multiverse_id: UUID) -> Optional[MultiverseResponse]:
    """
    Get a Multiverse by ID.

    Authority: Any agent (read-only)
    Use Case: DL-1

    Args:
        multiverse_id: UUID of the multiverse

    Returns:
        MultiverseResponse if found, None otherwise
    """
    client = get_neo4j_client()

    query = """
    MATCH (m:Multiverse {id: $id})
    RETURN m
    """
    result = client.execute_read(query, {"id": str(multiverse_id)})

    if not result:
        return None

    m = result[0]["m"]
    return MultiverseResponse(
        id=UUID(m["id"]),
        omniverse_id=UUID(m["omniverse_id"]),
        name=m["name"],
        system_name=m["system_name"],
        description=m["description"],
        created_at=m["created_at"],
    )


# =============================================================================
# UNIVERSE OPERATIONS
# =============================================================================


def neo4j_create_universe(params: UniverseCreate) -> UniverseResponse:
    """
    Create a new Universe node.

    Authority: CanonKeeper only
    Use Case: DL-1, M-4

    Args:
        params: Universe creation parameters

    Returns:
        UniverseResponse with created universe data

    Raises:
        ValueError: If multiverse_id doesn't exist or validation fails
    """
    client = get_neo4j_client()

    # Verify multiverse exists
    verify_query = """
    MATCH (m:Multiverse {id: $multiverse_id})
    RETURN m.id as id
    """
    result = client.execute_read(
        verify_query, {"multiverse_id": str(params.multiverse_id)}
    )
    if not result:
        raise ValueError(f"Multiverse {params.multiverse_id} not found")

    # Create universe
    universe_id = uuid4()
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
        confidence: $confidence,
        authority: $authority,
        created_at: datetime($created_at)
    })
    CREATE (m)-[:CONTAINS]->(u)
    RETURN u
    """
    created_at = datetime.now(timezone.utc)
    client.execute_write(
        create_query,
        {
            "id": str(universe_id),
            "multiverse_id": str(params.multiverse_id),
            "name": params.name,
            "description": params.description,
            "genre": params.genre,
            "tone": params.tone,
            "tech_level": params.tech_level,
            "canon_level": params.canon_level.value,
            "confidence": params.confidence,
            "authority": params.authority.value,
            "created_at": created_at.isoformat(),
        },
    )

    return UniverseResponse(
        id=universe_id,
        multiverse_id=params.multiverse_id,
        name=params.name,
        description=params.description,
        genre=params.genre,
        tone=params.tone,
        tech_level=params.tech_level,
        canon_level=params.canon_level,
        confidence=params.confidence,
        authority=params.authority,
        created_at=created_at,
    )


def neo4j_get_universe(universe_id: UUID) -> Optional[UniverseResponse]:
    """
    Get a Universe by ID with full data including relationships.

    Authority: Any agent (read-only)
    Use Case: DL-1, M-6

    Args:
        universe_id: UUID of the universe

    Returns:
        UniverseResponse if found, None otherwise
    """
    client = get_neo4j_client()

    query = """
    MATCH (u:Universe {id: $id})
    RETURN u
    """
    result = client.execute_read(query, {"id": str(universe_id)})

    if not result:
        return None

    u = result[0]["u"]
    return UniverseResponse(
        id=UUID(u["id"]),
        multiverse_id=UUID(u["multiverse_id"]),
        name=u["name"],
        description=u["description"],
        genre=u.get("genre"),
        tone=u.get("tone"),
        tech_level=u.get("tech_level"),
        canon_level=u["canon_level"],
        confidence=u["confidence"],
        authority=u["authority"],
        created_at=u["created_at"],
    )


def neo4j_list_universes(
    filters: Optional[UniverseFilter] = None,
) -> List[UniverseResponse]:
    """
    List universes with optional filtering and pagination.

    Authority: Any agent (read-only)
    Use Case: DL-1, M-5

    Args:
        filters: Optional filter parameters (multiverse_id, canon_level, genre, limit, offset)

    Returns:
        List of UniverseResponse objects
    """
    client = get_neo4j_client()

    if filters is None:
        filters = UniverseFilter()

    # Build WHERE clause
    where_clauses = []
    params: Dict[str, Any] = {
        "limit": filters.limit,
        "offset": filters.offset,
    }

    if filters.multiverse_id:
        where_clauses.append("u.multiverse_id = $multiverse_id")
        params["multiverse_id"] = str(filters.multiverse_id)

    if filters.canon_level:
        where_clauses.append("u.canon_level = $canon_level")
        params["canon_level"] = filters.canon_level.value

    if filters.genre:
        where_clauses.append("u.genre = $genre")
        params["genre"] = filters.genre

    # NOTE: where_clauses must only contain static fragments with parameter
    # placeholders (e.g., "u.field = $param"). Do not concatenate raw user
    # input into this clause to avoid Cypher injection.
    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Build query without f-strings to keep interpolation of dynamic parts explicit
    query_lines = [
        "MATCH (u:Universe)",
    ]
    if where_clause:
        query_lines.append(where_clause)
    query_lines.extend(
        [
            "RETURN u",
            "ORDER BY u.created_at DESC",
            "SKIP $offset",
            "LIMIT $limit",
        ]
    )
    query = "\n".join(query_lines)

    result = client.execute_read(query, params)

    universes = []
    for record in result:
        u = record["u"]
        universes.append(
            UniverseResponse(
                id=UUID(u["id"]),
                multiverse_id=UUID(u["multiverse_id"]),
                name=u["name"],
                description=u["description"],
                genre=u.get("genre"),
                tone=u.get("tone"),
                tech_level=u.get("tech_level"),
                canon_level=u["canon_level"],
                confidence=u["confidence"],
                authority=u["authority"],
                created_at=u["created_at"],
            )
        )

    return universes


def neo4j_update_universe(
    universe_id: UUID, params: UniverseUpdate
) -> UniverseResponse:
    """
    Update mutable fields of a Universe.

    Authority: CanonKeeper only
    Use Case: DL-1, M-7

    Args:
        universe_id: UUID of the universe to update
        params: Update parameters (only mutable fields: name, description, genre, tone, tech_level)

    Returns:
        UniverseResponse with updated universe data

    Raises:
        ValueError: If universe doesn't exist
    """
    client = get_neo4j_client()

    # Verify universe exists
    verify_query = """
    MATCH (u:Universe {id: $id})
    RETURN u
    """
    result = client.execute_read(verify_query, {"id": str(universe_id)})
    if not result:
        raise ValueError(f"Universe {universe_id} not found")

    # Build SET clause for only provided fields
    set_clauses = []
    update_params: Dict[str, Any] = {"id": str(universe_id)}

    if params.name is not None:
        set_clauses.append("u.name = $name")
        update_params["name"] = params.name

    if params.description is not None:
        set_clauses.append("u.description = $description")
        update_params["description"] = params.description

    if params.genre is not None:
        set_clauses.append("u.genre = $genre")
        update_params["genre"] = params.genre

    if params.tone is not None:
        set_clauses.append("u.tone = $tone")
        update_params["tone"] = params.tone

    if params.tech_level is not None:
        set_clauses.append("u.tech_level = $tech_level")
        update_params["tech_level"] = params.tech_level

    if not set_clauses:
        # No updates, just return current state
        result = neo4j_get_universe(universe_id)
        if result is None:
            # This should not happen since we already verified universe exists
            raise ValueError(f"Universe {universe_id} not found after verification")
        return result

    set_clause = ", ".join(set_clauses)
    update_query = f"""
    MATCH (u:Universe {{id: $id}})
    SET {set_clause}
    RETURN u
    """

    result = client.execute_write(update_query, update_params)
    u = result[0]["u"]

    return UniverseResponse(
        id=UUID(u["id"]),
        multiverse_id=UUID(u["multiverse_id"]),
        name=u["name"],
        description=u["description"],
        genre=u.get("genre"),
        tone=u.get("tone"),
        tech_level=u.get("tech_level"),
        canon_level=u["canon_level"],
        confidence=u["confidence"],
        authority=u["authority"],
        created_at=u["created_at"],
    )


def neo4j_delete_universe(universe_id: UUID, force: bool = False) -> Dict[str, Any]:
    """
    Delete a Universe node.

    Authority: CanonKeeper only
    Use Case: DL-1, M-8

    Args:
        universe_id: UUID of the universe to delete
        force: If True, cascade delete all dependent data. If False, prevent deletion if dependencies exist.

    Returns:
        Dict with deletion status and details

    Raises:
        ValueError: If universe doesn't exist or has dependent data (when force=False)
    """
    client = get_neo4j_client()

    # Verify universe exists
    verify_query = """
    MATCH (u:Universe {id: $id})
    RETURN u
    """
    result = client.execute_read(verify_query, {"id": str(universe_id)})
    if not result:
        raise ValueError(f"Universe {universe_id} not found")

    if not force:
        # Check for dependent data
        dependency_query = """
        MATCH (u:Universe {id: $id})
        OPTIONAL MATCH (u)-[:HAS_SOURCE]->(s:Source)
        OPTIONAL MATCH (u)-[:HAS_AXIOM]->(a:Axiom)
        OPTIONAL MATCH (u)<-[:IN_UNIVERSE]-(e)
        WHERE e:EntityArchetype OR e:EntityInstance
        RETURN count(DISTINCT s) AS sources,
               count(DISTINCT a) AS axioms,
               count(DISTINCT e) AS entities
        """
        dep_result = client.execute_read(dependency_query, {"id": str(universe_id)})
        deps = dep_result[0]

        if deps["sources"] > 0 or deps["axioms"] > 0 or deps["entities"] > 0:
            raise ValueError(
                f"Universe {universe_id} has dependent data: "
                f"{deps['sources']} sources, {deps['axioms']} axioms, {deps['entities']} entities. "
                f"Use force=True to cascade delete."
            )

    # Delete universe (with cascade if force=True)
    if force:
        delete_query = """
        MATCH (u:Universe {id: $id})
        // Explicitly collect direct dependencies with depth limit
        OPTIONAL MATCH (u)-[:HAS_SOURCE]->(source:Source)
        OPTIONAL MATCH (u)-[:HAS_AXIOM]->(axiom:Axiom)
        OPTIONAL MATCH (u)-[:HAS_STORY]->(story:Story)
        // Collect story dependencies (1 level deep from Story)
        OPTIONAL MATCH (story)-[:HAS_SCENE]->(scene:Scene)
        OPTIONAL MATCH (story)-[:HAS_THREAD]->(thread:PlotThread)
        // Collect entities with IN_UNIVERSE relationship
        OPTIONAL MATCH (u)<-[:IN_UNIVERSE]-(entity)
        WHERE entity:EntityArchetype OR entity:EntityInstance
        // Collect and filter out nulls from OPTIONAL MATCH results
        WITH u, 
             [x IN collect(DISTINCT source) WHERE x IS NOT NULL] as sources,
             [x IN collect(DISTINCT axiom) WHERE x IS NOT NULL] as axioms,
             [x IN collect(DISTINCT story) WHERE x IS NOT NULL] as stories,
             [x IN collect(DISTINCT scene) WHERE x IS NOT NULL] as scenes,
             [x IN collect(DISTINCT thread) WHERE x IS NOT NULL] as threads,
             [x IN collect(DISTINCT entity) WHERE x IS NOT NULL] as entities
        // Flatten into single list
        WITH u, sources + axioms + stories + scenes + threads + entities AS dependents
        UNWIND dependents AS dependent
        // Final safety check: only delete expected node types
        WITH u, dependent
        WHERE dependent:Source OR dependent:Axiom OR dependent:Story OR 
              dependent:Scene OR dependent:PlotThread OR 
              dependent:EntityArchetype OR dependent:EntityInstance
        WITH collect(DISTINCT dependent) + u AS nodes
        UNWIND nodes AS n
        DETACH DELETE n
        RETURN count(DISTINCT n) as deleted_count
        """
    else:
        delete_query = """
        MATCH (u:Universe {id: $id})
        DETACH DELETE u
        RETURN count(u) as deleted_count
        """

    result = client.execute_write(delete_query, {"id": str(universe_id)})

    return {
        "universe_id": str(universe_id),
        "deleted": True,
        "force": force,
        "deleted_count": result[0]["deleted_count"],
    }


# =============================================================================
# OMNIVERSE OPERATIONS (Utility)
# =============================================================================


def neo4j_ensure_omniverse() -> Dict[str, Any]:
    """
    Ensure an Omniverse node exists (create if missing).

    This is typically called on first run to initialize the root node.
    Authority: CanonKeeper only

    Returns:
        Dict with omniverse_id and whether it was created
    """
    client = get_neo4j_client()

    # Check if omniverse exists
    check_query = """
    MATCH (o:Omniverse)
    RETURN o.id as id
    LIMIT 1
    """
    result = client.execute_read(check_query)

    if result:
        return {"omniverse_id": result[0]["id"], "created": False}

    # Create omniverse
    omniverse_id = uuid4()
    create_query = """
    CREATE (o:Omniverse {
        id: $id,
        name: $name,
        description: $description,
        created_at: datetime($created_at)
    })
    RETURN o.id as id
    """
    created_at = datetime.now(timezone.utc)
    client.execute_write(
        create_query,
        {
            "id": str(omniverse_id),
            "name": "MONITOR Omniverse",
            "description": "Root container for all multiverses and universes",
            "created_at": created_at.isoformat(),
        },
    )

    return {"omniverse_id": str(omniverse_id), "created": True}
