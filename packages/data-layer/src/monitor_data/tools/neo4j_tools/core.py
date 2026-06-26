"""
Neo4j Universe Tools for MONITOR Data Layer.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.base import KnowledgeTreeType
from monitor_data.tools.neo4j_tools._helpers import verify_node_exists
from monitor_data.schemas.universe import (
    UniverseCreate,
    UniverseUpdate,
    UniverseResponse,
    UniverseFilter,
    MultiverseCreate,
    MultiverseResponse,
)
from monitor_data.schemas.documents import (
    SourceCreate,
    SourceResponse,
)
from monitor_data.schemas.base import (
    SourceType,
    SourcePriority,
    SourceCanonLevel,
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
    verify_node_exists(client, "Omniverse", params.omniverse_id)

    # Create multiverse
    multiverse_id = params.id or uuid4()
    create_query = """
    MATCH (o:Omniverse {id: $omniverse_id})
    CREATE (m:Multiverse {
        id: $id,
        omniverse_id: $omniverse_id,
        name: $name,
        system_name: $system_name,
        description: $description,
        is_template: $is_template,
        knowledge_tree_type: $knowledge_tree_type,
        source_document_id: $source_document_id,
        parent_multiverse_id: $parent_multiverse_id,
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
            "is_template": params.is_template,
            "knowledge_tree_type": params.knowledge_tree_type.value,
            "source_document_id": str(params.source_document_id)
            if params.source_document_id
            else None,
            "parent_multiverse_id": str(params.parent_multiverse_id)
            if params.parent_multiverse_id
            else None,
            "created_at": created_at.isoformat(),
        },
    )

    return MultiverseResponse(
        id=multiverse_id,
        omniverse_id=params.omniverse_id,
        name=params.name,
        system_name=params.system_name,
        description=params.description,
        is_template=params.is_template,
        knowledge_tree_type=params.knowledge_tree_type,
        source_document_id=params.source_document_id,
        parent_multiverse_id=params.parent_multiverse_id,
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
        system_name=m.get("system_name", ""),
        description=m.get("description", ""),
        is_template=m.get("is_template", False),
        knowledge_tree_type=m.get("knowledge_tree_type") or KnowledgeTreeType.DYNAMIC,
        source_document_id=UUID(m["source_document_id"]) if m.get("source_document_id") else None,
        parent_multiverse_id=UUID(m["parent_multiverse_id"])
        if m.get("parent_multiverse_id")
        else None,
        created_at=m["created_at"].to_native()
        if hasattr(m["created_at"], "to_native")
        else m["created_at"],
    )


def neo4j_list_multiverses(omniverse_id: Optional[UUID] = None) -> List[MultiverseResponse]:
    """
    List all Multiverses.

    Authority: Any agent (read-only)
    Use Case: DL-1

    Args:
        omniverse_id: Optional filter by parent omniverse

    Returns:
        List of MultiverseResponse objects ordered by creation time
    """
    client = get_neo4j_client()

    if omniverse_id:
        query = """
        MATCH (m:Multiverse {omniverse_id: $omniverse_id})
        RETURN m
        ORDER BY m.created_at ASC
        """
        params: Dict[str, Any] = {"omniverse_id": str(omniverse_id)}
    else:
        query = """
        MATCH (m:Multiverse)
        RETURN m
        ORDER BY m.created_at ASC
        """
        params = {}

    result = client.execute_read(query, params)

    multiverses = []
    for record in result:
        m = record["m"]
        multiverses.append(
            MultiverseResponse(
                id=UUID(m["id"]),
                omniverse_id=UUID(m["omniverse_id"]),
                name=m["name"],
                system_name=m.get("system_name", ""),
                description=m.get("description", ""),
                is_template=m.get("is_template", False),
                knowledge_tree_type=m.get("knowledge_tree_type") or KnowledgeTreeType.DYNAMIC,
                source_document_id=UUID(m["source_document_id"])
                if m.get("source_document_id")
                else None,
                parent_multiverse_id=UUID(m["parent_multiverse_id"])
                if m.get("parent_multiverse_id")
                else None,
                created_at=m["created_at"].to_native()
                if hasattr(m["created_at"], "to_native")
                else m["created_at"],
            )
        )

    return multiverses


