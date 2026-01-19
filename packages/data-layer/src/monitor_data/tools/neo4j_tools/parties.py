"""
Auto-extracted module.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.base import PartyStatus
from monitor_data.schemas.parties import (
    PartyCreate,
    PartyResponse,
    PartyFilter,
    AddPartyMember,
    RemovePartyMember,
    SetActivePC,
    PartyMemberInfo,
)


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


