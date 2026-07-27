"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.base import (
    CombatSide,
    CombatStatus,
)
from monitor_data.schemas.combat import (
    AddCombatLogEntry,
    AddCombatParticipant,
    CombatCreate,
    CombatEnvironment,
    CombatFilter,
    CombatListResponse,
    CombatLogEntry,
    CombatOutcome,
    CombatParticipant,
    CombatResponse,
    CombatUpdate,
    Condition,
    RemoveCombatParticipant,
    SetCombatOutcome,
    UpdateCombatParticipant,
)

# =============================================================================
# COMBAT OPERATIONS (DL-25)
# =============================================================================


def _convert_combat_doc_to_response(combat_doc: dict[str, Any]) -> CombatResponse:
    """
    Convert a combat document from MongoDB to a CombatResponse object.

    Args:
        combat_doc: Combat data from MongoDB document

    Returns:
        CombatResponse object
    """
    # Convert participants
    participants = [
        CombatParticipant(
            entity_id=UUID(p["entity_id"]),
            name=p["name"],
            side=CombatSide(p["side"]),
            initiative_value=p.get("initiative_value"),
            is_active=p.get("is_active", True),
            conditions=[Condition(**c) for c in p.get("conditions", [])],
            resources=p.get("resources", {}),
            position=p.get("position"),
        )
        for p in combat_doc.get("participants", [])
    ]

    # Convert environment
    env_data = combat_doc.get("environment", {})
    environment = CombatEnvironment(**env_data) if env_data else CombatEnvironment()

    # Convert combat log
    combat_log = [
        CombatLogEntry(
            round=entry["round"],
            turn=entry["turn"],
            actor_id=UUID(entry["actor_id"]),
            action=entry["action"],
            resolution_id=(UUID(entry["resolution_id"]) if entry.get("resolution_id") else None),
            summary=entry["summary"],
            timestamp=entry["timestamp"],
        )
        for entry in combat_doc.get("combat_log", [])
    ]

    # Convert outcome
    outcome_data = combat_doc.get("outcome")
    outcome = None
    if outcome_data:
        outcome = CombatOutcome(
            result=outcome_data["result"],
            winning_side=(CombatSide(outcome_data["winning_side"]) if outcome_data.get("winning_side") else None),
            survivors=[UUID(sid) for sid in outcome_data.get("survivors", [])],
            casualties=[UUID(cid) for cid in outcome_data.get("casualties", [])],
            loot=outcome_data.get("loot", []),
            xp_awarded=outcome_data.get("xp_awarded"),
            metadata=outcome_data.get("metadata", {}),
        )

    return CombatResponse(
        id=UUID(combat_doc["encounter_id"]),
        scene_id=UUID(combat_doc["scene_id"]),
        story_id=UUID(combat_doc["story_id"]),
        status=CombatStatus(combat_doc.get("status", "initializing")),
        round=combat_doc.get("round", 0),
        turn_order=[UUID(tid) for tid in combat_doc.get("turn_order", [])],
        current_turn_index=combat_doc.get("current_turn_index", 0),
        participants=participants,
        environment=environment,
        combat_log=combat_log,
        outcome=outcome,
        created_at=combat_doc["created_at"],
        updated_at=combat_doc.get("updated_at"),
    )