def neo4j_delete_multiverse(multiverse_id: UUID, force: bool = False) -> Dict[str, Any]:
    """
    Delete a Multiverse node.

    Authority: CanonKeeper only
    Use Case: DL-1

    Args:
        multiverse_id: UUID of the multiverse to delete
        force: If True, cascade-delete all contained universes and their data

    Raises:
        ValueError: If multiverse not found or has children and force=False
    """
    client = get_neo4j_client()

    check = client.execute_read(
        "MATCH (m:Multiverse {id: $id}) RETURN m.id as id",
        {"id": str(multiverse_id)},
    )
    if not check:
        raise ValueError(f"Multiverse {multiverse_id} not found")

    children = client.execute_read(
        "MATCH (m:Multiverse {id: $id})-[:CONTAINS]->(u:Universe) RETURN count(u) as cnt",
        {"id": str(multiverse_id)},
    )
    child_count = children[0]["cnt"] if children else 0

    if child_count > 0 and not force:
        raise ValueError(
            f"Multiverse has {child_count} universe(s). Use force=True to cascade delete."
        )

    if force:
        client.execute_write(
            """
            MATCH (m:Multiverse {id: $id})
            OPTIONAL MATCH (m)-[:CONTAINS*]->(n)
            DETACH DELETE m, n
            """,
            {"id": str(multiverse_id)},
        )
    else:
        client.execute_write(
            "MATCH (m:Multiverse {id: $id}) DETACH DELETE m",
            {"id": str(multiverse_id)},
        )

    return {"multiverse_id": str(multiverse_id), "deleted": True, "force": force}


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
    verify_node_exists(client, "Multiverse", params.multiverse_id)

    # Create universe
    universe_id = params.id or uuid4()
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
        parent_universe_id: $parent_universe_id,
        alt_world_type: $alt_world_type,
        is_template: $is_template,
        default_game_system_id: $default_game_system_id,
        default_system_source_type: $default_system_source_type,
        default_system_source_id: $default_system_source_id,
        default_system_name: $default_system_name,
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
            "parent_universe_id": str(params.parent_universe_id)
            if params.parent_universe_id
            else None,
            "alt_world_type": params.alt_world_type.value,
            "is_template": params.is_template,
            "default_game_system_id": str(params.default_game_system_id)
            if params.default_game_system_id
            else None,
            "default_system_source_type": params.default_system_source_type,
            "default_system_source_id": params.default_system_source_id,
            "default_system_name": params.default_system_name,
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
        parent_universe_id=params.parent_universe_id,
        alt_world_type=params.alt_world_type,
        is_template=params.is_template,
        default_game_system_id=params.default_game_system_id,
        default_system_source_type=params.default_system_source_type,
        default_system_source_id=params.default_system_source_id,
        default_system_name=params.default_system_name,
        canon_level=params.canon_level,
        confidence=params.confidence,
        authority=params.authority,
        source_ids=[],
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
        description=u.get("description", ""),
        genre=u.get("genre"),
        tone=u.get("tone"),
        tech_level=u.get("tech_level"),
        parent_universe_id=UUID(u["parent_universe_id"]) if u.get("parent_universe_id") else None,
        alt_world_type=u.get("alt_world_type", "main"),
        is_template=u.get("is_template", False),
        default_game_system_id=UUID(u["default_game_system_id"])
        if u.get("default_game_system_id")
        else None,
        default_system_source_type=u.get("default_system_source_type"),
        default_system_source_id=u.get("default_system_source_id"),
        default_system_name=u.get("default_system_name"),
        canon_level=u.get("canon_level", "canon"),
        confidence=u.get("confidence", 1.0),
        authority=u.get("authority", "system"),
        source_ids=[UUID(sid) for sid in u.get("source_ids", [])],
        created_at=u["created_at"].to_native()
        if hasattr(u["created_at"], "to_native")
        else u["created_at"],
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

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

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
                description=u.get("description", ""),
                genre=u.get("genre"),
                tone=u.get("tone"),
                tech_level=u.get("tech_level"),
                parent_universe_id=UUID(u["parent_universe_id"])
                if u.get("parent_universe_id")
                else None,
                alt_world_type=u.get("alt_world_type", "main"),
                is_template=u.get("is_template", False),
                default_game_system_id=UUID(u["default_game_system_id"])
                if u.get("default_game_system_id")
                else None,
                default_system_source_type=u.get("default_system_source_type"),
                default_system_source_id=u.get("default_system_source_id"),
                default_system_name=u.get("default_system_name"),
                canon_level=u.get("canon_level", "canon"),
                confidence=u.get("confidence", 1.0),
                authority=u.get("authority", "system"),
                source_ids=[UUID(sid) for sid in u.get("source_ids", [])],
                created_at=u["created_at"].to_native()
                if hasattr(u["created_at"], "to_native")
                else u["created_at"],
            )
        )

    return universes


