"""
Neo4j Entity Tools for MONITOR Data Layer.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from uuid import UUID, uuid4

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.entities import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntityFilter,
    EntityListResponse,
    StateTagsUpdate,
)

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
    # Serialize properties to JSON string for Neo4j compatibility
    entity_props: Dict[str, Any] = {
        "id": str(entity_id),
        "universe_id": str(params.universe_id),
        "name": params.name,
        "entity_type": params.entity_type.value,
        "is_archetype": params.is_archetype,
        "description": params.description,
        "properties": json.dumps(params.properties),
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
        properties=json.loads(e.get("properties", "{}")) if isinstance(e.get("properties"), str) else e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(e["archetype_id"]) if e.get("archetype_id") else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"].to_native() if hasattr(e["created_at"], "to_native") else e["created_at"],
        updated_at=e.get("updated_at").to_native() if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native") else e.get("updated_at"),
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
        properties=json.loads(e.get("properties", "{}")) if isinstance(e.get("properties"), str) else e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(archetype_id) if archetype_id else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"].to_native() if hasattr(e["created_at"], "to_native") else e["created_at"],
        updated_at=e.get("updated_at").to_native() if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native") else e.get("updated_at"),
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
                properties=json.loads(e.get("properties", "{}")) if isinstance(e.get("properties"), str) else e.get("properties", {}),
                state_tags=e.get("state_tags", []),
                archetype_id=UUID(archetype_id) if archetype_id else None,
                canon_level=e["canon_level"],
                confidence=e["confidence"],
                authority=e["authority"],
                created_at=e["created_at"].to_native() if hasattr(e["created_at"], "to_native") else e["created_at"],
                updated_at=e.get("updated_at").to_native() if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native") else e.get("updated_at"),
            )
        )

    return EntityListResponse(
        entities=entities, total=total, limit=filters.limit, offset=filters.offset
    )


def neo4j_update_entity(entity_id: UUID, params: EntityUpdate) -> EntityResponse:
    """
    Update mutable fields of an Entity.

    Authority: CanonKeeper only
    Use Case: DL-2

    Args:
        entity_id: UUID of the entity to update
        params: Update parameters

    Returns:
        EntityResponse with updated entity data

    Raises:
        ValueError: If entity doesn't exist or verification fails
    """
    client = get_neo4j_client()

    # Verify entity exists
    verify_query = """
    MATCH (e:Entity {id: $id})
    OPTIONAL MATCH (e)-[:DERIVES_FROM]->(a:Entity)
    RETURN e, a.id as archetype_id
    """
    verify_result = client.execute_read(verify_query, {"id": str(entity_id)})
    if not verify_result:
        raise ValueError(f"Entity {entity_id} not found")
    
    current_e = verify_result[0]["e"]
    archetype_id = verify_result[0].get("archetype_id")

    set_clauses = []
    update_params: Dict[str, Any] = {"id": str(entity_id)}

    if params.name is not None:
        set_clauses.append("e.name = $name")
        update_params["name"] = params.name

    if params.description is not None:
        set_clauses.append("e.description = $description")
        update_params["description"] = params.description

    if params.properties is not None:
        set_clauses.append("e.properties = $properties")
        update_params["properties"] = json.dumps(params.properties)

    if params.canon_level is not None:
        set_clauses.append("e.canon_level = $canon_level")
        update_params["canon_level"] = params.canon_level.value

    if params.confidence is not None:
        set_clauses.append("e.confidence = $confidence")
        update_params["confidence"] = params.confidence
        
    # State Tag operations
    if params.state_tags_update:
        tag_update = params.state_tags_update
        if tag_update.add:
            # Cypher to add tags avoiding duplicates
            set_clauses.append("e.state_tags = apoc.coll.toSet(e.state_tags + $add_tags)")
            update_params["add_tags"] = tag_update.add
        if tag_update.remove:
            # Cypher to remove tags
            set_clauses.append("e.state_tags = [x IN e.state_tags WHERE NOT x IN $remove_tags]")
            update_params["remove_tags"] = tag_update.remove

    if not set_clauses:
        return neo4j_get_entity(entity_id) # Reuse getter logic which now includes fixes

    # Always update updated_at
    set_clauses.append("e.updated_at = datetime($updated_at)")
    update_params["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    set_clause = ", ".join(set_clauses)
    update_query = (
        "MATCH (e:Entity {id: $id})\n" "SET " + set_clause + "\n" "RETURN e"
    )

    result = client.execute_write(update_query, update_params)
    e = result[0]["e"]

    return EntityResponse(
        id=UUID(e["id"]),
        universe_id=UUID(e["universe_id"]),
        name=e["name"],
        entity_type=e["entity_type"],
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=json.loads(e.get("properties", "{}")) if isinstance(e.get("properties"), str) else e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(archetype_id) if archetype_id else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"].to_native() if hasattr(e["created_at"], "to_native") else e["created_at"],
        updated_at=e.get("updated_at").to_native() if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native") else e.get("updated_at"),
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
