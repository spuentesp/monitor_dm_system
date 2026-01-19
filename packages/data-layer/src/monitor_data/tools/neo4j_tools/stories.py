"""
Auto-extracted module.
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.base import CanonLevel, StoryStatus
from monitor_data.schemas.stories import (
    StoryCreate,
    StoryResponse,
    StoryUpdate,
    StoryFilter,
    StoryListResponse,
)
from monitor_data.schemas.story_outlines import (
    PlotThreadCreate,
    PlotThreadResponse,
    PlotThreadUpdate,
    PlotThreadFilter,
    PlotThreadListResponse,
    PlotThreadStatus,
    ThreadDeadline,
)


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