def neo4j_update_universe(universe_id: UUID, params: UniverseUpdate) -> UniverseResponse:
    """
    Update mutable fields of a Universe.

    Authority: CanonKeeper only
    Use Case: DL-1, M-7
    """
    client = get_neo4j_client()

    verify_node_exists(client, "Universe", universe_id)

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

    if params.default_game_system_id is not None:
        set_clauses.append("u.default_game_system_id = $default_game_system_id")
        update_params["default_game_system_id"] = str(params.default_game_system_id)

    if params.default_system_source_type is not None:
        set_clauses.append("u.default_system_source_type = $default_system_source_type")
        update_params["default_system_source_type"] = params.default_system_source_type

    if params.default_system_source_id is not None:
        set_clauses.append("u.default_system_source_id = $default_system_source_id")
        update_params["default_system_source_id"] = params.default_system_source_id

    if params.default_system_name is not None:
        set_clauses.append("u.default_system_name = $default_system_name")
        update_params["default_system_name"] = params.default_system_name

    if not set_clauses:
        existing = neo4j_get_universe(universe_id)
        if existing is None:
            raise ValueError(f"Universe {universe_id} not found")
        return existing

    set_clause = ", ".join(set_clauses)
    update_query = "MATCH (u:Universe {id: $id})\nSET " + set_clause + "\nRETURN u"

    write_result = client.execute_write(update_query, update_params)
    u = write_result[0]["u"]

    return UniverseResponse(
        id=UUID(u["id"]),
        multiverse_id=UUID(u["multiverse_id"]),
        name=u["name"],
        description=u.get("description", ""),
        genre=u.get("genre"),
        tone=u.get("tone"),
        tech_level=u.get("tech_level"),
        parent_universe_id=UUID(u["parent_universe_id"]) if u.get("parent_universe_id") else None,
        alt_world_type=u.get("alt_world_type", "main"),
        is_template=u.get("is_template", False),
        default_game_system_id=UUID(u["default_game_system_id"])
        if u.get("default_game_system_id")
        else None,
        default_system_source_type=u.get("default_system_source_type"),
        default_system_source_id=u.get("default_system_source_id"),
        default_system_name=u.get("default_system_name"),
        canon_level=u.get("canon_level", "canon"),
        confidence=u.get("confidence", 1.0),
        authority=u.get("authority", "system"),
        source_ids=[UUID(sid) for sid in u.get("source_ids", [])],
        created_at=u["created_at"].to_native()
        if hasattr(u["created_at"], "to_native")
        else u["created_at"],
    )


