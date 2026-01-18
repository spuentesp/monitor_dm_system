"""
Auto-extracted module.
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.base import CanonLevel
from monitor_data.schemas.relationships import (
    RelationshipCreate,
    RelationshipResponse,
    RelationshipUpdate,
    RelationshipFilter,
    RelationshipListResponse,
    RelationshipType,
    Direction,
    StateTagUpdate,
    StateTagResponse,
)


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
