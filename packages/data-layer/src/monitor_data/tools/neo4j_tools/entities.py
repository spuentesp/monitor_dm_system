"""
Neo4j Entity Tools for MONITOR Data Layer.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.tools.neo4j_tools._helpers import verify_node_exists
from monitor_data.schemas.entities import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntityFilter,
    EntityListResponse,
    StateTagsUpdate,
    BatchError,
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
    verify_node_exists(client, "Universe", params.universe_id)

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
    entity_id = params.id or uuid4()
    created_at = datetime.now(timezone.utc)

    # Base properties for all entities
    # Serialize properties to JSON string for Neo4j compatibility
    entity_props: Dict[str, Any] = {
        "id": str(entity_id),
        "universe_id": str(params.universe_id),
        "name": params.name,
        "entity_type": params.entity_type.value,
        "sub_type": params.sub_type or "",
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
        sub_type=e.get("sub_type") or None,
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=json.loads(e.get("properties", "{}"))
        if isinstance(e.get("properties"), str)
        else e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(e["archetype_id"]) if e.get("archetype_id") else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"].to_native()
        if hasattr(e["created_at"], "to_native")
        else e["created_at"],
        updated_at=e.get("updated_at").to_native()
        if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native")
        else e.get("updated_at"),
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
        sub_type=e.get("sub_type") or None,
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=json.loads(e.get("properties", "{}"))
        if isinstance(e.get("properties"), str)
        else e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(archetype_id) if archetype_id else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"].to_native()
        if hasattr(e["created_at"], "to_native")
        else e["created_at"],
        updated_at=e.get("updated_at").to_native()
        if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native")
        else e.get("updated_at"),
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

    if filters.name:
        params["name"] = " ".join(filters.name.split())

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

    params["offset"] = filters.offset
    params["limit"] = filters.limit

    # Count total + page results
    if filters.name:
        count_query = f"""
        CALL db.index.fulltext.queryNodes('entity_text_idx', $name) YIELD node AS e, score
        {where_clause}
        RETURN count(DISTINCT e) as total
        """
        count_result = client.execute_read(count_query, params)
        total = count_result[0]["total"] if count_result else 0

        list_query = f"""
        CALL db.index.fulltext.queryNodes('entity_text_idx', $name) YIELD node AS e, score
        {where_clause}
        OPTIONAL MATCH (e)-[:DERIVES_FROM]->(a:Entity)
        RETURN e, a.id as archetype_id, score
        ORDER BY score DESC, {sort_field} {sort_order}
        SKIP $offset
        LIMIT $limit
        """
    else:
        count_query = f"""
        MATCH (e:Entity)
        {where_clause}
        RETURN count(e) as total
        """
        count_result = client.execute_read(count_query, params)
        total = count_result[0]["total"] if count_result else 0

        list_query = f"""
        MATCH (e:Entity)
        {where_clause}
        OPTIONAL MATCH (e)-[:DERIVES_FROM]->(a:Entity)
        RETURN e, a.id as archetype_id
        ORDER BY {sort_field} {sort_order}
        SKIP $offset
        LIMIT $limit
        """

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
                sub_type=e.get("sub_type") or None,
                is_archetype=e["is_archetype"],
                description=e["description"],
                properties=json.loads(e.get("properties", "{}"))
                if isinstance(e.get("properties"), str)
                else e.get("properties", {}),
                state_tags=e.get("state_tags", []),
                archetype_id=UUID(archetype_id) if archetype_id else None,
                canon_level=e["canon_level"],
                confidence=e["confidence"],
                authority=e["authority"],
                created_at=e["created_at"].to_native()
                if hasattr(e["created_at"], "to_native")
                else e["created_at"],
                updated_at=e.get("updated_at").to_native()
                if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native")
                else e.get("updated_at"),
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

    canon_level = getattr(params, "canon_level", None)
    if canon_level is not None:
        set_clauses.append("e.canon_level = $canon_level")
        update_params["canon_level"] = canon_level.value

    confidence = getattr(params, "confidence", None)
    if confidence is not None:
        set_clauses.append("e.confidence = $confidence")
        update_params["confidence"] = confidence

    # Optional backwards-compatible state-tag updates
    state_tags_update = getattr(params, "state_tags_update", None)
    if state_tags_update:
        if state_tags_update.add:
            set_clauses.append("e.state_tags = apoc.coll.toSet(e.state_tags + $add_tags)")
            update_params["add_tags"] = state_tags_update.add
        if state_tags_update.remove:
            set_clauses.append("e.state_tags = [x IN e.state_tags WHERE NOT x IN $remove_tags]")
            update_params["remove_tags"] = state_tags_update.remove

    if not set_clauses:
        existing = neo4j_get_entity(entity_id)  # Reuse getter logic which now includes fixes
        if existing is None:
            raise ValueError(f"Entity {entity_id} not found")
        return existing

    # Always update updated_at
    set_clauses.append("e.updated_at = datetime($updated_at)")
    update_params["updated_at"] = datetime.now(timezone.utc).isoformat()

    set_clause = ", ".join(set_clauses)
    update_query = "MATCH (e:Entity {id: $id})\nSET " + set_clause + "\nRETURN e"

    result = client.execute_write(update_query, update_params)
    e = result[0]["e"]

    return EntityResponse(
        id=UUID(e["id"]),
        universe_id=UUID(e["universe_id"]),
        name=e["name"],
        entity_type=e["entity_type"],
        sub_type=e.get("sub_type") or None,
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=json.loads(e.get("properties", "{}"))
        if isinstance(e.get("properties"), str)
        else e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(archetype_id) if archetype_id else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"].to_native()
        if hasattr(e["created_at"], "to_native")
        else e["created_at"],
        updated_at=e.get("updated_at").to_native()
        if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native")
        else e.get("updated_at"),
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
    verify_node_exists(client, "Entity", entity_id)

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
        update_parts.append("e.state_tags = [tag IN e.state_tags WHERE NOT tag IN $remove_tags]")
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
    SET {", ".join(update_parts)}
    WITH e
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
        sub_type=e.get("sub_type") or None,
        is_archetype=e["is_archetype"],
        description=e["description"],
        properties=json.loads(e.get("properties", "{}"))
        if isinstance(e.get("properties"), str)
        else e.get("properties", {}),
        state_tags=e.get("state_tags", []),
        archetype_id=UUID(archetype_id) if archetype_id else None,
        canon_level=e["canon_level"],
        confidence=e["confidence"],
        authority=e["authority"],
        created_at=e["created_at"].to_native()
        if hasattr(e["created_at"], "to_native")
        else e["created_at"],
        updated_at=e.get("updated_at").to_native()
        if e.get("updated_at") and hasattr(e.get("updated_at"), "to_native")
        else e.get("updated_at"),
    )


def neo4j_tick_agendas(universe_id: str) -> list[str]:
    """
    Find all NPCs with active agendas in the universe and advance them.

    This is a stub for v1.0 readiness; real logic will involve LLM agent ticking.
    For now, it just returns an empty list to satisfy the interface.
    """
    return []


def neo4j_save_entity_as_template(entity_id: UUID, template_name: str) -> dict:
    """
    Clone an existing entity as an EntityTemplate node in Neo4j.

    Creates a new EntityTemplate node that copies the entity's properties,
    entity_type, and state_tags. The template can then be used to instantiate
    new entities with similar characteristics.

    Authority: CanonKeeper only
    Use Case: M-31

    Args:
        entity_id: UUID of the entity to clone as a template.
        template_name: Name for the new template.

    Returns:
        Dict with template_id, name, entity_type, and properties.

    Raises:
        ValueError: If the entity doesn't exist.
    """
    client = get_neo4j_client()

    # Fetch the source entity
    query = """
    MATCH (e:Entity {entity_id: $entity_id})
    RETURN e.entity_id AS entity_id,
           e.name AS name,
           e.entity_type AS entity_type,
           e.description AS description,
           e.properties AS properties,
           e.state_tags AS state_tags,
           e.universe_id AS universe_id
    """
    result = client.execute_query(query, entity_id=str(entity_id))
    records = [dict(r) for r in result]

    if not records:
        raise ValueError(f"Entity {entity_id} not found")

    source = records[0]
    template_id = str(uuid4())

    # Create the template node
    create_query = """
    CREATE (t:EntityTemplate:Entity {
        entity_id: $template_id,
        name: $template_name,
        entity_type: $entity_type,
        description: $description,
        properties: $properties,
        state_tags: $state_tags,
        universe_id: $universe_id,
        source_entity_id: $source_entity_id,
        created_at: datetime(),
        updated_at: datetime()
    })
    RETURN t.entity_id AS template_id,
           t.name AS name,
           t.entity_type AS entity_type
    """
    result = client.execute_query(
        create_query,
        template_id=template_id,
        template_name=template_name,
        entity_type=source.get("entity_type", "unknown"),
        description=source.get("description", ""),
        properties=source.get("properties", {}),
        state_tags=source.get("state_tags", []),
        universe_id=source.get("universe_id", ""),
        source_entity_id=str(entity_id),
    )
    records = [dict(r) for r in result]

    if not records:
        raise ValueError(f"Failed to create template from entity {entity_id}")

    return {
        "template_id": records[0]["template_id"],
        "name": records[0]["name"],
        "entity_type": records[0]["entity_type"],
    }


# =============================================================================
# STANDALONE CHARACTER LINKING (GAP-C, GAP-F)
# =============================================================================


def neo4j_link_to_archetype(entity_id: UUID, archetype_id: UUID) -> dict:
    """
    Create a DERIVES_FROM relationship from an entity to an archetype.

    Used to link standalone characters (or entity instances) to their
    archetype in Neo4j, enabling property inheritance and archetype queries.

    Authority: CanonKeeper, Narrator
    Use Case: GAP-C

    Args:
        entity_id: UUID of the entity to link.
        archetype_id: UUID of the archetype to link to.

    Returns:
        Dict with entity_id, archetype_id, and relationship type.

    Raises:
        ValueError: If either entity doesn't exist.
    """
    client = get_neo4j_client()

    # Verify both entities exist
    verify_query = """
    MATCH (e:Entity {id: $entity_id})
    MATCH (a:Entity {id: $archetype_id})
    RETURN e.id AS eid, a.id AS aid
    """
    result = client.execute_query(
        verify_query,
        entity_id=str(entity_id),
        archetype_id=str(archetype_id),
    )
    records = [dict(r) for r in result]

    if not records:
        raise ValueError(f"Entity {entity_id} or archetype {archetype_id} not found")

    # Check if relationship already exists
    check_query = """
    MATCH (e:Entity {id: $entity_id})-[r:DERIVES_FROM]->(a:Entity {id: $archetype_id})
    RETURN r
    """
    existing = client.execute_query(
        check_query,
        entity_id=str(entity_id),
        archetype_id=str(archetype_id),
    )
    if list(existing):
        return {
            "entity_id": str(entity_id),
            "archetype_id": str(archetype_id),
            "relationship": "DERIVES_FROM",
            "status": "already_exists",
        }

    # Create the relationship
    link_query = """
    MATCH (e:Entity {id: $entity_id})
    MATCH (a:Entity {id: $archetype_id})
    CREATE (e)-[:DERIVES_FROM]->(a)
    RETURN e.id AS eid, a.id AS aid
    """
    client.execute_write(
        link_query,
        entity_id=str(entity_id),
        archetype_id=str(archetype_id),
    )

    return {
        "entity_id": str(entity_id),
        "archetype_id": str(archetype_id),
        "relationship": "DERIVES_FROM",
        "status": "created",
    }


def neo4j_create_character_relationship(
    from_id: UUID,
    to_id: UUID,
    rel_type: str,
    properties: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Create a relationship between two characters (standalone or entity).

    Supports creating relationships like ALLY_OF, RIVAL_OF, MENTOR_OF, etc.
    between any two characters regardless of whether they are standalone
    MongoDB characters or Neo4j entities.

    Authority: CanonKeeper, Narrator
    Use Case: GAP-F

    Args:
        from_id: UUID of the source character.
        to_id: UUID of the target character.
        rel_type: Relationship type (e.g., 'ALLY_OF', 'RIVAL_OF').
        properties: Optional dict of relationship properties.

    Returns:
        Dict with from_id, to_id, relationship type, and status.

    Raises:
        ValueError: If either character doesn't exist.
    """
    client = get_neo4j_client()
    props = properties or {}

    # Verify both entities exist
    verify_query = """
    MATCH (a:Entity {id: $from_id})
    MATCH (b:Entity {id: $to_id})
    RETURN a.id AS aid, b.id AS bid
    """
    result = client.execute_query(
        verify_query,
        from_id=str(from_id),
        to_id=str(to_id),
    )
    records = [dict(r) for r in result]

    if not records:
        raise ValueError(f"Character {from_id} or {to_id} not found in Neo4j")

    # Create the relationship
    # Sanitize rel_type to prevent Cypher injection
    safe_types = {
        "ALLY_OF",
        "RIVAL_OF",
        "MENTOR_OF",
        "STUDENT_OF",
        "FAMILY_OF",
        "ENEMY_OF",
        "MEMBER_OF",
        "LEADER_OF",
        "SUBORDINATE_OF",
        "FRIEND_OF",
        "LOVER_OF",
        "OWES",
        "KNOWS",
        "SERVES",
        "COMMANDS",
        "DERIVES_FROM",
    }
    if rel_type not in safe_types:
        raise ValueError(
            f"Invalid relationship type: {rel_type}. "
            f"Must be one of: {', '.join(sorted(safe_types))}"
        )

    create_query = """
    MATCH (a:Entity {id: $from_id})
    MATCH (b:Entity {id: $to_id})
    CREATE (a)-[r:RELATIONSHIP {rel_type: $rel_type, properties: $props}]->(b)
    RETURN type(r) AS rel_type, a.id AS from_id, b.id AS to_id
    """
    client.execute_write(
        create_query,
        from_id=str(from_id),
        to_id=str(to_id),
        rel_type=rel_type,
        props=props,
    )

    return {
        "from_id": str(from_id),
        "to_id": str(to_id),
        "relationship_type": rel_type,
        "properties": props,
        "status": "created",
    }