def neo4j_delete_universe(universe_id: UUID, force: bool = False) -> Dict[str, Any]:
    """
    Delete a Universe node.

    Authority: CanonKeeper only
    Use Case: DL-1, M-8
    """
    client = get_neo4j_client()

    verify_node_exists(client, "Universe", universe_id)

    if not force:
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

        if deps["sources"] > 0 or deps["axioms"] > 0 or deps["stories"] > 0 or deps["entities"] > 0:
            raise ValueError(
                f"Universe {universe_id} has dependent data. Use force=True to cascade delete."
            )

    if force:
        delete_query = """
        MATCH (u:Universe {id: $id})
        OPTIONAL MATCH (u)-[:HAS_SOURCE]->(source:Source)
        OPTIONAL MATCH (u)-[:HAS_AXIOM]->(axiom:Axiom)
        OPTIONAL MATCH (u)-[:HAS_STORY]->(story:Story)
        OPTIONAL MATCH (u)-[:HAS_STORY]->(:Story)-[:HAS_SCENE]->(scene:Scene)
        OPTIONAL MATCH (u)-[:HAS_STORY]->(:Story)-[:HAS_THREAD]->(thread:PlotThread)
        OPTIONAL MATCH (u)<-[:IN_UNIVERSE]-(entity)
        WHERE entity:EntityArchetype OR entity:EntityInstance
        WITH u, 
             [x IN collect(DISTINCT source) WHERE x IS NOT NULL] as sources,
             [x IN collect(DISTINCT axiom) WHERE x IS NOT NULL] as axioms,
             [x IN collect(DISTINCT story) WHERE x IS NOT NULL] as stories,
             [x IN collect(DISTINCT scene) WHERE x IS NOT NULL] as scenes,
             [x IN collect(DISTINCT thread) WHERE x IS NOT NULL] as threads,
             [x IN collect(DISTINCT entity) WHERE x IS NOT NULL] as entities
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


def neo4j_ensure_omniverse() -> Dict[str, Any]:
    """
    Ensure an Omniverse node exists (create if missing).

    Authority: CanonKeeper only
    """
    client = get_neo4j_client()

    check_query = "MATCH (o:Omniverse) RETURN o.id as id LIMIT 1"
    result = client.execute_read(check_query)

    if result:
        return {"omniverse_id": result[0]["id"], "created": False}

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
# SOURCE NODE OPERATIONS
# =============================================================================


def neo4j_create_source(params: SourceCreate) -> SourceResponse:
    """
    Create a Source node in Neo4j and link it to its universe.

    Source nodes are canonical provenance records.  Facts, Axioms, and Entities
    carry SUPPORTED_BY edges pointing to the Source that introduced them.

    Authority: IngestionPipeline, CanonKeeper
    Use Case: DL-B1 (ingestion pipeline)

    Args:
        params: Source creation parameters

    Returns:
        SourceResponse with new source_id

    Raises:
        ValueError: If universe_id does not exist
    """
    client = get_neo4j_client()

    # Verify universe exists
    verify_node_exists(client, "Universe", params.universe_id)

    source_id = uuid4()
    now = datetime.now(timezone.utc)

    create_query = """
    MATCH (u:Universe {id: $universe_id})
    CREATE (s:Source {
        id: $id,
        universe_id: $universe_id,
        title: $title,
        edition: $edition,
        provenance: $provenance,
        source_type: $source_type,
        priority: $priority,
        knowledge_tree_type: $knowledge_tree_type,
        canon_level: $canon_level,
        created_at: datetime($created_at)
    })
    CREATE (u)-[:HAS_SOURCE]->(s)
    RETURN s
    """
    client.execute_write(
        create_query,
        {
            "id": str(source_id),
            "universe_id": str(params.universe_id),
            "title": params.title,
            "edition": params.edition or "",
            "provenance": params.provenance or "",
            "source_type": params.source_type.value,
            "priority": params.priority.value,
            "knowledge_tree_type": params.knowledge_tree_type.value,
            "canon_level": params.canon_level.value,
            "created_at": now.isoformat(),
        },
    )

    return SourceResponse(
        id=source_id,
        universe_id=params.universe_id,
        title=params.title,
        edition=params.edition,
        provenance=params.provenance,
        source_type=params.source_type,
        priority=params.priority,
        knowledge_tree_type=params.knowledge_tree_type,
        canon_level=params.canon_level,
        created_at=now,
    )


def neo4j_get_source(source_id: UUID) -> Optional[SourceResponse]:
    """
    Get a Source node by ID.

    Args:
        source_id: UUID of the source

    Returns:
        SourceResponse or None if not found
    """
    client = get_neo4j_client()
    result = client.execute_read("MATCH (s:Source {id: $id}) RETURN s", {"id": str(source_id)})
    if not result:
        return None
    s = result[0]["s"]
    return SourceResponse(
        id=UUID(s["id"]),
        universe_id=UUID(s["universe_id"]),
        title=s["title"],
        edition=s.get("edition") or None,
        provenance=s.get("provenance") or None,
        source_type=SourceType(s["source_type"]),
        priority=SourcePriority(s["priority"]),
        knowledge_tree_type=KnowledgeTreeType(s["knowledge_tree_type"]),
        canon_level=SourceCanonLevel(s["canon_level"]),
        created_at=s["created_at"],
    )


def neo4j_get_universe_state(universe_id: UUID) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get the complete state of a Universe (all entities, facts, axioms, relationships).
    Used for creating world snapshots.

    Authority: Any agent (read-only)
    Use Case: DL-23
    """
    client = get_neo4j_client()
    uid = str(universe_id)

    def _native(record: Dict[str, Any]) -> Dict[str, Any]:
        """Convert neo4j temporal values to native datetimes (JSON-safe)."""
        return {k: (v.to_native() if hasattr(v, "to_native") else v) for k, v in record.items()}

    # 1. Fetch Entities — created as (u)-[:HAS_ENTITY]->(e:Entity) by
    # neo4j_create_entity; keep legacy IN_UNIVERSE/labels for old data.
    entities_query = """
    MATCH (u:Universe {id: $uid})
    OPTIONAL MATCH (u)-[:HAS_ENTITY]->(e1)
    OPTIONAL MATCH (e2)-[:IN_UNIVERSE]->(u)
    WITH collect(DISTINCT e1) + collect(DISTINCT e2) AS nodes
    UNWIND nodes AS e
    WITH DISTINCT e
    WHERE e IS NOT NULL AND (e:Entity OR e:EntityArchetype OR e:EntityInstance)
    RETURN e, labels(e) as labels
    """
    entities_res = client.execute_read(entities_query, {"uid": uid})
    entities = []
    for record in entities_res:
        e_data = _native(dict(record["e"]))
        e_data["labels"] = record["labels"]
        entities.append(e_data)

    # 2. Fetch Facts & Events — direct (u)-[:HAS_FACT]->(f) links plus the
    # scene-supported path.
    facts_query = """
    MATCH (u:Universe {id: $uid})
    OPTIONAL MATCH (u)-[:HAS_FACT]->(f1)
    OPTIONAL MATCH (u)-[:HAS_STORY]->(:Story)-[:HAS_SCENE]->(:Scene)<-[:SUPPORTED_BY]-(f2)
    WITH collect(DISTINCT f1) + collect(DISTINCT f2) AS nodes
    UNWIND nodes AS f
    WITH DISTINCT f
    WHERE f IS NOT NULL AND (f:Fact OR f:Event)
    RETURN f, labels(f) as labels
    """
    facts_res = client.execute_read(facts_query, {"uid": uid})
    facts = []
    for record in facts_res:
        f_data = _native(dict(record["f"]))
        f_data["labels"] = record["labels"]
        facts.append(f_data)

    # 3. Fetch Axioms
    axioms_query = """
    MATCH (u:Universe {id: $uid})-[:HAS_AXIOM]->(a:Axiom)
    RETURN a
    """
    axioms_res = client.execute_read(axioms_query, {"uid": uid})
    axioms = [_native(dict(record["a"])) for record in axioms_res]

    # 4. Fetch Relationships between entities in this universe
    rels_query = """
    MATCH (u:Universe {id: $uid})-[:HAS_ENTITY]->(e1)
    MATCH (u)-[:HAS_ENTITY]->(e2)
    MATCH (e1)-[r]->(e2)
    RETURN r, type(r) as rel_type, e1.id as from_id, e2.id as to_id
    """
    rels_res = client.execute_read(rels_query, {"uid": uid})
    relationships = []
    for record in rels_res:
        r_data = _native(dict(record["r"]))
        r_data["type"] = record["rel_type"]
        r_data["from_id"] = record["from_id"]
        r_data["to_id"] = record["to_id"]
        relationships.append(r_data)

    return {
        "entities": entities,
        "facts": facts,
        "axioms": axioms,
        "relationships": relationships,
    }


