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
from monitor_data.schemas.base import CanonLevel, PartyStatus
from monitor_data.schemas.universe import (
    UniverseCreate,
    UniverseUpdate,
    UniverseResponse,
    UniverseFilter,
    MultiverseCreate,
    MultiverseResponse,
)
from monitor_data.schemas.entities import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntityFilter,
    EntityListResponse,
    StateTagsUpdate,
)
from monitor_data.schemas.facts import (
    FactCreate,
    FactUpdate,
    FactResponse,
    FactFilter,
    EventCreate,
    EventResponse,
    EventFilter,
)
from monitor_data.schemas.stories import (
    StoryCreate,
    StoryUpdate,
    StoryResponse,
    StoryFilter,
    StoryListResponse,
)
from monitor_data.schemas.story_outlines import (
    PlotThreadCreate,
    PlotThreadUpdate,
    PlotThreadResponse,
    PlotThreadFilter,
    PlotThreadListResponse,
    PlotThreadStatus,
    ThreadDeadline,
)
from monitor_data.schemas.parties import (
    PartyCreate,
    PartyResponse,
    PartyFilter,
    PartyMemberInfo,
    AddPartyMember,
    RemovePartyMember,
    SetActivePC,
)
from monitor_data.schemas.relationships import (
    RelationshipType,
    RelationshipCreate,
    RelationshipUpdate,
    RelationshipResponse,
    RelationshipFilter,
    RelationshipListResponse,
    StateTagUpdate,
    StateTagResponse,
    Direction,
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
    verify_result = client.execute_read(verify_query, {"id": str(universe_id)})
    if not verify_result:
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
        existing_universe = neo4j_get_universe(universe_id)
        if existing_universe is None:
            # This should not happen since we already verified universe exists
            raise ValueError(f"Universe {universe_id} not found after verification")
        return existing_universe

    set_clause = ", ".join(set_clauses)
    update_query = (
        "MATCH (u:Universe {id: $id})\n" "SET " + set_clause + "\n" "RETURN u"
    )

    write_result = client.execute_write(update_query, update_params)
    u = write_result[0]["u"]

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
        OPTIONAL MATCH (u)-[:HAS_STORY]->(st:Story)
        OPTIONAL MATCH (u)<-[:IN_UNIVERSE]-(e)
        WHERE e:EntityArchetype OR e:EntityInstance
        RETURN count(DISTINCT s) AS sources,
               count(DISTINCT a) AS axioms,
               count(DISTINCT st) AS stories,
               count(DISTINCT e) AS entities
        """
        dep_result = client.execute_read(dependency_query, {"id": str(universe_id)})
        deps = dep_result[0]

        if (
            deps["sources"] > 0
            or deps["axioms"] > 0
            or deps["stories"] > 0
            or deps["entities"] > 0
        ):
            raise ValueError(
                f"Universe {universe_id} has dependent data: "
                f"{deps['sources']} sources, {deps['axioms']} axioms, "
                f"{deps['stories']} stories, {deps['entities']} entities. "
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
        // Collect story dependencies (1 level deep from Story), matched from universe
        OPTIONAL MATCH (u)-[:HAS_STORY]->(:Story)-[:HAS_SCENE]->(scene:Scene)
        OPTIONAL MATCH (u)-[:HAS_STORY]->(:Story)-[:HAS_THREAD]->(thread:PlotThread)
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
        // Flatten into single list and filter to expected node types, always include universe
        WITH u, [x IN sources + axioms + stories + scenes + threads + entities
                 WHERE x:Source OR x:Axiom OR x:Story OR 
                       x:Scene OR x:PlotThread OR 
                       x:EntityArchetype OR x:EntityInstance] + [u] AS nodes
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


# =============================================================================
# ENTITY OPERATIONS (DL-2)
# =============================================================================


def neo4j_create_entity(params: EntityCreate) -> EntityResponse:
    """
    Create a new Entity node (EntityArchetype or EntityInstance).

    Authority: CanonKeeper only
    Use Case: DL-2

    Args:
        params: Entity creation parameters

    Returns:
        EntityResponse with created entity data

    Raises:
        ValueError: If universe_id doesn't exist, archetype_id is invalid, or validation fails
    """
    client = get_neo4j_client()

    # Verify universe exists
    verify_query = """
    MATCH (u:Universe {id: $universe_id})
    RETURN u.id as id
    """
    result = client.execute_read(verify_query, {"universe_id": str(params.universe_id)})
    if not result:
        raise ValueError(f"Universe {params.universe_id} not found")

    # Verify archetype exists if provided
    archetype_id_str = None
    if params.archetype_id:
        archetype_query = """
        MATCH (a:Entity {id: $archetype_id, is_archetype: true})
        RETURN a.id as id
        """
        archetype_result = client.execute_read(
            archetype_query, {"archetype_id": str(params.archetype_id)}
        )
        if not archetype_result:
            raise ValueError(f"Archetype {params.archetype_id} not found")
        archetype_id_str = str(params.archetype_id)

    # state_tags should only be on instances
    if params.is_archetype and params.state_tags:
        raise ValueError("state_tags cannot be set on EntityArchetype")

    # Create entity
    entity_id = uuid4()
    created_at = datetime.now(timezone.utc)

    # Base properties for all entities
    entity_props: Dict[str, Any] = {
        "id": str(entity_id),
        "universe_id": str(params.universe_id),
        "name": params.name,
        "entity_type": params.entity_type.value,
        "is_archetype": params.is_archetype,
        "description": params.description,
        "properties": params.properties,
        "canon_level": params.canon_level.value,
        "confidence": params.confidence,
        "authority": params.authority.value,
        "created_at": created_at.isoformat(),
    }

    # Add state_tags for instances; ensure archetypes also have an explicit (empty) list
    if not params.is_archetype:
        entity_props["state_tags"] = params.state_tags
        entity_props["updated_at"] = created_at.isoformat()
    else:
        entity_props["state_tags"] = []

    # Build creation query
    create_query = """
    MATCH (u:Universe {id: $universe_id})
    CREATE (e:Entity $entity_props)
    CREATE (u)-[:HAS_ENTITY]->(e)
    """

    # Add DERIVES_FROM relationship if archetype provided
    if archetype_id_str:
        create_query += """
        WITH e
        MATCH (a:Entity {id: $archetype_id})
        CREATE (e)-[:DERIVES_FROM]->(a)
        """

    create_query += "\nRETURN e"

    params_dict = {"universe_id": str(params.universe_id), "entity_props": entity_props}
    if archetype_id_str:
        params_dict["archetype_id"] = archetype_id_str

    result = client.execute_write(create_query, params_dict)
    e = result[0]["e"]

    return EntityResponse(
        id=UUID(e["id"]),
        universe_id=UUID(e["universe_id"]),
        name=e["name"],
        entity_type=e["entity_type"],
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(e["archetype_id"]) if e.get("archetype_id") else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"],
        updated_at=e.get("updated_at"),
    )


def neo4j_get_entity(entity_id: UUID) -> Optional[EntityResponse]:
    """
    Get an Entity by ID with relationships and state_tags.

    Authority: Any agent (read-only)
    Use Case: DL-2

    Args:
        entity_id: UUID of the entity

    Returns:
        EntityResponse if found, None otherwise
    """
    client = get_neo4j_client()

    query = """
    MATCH (e:Entity {id: $id})
    OPTIONAL MATCH (e)-[:DERIVES_FROM]->(a:Entity)
    RETURN e, a.id as archetype_id
    """
    result = client.execute_read(query, {"id": str(entity_id)})

    if not result:
        return None

    e = result[0]["e"]
    archetype_id = result[0].get("archetype_id")

    return EntityResponse(
        id=UUID(e["id"]),
        universe_id=UUID(e["universe_id"]),
        name=e["name"],
        entity_type=e["entity_type"],
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(archetype_id) if archetype_id else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"],
        updated_at=e.get("updated_at"),
    )


def neo4j_list_entities(filters: EntityFilter) -> EntityListResponse:
    """
    List entities with filtering, pagination, and sorting.

    Authority: Any agent (read-only)
    Use Case: DL-2

    Args:
        filters: Filter, pagination, and sorting parameters

    Returns:
        EntityListResponse with entities and pagination info
    """
    client = get_neo4j_client()

    # Build WHERE clause
    where_clauses = []
    params: Dict[str, Any] = {}

    if filters.universe_id:
        where_clauses.append("e.universe_id = $universe_id")
        params["universe_id"] = str(filters.universe_id)

    if filters.entity_type:
        where_clauses.append("e.entity_type = $entity_type")
        params["entity_type"] = filters.entity_type.value

    if filters.is_archetype is not None:
        where_clauses.append("e.is_archetype = $is_archetype")
        params["is_archetype"] = filters.is_archetype

    # State tags filter (AND logic - entity must have all specified tags)
    if filters.state_tags:
        for i, tag in enumerate(filters.state_tags):
            where_clauses.append(f"$tag{i} IN e.state_tags")
            params[f"tag{i}"] = tag

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Build ORDER BY clause
    sort_field_map = {"created_at": "e.created_at", "name": "e.name"}
    sort_field = sort_field_map.get(filters.sort_by, "e.created_at")
    sort_order = "DESC" if filters.sort_order == "desc" else "ASC"

    # Count total
    count_query = f"""
    MATCH (e:Entity)
    {where_clause}
    RETURN count(e) as total
    """
    count_result = client.execute_read(count_query, params)
    total = count_result[0]["total"]

    # Get entities with pagination
    list_query = f"""
    MATCH (e:Entity)
    {where_clause}
    OPTIONAL MATCH (e)-[:DERIVES_FROM]->(a:Entity)
    RETURN e, a.id as archetype_id
    ORDER BY {sort_field} {sort_order}
    SKIP $offset
    LIMIT $limit
    """
    params["offset"] = filters.offset
    params["limit"] = filters.limit

    result = client.execute_read(list_query, params)

    entities = []
    for record in result:
        e = record["e"]
        archetype_id = record.get("archetype_id")
        entities.append(
            EntityResponse(
                id=UUID(e["id"]),
                universe_id=UUID(e["universe_id"]),
                name=e["name"],
                entity_type=e["entity_type"],
                is_archetype=e["is_archetype"],
                description=e["description"],
                properties=e.get("properties", {}),
                state_tags=e.get("state_tags", []),
                archetype_id=UUID(archetype_id) if archetype_id else None,
                canon_level=e["canon_level"],
                confidence=e["confidence"],
                authority=e["authority"],
                created_at=e["created_at"],
                updated_at=e.get("updated_at"),
            )
        )

    return EntityListResponse(
        entities=entities, total=total, limit=filters.limit, offset=filters.offset
    )


def neo4j_update_entity(entity_id: UUID, params: EntityUpdate) -> EntityResponse:
    """
    Update an Entity's mutable fields.

    Authority: CanonKeeper only
    Use Case: DL-2

    Args:
        entity_id: UUID of the entity to update
        params: Update parameters

    Returns:
        EntityResponse with updated entity data

    Raises:
        ValueError: If entity doesn't exist
    """
    client = get_neo4j_client()

    # Verify entity exists
    verify_query = """
    MATCH (e:Entity {id: $id})
    RETURN e.id as id
    """
    result = client.execute_read(verify_query, {"id": str(entity_id)})
    if not result:
        raise ValueError(f"Entity {entity_id} not found")

    # Build SET clauses for updates
    set_clauses = ["e.updated_at = datetime($updated_at)"]
    update_params: Dict[str, Any] = {
        "id": str(entity_id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if params.name is not None:
        set_clauses.append("e.name = $name")
        update_params["name"] = params.name

    if params.description is not None:
        set_clauses.append("e.description = $description")
        update_params["description"] = params.description

    if params.properties is not None:
        set_clauses.append("e.properties = $properties")
        update_params["properties"] = params.properties

    if len(set_clauses) == 1:
        # Only updated_at would be set, so just return current state
        existing_entity = neo4j_get_entity(entity_id)
        if existing_entity is None:
            raise ValueError(f"Entity {entity_id} not found after verification")
        return existing_entity

    set_clause = ", ".join(set_clauses)
    update_query = f"""
    MATCH (e:Entity {{id: $id}})
    SET {set_clause}
    OPTIONAL MATCH (e)-[:DERIVES_FROM]->(a:Entity)
    RETURN e, a.id as archetype_id
    """

    write_result = client.execute_write(update_query, update_params)
    e = write_result[0]["e"]
    archetype_id = write_result[0].get("archetype_id")

    return EntityResponse(
        id=UUID(e["id"]),
        universe_id=UUID(e["universe_id"]),
        name=e["name"],
        entity_type=e["entity_type"],
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(archetype_id) if archetype_id else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"],
        updated_at=e.get("updated_at"),
    )


def neo4j_delete_entity(entity_id: UUID, force: bool = False) -> Dict[str, Any]:
    """
    Delete an Entity node.

    Authority: CanonKeeper only
    Use Case: DL-2

    Args:
        entity_id: UUID of the entity to delete
        force: If True, cascade delete relationships. If False, prevent deletion if dependencies exist.

    Returns:
        Dict with deletion status and details

    Raises:
        ValueError: If entity doesn't exist or has dependent data (when force=False)
    """
    client = get_neo4j_client()

    # Verify entity exists
    verify_query = """
    MATCH (e:Entity {id: $id})
    RETURN e.id as id
    """
    result = client.execute_read(verify_query, {"id": str(entity_id)})
    if not result:
        raise ValueError(f"Entity {entity_id} not found")

    if not force:
        # Check for dependent facts or events
        # Facts reference entities via INVOLVES or ABOUT relationships
        # Events also use similar patterns
        dependency_query = """
        MATCH (e:Entity {id: $id})
        OPTIONAL MATCH (f)-[:INVOLVES|ABOUT]->(e)
        WHERE f:Fact OR f:Event
        RETURN count(f) as dependent_count
        """
        dep_result = client.execute_read(dependency_query, {"id": str(entity_id)})
        dependent_count = dep_result[0]["dependent_count"]

        if dependent_count > 0:
            raise ValueError(
                f"Entity {entity_id} has {dependent_count} dependent facts/events. "
                "Use force=True to delete anyway."
            )

    # Delete entity and its relationships
    delete_query = """
    MATCH (e:Entity {id: $id})
    DETACH DELETE e
    """

    client.execute_write(delete_query, {"id": str(entity_id)})

    return {
        "entity_id": str(entity_id),
        "deleted": True,
        "forced": force,
    }


def neo4j_set_state_tags(entity_id: UUID, params: StateTagsUpdate) -> EntityResponse:
    """
    Atomically add/remove state tags on an EntityInstance.

    Authority: CanonKeeper only
    Use Case: DL-2

    Args:
        entity_id: UUID of the entity
        params: Tags to add and/or remove

    Returns:
        EntityResponse with updated entity data

    Raises:
        ValueError: If entity doesn't exist or is an archetype
    """
    client = get_neo4j_client()

    # Verify entity exists and is an instance
    verify_query = """
    MATCH (e:Entity {id: $id})
    RETURN e.is_archetype as is_archetype
    """
    result = client.execute_read(verify_query, {"id": str(entity_id)})
    if not result:
        raise ValueError(f"Entity {entity_id} not found")

    if result[0]["is_archetype"]:
        raise ValueError("Cannot set state_tags on EntityArchetype")

    # Build the update query
    update_parts = []
    update_params: Dict[str, Any] = {
        "id": str(entity_id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if params.remove_tags:
        update_parts.append(
            "e.state_tags = [tag IN e.state_tags WHERE NOT tag IN $remove_tags]"
        )
        update_params["remove_tags"] = params.remove_tags

    if params.add_tags:
        # Add tags, avoiding duplicates
        update_parts.append(
            "e.state_tags = e.state_tags + [tag IN $add_tags WHERE NOT tag IN e.state_tags]"
        )
        update_params["add_tags"] = params.add_tags

    if not update_parts:
        # No changes, return current state
        existing_entity = neo4j_get_entity(entity_id)
        if existing_entity is None:
            raise ValueError(f"Entity {entity_id} not found after verification")
        return existing_entity

    update_parts.append("e.updated_at = datetime($updated_at)")

    update_query = f"""
    MATCH (e:Entity {{id: $id}})
    SET {', '.join(update_parts)}
    OPTIONAL MATCH (e)-[:DERIVES_FROM]->(a:Entity)
    RETURN e, a.id as archetype_id
    """

    write_result = client.execute_write(update_query, update_params)
    e = write_result[0]["e"]
    archetype_id = write_result[0].get("archetype_id")

    return EntityResponse(
        id=UUID(e["id"]),
        universe_id=UUID(e["universe_id"]),
        name=e["name"],
        entity_type=e["entity_type"],
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(archetype_id) if archetype_id else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"],
        updated_at=e.get("updated_at"),
    )


# =============================================================================
# FACT OPERATIONS
# =============================================================================


def neo4j_create_fact(params: FactCreate) -> FactResponse:
    """
    Create a new Fact node with provenance and entity relationships.

    Authority: CanonKeeper only
    Use Case: DL-3

    Args:
        params: Fact creation parameters

    Returns:
        FactResponse with created fact data

    Raises:
        ValueError: If universe_id doesn't exist or entity references are invalid
    """
    client = get_neo4j_client()

    # Verify universe exists
    verify_query = """
    MATCH (u:Universe {id: $universe_id})
    RETURN u.id as id
    """
    result = client.execute_read(verify_query, {"universe_id": str(params.universe_id)})
    if not result:
        raise ValueError(f"Universe {params.universe_id} not found")

    # Verify entity references if provided
    if params.entity_ids:
        entity_check_query = """
        MATCH (e {id: $entity_id})
        WHERE e:EntityArchetype OR e:EntityInstance
        RETURN e.id as id
        """
        for entity_id in params.entity_ids:
            result = client.execute_read(
                entity_check_query, {"entity_id": str(entity_id)}
            )
            if not result:
                raise ValueError(f"Entity {entity_id} not found")

    # Verify source references if provided
    if params.source_ids:
        source_check_query = """
        MATCH (s:Source {id: $source_id})
        RETURN s.id as id
        """
        for source_id in params.source_ids:
            result = client.execute_read(
                source_check_query, {"source_id": str(source_id)}
            )
            if not result:
                raise ValueError(f"Source {source_id} not found")

    # Verify scene references if provided
    if params.scene_ids:
        scene_check_query = """
        MATCH (sc:Scene {id: $scene_id})
        RETURN sc.id as id
        """
        for scene_id in params.scene_ids:
            result = client.execute_read(scene_check_query, {"scene_id": str(scene_id)})
            if not result:
                raise ValueError(f"Scene {scene_id} not found")

    # Verify replaces reference if provided
    if params.replaces:
        replaces_check_query = """
        MATCH (old:Fact {id: $replaces_id})
        RETURN old.id as id
        """
        result = client.execute_read(
            replaces_check_query, {"replaces_id": str(params.replaces)}
        )
        if not result:
            raise ValueError(f"Fact to replace {params.replaces} not found")

    # Create fact node
    fact_id = uuid4()
    created_at = datetime.now(timezone.utc)

    create_query = """
    MATCH (u:Universe {id: $universe_id})
    CREATE (f:Fact {
        id: $id,
        universe_id: $universe_id,
        statement: $statement,
        fact_type: $fact_type,
        time_ref: CASE WHEN $time_ref IS NOT NULL THEN datetime($time_ref) ELSE null END,
        duration: $duration,
        canon_level: $canon_level,
        confidence: $confidence,
        authority: $authority,
        created_at: datetime($created_at),
        replaces: $replaces,
        properties: $properties
    })
    CREATE (u)-[:HAS_FACT]->(f)
    RETURN f
    """

    client.execute_write(
        create_query,
        {
            "id": str(fact_id),
            "universe_id": str(params.universe_id),
            "statement": params.statement,
            "fact_type": params.fact_type.value,
            "time_ref": params.time_ref.isoformat() if params.time_ref else None,
            "duration": params.duration,
            "canon_level": params.canon_level.value,
            "confidence": params.confidence,
            "authority": params.authority.value,
            "created_at": created_at.isoformat(),
            "replaces": str(params.replaces) if params.replaces else None,
            "properties": params.properties,
        },
    )

    # Create INVOLVES edges to entities
    if params.entity_ids:
        entity_edge_query = """
        MATCH (f:Fact {id: $fact_id})
        MATCH (e {id: $entity_id})
        WHERE e:EntityArchetype OR e:EntityInstance
        CREATE (f)-[:INVOLVES]->(e)
        """
        for entity_id in params.entity_ids:
            client.execute_write(
                entity_edge_query,
                {"fact_id": str(fact_id), "entity_id": str(entity_id)},
            )

    # Create SUPPORTED_BY edges to sources
    if params.source_ids:
        source_edge_query = """
        MATCH (f:Fact {id: $fact_id})
        MATCH (s:Source {id: $source_id})
        CREATE (f)-[:SUPPORTED_BY]->(s)
        """
        for source_id in params.source_ids:
            client.execute_write(
                source_edge_query,
                {"fact_id": str(fact_id), "source_id": str(source_id)},
            )

    # Create SUPPORTED_BY edges to scenes
    if params.scene_ids:
        scene_edge_query = """
        MATCH (f:Fact {id: $fact_id})
        MATCH (sc:Scene {id: $scene_id})
        CREATE (f)-[:SUPPORTED_BY]->(sc)
        """
        for scene_id in params.scene_ids:
            client.execute_write(
                scene_edge_query,
                {"fact_id": str(fact_id), "scene_id": str(scene_id)},
            )

    # Create REPLACES edge if this retcons another fact
    if params.replaces:
        replaces_edge_query = """
        MATCH (f:Fact {id: $fact_id})
        MATCH (old:Fact {id: $replaces_id})
        CREATE (f)-[:REPLACES]->(old)
        SET old.canon_level = $retconned_level
        """
        client.execute_write(
            replaces_edge_query,
            {
                "fact_id": str(fact_id),
                "replaces_id": str(params.replaces),
                "retconned_level": CanonLevel.RETCONNED.value,
            },
        )

    # Retrieve with relationships
    fact = neo4j_get_fact(fact_id)
    if fact is None:
        raise ValueError(f"Failed to retrieve created fact {fact_id}")
    return fact


def neo4j_get_fact(fact_id: UUID) -> Optional[FactResponse]:
    """
    Get a Fact by ID with all relationships and provenance chain.

    Authority: Any agent (read-only)
    Use Case: DL-3

    Args:
        fact_id: UUID of the fact

    Returns:
        FactResponse if found, None otherwise
    """
    client = get_neo4j_client()

    query = """
    MATCH (f:Fact {id: $id})
    OPTIONAL MATCH (f)-[:INVOLVES]->(e)
    WHERE e:EntityArchetype OR e:EntityInstance
    OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(s:Source)
    OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(sc:Scene)
    RETURN f,
           collect(DISTINCT e.id) as entity_ids,
           collect(DISTINCT s.id) as source_ids,
           collect(DISTINCT sc.id) as scene_ids
    """
    result = client.execute_read(query, {"id": str(fact_id)})

    if not result:
        return None

    record = result[0]
    f = record["f"]

    return FactResponse(
        id=UUID(f["id"]),
        universe_id=UUID(f["universe_id"]),
        statement=f["statement"],
        fact_type=f["fact_type"],
        time_ref=f.get("time_ref"),
        duration=f.get("duration"),
        canon_level=f["canon_level"],
        confidence=f["confidence"],
        authority=f["authority"],
        created_at=f["created_at"],
        replaces=UUID(f["replaces"]) if f.get("replaces") else None,
        properties=f.get("properties"),
        entity_ids=[UUID(eid) for eid in record["entity_ids"] if eid],
        source_ids=[UUID(sid) for sid in record["source_ids"] if sid],
        snippet_ids=[],  # Snippets not stored in Neo4j
        scene_ids=[UUID(scid) for scid in record["scene_ids"] if scid],
    )


def neo4j_list_facts(filters: Optional[FactFilter] = None) -> List[FactResponse]:
    """
    List facts with optional filtering and pagination.

    Authority: Any agent (read-only)
    Use Case: DL-3

    Args:
        filters: Optional filter parameters

    Returns:
        List of FactResponse objects
    """
    client = get_neo4j_client()

    if filters is None:
        filters = FactFilter()  # type: ignore[call-arg]

    # Build WHERE clause
    where_clauses = []
    params: Dict[str, Any] = {
        "limit": filters.limit,
        "offset": filters.offset,
    }

    if filters.universe_id:
        where_clauses.append("f.universe_id = $universe_id")
        params["universe_id"] = str(filters.universe_id)

    if filters.fact_type:
        where_clauses.append("f.fact_type = $fact_type")
        params["fact_type"] = filters.fact_type.value

    if filters.canon_level:
        where_clauses.append("f.canon_level = $canon_level")
        params["canon_level"] = filters.canon_level.value

    # Handle entity filter separately
    if filters.entity_id:
        # When filtering by entity, we need to match the INVOLVES relationship
        # and combine it with other filters using AND
        where_clauses.insert(0, "e.id = $entity_id")
        where_clause = "WHERE " + " AND ".join(where_clauses)

        query = f"""
        MATCH (f:Fact)-[:INVOLVES]->(e)
        {where_clause}
        OPTIONAL MATCH (f)-[:INVOLVES]->(e2)
        WHERE e2:EntityArchetype OR e2:EntityInstance
        OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(s:Source)
        OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(sc:Scene)
        RETURN f,
               collect(DISTINCT e2.id) as entity_ids,
               collect(DISTINCT s.id) as source_ids,
               collect(DISTINCT sc.id) as scene_ids
        ORDER BY f.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        params["entity_id"] = str(filters.entity_id)
    else:
        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        query = f"""
        MATCH (f:Fact)
        {where_clause}
        OPTIONAL MATCH (f)-[:INVOLVES]->(e)
        WHERE e:EntityArchetype OR e:EntityInstance
        OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(s:Source)
        OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(sc:Scene)
        RETURN f,
               collect(DISTINCT e.id) as entity_ids,
               collect(DISTINCT s.id) as source_ids,
               collect(DISTINCT sc.id) as scene_ids
        ORDER BY f.created_at DESC
        SKIP $offset
        LIMIT $limit
        """

    results = client.execute_read(query, params)

    facts = []
    for record in results:
        f = record["f"]
        facts.append(
            FactResponse(
                id=UUID(f["id"]),
                universe_id=UUID(f["universe_id"]),
                statement=f["statement"],
                fact_type=f["fact_type"],
                time_ref=f.get("time_ref"),
                duration=f.get("duration"),
                canon_level=f["canon_level"],
                confidence=f["confidence"],
                authority=f["authority"],
                created_at=f["created_at"],
                replaces=UUID(f["replaces"]) if f.get("replaces") else None,
                properties=f.get("properties"),
                entity_ids=[UUID(eid) for eid in record["entity_ids"] if eid],
                source_ids=[UUID(sid) for sid in record["source_ids"] if sid],
                snippet_ids=[],
                scene_ids=[UUID(scid) for scid in record["scene_ids"] if scid],
            )
        )

    return facts


def neo4j_update_fact(fact_id: UUID, params: FactUpdate) -> FactResponse:
    """
    Update a Fact's mutable fields.

    Authority: CanonKeeper only
    Use Case: DL-3

    Args:
        fact_id: UUID of the fact to update
        params: Update parameters

    Returns:
        FactResponse with updated fact data

    Raises:
        ValueError: If fact doesn't exist
    """
    client = get_neo4j_client()

    # Verify fact exists
    verify_query = """
    MATCH (f:Fact {id: $id})
    RETURN f
    """
    result = client.execute_read(verify_query, {"id": str(fact_id)})
    if not result:
        raise ValueError(f"Fact {fact_id} not found")

    # Build SET clause for only provided fields
    set_clauses = []
    update_params: Dict[str, Any] = {"id": str(fact_id)}

    if params.statement is not None:
        set_clauses.append("f.statement = $statement")
        update_params["statement"] = params.statement

    if params.canon_level is not None:
        set_clauses.append("f.canon_level = $canon_level")
        update_params["canon_level"] = params.canon_level.value

    if params.confidence is not None:
        set_clauses.append("f.confidence = $confidence")
        update_params["confidence"] = params.confidence

    if params.properties is not None:
        set_clauses.append("f.properties = $properties")
        update_params["properties"] = params.properties

    if not set_clauses:
        # No updates, just return current state
        existing_fact = neo4j_get_fact(fact_id)
        if existing_fact is None:
            raise ValueError(f"Fact {fact_id} not found after verification")
        return existing_fact

    set_clause = ", ".join(set_clauses)
    update_query = f"""
    MATCH (f:Fact {{id: $id}})
    SET {set_clause}
    RETURN f
    """

    client.execute_write(update_query, update_params)

    # Retrieve updated fact with relationships
    updated_fact = neo4j_get_fact(fact_id)
    if updated_fact is None:
        raise ValueError(f"Fact {fact_id} not found after update")
    return updated_fact


def neo4j_delete_fact(fact_id: UUID, force: bool = False) -> Dict[str, Any]:
    """
    Delete a Fact node.

    Authority: CanonKeeper only
    Use Case: DL-3

    Args:
        fact_id: UUID of the fact to delete
        force: If True, allow deletion of canon facts. If False, prevent deletion of canon facts.

    Returns:
        Dict with deletion status

    Raises:
        ValueError: If fact doesn't exist or is canon (when force=False)
    """
    client = get_neo4j_client()

    # Verify fact exists
    verify_query = """
    MATCH (f:Fact {id: $id})
    RETURN f.canon_level as canon_level
    """
    result = client.execute_read(verify_query, {"id": str(fact_id)})
    if not result:
        raise ValueError(f"Fact {fact_id} not found")

    canon_level = result[0]["canon_level"]

    # Prevent deletion of canon facts unless force=True
    if canon_level == CanonLevel.CANON.value and not force:
        raise ValueError(
            f"Cannot delete canon fact {fact_id} without force=True. "
            "Canon facts must be explicitly retconned before deletion."
        )

    # Delete fact and all relationships
    delete_query = """
    MATCH (f:Fact {id: $id})
    DETACH DELETE f
    """
    client.execute_write(delete_query, {"id": str(fact_id)})

    return {
        "fact_id": str(fact_id),
        "deleted": True,
        "canon_level": canon_level,
        "forced": force,
    }


# =============================================================================
# EVENT OPERATIONS
# =============================================================================


def neo4j_create_event(params: EventCreate) -> EventResponse:
    """
    Create a new Event node with temporal properties and timeline edges.

    Authority: CanonKeeper only
    Use Case: DL-3

    Args:
        params: Event creation parameters

    Returns:
        EventResponse with created event data

    Raises:
        ValueError: If universe_id doesn't exist or entity/scene references are invalid
    """
    client = get_neo4j_client()

    # Verify universe exists
    verify_query = """
    MATCH (u:Universe {id: $universe_id})
    RETURN u.id as id
    """
    result = client.execute_read(verify_query, {"universe_id": str(params.universe_id)})
    if not result:
        raise ValueError(f"Universe {params.universe_id} not found")

    # Verify scene if provided
    if params.scene_id:
        scene_check_query = """
        MATCH (sc:Scene {id: $scene_id})
        RETURN sc.id as id
        """
        result = client.execute_read(
            scene_check_query, {"scene_id": str(params.scene_id)}
        )
        if not result:
            raise ValueError(f"Scene {params.scene_id} not found")

    # Verify entity references if provided
    if params.entity_ids:
        entity_check_query = """
        MATCH (e {id: $entity_id})
        WHERE e:EntityArchetype OR e:EntityInstance
        RETURN e.id as id
        """
        for entity_id in params.entity_ids:
            result = client.execute_read(
                entity_check_query, {"entity_id": str(entity_id)}
            )
            if not result:
                raise ValueError(f"Entity {entity_id} not found")

    # Verify source references if provided
    if params.source_ids:
        source_check_query = """
        MATCH (s:Source {id: $source_id})
        RETURN s.id as id
        """
        for source_id in params.source_ids:
            result = client.execute_read(
                source_check_query, {"source_id": str(source_id)}
            )
            if not result:
                raise ValueError(f"Source {source_id} not found")

    # Verify timeline_after event references if provided
    if params.timeline_after:
        event_check_query = """
        MATCH (ev:Event {id: $event_id})
        RETURN ev.id as id
        """
        for after_id in params.timeline_after:
            result = client.execute_read(event_check_query, {"event_id": str(after_id)})
            if not result:
                raise ValueError(f"Timeline after event {after_id} not found")

    # Verify timeline_before event references if provided
    if params.timeline_before:
        event_check_query = """
        MATCH (ev:Event {id: $event_id})
        RETURN ev.id as id
        """
        for before_id in params.timeline_before:
            result = client.execute_read(
                event_check_query, {"event_id": str(before_id)}
            )
            if not result:
                raise ValueError(f"Timeline before event {before_id} not found")

    # Verify causes event references if provided
    if params.causes:
        event_check_query = """
        MATCH (ev:Event {id: $event_id})
        RETURN ev.id as id
        """
        for caused_id in params.causes:
            result = client.execute_read(
                event_check_query, {"event_id": str(caused_id)}
            )
            if not result:
                raise ValueError(f"Caused event {caused_id} not found")

    # Create event node
    event_id = uuid4()
    created_at = datetime.now(timezone.utc)

    create_query = """
    MATCH (u:Universe {id: $universe_id})
    CREATE (ev:Event {
        id: $id,
        universe_id: $universe_id,
        scene_id: $scene_id,
        title: $title,
        description: $description,
        start_time: datetime($start_time),
        end_time: CASE WHEN $end_time IS NOT NULL THEN datetime($end_time) ELSE null END,
        severity: $severity,
        canon_level: $canon_level,
        confidence: $confidence,
        authority: $authority,
        created_at: datetime($created_at),
        properties: $properties
    })
    CREATE (u)-[:HAS_EVENT]->(ev)
    RETURN ev
    """

    client.execute_write(
        create_query,
        {
            "id": str(event_id),
            "universe_id": str(params.universe_id),
            "scene_id": str(params.scene_id) if params.scene_id else None,
            "title": params.title,
            "description": params.description,
            "start_time": params.start_time.isoformat(),
            "end_time": params.end_time.isoformat() if params.end_time else None,
            "severity": params.severity,
            "canon_level": params.canon_level.value,
            "confidence": params.confidence,
            "authority": params.authority.value,
            "created_at": created_at.isoformat(),
            "properties": params.properties,
        },
    )

    # Create INVOLVES edges to entities
    if params.entity_ids:
        entity_edge_query = """
        MATCH (ev:Event {id: $event_id})
        MATCH (e {id: $entity_id})
        WHERE e:EntityArchetype OR e:EntityInstance
        CREATE (ev)-[:INVOLVES]->(e)
        """
        for entity_id in params.entity_ids:
            client.execute_write(
                entity_edge_query,
                {"event_id": str(event_id), "entity_id": str(entity_id)},
            )

    # Create SUPPORTED_BY edges to sources
    if params.source_ids:
        source_edge_query = """
        MATCH (ev:Event {id: $event_id})
        MATCH (s:Source {id: $source_id})
        CREATE (ev)-[:SUPPORTED_BY]->(s)
        """
        for source_id in params.source_ids:
            client.execute_write(
                source_edge_query,
                {"event_id": str(event_id), "source_id": str(source_id)},
            )

    # Create timeline edges (AFTER)
    if params.timeline_after:
        for after_id in params.timeline_after:
            after_edge_query = """
            MATCH (ev1:Event {id: $event_id})
            MATCH (ev2:Event {id: $after_id})
            CREATE (ev1)-[:AFTER]->(ev2)
            """
            client.execute_write(
                after_edge_query,
                {"event_id": str(event_id), "after_id": str(after_id)},
            )

    # Create timeline edges (BEFORE)
    if params.timeline_before:
        for before_id in params.timeline_before:
            before_edge_query = """
            MATCH (ev1:Event {id: $event_id})
            MATCH (ev2:Event {id: $before_id})
            CREATE (ev1)-[:BEFORE]->(ev2)
            """
            client.execute_write(
                before_edge_query,
                {"event_id": str(event_id), "before_id": str(before_id)},
            )

    # Create CAUSES edges
    if params.causes:
        for caused_id in params.causes:
            causes_edge_query = """
            MATCH (ev1:Event {id: $event_id})
            MATCH (ev2:Event {id: $caused_id})
            CREATE (ev1)-[:CAUSES]->(ev2)
            """
            client.execute_write(
                causes_edge_query,
                {"event_id": str(event_id), "caused_id": str(caused_id)},
            )

    # Retrieve with relationships
    event = neo4j_get_event(event_id)
    if event is None:
        raise ValueError(f"Failed to retrieve created event {event_id}")
    return event


def neo4j_get_event(event_id: UUID) -> Optional[EventResponse]:
    """
    Get an Event by ID with all relationships.

    Authority: Any agent (read-only)
    Use Case: DL-3

    Args:
        event_id: UUID of the event

    Returns:
        EventResponse if found, None otherwise
    """
    client = get_neo4j_client()

    query = """
    MATCH (ev:Event {id: $id})
    OPTIONAL MATCH (ev)-[:INVOLVES]->(e)
    WHERE e:EntityArchetype OR e:EntityInstance
    OPTIONAL MATCH (ev)-[:SUPPORTED_BY]->(s:Source)
    OPTIONAL MATCH (ev)-[:AFTER]->(after:Event)
    OPTIONAL MATCH (ev)-[:BEFORE]->(before:Event)
    OPTIONAL MATCH (ev)-[:CAUSES]->(caused:Event)
    RETURN ev,
           collect(DISTINCT e.id) as entity_ids,
           collect(DISTINCT s.id) as source_ids,
           collect(DISTINCT after.id) as timeline_after,
           collect(DISTINCT before.id) as timeline_before,
           collect(DISTINCT caused.id) as causes
    """
    result = client.execute_read(query, {"id": str(event_id)})

    if not result:
        return None

    record = result[0]
    ev = record["ev"]

    return EventResponse(
        id=UUID(ev["id"]),
        universe_id=UUID(ev["universe_id"]),
        scene_id=UUID(ev["scene_id"]) if ev.get("scene_id") else None,
        title=ev["title"],
        description=ev.get("description"),
        start_time=ev["start_time"],
        end_time=ev.get("end_time"),
        severity=ev["severity"],
        canon_level=ev["canon_level"],
        confidence=ev["confidence"],
        authority=ev["authority"],
        created_at=ev["created_at"],
        properties=ev.get("properties"),
        entity_ids=[UUID(eid) for eid in record["entity_ids"] if eid],
        source_ids=[UUID(sid) for sid in record["source_ids"] if sid],
        timeline_after=[UUID(aid) for aid in record["timeline_after"] if aid],
        timeline_before=[UUID(bid) for bid in record["timeline_before"] if bid],
        causes=[UUID(cid) for cid in record["causes"] if cid],
    )


def neo4j_list_events(filters: Optional[EventFilter] = None) -> List[EventResponse]:
    """
    List events with optional filtering and pagination.

    Authority: Any agent (read-only)
    Use Case: DL-3

    Args:
        filters: Optional filter parameters

    Returns:
        List of EventResponse objects
    """
    client = get_neo4j_client()

    if filters is None:
        filters = EventFilter()  # type: ignore[call-arg]

    # Build WHERE clause
    where_clauses = []
    params: Dict[str, Any] = {
        "limit": filters.limit,
        "offset": filters.offset,
    }

    if filters.universe_id:
        where_clauses.append("ev.universe_id = $universe_id")
        params["universe_id"] = str(filters.universe_id)

    if filters.scene_id:
        where_clauses.append("ev.scene_id = $scene_id")
        params["scene_id"] = str(filters.scene_id)

    if filters.canon_level:
        where_clauses.append("ev.canon_level = $canon_level")
        params["canon_level"] = filters.canon_level.value

    if filters.start_after:
        where_clauses.append("ev.start_time >= datetime($start_after)")
        params["start_after"] = filters.start_after.isoformat()

    if filters.start_before:
        where_clauses.append("ev.start_time <= datetime($start_before)")
        params["start_before"] = filters.start_before.isoformat()

    # Handle entity filter separately
    if filters.entity_id:
        # When filtering by entity, we need to match the INVOLVES relationship
        # and combine it with other filters using AND
        where_clauses.insert(0, "e.id = $entity_id")
        where_clause = "WHERE " + " AND ".join(where_clauses)

        query = f"""
        MATCH (ev:Event)-[:INVOLVES]->(e)
        {where_clause}
        OPTIONAL MATCH (ev)-[:INVOLVES]->(e2)
        WHERE e2:EntityArchetype OR e2:EntityInstance
        OPTIONAL MATCH (ev)-[:SUPPORTED_BY]->(s:Source)
        OPTIONAL MATCH (ev)-[:AFTER]->(after:Event)
        OPTIONAL MATCH (ev)-[:BEFORE]->(before:Event)
        OPTIONAL MATCH (ev)-[:CAUSES]->(caused:Event)
        RETURN ev,
               collect(DISTINCT e2.id) as entity_ids,
               collect(DISTINCT s.id) as source_ids,
               collect(DISTINCT after.id) as timeline_after,
               collect(DISTINCT before.id) as timeline_before,
               collect(DISTINCT caused.id) as causes
        ORDER BY ev.start_time DESC
        SKIP $offset
        LIMIT $limit
        """
        params["entity_id"] = str(filters.entity_id)
    else:
        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        query = f"""
        MATCH (ev:Event)
        {where_clause}
        OPTIONAL MATCH (ev)-[:INVOLVES]->(e)
        WHERE e:EntityArchetype OR e:EntityInstance
        OPTIONAL MATCH (ev)-[:SUPPORTED_BY]->(s:Source)
        OPTIONAL MATCH (ev)-[:AFTER]->(after:Event)
        OPTIONAL MATCH (ev)-[:BEFORE]->(before:Event)
        OPTIONAL MATCH (ev)-[:CAUSES]->(caused:Event)
        RETURN ev,
               collect(DISTINCT e.id) as entity_ids,
               collect(DISTINCT s.id) as source_ids,
               collect(DISTINCT after.id) as timeline_after,
               collect(DISTINCT before.id) as timeline_before,
               collect(DISTINCT caused.id) as causes
        ORDER BY ev.start_time DESC
        SKIP $offset
        LIMIT $limit
        """

    results = client.execute_read(query, params)

    events = []
    for record in results:
        ev = record["ev"]
        events.append(
            EventResponse(
                id=UUID(ev["id"]),
                universe_id=UUID(ev["universe_id"]),
                scene_id=UUID(ev["scene_id"]) if ev.get("scene_id") else None,
                title=ev["title"],
                description=ev.get("description"),
                start_time=ev["start_time"],
                end_time=ev.get("end_time"),
                severity=ev["severity"],
                canon_level=ev["canon_level"],
                confidence=ev["confidence"],
                authority=ev["authority"],
                created_at=ev["created_at"],
                properties=ev.get("properties"),
                entity_ids=[UUID(eid) for eid in record["entity_ids"] if eid],
                source_ids=[UUID(sid) for sid in record["source_ids"] if sid],
                timeline_after=[UUID(aid) for aid in record["timeline_after"] if aid],
                timeline_before=[UUID(bid) for bid in record["timeline_before"] if bid],
                causes=[UUID(cid) for cid in record["causes"] if cid],
            )
        )

    return events


# =============================================================================
# STORY OPERATIONS
# =============================================================================


def neo4j_create_story(params: StoryCreate) -> StoryResponse:
    """
    Create a new Story node linked to universe.

    Authority: CanonKeeper, Orchestrator
    Use Case: DL-4

    Args:
        params: Story creation parameters

    Returns:
        StoryResponse with created story data

    Raises:
        ValueError: If universe_id doesn't exist or pc_ids are invalid
    """
    client = get_neo4j_client()

    # Verify universe exists
    verify_query = """
    MATCH (u:Universe {id: $universe_id})
    RETURN u.id as id
    """
    result = client.execute_read(verify_query, {"universe_id": str(params.universe_id)})
    if not result:
        raise ValueError(f"Universe {params.universe_id} not found")

    # Verify player character entity IDs if provided
    if params.pc_ids:
        entity_check_query = """
        MATCH (e {id: $entity_id})
        WHERE e:EntityArchetype OR e:EntityInstance
        RETURN e.id as id
        """
        for pc_id in params.pc_ids:
            result = client.execute_read(entity_check_query, {"entity_id": str(pc_id)})
            if not result:
                raise ValueError(f"Player character entity {pc_id} not found")

    # Create story
    story_id = uuid4()
    created_at = datetime.now(timezone.utc)

    create_query = """
    MATCH (u:Universe {id: $universe_id})
    CREATE (s:Story {
        id: $id,
        universe_id: $universe_id,
        title: $title,
        story_type: $story_type,
        theme: $theme,
        premise: $premise,
        status: $status,
        start_time_ref: datetime($start_time_ref),
        created_at: datetime($created_at)
    })
    CREATE (u)-[:HAS_STORY]->(s)
    RETURN s
    """
    create_params = {
        "id": str(story_id),
        "universe_id": str(params.universe_id),
        "title": params.title,
        "story_type": params.story_type.value,
        "theme": params.theme,
        "premise": params.premise,
        "status": params.status.value,
        "start_time_ref": (
            params.start_time_ref.isoformat() if params.start_time_ref else None
        ),
        "created_at": created_at.isoformat(),
    }

    result = client.execute_write(create_query, create_params)
    s = result[0]["s"]

    # Create PARTICIPATES edges for player characters
    if params.pc_ids:
        for pc_id in params.pc_ids:
            pc_edge_query = """
            MATCH (s:Story {id: $story_id})
            MATCH (pc {id: $pc_id})
            WHERE pc:EntityArchetype OR pc:EntityInstance
            CREATE (pc)-[:PARTICIPATES]->(s)
            """
            client.execute_write(
                pc_edge_query, {"story_id": str(story_id), "pc_id": str(pc_id)}
            )

    return StoryResponse(
        id=UUID(s["id"]),
        universe_id=UUID(s["universe_id"]),
        title=s["title"],
        story_type=s["story_type"],
        theme=s["theme"],
        premise=s["premise"],
        status=s["status"],
        start_time_ref=s.get("start_time_ref"),
        end_time_ref=s.get("end_time_ref"),
        created_at=s["created_at"],
        completed_at=s.get("completed_at"),
        scene_count=0,
        pc_ids=params.pc_ids,
    )


def neo4j_get_story(story_id: UUID) -> Optional[StoryResponse]:
    """
    Retrieve a Story by ID with scene count and participant list.

    Authority: All agents
    Use Case: DL-4

    Args:
        story_id: UUID of the story to retrieve

    Returns:
        StoryResponse if found, None otherwise
    """
    client = get_neo4j_client()

    query = """
    MATCH (s:Story {id: $id})
    OPTIONAL MATCH (s)-[:HAS_SCENE]->(sc:Scene)
    OPTIONAL MATCH (pc)-[:PARTICIPATES]->(s)
    WHERE pc:EntityArchetype OR pc:EntityInstance
    RETURN s,
           count(DISTINCT sc) as scene_count,
           collect(DISTINCT pc.id) as pc_ids
    """

    result = client.execute_read(query, {"id": str(story_id)})
    if not result:
        return None

    record = result[0]
    s = record["s"]
    scene_count = record.get("scene_count", 0)
    pc_ids = [UUID(pc_id) for pc_id in record.get("pc_ids", []) if pc_id]

    return StoryResponse(
        id=UUID(s["id"]),
        universe_id=UUID(s["universe_id"]),
        title=s["title"],
        story_type=s["story_type"],
        theme=s["theme"],
        premise=s["premise"],
        status=s["status"],
        start_time_ref=s.get("start_time_ref"),
        end_time_ref=s.get("end_time_ref"),
        created_at=s["created_at"],
        completed_at=s.get("completed_at"),
        scene_count=scene_count,
        pc_ids=pc_ids,
    )


def neo4j_update_story(story_id: UUID, params: StoryUpdate) -> StoryResponse:
    """
    Update a Story's mutable fields with status transition enforcement.

    Authority: CanonKeeper only
    Use Case: DL-4

    Valid status transitions: planned → active → completed/abandoned

    Args:
        story_id: UUID of the story to update
        params: Fields to update

    Returns:
        StoryResponse with updated story data

    Raises:
        ValueError: If story doesn't exist or invalid status transition
    """
    from monitor_data.schemas.base import StoryStatus

    client = get_neo4j_client()

    # Verify story exists and get current status
    verify_query = """
    MATCH (s:Story {id: $id})
    RETURN s
    """
    result = client.execute_read(verify_query, {"id": str(story_id)})
    if not result:
        raise ValueError(f"Story {story_id} not found")

    current_story = result[0]["s"]

    # Validate status transition if status is being updated
    if params.status is not None:
        current_status = StoryStatus(current_story["status"])
        new_status = params.status

        # Define valid transitions
        valid_transitions = {
            StoryStatus.PLANNED: [StoryStatus.ACTIVE, StoryStatus.ABANDONED],
            StoryStatus.ACTIVE: [StoryStatus.COMPLETED, StoryStatus.ABANDONED],
            StoryStatus.COMPLETED: [],  # No transitions from completed
            StoryStatus.ABANDONED: [],  # No transitions from abandoned
        }

        if new_status != current_status:
            if new_status not in valid_transitions.get(current_status, []):
                raise ValueError(
                    f"Invalid status transition from {current_status.value} to {new_status.value}. "
                    f"Valid transitions: {[s.value for s in valid_transitions.get(current_status, [])]}"
                )

    # Build update query dynamically
    set_clauses = []
    update_params = {"id": str(story_id)}

    if params.title is not None:
        set_clauses.append("s.title = $title")
        update_params["title"] = params.title

    if params.theme is not None:
        set_clauses.append("s.theme = $theme")
        update_params["theme"] = params.theme

    if params.premise is not None:
        set_clauses.append("s.premise = $premise")
        update_params["premise"] = params.premise

    if params.status is not None:
        set_clauses.append("s.status = $status")
        update_params["status"] = params.status.value
        # If completing the story, set completed_at
        if params.status.value == "completed":
            set_clauses.append("s.completed_at = datetime($completed_at)")
            update_params["completed_at"] = datetime.now(timezone.utc).isoformat()

    if not set_clauses:
        # No updates, just return current state
        existing_story = neo4j_get_story(story_id)
        if existing_story is None:
            raise ValueError(f"Story {story_id} not found after verification")
        return existing_story

    set_clause = ", ".join(set_clauses)
    update_query = "MATCH (s:Story {id: $id})\n" "SET " + set_clause + "\n" "RETURN s"

    client.execute_write(update_query, update_params)

    # Get scene count and participants
    story_data = neo4j_get_story(story_id)
    if story_data is None:
        raise ValueError(f"Story {story_id} not found after update")

    return story_data


def neo4j_list_stories(params: StoryFilter) -> StoryListResponse:
    """
    List stories with filtering, sorting, and pagination.

    Authority: All agents
    Use Case: DL-4

    Args:
        params: Filter and pagination parameters

    Returns:
        StoryListResponse with list of stories and pagination info
    """
    client = get_neo4j_client()

    # Build WHERE clauses
    where_clauses = []
    query_params: Dict[str, Any] = {}

    if params.universe_id is not None:
        where_clauses.append("s.universe_id = $universe_id")
        query_params["universe_id"] = str(params.universe_id)

    if params.story_type is not None:
        where_clauses.append("s.story_type = $story_type")
        query_params["story_type"] = params.story_type.value

    if params.status is not None:
        where_clauses.append("s.status = $status")
        query_params["status"] = params.status.value

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Build ORDER BY clause
    sort_field = (
        params.sort_by if params.sort_by in ["created_at", "title"] else "created_at"
    )
    sort_order = "DESC" if params.sort_order == "desc" else "ASC"
    order_clause = f"ORDER BY s.{sort_field} {sort_order}"

    # Count query
    count_query = f"""
    MATCH (s:Story)
    {where_clause}
    RETURN count(s) as total
    """
    count_result = client.execute_read(count_query, query_params)
    total = count_result[0]["total"]

    # List query with pagination
    query_params["limit"] = params.limit
    query_params["offset"] = params.offset

    list_query = f"""
    MATCH (s:Story)
    {where_clause}
    OPTIONAL MATCH (s)-[:HAS_SCENE]->(sc:Scene)
    OPTIONAL MATCH (pc)-[:PARTICIPATES]->(s)
    WHERE pc:EntityArchetype OR pc:EntityInstance
    WITH s, count(DISTINCT sc) as scene_count, collect(DISTINCT pc.id) as pc_ids
    {order_clause}
    SKIP $offset
    LIMIT $limit
    RETURN s, scene_count, pc_ids
    """

    results = client.execute_read(list_query, query_params)

    stories = []
    for record in results:
        s = record["s"]
        scene_count = record["scene_count"]
        pc_ids = [UUID(pc_id) for pc_id in record["pc_ids"] if pc_id]

        stories.append(
            StoryResponse(
                id=UUID(s["id"]),
                universe_id=UUID(s["universe_id"]),
                title=s["title"],
                story_type=s["story_type"],
                theme=s["theme"],
                premise=s["premise"],
                status=s["status"],
                start_time_ref=s.get("start_time_ref"),
                end_time_ref=s.get("end_time_ref"),
                created_at=s["created_at"],
                completed_at=s.get("completed_at"),
                scene_count=scene_count,
                pc_ids=pc_ids,
            )
        )

    return StoryListResponse(
        stories=stories, total=total, limit=params.limit, offset=params.offset
    )


# =============================================================================
# PLOT THREAD OPERATIONS (DL-6)
# =============================================================================


def neo4j_create_plot_thread(params: PlotThreadCreate) -> PlotThreadResponse:
    """
    Create a plot thread with relationships (DL-6).

    Creates PlotThread node and relationships:
    - (:Story)-[:HAS_THREAD]->(:PlotThread)
    - (:PlotThread)-[:ADVANCED_BY]->(:Scene) for each scene_id
    - (:PlotThread)-[:INVOLVES]->(:EntityInstance) for each entity_id
    - (:Event)-[:FORESHADOWS]->(:PlotThread) for each foreshadowing_event
    - (:Event)-[:REVEALS]->(:PlotThread) for each revelation_event

    Authority: CanonKeeper
    Use Case: P-1, ST-1

    Args:
        params: Plot thread creation parameters

    Returns:
        Created plot thread

    Raises:
        ValueError: If story doesn't exist or referenced nodes not found
    """
    client = get_neo4j_client()

    # Verify story exists
    verify_query = "MATCH (s:Story {id: $story_id}) RETURN s.id as id"
    result = client.execute_read(verify_query, {"story_id": str(params.story_id)})
    if not result:
        raise ValueError(f"Story {params.story_id} not found")

    # Generate ID and prepare data
    thread_id = uuid4()
    now = datetime.now(timezone.utc)

    # Build create query with relationships
    create_query = """
    MATCH (s:Story {id: $story_id})
    CREATE (t:PlotThread {
        id: $id,
        story_id: $story_id,
        title: $title,
        thread_type: $thread_type,
        status: $status,
        priority: $priority,
        urgency: $urgency,
        deadline: $deadline,
        payoff_status: $payoff_status,
        player_interest_level: $player_interest_level,
        gm_importance: $gm_importance,
        created_at: datetime($created_at),
        updated_at: datetime($updated_at),
        resolved_at: $resolved_at
    })
    CREATE (s)-[:HAS_THREAD]->(t)
    RETURN t
    """

    query_params = {
        "id": str(thread_id),
        "story_id": str(params.story_id),
        "title": params.title,
        "thread_type": params.thread_type.value,
        "status": params.status.value,
        "priority": params.priority.value,
        "urgency": params.urgency.value,
        "deadline": (
            params.deadline.model_dump(mode="json") if params.deadline else None
        ),
        "payoff_status": params.payoff_status.value,
        "player_interest_level": params.player_interest_level,
        "gm_importance": params.gm_importance,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "resolved_at": None,
    }

    # Create node
    client.execute_write(create_query, query_params)

    # Create ADVANCED_BY relationships to scenes
    if params.scene_ids:
        for scene_id in params.scene_ids:
            scene_rel_query = """
            MATCH (t:PlotThread {id: $thread_id})
            MATCH (sc:Scene {id: $scene_id})
            MERGE (t)-[:ADVANCED_BY]->(sc)
            """
            client.execute_write(
                scene_rel_query,
                {"thread_id": str(thread_id), "scene_id": str(scene_id)},
            )

    # Create INVOLVES relationships to entities
    if params.entity_ids:
        for entity_id in params.entity_ids:
            entity_rel_query = """
            MATCH (t:PlotThread {id: $thread_id})
            MATCH (e {id: $entity_id})
            WHERE e:EntityArchetype OR e:EntityInstance
            MERGE (t)-[:INVOLVES]->(e)
            """
            client.execute_write(
                entity_rel_query,
                {"thread_id": str(thread_id), "entity_id": str(entity_id)},
            )

    # Create FORESHADOWS relationships
    if params.foreshadowing_events:
        for event_id in params.foreshadowing_events:
            foreshadow_query = """
            MATCH (t:PlotThread {id: $thread_id})
            MATCH (e:Event {id: $event_id})
            MERGE (e)-[:FORESHADOWS]->(t)
            """
            client.execute_write(
                foreshadow_query,
                {"thread_id": str(thread_id), "event_id": str(event_id)},
            )

    # Create REVEALS relationships
    if params.revelation_events:
        for event_id in params.revelation_events:
            reveal_query = """
            MATCH (t:PlotThread {id: $thread_id})
            MATCH (e:Event {id: $event_id})
            MERGE (e)-[:REVEALS]->(t)
            """
            client.execute_write(
                reveal_query,
                {"thread_id": str(thread_id), "event_id": str(event_id)},
            )

    # Return the created thread
    return neo4j_get_plot_thread(thread_id)  # type: ignore


def neo4j_get_plot_thread(id: UUID) -> Optional[PlotThreadResponse]:
    """
    Get a plot thread by ID with all relationships (DL-6).

    Authority: All agents
    Use Case: ST-1, CF-3

    Args:
        id: Plot thread UUID

    Returns:
        Plot thread or None if not found
    """
    client = get_neo4j_client()

    query = """
    MATCH (t:PlotThread {id: $id})
    OPTIONAL MATCH (t)-[:ADVANCED_BY]->(sc:Scene)
    OPTIONAL MATCH (t)-[:INVOLVES]->(e)
    WHERE (e:EntityArchetype OR e:EntityInstance)
    OPTIONAL MATCH (fe:Event)-[:FORESHADOWS]->(t)
    OPTIONAL MATCH (re:Event)-[:REVEALS]->(t)
    RETURN t,
           collect(DISTINCT sc.id) as scene_ids,
           collect(DISTINCT e.id) as entity_ids,
           collect(DISTINCT fe.id) as foreshadowing_event_ids,
           collect(DISTINCT re.id) as revelation_event_ids
    """

    results = client.execute_read(query, {"id": str(id)})
    if not results:
        return None

    record = results[0]
    t = record["t"]
    scene_ids = [UUID(sid) for sid in record["scene_ids"] if sid]
    entity_ids = [UUID(eid) for eid in record["entity_ids"] if eid]
    foreshadowing_events = [
        UUID(fid) for fid in record["foreshadowing_event_ids"] if fid
    ]
    revelation_events = [UUID(rid) for rid in record["revelation_event_ids"] if rid]

    # Parse deadline if present
    deadline = None
    if t.get("deadline"):
        deadline_data = t["deadline"]
        deadline = ThreadDeadline(
            world_time=deadline_data["world_time"],
            description=deadline_data["description"],
        )

    return PlotThreadResponse(
        id=UUID(t["id"]),
        story_id=UUID(t["story_id"]),
        title=t["title"],
        thread_type=t["thread_type"],
        status=t["status"],
        priority=t["priority"],
        urgency=t["urgency"],
        deadline=deadline,
        payoff_status=t["payoff_status"],
        player_interest_level=t["player_interest_level"],
        gm_importance=t["gm_importance"],
        scene_ids=scene_ids,
        entity_ids=entity_ids,
        foreshadowing_events=foreshadowing_events,
        revelation_events=revelation_events,
        created_at=t["created_at"],
        updated_at=t["updated_at"],
        resolved_at=t.get("resolved_at"),
    )


def neo4j_update_plot_thread(id: UUID, params: PlotThreadUpdate) -> PlotThreadResponse:
    """
    Update a plot thread and add relationships (DL-6).

    Note: Relationships are additive only (no removal) to preserve history.
    Status transitions are validated.

    Authority: CanonKeeper
    Use Case: P-8, ST-1, CF-3

    Args:
        id: Plot thread UUID
        params: Update parameters

    Returns:
        Updated plot thread

    Raises:
        ValueError: If thread not found or invalid status transition
    """
    client = get_neo4j_client()

    # Get existing thread
    existing = neo4j_get_plot_thread(id)
    if not existing:
        raise ValueError(f"Plot thread {id} not found")

    # Validate status transition if status is being updated
    if params.status:
        current_status = PlotThreadStatus(existing.status)
        new_status = params.status

        # Valid transitions
        valid_transitions = {
            PlotThreadStatus.OPEN: [
                PlotThreadStatus.ADVANCED,
                PlotThreadStatus.RESOLVED,
                PlotThreadStatus.ABANDONED,
            ],
            PlotThreadStatus.ADVANCED: [
                PlotThreadStatus.RESOLVED,
                PlotThreadStatus.ABANDONED,
            ],
            PlotThreadStatus.RESOLVED: [],
            PlotThreadStatus.ABANDONED: [],
        }

        if new_status not in valid_transitions[current_status]:
            raise ValueError(
                f"Invalid status transition from {current_status.value} to {new_status.value}"
            )

    # Build update query
    update_parts = ["t.updated_at = datetime($updated_at)"]
    query_params: Dict[str, Any] = {
        "id": str(id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if params.title is not None:
        update_parts.append("t.title = $title")
        query_params["title"] = params.title

    if params.status is not None:
        update_parts.append("t.status = $status")
        query_params["status"] = params.status.value
        # Set resolved_at if transitioning to resolved
        if params.status == PlotThreadStatus.RESOLVED:
            update_parts.append("t.resolved_at = datetime($resolved_at)")
            query_params["resolved_at"] = datetime.now(timezone.utc).isoformat()

    if params.priority is not None:
        update_parts.append("t.priority = $priority")
        query_params["priority"] = params.priority.value

    if params.urgency is not None:
        update_parts.append("t.urgency = $urgency")
        query_params["urgency"] = params.urgency.value

    if params.deadline is not None:
        update_parts.append("t.deadline = $deadline")
        query_params["deadline"] = params.deadline.model_dump(mode="json")

    if params.payoff_status is not None:
        update_parts.append("t.payoff_status = $payoff_status")
        query_params["payoff_status"] = params.payoff_status.value

    if params.player_interest_level is not None:
        update_parts.append("t.player_interest_level = $player_interest_level")
        query_params["player_interest_level"] = params.player_interest_level

    if params.gm_importance is not None:
        update_parts.append("t.gm_importance = $gm_importance")
        query_params["gm_importance"] = params.gm_importance

    # Update node properties
    update_query = f"""
    MATCH (t:PlotThread {{id: $id}})
    SET {', '.join(update_parts)}
    RETURN t
    """
    client.execute_write(update_query, query_params)

    # Add new scene relationships
    if params.add_scene_ids:
        for scene_id in params.add_scene_ids:
            scene_rel_query = """
            MATCH (t:PlotThread {id: $thread_id})
            MATCH (sc:Scene {id: $scene_id})
            MERGE (t)-[:ADVANCED_BY]->(sc)
            """
            client.execute_write(
                scene_rel_query, {"thread_id": str(id), "scene_id": str(scene_id)}
            )

    # Add new entity relationships
    if params.add_entity_ids:
        for entity_id in params.add_entity_ids:
            entity_rel_query = """
            MATCH (t:PlotThread {id: $thread_id})
            MATCH (e {id: $entity_id})
            WHERE e:EntityArchetype OR e:EntityInstance
            MERGE (t)-[:INVOLVES]->(e)
            """
            client.execute_write(
                entity_rel_query, {"thread_id": str(id), "entity_id": str(entity_id)}
            )

    # Add foreshadowing events
    if params.add_foreshadowing_events:
        for event_id in params.add_foreshadowing_events:
            foreshadow_query = """
            MATCH (t:PlotThread {id: $thread_id})
            MATCH (e:Event {id: $event_id})
            MERGE (e)-[:FORESHADOWS]->(t)
            """
            client.execute_write(
                foreshadow_query, {"thread_id": str(id), "event_id": str(event_id)}
            )

    # Add revelation events
    if params.add_revelation_events:
        for event_id in params.add_revelation_events:
            reveal_query = """
            MATCH (t:PlotThread {id: $thread_id})
            MATCH (e:Event {id: $event_id})
            MERGE (e)-[:REVEALS]->(t)
            """
            client.execute_write(
                reveal_query, {"thread_id": str(id), "event_id": str(event_id)}
            )

    # Return updated thread
    updated = neo4j_get_plot_thread(id)
    if not updated:
        raise ValueError(f"Plot thread {id} not found after update")

    return updated


def neo4j_list_plot_threads(params: PlotThreadFilter) -> PlotThreadListResponse:
    """
    List plot threads with filtering (DL-6).

    Supports filtering by:
    - story_id
    - thread_type
    - status
    - priority
    - entity_id (threads involving this entity)

    Authority: All agents
    Use Case: ST-1, CF-3

    Args:
        params: Filter parameters

    Returns:
        List of plot threads with pagination
    """
    client = get_neo4j_client()

    # Build WHERE clause
    where_clauses = []
    query_params: Dict[str, Any] = {}

    if params.story_id:
        where_clauses.append("t.story_id = $story_id")
        query_params["story_id"] = str(params.story_id)

    if params.thread_type:
        where_clauses.append("t.thread_type = $thread_type")
        query_params["thread_type"] = params.thread_type.value

    if params.status:
        where_clauses.append("t.status = $status")
        query_params["status"] = params.status.value

    if params.priority:
        where_clauses.append("t.priority = $priority")
        query_params["priority"] = params.priority.value

    # Entity filter requires additional MATCH
    entity_match = ""
    if params.entity_id:
        entity_match = """
        MATCH (t)-[:INVOLVES]->(involved_entity {id: $entity_id})
        """
        query_params["entity_id"] = str(params.entity_id)

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Count total
    count_query = f"""
    MATCH (t:PlotThread)
    {entity_match}
    {where_clause}
    RETURN count(t) as total
    """
    count_result = client.execute_read(count_query, query_params)
    total = count_result[0]["total"] if count_result else 0

    # Determine sort field
    sort_field_map = {
        "created_at": "t.created_at",
        "updated_at": "t.updated_at",
        "priority": "t.priority",
        "urgency": "t.urgency",
    }
    sort_field = sort_field_map.get(params.sort_by, "t.created_at")
    sort_order = "DESC" if params.sort_order == "desc" else "ASC"

    # List query with relationships
    list_query = f"""
    MATCH (t:PlotThread)
    {entity_match}
    {where_clause}
    OPTIONAL MATCH (t)-[:ADVANCED_BY]->(sc:Scene)
    OPTIONAL MATCH (t)-[:INVOLVES]->(e)
    WHERE e:EntityArchetype OR e:EntityInstance
    OPTIONAL MATCH (fe:Event)-[:FORESHADOWS]->(t)
    OPTIONAL MATCH (re:Event)-[:REVEALS]->(t)
    RETURN t,
           collect(DISTINCT sc.id) as scene_ids,
           collect(DISTINCT e.id) as entity_ids,
           collect(DISTINCT fe.id) as foreshadowing_event_ids,
           collect(DISTINCT re.id) as revelation_event_ids
    ORDER BY {sort_field} {sort_order}
    SKIP $offset
    LIMIT $limit
    """

    query_params["offset"] = params.offset
    query_params["limit"] = params.limit

    results = client.execute_read(list_query, query_params)

    threads = []
    for record in results:
        t = record["t"]
        scene_ids = [UUID(sid) for sid in record["scene_ids"] if sid]
        entity_ids = [UUID(eid) for eid in record["entity_ids"] if eid]
        foreshadowing_events = [
            UUID(fid) for fid in record["foreshadowing_event_ids"] if fid
        ]
        revelation_events = [UUID(rid) for rid in record["revelation_event_ids"] if rid]

        # Parse deadline if present
        deadline = None
        if t.get("deadline"):
            deadline_data = t["deadline"]
            deadline = ThreadDeadline(
                world_time=deadline_data["world_time"],
                description=deadline_data["description"],
            )

        threads.append(
            PlotThreadResponse(
                id=UUID(t["id"]),
                story_id=UUID(t["story_id"]),
                title=t["title"],
                thread_type=t["thread_type"],
                status=t["status"],
                priority=t["priority"],
                urgency=t["urgency"],
                deadline=deadline,
                payoff_status=t["payoff_status"],
                player_interest_level=t["player_interest_level"],
                gm_importance=t["gm_importance"],
                scene_ids=scene_ids,
                entity_ids=entity_ids,
                foreshadowing_events=foreshadowing_events,
                revelation_events=revelation_events,
                created_at=t["created_at"],
                updated_at=t["updated_at"],
                resolved_at=t.get("resolved_at"),
            )
        )

    return PlotThreadListResponse(
        threads=threads, total=total, limit=params.limit, offset=params.offset
    )


# =============================================================================
# PARTY OPERATIONS (DL-15)
# =============================================================================


def neo4j_create_party(params: PartyCreate) -> PartyResponse:
    """
    Create a new Party node.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-15

    Args:
        params: Party creation parameters

    Returns:
        PartyResponse with created party data

    Raises:
        ValueError: If story_id doesn't exist or initial_member_ids invalid
    """
    client = get_neo4j_client()

    # Verify story exists
    verify_query = """
    MATCH (s:Story {id: $story_id})
    RETURN s.id as id
    """
    result = client.execute_read(verify_query, {"story_id": str(params.story_id)})
    if not result:
        raise ValueError(f"Story {params.story_id} not found")

    # Verify initial members are EntityInstances of type CHARACTER if provided
    if params.initial_member_ids:
        verify_members_query = """
        MATCH (e:EntityInstance)
        WHERE e.id IN $member_ids AND e.entity_type = 'character'
        RETURN collect(e.id) as valid_ids
        """
        member_result = client.execute_read(
            verify_members_query,
            {"member_ids": [str(eid) for eid in params.initial_member_ids]},
        )
        valid_ids = member_result[0]["valid_ids"] if member_result else []
        if len(valid_ids) != len(params.initial_member_ids):
            raise ValueError(
                "All initial_member_ids must be EntityInstance nodes of type CHARACTER"
            )

    # Verify active_pc_id is in initial_member_ids if both are provided
    if (
        params.active_pc_id
        and params.initial_member_ids
        and params.active_pc_id not in params.initial_member_ids
    ):
        raise ValueError("active_pc_id must be one of the initial_member_ids")

    # Create party
    party_id = uuid4()
    now = datetime.now(timezone.utc)
    create_query = """
    MATCH (s:Story {id: $story_id})
    CREATE (p:Party {
        id: $id,
        story_id: $story_id,
        name: $name,
        status: $status,
        active_pc_id: $active_pc_id,
        location_id: $location_id,
        formation: $formation,
        created_at: $created_at,
        updated_at: $updated_at
    })
    CREATE (s)-[:HAS_PARTY]->(p)
    RETURN p
    """

    create_params = {
        "story_id": str(params.story_id),
        "id": str(party_id),
        "name": params.name,
        "status": params.status.value,
        "active_pc_id": str(params.active_pc_id) if params.active_pc_id else None,
        "location_id": str(params.location_id) if params.location_id else None,
        "formation": [str(eid) for eid in params.formation],
        "created_at": now,
        "updated_at": now,
    }

    result = client.execute_write(create_query, create_params)
    if not result:
        raise ValueError("Failed to create party")

    # Add initial members
    members = []
    if params.initial_member_ids:
        for idx, entity_id in enumerate(params.initial_member_ids):
            member_query = """
            MATCH (e:EntityInstance {id: $entity_id})
            MATCH (p:Party {id: $party_id})
            CREATE (e)-[r:MEMBER_OF {
                role: $role,
                position: $position,
                joined_at: $joined_at
            }]->(p)
            RETURN e.id as entity_id, r
            """
            member_params = {
                "entity_id": str(entity_id),
                "party_id": str(party_id),
                "role": None,
                "position": idx,
                "joined_at": now,
            }
            member_result = client.execute_write(member_query, member_params)
            if not member_result:
                raise ValueError(
                    f"Failed to add initial member {entity_id} to party - entity may not exist"
                )
            r = member_result[0]["r"]
            members.append(
                PartyMemberInfo(
                    entity_id=entity_id,
                    role=r.get("role"),
                    position=r.get("position"),
                    joined_at=r["joined_at"],
                )
            )

    return PartyResponse(
        id=party_id,
        story_id=params.story_id,
        name=params.name,
        status=params.status,
        active_pc_id=params.active_pc_id,
        location_id=params.location_id,
        formation=params.formation,
        members=members,
        created_at=now,
        updated_at=now,
    )


def neo4j_get_party(party_id: UUID) -> Optional[PartyResponse]:
    """
    Get a party by ID with all members.

    Authority: All
    Use Case: DL-15

    Args:
        party_id: Party UUID

    Returns:
        PartyResponse if found, None otherwise
    """
    client = get_neo4j_client()

    query = """
    MATCH (p:Party {id: $party_id})
    OPTIONAL MATCH (e:EntityInstance)-[r:MEMBER_OF]->(p)
    RETURN p,
           collect({
               entity_id: e.id,
               role: r.role,
               position: r.position,
               joined_at: r.joined_at
           }) as members
    """

    result = client.execute_read(query, {"party_id": str(party_id)})

    if not result:
        return None

    p = result[0]["p"]
    member_data = result[0]["members"]

    # Filter out null entries from OPTIONAL MATCH
    members = []
    for m in member_data:
        if m.get("entity_id"):
            members.append(
                PartyMemberInfo(
                    entity_id=UUID(m["entity_id"]),
                    role=m.get("role"),
                    position=m.get("position"),
                    joined_at=m["joined_at"],
                )
            )

    # Parse formation
    formation = [UUID(eid) for eid in p.get("formation", [])]

    return PartyResponse(
        id=UUID(p["id"]),
        story_id=UUID(p["story_id"]),
        name=p["name"],
        status=p["status"],
        active_pc_id=UUID(p["active_pc_id"]) if p.get("active_pc_id") else None,
        location_id=UUID(p["location_id"]) if p.get("location_id") else None,
        formation=formation,
        members=members,
        created_at=p["created_at"],
        updated_at=p.get("updated_at"),
    )


def neo4j_list_parties(params: PartyFilter = PartyFilter()) -> List[PartyResponse]:
    """
    List parties with optional filtering.

    Authority: All
    Use Case: DL-15

    Args:
        params: Filter parameters

    Returns:
        List of parties
    """
    client = get_neo4j_client()

    # Build WHERE clause
    where_clauses = []
    query_params: Dict[str, Any] = {}

    if params.story_id:
        where_clauses.append("p.story_id = $story_id")
        query_params["story_id"] = str(params.story_id)

    if params.status:
        where_clauses.append("p.status = $status")
        query_params["status"] = params.status

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query = f"""
    MATCH (p:Party)
    {where_clause}
    OPTIONAL MATCH (e:EntityInstance)-[r:MEMBER_OF]->(p)
    RETURN p,
           collect({{
               entity_id: e.id,
               role: r.role,
               position: r.position,
               joined_at: r.joined_at
           }}) as members
    ORDER BY p.created_at DESC
    SKIP $offset
    LIMIT $limit
    """

    query_params["offset"] = params.offset
    query_params["limit"] = params.limit

    results = client.execute_read(query, query_params)

    parties = []
    for record in results:
        p = record["p"]
        member_data = record["members"]

        # Filter out null entries
        members = []
        for m in member_data:
            if m.get("entity_id"):
                members.append(
                    PartyMemberInfo(
                        entity_id=UUID(m["entity_id"]),
                        role=m.get("role"),
                        position=m.get("position"),
                        joined_at=m["joined_at"],
                    )
                )

        formation = [UUID(eid) for eid in p.get("formation", [])]

        parties.append(
            PartyResponse(
                id=UUID(p["id"]),
                story_id=UUID(p["story_id"]),
                name=p["name"],
                status=p["status"],
                active_pc_id=UUID(p["active_pc_id"]) if p.get("active_pc_id") else None,
                location_id=UUID(p["location_id"]) if p.get("location_id") else None,
                formation=formation,
                members=members,
                created_at=p["created_at"],
                updated_at=p.get("updated_at"),
            )
        )

    return parties


def neo4j_add_party_member(params: AddPartyMember) -> PartyResponse:
    """
    Add a member to a party.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-15

    Args:
        params: Member addition parameters

    Returns:
        Updated PartyResponse

    Raises:
        ValueError: If party or entity not found, or entity not a character
    """
    client = get_neo4j_client()

    # Verify party exists
    party = neo4j_get_party(params.party_id)
    if not party:
        raise ValueError(f"Party {params.party_id} not found")

    # Verify entity is a character
    verify_query = """
    MATCH (e:EntityInstance {id: $entity_id})
    WHERE e.entity_type = 'character'
    RETURN e.id as id
    """
    result = client.execute_read(verify_query, {"entity_id": str(params.entity_id)})
    if not result:
        raise ValueError(f"Entity {params.entity_id} not found or not a character type")

    # Add member
    now = datetime.now(timezone.utc)
    add_query = """
    MATCH (e:EntityInstance {id: $entity_id})
    MATCH (p:Party {id: $party_id})
    MERGE (e)-[r:MEMBER_OF]->(p)
    SET r.role = $role,
        r.position = $position,
        r.joined_at = COALESCE(r.joined_at, $joined_at),
        p.updated_at = $updated_at
    RETURN r
    """

    add_params = {
        "entity_id": str(params.entity_id),
        "party_id": str(params.party_id),
        "role": params.role,
        "position": params.position,
        "joined_at": now,
        "updated_at": now,
    }

    client.execute_write(add_query, add_params)

    # Return updated party
    updated_party = neo4j_get_party(params.party_id)
    if updated_party is None:
        raise ValueError(f"Party {params.party_id} not found after update")
    return updated_party


def neo4j_remove_party_member(params: RemovePartyMember) -> PartyResponse:
    """
    Remove a member from a party.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-15

    Args:
        params: Member removal parameters

    Returns:
        Updated PartyResponse

    Raises:
        ValueError: If party not found
    """
    client = get_neo4j_client()

    # Verify party exists
    party = neo4j_get_party(params.party_id)
    if not party:
        raise ValueError(f"Party {params.party_id} not found")

    # Remove member and clean up active_pc_id and formation
    now = datetime.now(timezone.utc)
    remove_query = """
    MATCH (e:EntityInstance {id: $entity_id})-[r:MEMBER_OF]->(p:Party {id: $party_id})
    DELETE r
    WITH p, $entity_id as removed_id
    SET p.updated_at = $updated_at,
        p.active_pc_id = CASE
            WHEN p.active_pc_id = removed_id THEN null
            ELSE p.active_pc_id
        END,
        p.formation = [id IN p.formation WHERE id <> removed_id]
    RETURN p
    """

    remove_params = {
        "entity_id": str(params.entity_id),
        "party_id": str(params.party_id),
        "updated_at": now,
    }

    client.execute_write(remove_query, remove_params)

    # Return updated party
    updated_party = neo4j_get_party(params.party_id)
    if updated_party is None:
        raise ValueError(f"Party {params.party_id} not found after update")
    return updated_party


def neo4j_set_active_pc(params: SetActivePC) -> PartyResponse:
    """
    Set the active PC for a party.

    Authority: Orchestrator
    Use Case: DL-15

    Args:
        params: Active PC parameters

    Returns:
        Updated PartyResponse

    Raises:
        ValueError: If party not found or entity not a member
    """
    client = get_neo4j_client()

    # Verify party exists and entity is a member
    party = neo4j_get_party(params.party_id)
    if not party:
        raise ValueError(f"Party {params.party_id} not found")

    member_ids = {m.entity_id for m in party.members}
    if params.entity_id not in member_ids:
        raise ValueError(
            f"Entity {params.entity_id} is not a member of party {params.party_id}"
        )

    # Update active PC
    now = datetime.now(timezone.utc)
    update_query = """
    MATCH (p:Party {id: $party_id})
    SET p.active_pc_id = $active_pc_id,
        p.updated_at = $updated_at
    RETURN p
    """

    update_params = {
        "party_id": str(params.party_id),
        "active_pc_id": str(params.entity_id),
        "updated_at": now,
    }

    client.execute_write(update_query, update_params)

    # Return updated party
    updated_party = neo4j_get_party(params.party_id)
    if updated_party is None:
        raise ValueError(f"Party {params.party_id} not found after update")
    return updated_party


def neo4j_update_party_status(party_id: UUID, status: PartyStatus) -> PartyResponse:
    """
    Update party status.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-15

    Args:
        party_id: Party UUID
        status: New PartyStatus enum value

    Returns:
        Updated PartyResponse

    Raises:
        ValueError: If party not found
    """
    client = get_neo4j_client()

    # Verify party exists
    party = neo4j_get_party(party_id)
    if not party:
        raise ValueError(f"Party {party_id} not found")

    # Update status
    now = datetime.now(timezone.utc)
    update_query = """
    MATCH (p:Party {id: $party_id})
    SET p.status = $status,
        p.updated_at = $updated_at
    RETURN p
    """

    update_params = {
        "party_id": str(party_id),
        "status": status.value,  # Convert enum to string
        "updated_at": now,
    }

    client.execute_write(update_query, update_params)

    # Return updated party
    updated_party = neo4j_get_party(party_id)
    if updated_party is None:
        raise ValueError(f"Party {party_id} not found after update")
    return updated_party


def neo4j_update_party_location(
    party_id: UUID, location_id: Optional[UUID]
) -> PartyResponse:
    """
    Update party location.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-15

    Args:
        party_id: Party UUID
        location_id: Location entity UUID (or None to clear)

    Returns:
        Updated PartyResponse

    Raises:
        ValueError: If party not found
    """
    client = get_neo4j_client()

    # Verify party exists
    party = neo4j_get_party(party_id)
    if not party:
        raise ValueError(f"Party {party_id} not found")

    # Update location
    now = datetime.now(timezone.utc)
    update_query = """
    MATCH (p:Party {id: $party_id})
    SET p.location_id = $location_id,
        p.updated_at = $updated_at
    RETURN p
    """

    update_params = {
        "party_id": str(party_id),
        "location_id": str(location_id) if location_id else None,
        "updated_at": now,
    }

    client.execute_write(update_query, update_params)

    # Return updated party
    updated_party = neo4j_get_party(party_id)
    if updated_party is None:
        raise ValueError(f"Party {party_id} not found after update")
    return updated_party


def neo4j_update_party_formation(
    party_id: UUID, formation: List[UUID]
) -> PartyResponse:
    """
    Update party marching order formation.

    Authority: Orchestrator
    Use Case: DL-15

    Args:
        party_id: Party UUID
        formation: Ordered list of entity IDs

    Returns:
        Updated PartyResponse

    Raises:
        ValueError: If party not found
    """
    client = get_neo4j_client()

    # Verify party exists
    party = neo4j_get_party(party_id)
    if not party:
        raise ValueError(f"Party {party_id} not found")

    # Verify all formation IDs are party members
    if formation:
        member_ids = {m.entity_id for m in party.members}
        invalid_ids = [eid for eid in formation if eid not in member_ids]
        if invalid_ids:
            raise ValueError(f"Formation contains non-member entity IDs: {invalid_ids}")

    # Update formation
    now = datetime.now(timezone.utc)
    update_query = """
    MATCH (p:Party {id: $party_id})
    SET p.formation = $formation,
        p.updated_at = $updated_at
    RETURN p
    """

    update_params = {
        "party_id": str(party_id),
        "formation": [str(eid) for eid in formation],
        "updated_at": now,
    }

    client.execute_write(update_query, update_params)

    # Return updated party
    updated_party = neo4j_get_party(party_id)
    if updated_party is None:
        raise ValueError(f"Party {party_id} not found after update")
    return updated_party


def neo4j_delete_party(party_id: UUID) -> Dict[str, Any]:
    """
    Delete a party and all MEMBER_OF relationships.

    Authority: CanonKeeper only
    Use Case: DL-15

    Args:
        party_id: Party UUID

    Returns:
        Dict with deletion status

    Raises:
        ValueError: If party not found
    """
    client = get_neo4j_client()

    # Verify party exists
    party = neo4j_get_party(party_id)
    if not party:
        raise ValueError(f"Party {party_id} not found")

    # Delete party and relationships
    delete_query = """
    MATCH (p:Party {id: $party_id})
    DETACH DELETE p
    RETURN count(p) as deleted_count
    """

    result = client.execute_write(delete_query, {"party_id": str(party_id)})

    return {
        "deleted": True,
        "party_id": str(party_id),
        "deleted_count": result[0]["deleted_count"] if result else 0,
    }


# =============================================================================
# RELATIONSHIP TOOLS (DL-14)
# =============================================================================


def neo4j_create_relationship(params: RelationshipCreate) -> RelationshipResponse:
    """
    Create a typed relationship (edge) between two entities.

    Authority: CanonKeeper only
    Use Case: DL-14

    Args:
        params: Relationship creation parameters

    Returns:
        RelationshipResponse with created relationship data

    Raises:
        ValueError: If either entity doesn't exist
    """
    client = get_neo4j_client()

    # Validate both entities exist
    from_exists = client.execute_read(
        "MATCH (e:Entity {id: $entity_id}) RETURN e.id",
        {"entity_id": str(params.from_entity_id)},
    )
    if not from_exists:
        raise ValueError(f"From entity {params.from_entity_id} not found")

    to_exists = client.execute_read(
        "MATCH (e:Entity {id: $entity_id}) RETURN e.id",
        {"entity_id": str(params.to_entity_id)},
    )
    if not to_exists:
        raise ValueError(f"To entity {params.to_entity_id} not found")

    # Validate no self-reference for relationship types where it doesn't make sense
    if params.from_entity_id == params.to_entity_id:
        # OWNS might be valid (e.g., recursive ownership), but most types are not
        if params.rel_type in (
            RelationshipType.KNOWS,
            RelationshipType.ALLIED_WITH,
            RelationshipType.HOSTILE_TO,
        ):
            raise ValueError(
                f"Self-referencing relationships are not allowed for {params.rel_type.value}"
            )

    # Create relationship with properties
    now = datetime.now(timezone.utc)
    props = {**params.properties, "created_at": now.isoformat()}

    create_query = f"""
    MATCH (from:Entity {{id: $from_id}})
    MATCH (to:Entity {{id: $to_id}})
    CREATE (from)-[r:{params.rel_type.value} $props]->(to)
    RETURN id(r) as rel_id, type(r) as rel_type, properties(r) as props
    """

    result = client.execute_write(
        create_query,
        {
            "from_id": str(params.from_entity_id),
            "to_id": str(params.to_entity_id),
            "props": props,
        },
    )

    if not result:
        raise ValueError("Failed to create relationship")

    rel_data = result[0]
    return RelationshipResponse(
        relationship_id=str(rel_data["rel_id"]),
        from_entity_id=params.from_entity_id,
        to_entity_id=params.to_entity_id,
        rel_type=params.rel_type,
        properties=rel_data["props"],
        created_at=now,
    )


def neo4j_get_relationship(relationship_id: str) -> Optional[RelationshipResponse]:
    """
    Get a relationship by its Neo4j internal ID.

    Authority: All agents
    Use Case: DL-14

    Args:
        relationship_id: Neo4j relationship ID

    Returns:
        RelationshipResponse if found, None otherwise
    """
    client = get_neo4j_client()

    query = """
    MATCH (from:Entity)-[r]->(to:Entity)
    WHERE id(r) = $rel_id
    RETURN id(r) as rel_id, from.id as from_id, to.id as to_id,
           type(r) as rel_type, properties(r) as props
    """

    try:
        rel_id_int = int(relationship_id)
    except (TypeError, ValueError):
        raise ValueError(
            "Invalid relationship ID format: must be a numeric string"
        ) from None

    result = client.execute_read(query, {"rel_id": rel_id_int})

    if not result:
        return None

    rel = result[0]
    return RelationshipResponse(
        relationship_id=str(rel["rel_id"]),
        from_entity_id=UUID(rel["from_id"]),
        to_entity_id=UUID(rel["to_id"]),
        rel_type=rel["rel_type"],
        properties=rel["props"],
        created_at=(
            datetime.fromisoformat(rel["props"].get("created_at"))
            if rel["props"].get("created_at")
            else None
        ),
    )


def neo4j_list_relationships(
    params: RelationshipFilter,
) -> RelationshipListResponse:
    """
    List relationships with optional filtering.

    Authority: All agents
    Use Case: DL-14

    Args:
        params: Filter parameters

    Returns:
        RelationshipListResponse with matching relationships
    """
    client = get_neo4j_client()

    # Build query based on filters
    match_clause = "MATCH (from:Entity)-[r]->(to:Entity)"
    where_clauses = []
    query_params: Dict[str, Any] = {
        "limit": params.limit,
        "offset": params.offset,
    }

    if params.entity_id:
        if params.direction == Direction.OUTGOING:
            where_clauses.append("from.id = $entity_id")
        elif params.direction == Direction.INCOMING:
            where_clauses.append("to.id = $entity_id")
        else:  # BOTH
            where_clauses.append("(from.id = $entity_id OR to.id = $entity_id)")
        query_params["entity_id"] = str(params.entity_id)

    if params.rel_type:
        where_clauses.append("type(r) = $rel_type")
        query_params["rel_type"] = params.rel_type.value

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Count query
    count_query = f"""
    {match_clause}
    {where_clause}
    RETURN count(r) as total
    """

    count_result = client.execute_read(count_query, query_params)
    total = count_result[0]["total"] if count_result else 0

    # Data query
    data_query = f"""
    {match_clause}
    {where_clause}
    RETURN id(r) as rel_id, from.id as from_id, to.id as to_id,
           type(r) as rel_type, properties(r) as props
    ORDER BY id(r)
    SKIP $offset
    LIMIT $limit
    """

    results = client.execute_read(data_query, query_params)

    relationships = []
    for rel in results:
        relationships.append(
            RelationshipResponse(
                relationship_id=str(rel["rel_id"]),
                from_entity_id=UUID(rel["from_id"]),
                to_entity_id=UUID(rel["to_id"]),
                rel_type=rel["rel_type"],
                properties=rel["props"],
                created_at=(
                    datetime.fromisoformat(rel["props"].get("created_at"))
                    if rel["props"].get("created_at")
                    else None
                ),
            )
        )

    return RelationshipListResponse(
        relationships=relationships,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def neo4j_update_relationship(
    relationship_id: str, params: RelationshipUpdate
) -> RelationshipResponse:
    """
    Update a relationship's properties.

    Authority: CanonKeeper only
    Use Case: DL-14

    Args:
        relationship_id: Neo4j relationship ID
        params: Update parameters

    Returns:
        RelationshipResponse with updated data

    Raises:
        ValueError: If relationship not found
    """
    client = get_neo4j_client()

    # Verify relationship exists
    existing = neo4j_get_relationship(relationship_id)
    if not existing:
        raise ValueError(f"Relationship {relationship_id} not found")

    # Update properties (preserve created_at)
    updated_props = {
        **params.properties,
        "created_at": existing.created_at.isoformat() if existing.created_at else None,
    }

    update_query = """
    MATCH ()-[r]->()
    WHERE id(r) = $rel_id
    SET r = $props
    RETURN id(r) as rel_id
    """

    try:
        rel_id_int = int(relationship_id)
    except (TypeError, ValueError):
        raise ValueError(
            "Invalid relationship ID format: must be a numeric string"
        ) from None

    result = client.execute_write(
        update_query, {"rel_id": rel_id_int, "props": updated_props}
    )

    if not result:
        raise ValueError(f"Failed to update relationship {relationship_id}")

    # Return updated relationship
    updated = neo4j_get_relationship(relationship_id)
    if not updated:
        raise ValueError(f"Relationship {relationship_id} not found after update")
    return updated


def neo4j_delete_relationship(relationship_id: str) -> Dict[str, Any]:
    """
    Delete a relationship.

    Authority: CanonKeeper only
    Use Case: DL-14

    Args:
        relationship_id: Neo4j relationship ID

    Returns:
        Dict with deletion status

    Raises:
        ValueError: If relationship not found
    """
    client = get_neo4j_client()

    # Verify relationship exists
    existing = neo4j_get_relationship(relationship_id)
    if not existing:
        raise ValueError(f"Relationship {relationship_id} not found")

    delete_query = """
    MATCH ()-[r]->()
    WHERE id(r) = $rel_id
    WITH r
    DELETE r
    RETURN count(*) as deleted_count
    """

    try:
        rel_id_int = int(relationship_id)
    except (TypeError, ValueError):
        raise ValueError(
            "Invalid relationship ID format: must be a numeric string"
        ) from None

    result = client.execute_write(delete_query, {"rel_id": rel_id_int})

    return {
        "deleted": True,
        "relationship_id": relationship_id,
        "deleted_count": result[0]["deleted_count"] if result else 0,
    }


# =============================================================================
# STATE TAG TOOLS (DL-14)
# =============================================================================


def neo4j_update_state_tags(params: StateTagUpdate) -> StateTagResponse:
    """
    Update state tags on an entity instance atomically.

    Authority: CanonKeeper only
    Use Case: DL-14

    Args:
        params: State tag update parameters

    Returns:
        StateTagResponse with updated tags

    Raises:
        ValueError: If entity not found or is an archetype
    """
    client = get_neo4j_client()

    # Validate entity exists and is an instance
    entity_check = client.execute_read(
        """
        MATCH (e:Entity {id: $entity_id})
        RETURN e.id as id, e.is_archetype as is_archetype
        """,
        {"entity_id": str(params.entity_id)},
    )

    if not entity_check:
        raise ValueError(f"Entity {params.entity_id} not found")

    if entity_check[0]["is_archetype"]:
        raise ValueError(
            f"Cannot set state tags on archetype {params.entity_id}. "
            "State tags are only valid on entity instances."
        )

    # Validate at least one operation
    if not params.add_tags and not params.remove_tags:
        raise ValueError("At least one of add_tags or remove_tags must be non-empty")

    # Convert tags to strings
    add_tag_strs = [tag.value for tag in params.add_tags]
    remove_tag_strs = [tag.value for tag in params.remove_tags]

    # Update tags atomically (remove first, then add, then deduplicate)
    # If same tag in both add and remove, addition takes precedence
    update_query = """
    MATCH (e:Entity {id: $entity_id})
    WITH e,
         [tag IN coalesce(e.state_tags, []) WHERE NOT tag IN $remove_tags] as after_remove
    SET e.state_tags =
        REDUCE(
            s = [],
            t IN (after_remove + $add_tags) |
            CASE
                WHEN t IN s THEN s
                ELSE s + t
            END
        )
    RETURN e.state_tags as tags
    """

    result = client.execute_write(
        update_query,
        {
            "entity_id": str(params.entity_id),
            "add_tags": add_tag_strs,
            "remove_tags": remove_tag_strs,
        },
    )

    tags = result[0]["tags"] if result and result[0]["tags"] else []

    return StateTagResponse(entity_id=params.entity_id, state_tags=tags)


def neo4j_get_state_tags(entity_id: UUID) -> StateTagResponse:
    """
    Get current state tags for an entity.

    Authority: All agents
    Use Case: DL-14

    Args:
        entity_id: Entity UUID

    Returns:
        StateTagResponse with current tags

    Raises:
        ValueError: If entity not found
    """
    client = get_neo4j_client()

    query = """
    MATCH (e:Entity {id: $entity_id})
    RETURN e.state_tags as tags
    """

    result = client.execute_read(query, {"entity_id": str(entity_id)})

    if not result:
        raise ValueError(f"Entity {entity_id} not found")

    tags = result[0]["tags"] if result[0]["tags"] else []

    return StateTagResponse(entity_id=entity_id, state_tags=tags)
