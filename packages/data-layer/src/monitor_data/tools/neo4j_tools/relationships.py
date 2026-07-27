"""
Auto-extracted module.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.relationships import (
    Direction,
    RelationshipCategory,
    RelationshipCreate,
    RelationshipFilter,
    RelationshipListResponse,
    RelationshipResponse,
    RelationshipSubcategory,
    RelationshipType,
    RelationshipUpdate,
    StateTagResponse,
    StateTagUpdate,
)
from monitor_data.tools.neo4j_tools._helpers import verify_node_exists


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
    verify_node_exists(client, "Entity", params.from_entity_id)
    verify_node_exists(client, "Entity", params.to_entity_id)

    # Validate no self-reference for relationship types where it doesn't make sense
    if params.from_entity_id == params.to_entity_id:
        # OWNS might be valid (e.g., recursive ownership), but most types are not.
        # Taxonomic/membership types are never legitimately self-referential —
        # "X is a subtype of X" / "X is part of X" is always an extraction bug
        # (live example: a name-resolution collision creating "Railroad Agent
        # SUBTYPE_OF Railroad Agent" during the 2026-07-22 Fallout ingest).
        if params.rel_type in (
            RelationshipType.KNOWS,
            RelationshipType.ALLIED_WITH,
            RelationshipType.HOSTILE_TO,
            RelationshipType.SUBTYPE_OF,
            RelationshipType.DERIVES_FROM,
            RelationshipType.INSTANCE_OF,
            RelationshipType.PART_OF,
            RelationshipType.MEMBER_OF,
            RelationshipType.SUBGROUP_OF,
        ):
            raise ValueError(f"Self-referencing relationships are not allowed for {params.rel_type.value}")

    # Create relationship with properties
    now = datetime.now(UTC)
    props = {**params.properties, "created_at": now.isoformat()}
    props["category"] = params.category.value
    if params.subcategory:
        props["subcategory"] = params.subcategory.value
    if params.tags:
        props["tags"] = params.tags

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
        category=params.category,
        subcategory=params.subcategory,
        tags=params.tags,
        properties=rel_data["props"],
        created_at=now,
    )


def neo4j_get_relationship(relationship_id: str) -> RelationshipResponse | None:
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
           type(r) as rel_type, r.category as category, r.subcategory as subcategory,
           r.tags as tags, properties(r) as props
    """

    try:
        rel_id_int = int(relationship_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid relationship ID format: must be a numeric string") from None

    result = client.execute_read(query, {"rel_id": rel_id_int})

    if not result:
        return None

    rel = result[0]
    props = rel["props"] or {}

    # Extract category and subcategory from relationship properties or separate fields
    category_str = rel.get("category") or props.get("category")
    subcategory_str = rel.get("subcategory") or props.get("subcategory")
    tags = rel.get("tags") or props.get("tags", [])

    # Parse category and subcategory
    category = RelationshipCategory(category_str) if category_str else RelationshipCategory.GENERIC
    subcategory = RelationshipSubcategory(subcategory_str) if subcategory_str else None

    return RelationshipResponse(
        relationship_id=str(rel["rel_id"]),
        from_entity_id=UUID(rel["from_id"]),
        to_entity_id=UUID(rel["to_id"]),
        rel_type=RelationshipType(rel["rel_type"]),
        category=category,
        subcategory=subcategory,
        tags=tags,
        properties=props,
        created_at=(datetime.fromisoformat(str(props.get("created_at"))) if props.get("created_at") else None),
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
    query_params: dict[str, Any] = {
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

    if params.category:
        where_clauses.append("(r.category = $category OR r.category IS NULL)")
        query_params["category"] = params.category.value

    if params.subcategory:
        where_clauses.append("(r.subcategory = $subcategory OR r.subcategory IS NULL)")
        query_params["subcategory"] = params.subcategory.value

    if params.tags:
        # Filter relationships that have all specified tags
        where_clauses.append("ALL(tag IN $tags WHERE tag IN coalesce(r.tags, []))")
        query_params["tags"] = params.tags

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
           type(r) as rel_type, r.category as category, r.subcategory as subcategory,
           r.tags as tags, properties(r) as props
    ORDER BY id(r)
    SKIP $offset
    LIMIT $limit
    """

    results = client.execute_read(data_query, query_params)

    relationships = []
    for rel in results:
        props = rel["props"] or {}

        # Extract category and subcategory from relationship properties or separate fields
        category_str = rel.get("category") or props.get("category")
        subcategory_str = rel.get("subcategory") or props.get("subcategory")
        tags = rel.get("tags") or props.get("tags", [])

        # Parse category and subcategory
        category = RelationshipCategory(category_str) if category_str else RelationshipCategory.GENERIC
        subcategory = RelationshipSubcategory(subcategory_str) if subcategory_str else None

        relationships.append(
            RelationshipResponse(
                relationship_id=str(rel["rel_id"]),
                from_entity_id=UUID(rel["from_id"]),
                to_entity_id=UUID(rel["to_id"]),
                rel_type=RelationshipType(rel["rel_type"]),
                category=category,
                subcategory=subcategory,
                tags=tags,
                properties=props,
                created_at=(datetime.fromisoformat(str(props.get("created_at"))) if props.get("created_at") else None),
            )
        )

    return RelationshipListResponse(
        relationships=relationships,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def neo4j_update_relationship(relationship_id: str, params: RelationshipUpdate) -> RelationshipResponse:
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

    # Build update clauses
    set_clauses = []
    update_params: dict[str, Any] = {"rel_id": int(relationship_id)}

    if params.properties is not None:
        set_clauses.append("r += $properties")
        update_params["properties"] = params.properties

    if params.category is not None:
        set_clauses.append("r.category = $category")
        update_params["category"] = params.category.value

    if params.subcategory is not None:
        set_clauses.append("r.subcategory = $subcategory")
        update_params["subcategory"] = params.subcategory.value

    if params.tags is not None:
        set_clauses.append("r.tags = $tags")
        update_params["tags"] = params.tags

    # Preserve created_at
    set_clauses.append("r.created_at = $created_at")
    update_params["created_at"] = existing.created_at.isoformat() if existing.created_at else None

    if not set_clauses:
        raise ValueError("At least one field must be specified for update")

    update_query = f"""
    MATCH ()-[r]->()
    WHERE id(r) = $rel_id
    SET {", ".join(set_clauses)}
    RETURN id(r) as rel_id
    """

    result = client.execute_write(update_query, update_params)

    if not result:
        raise ValueError(f"Failed to update relationship {relationship_id}")

    # Return updated relationship
    updated = neo4j_get_relationship(relationship_id)
    if not updated:
        raise ValueError(f"Relationship {relationship_id} not found after update")
    return updated


def neo4j_delete_relationship(relationship_id: str) -> dict[str, Any]:
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
        raise ValueError("Invalid relationship ID format: must be a numeric string") from None

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
            f"Cannot set state tags on archetype {params.entity_id}. State tags are only valid on entity instances."
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