def neo4j_delete_source(source_id: UUID) -> bool:
    """
    Delete a Source node and its relationships from Neo4j.

    Detaches all edges (HAS_SOURCE, SUPPORTED_BY, etc.) before deleting.

    Authority: CanonKeeper, IngestionPipeline
    Use Case: DL-B1 (source cleanup)

    Args:
        source_id: UUID of the source to delete

    Returns:
        True if deleted, False if not found
    """
    client = get_neo4j_client()
    result = client.execute_write(
        "MATCH (s:Source {id: $id}) DETACH DELETE s RETURN count(s) AS deleted",
        {"id": str(source_id)},
    )
    return bool(result and result[0].get("deleted", 0) > 0)


def neo4j_fork_universe(
    source_universe_id: UUID,
    name: str,
    description: str = "",
) -> Dict[str, Any]:
    """
    Fork a universe: deep-clone all entities with new IDs into a new universe.

    The new universe shares the same multiverse as the source.
    Entity IDs are remapped so the fork is independent.

    Authority: CanonKeeper only
    Use Case: D-35 (universe fork)
    """
    client = get_neo4j_client()
    source_uid = str(source_universe_id)
    new_universe_id = uuid4()
    new_uid = str(new_universe_id)
    now = datetime.now(timezone.utc)

    source = neo4j_get_universe(source_universe_id)
    if not source:
        raise ValueError(f"Universe {source_universe_id} not found")

    create_universe_query = """
    MATCH (mv:Multiverse)-[:CONTAINS]->(source:Universe {id: $source_uid})
    CREATE (new:Universe {
        id: $new_uid,
        name: $name,
        description: $description,
        genre: source.genre,
        tone: source.tone,
        tech_level: source.tech_level,
        is_template: false,
        parent_universe_id: $source_uid,
        alt_world_type: 'fork',
        canon_level: source.canon_level,
        confidence: source.confidence,
        authority: source.authority,
        created_at: datetime($now)
    })
    CREATE (mv)-[:CONTAINS]->(new)
    RETURN new
    """
    client.execute_write(
        create_universe_query,
        {
            "source_uid": source_uid,
            "new_uid": new_uid,
            "name": name,
            "description": description or f"Fork of {source.name}",
            "now": now.isoformat(),
        },
    )

    id_map: Dict[str, str] = {}
    entities_query = """
    MATCH (e)-[:IN_UNIVERSE]->(:Universe {id: $source_uid})
    WHERE e:EntityInstance OR e:EntityArchetype
    RETURN e, labels(e) as labels
    """
    entities = client.execute_read(entities_query, {"source_uid": source_uid})

    entities_cloned = 0
    for record in entities:
        old_data = dict(record["e"])
        old_labels = record["labels"]
        old_id = old_data.get("id", "")
        new_entity_id = str(uuid4())
        id_map[old_id] = new_entity_id

        entity_label = "EntityInstance"
        if "EntityArchetype" in old_labels:
            entity_label = "EntityArchetype"

        clone_query = f"""
        MATCH (u:Universe {{id: $new_uid}})
        CREATE (e:{entity_label} {{
            id: $new_id,
            name: $name,
            entity_type: $entity_type,
            description: $description,
            properties: $properties,
            state_tags: $state_tags,
            canon_level: $canon_level,
            confidence: $confidence,
            authority: $authority,
            created_at: datetime($now)
        }})
        CREATE (e)-[:IN_UNIVERSE]->(u)
        """
        client.execute_write(
            clone_query,
            {
                "new_uid": new_uid,
                "new_id": new_entity_id,
                "name": old_data.get("name", "Unknown"),
                "entity_type": old_data.get("entity_type", "character"),
                "description": old_data.get("description", ""),
                "properties": old_data.get("properties", "{}"),
                "state_tags": old_data.get("state_tags", []),
                "canon_level": old_data.get("canon_level", "canon"),
                "confidence": old_data.get("confidence", 1.0),
                "authority": old_data.get("authority", "system"),
                "now": now.isoformat(),
            },
        )
        entities_cloned += 1

    relationships_cloned = 0
    if id_map:
        rels_query = """
        MATCH (e1)-[:IN_UNIVERSE]->(:Universe {id: $source_uid})
        MATCH (e2)-[:IN_UNIVERSE]->(:Universe {id: $source_uid})
        MATCH (e1)-[r]->(e2)
        WHERE NOT 'Universe' IN labels(e1) AND NOT 'Universe' IN labels(e2)
        RETURN type(r) as rel_type, e1.id as from_id, e2.id as to_id, properties(r) as props
        """
        rels = client.execute_read(rels_query, {"source_uid": source_uid})

        for rel in rels:
            from_new = id_map.get(rel["from_id"])
            to_new = id_map.get(rel["to_id"])
            if from_new and to_new:
                rel_query = f"""
                MATCH (e1 {{id: $from_id}})
                MATCH (e2 {{id: $to_id}})
                CREATE (e1)-[:`{rel["rel_type"]}` $props]->(e2)
                """
                client.execute_write(
                    rel_query,
                    {
                        "from_id": from_new,
                        "to_id": to_new,
                        "props": rel["props"] or {},
                    },
                )
                relationships_cloned += 1

    return {
        "new_universe_id": str(new_universe_id),
        "entities_cloned": entities_cloned,
        "relationships_cloned": relationships_cloned,
    }