def neo4j_save_template(entity_id: str, template_name: str) -> str:
    """Clone an entity as an EntityTemplate."""
    from monitor_data.db.neo4j import get_neo4j_client
    import uuid

    client = get_neo4j_client()
    new_id = str(uuid.uuid4())

    q = """
    MATCH (e:Entity {id: $entity_id})
    CREATE (t:EntityTemplate:Entity {
        id: $new_id,
        name: $template_name,
        properties: e.properties
    })
    RETURN t.id as id
    """
    res = client.execute_write(
        q, {"entity_id": entity_id, "new_id": new_id, "template_name": template_name}
    )
    return res[0]["id"] if res else ""


def neo4j_batch_create_entities(
    requests: List[EntityCreate],
    continue_on_error: bool = False,
) -> Dict[str, Any]:
    """
    Create multiple Entity nodes in a single operation.

    Authority: CanonKeeper only
    Use Case: DL-2, M-12

    Args:
        requests: List of EntityCreate parameters (1-100 items)
        continue_on_error: If True, continue processing after an error

    Returns:
        Dict with created entities, counts, and errors
    """

    if len(requests) > 100:
        raise ValueError("Maximum 100 entities per batch")
    if len(requests) < 1:
        raise ValueError("At least 1 entity required")

    created: List[EntityResponse] = []
    errors: List[Dict[str, Any]] = []

    for i, params in enumerate(requests):
        try:
            entity = neo4j_create_entity(params)
            created.append(entity)
        except Exception as exc:  # noqa: BLE001
            batch_err = BatchError(
                index=i,
                entity_id=getattr(params, "id", None),
                message=str(exc),
                code=getattr(exc, "code", None) or "CREATE_FAILED",
            )
            errors.append(batch_err.model_dump())
            if not continue_on_error:
                break

    return {
        "entities": [e.model_dump() if hasattr(e, "model_dump") else e for e in created],
        "total": len(requests),
        "succeeded": len(created),
        "failed": len(errors),
        "errors": errors,
    }


