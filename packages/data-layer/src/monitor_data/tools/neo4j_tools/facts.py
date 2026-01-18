"""
Auto-extracted module.
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.base import CanonLevel
from monitor_data.schemas.facts import (
    FactCreate,
    FactResponse,
    FactFilter,
    FactUpdate,
    EventCreate,
    EventResponse,
    EventFilter,
)


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