# ---------------------------------------------------------------------------
# Universe split & merge (M-39 / M-40) — built on the fork clone pattern.
# ---------------------------------------------------------------------------


def _clone_entity_into_universe(client, new_uid, old_data, now_iso) -> str:
    """Deep-clone one ``:Entity`` (fresh id, re-homed) into ``new_uid``.

    Copies every property of the source node, then overrides identity fields so
    the clone is an independent entity in the target universe. Matches the
    canonical model written by ``neo4j_create_entity``:
    ``(:Universe)-[:HAS_ENTITY]->(e:Entity {universe_id})``.
    """
    new_entity_id = str(uuid4())
    props = dict(old_data)
    props["id"] = new_entity_id
    props["universe_id"] = new_uid
    props["updated_at"] = now_iso
    client.execute_write(
        """
        MATCH (u:Universe {id: $new_uid})
        CREATE (e:Entity)
        SET e = $props
        CREATE (u)-[:HAS_ENTITY]->(e)
        """,
        {"new_uid": new_uid, "props": props},
    )
    return new_entity_id


def _clone_induced_relationships(client, source_uid, id_map, seen=None) -> int:
    """Clone edges whose *both* endpoints were cloned (present in ``id_map``).

    ``seen`` — an optional set of ``(from_new, rel_type, to_new)`` keys — lets a
    caller dedupe identical edges across multiple source universes (merge).
    """
    if not id_map:
        return 0
    rels = client.execute_read(
        """
        MATCH (:Universe {id: $source_uid})-[:HAS_ENTITY]->(e1:Entity)
        MATCH (:Universe {id: $source_uid})-[:HAS_ENTITY]->(e2:Entity)
        MATCH (e1)-[r]->(e2)
        WHERE type(r) <> 'HAS_ENTITY'
        RETURN type(r) as rel_type, e1.id as from_id, e2.id as to_id, properties(r) as props
        """,
        {"source_uid": source_uid},
    )
    cloned = 0
    for rel in rels:
        from_new = id_map.get(rel["from_id"])
        to_new = id_map.get(rel["to_id"])
        if not (from_new and to_new):
            continue
        key = (from_new, rel["rel_type"], to_new)
        if seen is not None:
            if key in seen:
                continue
            seen.add(key)
        client.execute_write(
            f"""
            MATCH (e1 {{id: $from_id}})
            MATCH (e2 {{id: $to_id}})
            CREATE (e1)-[:`{rel["rel_type"]}` $props]->(e2)
            """,
            {"from_id": from_new, "to_id": to_new, "props": rel["props"] or {}},
        )
        cloned += 1
    return cloned