def neo4j_batch_update_entities(
    updates: List[Tuple[UUID, EntityUpdate]],
    continue_on_error: bool = False,
) -> Dict[str, Any]:
    """
    Update multiple entities in a single operation.

    Authority: CanonKeeper only
    Use Case: DL-2

    Args:
        updates: List of (entity_id, EntityUpdate) tuples (1-100 items)
        continue_on_error: If True, continue after an error

    Returns:
        Dict with updated entities, counts, and errors
    """

    if len(updates) > 100:
        raise ValueError("Maximum 100 updates per batch")
    if len(updates) < 1:
        raise ValueError("At least 1 update required")

    updated: List[EntityResponse] = []
    errors: List[Dict[str, Any]] = []

    for i, (entity_id, params) in enumerate(updates):
        try:
            entity = neo4j_update_entity(entity_id, params)
            updated.append(entity)
        except Exception as exc:  # noqa: BLE001
            batch_err = BatchError(
                index=i,
                entity_id=entity_id,
                message=str(exc),
                code=getattr(exc, "code", None) or "UPDATE_FAILED",
            )
            errors.append(batch_err.model_dump())
            if not continue_on_error:
                break

    return {
        "entities": [e.model_dump() if hasattr(e, "model_dump") else e for e in updated],
        "total": len(updates),
        "succeeded": len(updated),
        "failed": len(errors),
        "errors": errors,
    }