def mongodb_create_combat(params: CombatCreate) -> CombatResponse:
    """
    Create a new combat encounter.

    Args:
        params: Combat creation parameters

    Returns:
        CombatResponse with created combat data

    Raises:
        ValueError: If scene_id or story_id doesn't exist
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Validate scene exists
    scenes_collection = mongodb.get_collection("scenes")
    scene = scenes_collection.find_one({"scene_id": str(params.scene_id)})
    if not scene:
        raise ValueError(f"Scene {params.scene_id} not found")

    # Validate story exists (via Neo4j)
    neo4j_client = get_neo4j_client()
    story_exists = neo4j_client.execute_read(
        "MATCH (s:Story {id: $story_id}) RETURN s.id AS story_id",
        {"story_id": str(params.story_id)},
    )
    if not story_exists:
        raise ValueError(f"Story {params.story_id} not found")

    now = datetime.now(UTC)
    encounter_id = uuid4()

    # Prepare environment
    environment = params.environment if params.environment else CombatEnvironment()

    combat_doc = {
        "encounter_id": str(encounter_id),
        "scene_id": str(params.scene_id),
        "story_id": str(params.story_id),
        "status": "initializing",
        "round": 0,
        "turn_order": [],
        "current_turn_index": 0,
        "participants": [p.model_dump(mode="json") for p in params.participants],
        "environment": environment.model_dump(mode="json"),
        "combat_log": [],
        "outcome": None,
        "created_at": now,
        "updated_at": None,
    }

    combats_collection.insert_one(combat_doc)

    return _convert_combat_doc_to_response(combat_doc)


def mongodb_get_combat(encounter_id: UUID) -> CombatResponse | None:
    """
    Get a combat encounter by ID.

    Args:
        encounter_id: Combat encounter UUID

    Returns:
        CombatResponse or None if not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    combat_doc = combats_collection.find_one({"encounter_id": str(encounter_id)})
    if not combat_doc:
        return None

    return _convert_combat_doc_to_response(combat_doc)


def mongodb_list_combats(params: CombatFilter) -> CombatListResponse:
    """
    List combat encounters with filtering.

    Args:
        params: Filter parameters

    Returns:
        CombatListResponse with matching combats
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Build query
    query: dict[str, Any] = {}
    if params.scene_id:
        query["scene_id"] = str(params.scene_id)
    if params.story_id:
        query["story_id"] = str(params.story_id)
    if params.status:
        query["status"] = params.status

    # Count total
    total = combats_collection.count_documents(query)

    # Get page
    cursor = combats_collection.find(query).sort("created_at", -1).skip(params.offset).limit(params.limit)

    combats = [_convert_combat_doc_to_response(doc) for doc in cursor]

    return CombatListResponse(
        combats=combats,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_update_combat(encounter_id: UUID, params: CombatUpdate) -> CombatResponse:
    """
    Update a combat encounter.

    Args:
        encounter_id: Combat encounter UUID
        params: Update parameters

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {encounter_id} not found")

    now = datetime.now(UTC)
    update_doc: dict[str, Any] = {"updated_at": now}

    if params.status is not None:
        update_doc["status"] = params.status.value
    if params.round is not None:
        update_doc["round"] = params.round
    if params.turn_order is not None:
        update_doc["turn_order"] = [str(tid) for tid in params.turn_order]
    if params.current_turn_index is not None:
        update_doc["current_turn_index"] = params.current_turn_index

    combats_collection.update_one({"encounter_id": str(encounter_id)}, {"$set": update_doc})

    updated = mongodb_get_combat(encounter_id)
    if not updated:
        raise ValueError(f"Combat encounter {encounter_id} not found after update")

    return updated


def mongodb_delete_combat(encounter_id: UUID) -> bool:
    """
    Delete a combat encounter.

    Args:
        encounter_id: Combat encounter UUID

    Returns:
        True if deleted, False if not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    result = combats_collection.delete_one({"encounter_id": str(encounter_id)})
    return result.deleted_count > 0


def mongodb_add_combat_participant(params: AddCombatParticipant) -> CombatResponse:
    """
    Add a participant to a combat encounter.

    Args:
        params: Participant data

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat not found or entity already participating
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    # Check if entity already participating
    for p in combat.get("participants", []):
        if p["entity_id"] == str(params.entity_id):
            raise ValueError(f"Entity {params.entity_id} is already in combat")

    # Create participant
    participant = CombatParticipant(
        entity_id=params.entity_id,
        name=params.name,
        side=params.side,
        initiative_value=params.initiative_value,
        is_active=True,
        conditions=[],
        resources=params.resources if params.resources else {},
        position=None,
    )

    now = datetime.now(UTC)
    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)},
        {
            "$push": {"participants": participant.model_dump(mode="json")},
            "$set": {"updated_at": now},
        },
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(f"Combat encounter {params.encounter_id} not found after update")

    return updated