def neo4j_split_universe(
    source_universe_id: UUID,
    name: str,
    entity_ids: list,
    description: str = "",
) -> Dict[str, Any]:
    """
    Split a *subset* of a universe's entities into a new universe.

    The selected entities (and the relationships induced between them) are
    deep-cloned with fresh IDs into a new universe that shares the source's
    multiverse and is tagged ``alt_world_type='split'``.

    Authority: CanonKeeper only
    Use Case: M-39
    """
    client = get_neo4j_client()
    source_uid = str(source_universe_id)
    wanted = [str(e) for e in entity_ids]
    if not wanted:
        raise ValueError("entity_ids must not be empty")

    source = neo4j_get_universe(source_universe_id)
    if not source:
        raise ValueError(f"Universe {source_universe_id} not found")

    new_universe_id = uuid4()
    new_uid = str(new_universe_id)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    client.execute_write(
        """
        MATCH (mv:Multiverse)-[:CONTAINS]->(source:Universe {id: $source_uid})
        CREATE (new:Universe {
            id: $new_uid, name: $name, description: $description,
            genre: source.genre, tone: source.tone, tech_level: source.tech_level,
            is_template: false, parent_universe_id: $source_uid, alt_world_type: 'split',
            canon_level: source.canon_level, confidence: source.confidence,
            authority: source.authority, created_at: datetime($now)
        })
        CREATE (mv)-[:CONTAINS]->(new)
        RETURN new
        """,
        {
            "source_uid": source_uid,
            "new_uid": new_uid,
            "name": name,
            "description": description or f"Split of {source.name}",
            "now": now_iso,
        },
    )

    entities = client.execute_read(
        """
        MATCH (:Universe {id: $source_uid})-[:HAS_ENTITY]->(e:Entity)
        WHERE e.id IN $ids
        RETURN e
        """,
        {"source_uid": source_uid, "ids": wanted},
    )

    id_map: Dict[str, str] = {}
    for record in entities:
        old_data = dict(record["e"])
        new_id = _clone_entity_into_universe(client, new_uid, old_data, now_iso)
        id_map[old_data.get("id", "")] = new_id

    relationships_cloned = _clone_induced_relationships(client, source_uid, id_map)

    return {
        "new_universe_id": new_uid,
        "entities_cloned": len(id_map),
        "relationships_cloned": relationships_cloned,
    }