def neo4j_batch_delete_entities(
    entity_ids: List[UUID],
    force: bool = False,
    continue_on_error: bool = False,
) -> Dict[str, Any]:
    """
    Delete multiple entities in a single operation.

    Authority: CanonKeeper only
    Use Case: DL-2, M-12

    Args:
        entity_ids: List of entity UUIDs to delete (1-100 items)
        force: Force delete even if entity has relationships
        continue_on_error: If True, continue after an error

    Returns:
        Dict with deleted IDs, counts, and errors
    """

    if len(entity_ids) > 100:
        raise ValueError("Maximum 100 entities per batch")
    if len(entity_ids) < 1:
        raise ValueError("At least 1 entity ID required")

    deleted: List[str] = []
    errors: List[Dict[str, Any]] = []

    for i, entity_id in enumerate(entity_ids):
        try:
            result = neo4j_delete_entity(entity_id, force=force)
            if result.get("status") == "deleted":
                deleted.append(str(entity_id))
            else:
                errors.append(
                    {
                        "index": i,
                        "entity_id": entity_id,
                        "message": result.get("message", "Delete failed"),
                        "code": result.get("code", "DELETE_FAILED"),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "index": i,
                    "entity_id": entity_id,
                    "message": str(exc),
                    "code": getattr(exc, "code", None) or "DELETE_FAILED",
                }
            )
            if not continue_on_error:
                break

    return {
        "deleted": deleted,
        "total": len(entity_ids),
        "succeeded": len(deleted),
        "failed": len(errors),
        "errors": errors,
    }