def mongodb_update_combat_participant(
    params: UpdateCombatParticipant,
) -> CombatResponse:
    """
    Update a combat participant.

    Args:
        params: Participant update data

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat or participant not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    # Find participant index
    participants = combat.get("participants", [])
    participant_idx = None
    for i, p in enumerate(participants):
        if p["entity_id"] == str(params.entity_id):
            participant_idx = i
            break

    if participant_idx is None:
        raise ValueError(f"Participant {params.entity_id} not found in combat {params.encounter_id}")

    # Build update
    now = datetime.now(UTC)
    update_fields: dict[str, Any] = {}

    if params.initiative_value is not None:
        update_fields[f"participants.{participant_idx}.initiative_value"] = params.initiative_value
    if params.is_active is not None:
        update_fields[f"participants.{participant_idx}.is_active"] = params.is_active
    if params.conditions is not None:
        update_fields[f"participants.{participant_idx}.conditions"] = [
            c.model_dump(mode="json") for c in params.conditions
        ]
    if params.resources is not None:
        update_fields[f"participants.{participant_idx}.resources"] = params.resources
    if params.position is not None:
        update_fields[f"participants.{participant_idx}.position"] = params.position

    update_fields["updated_at"] = now

    combats_collection.update_one({"encounter_id": str(params.encounter_id)}, {"$set": update_fields})

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(f"Combat encounter {params.encounter_id} not found after update")

    return updated


def mongodb_remove_combat_participant(
    params: RemoveCombatParticipant,
) -> CombatResponse:
    """
    Remove a participant from a combat encounter.

    Args:
        params: Removal parameters

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat or participant not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    # Verify participant exists
    participants = combat.get("participants", [])
    found = any(p["entity_id"] == str(params.entity_id) for p in participants)
    if not found:
        raise ValueError(f"Participant {params.entity_id} not found in combat {params.encounter_id}")

    now = datetime.now(UTC)
    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)},
        {
            "$pull": {"participants": {"entity_id": str(params.entity_id)}},
            "$set": {"updated_at": now},
        },
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(f"Combat encounter {params.encounter_id} not found after update")

    return updated


def mongodb_add_combat_log_entry(params: AddCombatLogEntry) -> CombatResponse:
    """
    Add an entry to the combat log.

    Args:
        params: Log entry data

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    now = datetime.now(UTC)
    log_entry = CombatLogEntry(
        round=params.round,
        turn=params.turn,
        actor_id=params.actor_id,
        action=params.action,
        resolution_id=params.resolution_id,
        summary=params.summary,
        timestamp=now,
    )

    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)},
        {
            "$push": {"combat_log": log_entry.model_dump(mode="json")},
            "$set": {"updated_at": now},
        },
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(f"Combat encounter {params.encounter_id} not found after update")

    return updated


def mongodb_set_combat_outcome(params: SetCombatOutcome) -> CombatResponse:
    """
    Set the final outcome of a combat encounter.

    Args:
        params: Outcome data

    Returns:
        Updated CombatResponse

    Raises:
        ValueError: If combat not found
    """
    mongodb = get_mongodb_client()
    combats_collection = mongodb.get_collection("combat_encounters")

    # Verify combat exists
    combat = combats_collection.find_one({"encounter_id": str(params.encounter_id)})
    if not combat:
        raise ValueError(f"Combat encounter {params.encounter_id} not found")

    outcome = CombatOutcome(
        result=params.result,
        winning_side=params.winning_side,
        survivors=params.survivors if params.survivors else [],
        casualties=params.casualties if params.casualties else [],
        loot=params.loot if params.loot else [],
        xp_awarded=params.xp_awarded,
        metadata={},
    )

    now = datetime.now(UTC)
    combats_collection.update_one(
        {"encounter_id": str(params.encounter_id)},
        {
            "$set": {
                "outcome": outcome.model_dump(mode="json"),
                "status": "resolved",
                "updated_at": now,
            }
        },
    )

    updated = mongodb_get_combat(params.encounter_id)
    if not updated:
        raise ValueError(f"Combat encounter {params.encounter_id} not found after update")

    return updated