def neo4j_merge_universes(
    source_universe_ids: list,
    name: str,
    description: str = "",
    dedupe_by_name: bool = True,
) -> Dict[str, Any]:
    """
    Merge two or more universes' canon into a single new universe.

    Entities from every source are deep-cloned into the new universe. With
    ``dedupe_by_name`` (default), entities that share a name collapse into one
    node and their relationships are re-pointed at the survivor; identical edges
    are de-duplicated. The new universe lives in the first source's multiverse
    and is tagged ``alt_world_type='merge'``.

    Authority: CanonKeeper only
    Use Case: M-40
    """
    client = get_neo4j_client()
    if len(source_universe_ids) < 2:
        raise ValueError("merge requires at least two source universes")

    sources = []
    for sid in source_universe_ids:
        s = neo4j_get_universe(sid if isinstance(sid, UUID) else UUID(str(sid)))
        if not s:
            raise ValueError(f"Universe {sid} not found")
        sources.append(s)

    primary_uid = str(source_universe_ids[0])
    new_universe_id = uuid4()
    new_uid = str(new_universe_id)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    created = client.execute_write(
        """
        MATCH (mv:Multiverse)-[:CONTAINS]->(primary:Universe {id: $primary_uid})
        CREATE (new:Universe {
            id: $new_uid, name: $name, description: $description,
            genre: primary.genre, tone: primary.tone, tech_level: primary.tech_level,
            is_template: false, parent_universe_id: $primary_uid, alt_world_type: 'merge',
            canon_level: primary.canon_level, confidence: primary.confidence,
            authority: primary.authority, created_at: datetime($now)
        })
        CREATE (mv)-[:CONTAINS]->(new)
        RETURN new
        """,
        {
            "primary_uid": primary_uid,
            "new_uid": new_uid,
            "name": name,
            "description": description or f"Merge of {len(sources)} universes",
            "now": now_iso,
        },
    )
    if not created:
        raise ValueError("Could not create merged universe (is the primary in a multiverse?)")

    id_map: Dict[str, str] = {}
    name_to_new: Dict[str, str] = {}
    entities_cloned = 0
    duplicates_merged = 0

    for sid in source_universe_ids:
        suid = str(sid)
        entities = client.execute_read(
            """
            MATCH (:Universe {id: $source_uid})-[:HAS_ENTITY]->(e:Entity)
            RETURN e
            """,
            {"source_uid": suid},
        )
        for record in entities:
            old_data = dict(record["e"])
            old_id = old_data.get("id", "")
            nm = old_data.get("name", "Unknown")
            if dedupe_by_name and nm in name_to_new:
                id_map[old_id] = name_to_new[nm]
                duplicates_merged += 1
                continue
            new_id = _clone_entity_into_universe(
                client, new_uid, old_data, now_iso
            )
            id_map[old_id] = new_id
            name_to_new[nm] = new_id
            entities_cloned += 1

    seen: set = set()
    relationships_cloned = 0
    for sid in source_universe_ids:
        relationships_cloned += _clone_induced_relationships(client, str(sid), id_map, seen)

    return {
        "new_universe_id": new_uid,
        "entities_cloned": entities_cloned,
        "relationships_cloned": relationships_cloned,
        "sources_merged": len(sources),
        "duplicates_merged": duplicates_merged,
    }
