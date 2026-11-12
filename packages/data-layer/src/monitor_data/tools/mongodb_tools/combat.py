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
    CombatEnd,
    CombatEnvironment,
    CombatFilter,
    CombatListResponse,
    CombatLogEntry,
    CombatNextRound,
    CombatOutcome,
    CombatParticipant,
    CombatResponse,
    CombatSessionState,
    CombatSetInitiative,
    CombatStart,
    CombatUpdate,
    CombatUpdateCombatant,
    CombatantState,
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


# =============================================================================
# SESSION COMBAT TRACKER (CF-9 — ephemeral at-the-table state)
# =============================================================================
# Combat state for a live table encounter is ephemeral session state keyed by
# ``(universe_id, session_id)`` in MongoDB. Nothing here writes to Neo4j:
# permanent world effects leave the encounter only as ProposedChange items
# staged for CanonKeeper (CF-8 path). Tool names carry the ``mongodb_combat_``
# prefix so the MCP server's ``mongodb_`` scanner registers them.

_SESSION_COMBAT_COLLECTION = "session_combats"


def _session_combat_doc_to_state(doc: dict[str, Any]) -> CombatSessionState:
    """Convert a stored ``session_combats`` document to ``CombatSessionState``."""
    combatants = [CombatantState(**c) for c in doc.get("combatants", [])]
    return CombatSessionState(
        universe_id=UUID(doc["universe_id"]),
        session_id=doc["session_id"],
        status=CombatStatus(doc.get("status", "initiative")),
        round=doc.get("round", 1),
        turn_order=[UUID(t) for t in doc.get("turn_order", [])],
        combatants=combatants,
        story_id=UUID(doc["story_id"]) if doc.get("story_id") else None,
        scene_id=UUID(doc["scene_id"]) if doc.get("scene_id") else None,
        started_at=doc["started_at"],
        ended_at=doc.get("ended_at"),
    )


def _load_session_combat(universe_id: UUID, session_id: str) -> dict[str, Any] | None:
    """Fetch the raw session-combat document, or ``None`` if absent."""
    client = get_mongodb_client()
    collection = client.get_collection(_SESSION_COMBAT_COLLECTION)
    return collection.find_one({"universe_id": str(universe_id), "session_id": session_id})


def _save_session_combat(doc: dict[str, Any]) -> CombatSessionState:
    """Persist the document (replace) and return the canonical state."""
    client = get_mongodb_client()
    collection = client.get_collection(_SESSION_COMBAT_COLLECTION)
    collection.replace_one(
        {"universe_id": doc["universe_id"], "session_id": doc["session_id"]},
        doc,
        upsert=True,
    )
    return _session_combat_doc_to_state(doc)


def mongodb_combat_start(params: CombatStart) -> CombatSessionState:
    """Start (or restart) the session combat encounter for (universe, session).

    Restarting replaces any prior state for the same key — the GM explicitly
    asked for a fresh encounter.
    """
    now = datetime.now(UTC)
    combatants: list[dict[str, Any]] = []
    for c in params.combatants:
        if c.hp > c.max_hp:
            raise ValueError(f"{c.name}: hp ({c.hp}) cannot exceed max_hp ({c.max_hp})")
        combatants.append(
            CombatantState(
                id=uuid4(),
                name=c.name,
                side=c.side,
                hp=c.hp,
                max_hp=c.max_hp,
                temp_hp=c.temp_hp,
                conditions=list(c.conditions),
                notes=c.notes,
                entity_id=c.entity_id,
            ).model_dump(mode="json")
        )
    doc = {
        "universe_id": str(params.universe_id),
        "session_id": params.session_id,
        "status": CombatStatus.INITIATIVE.value,
        "round": 1,
        "turn_order": [],
        "combatants": combatants,
        "story_id": str(params.story_id) if params.story_id else None,
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "started_at": now,
        "ended_at": None,
    }
    return _save_session_combat(doc)


def mongodb_combat_get(universe_id: UUID, session_id: str) -> CombatSessionState | None:
    """Return the session combat state, or ``None`` if no encounter exists."""
    doc = _load_session_combat(universe_id, session_id)
    if doc is None:
        return None
    return _session_combat_doc_to_state(doc)


def mongodb_combat_update_combatant(params: CombatUpdateCombatant) -> CombatSessionState:
    """Adjust one combatant's HP / temp HP / conditions / flags / notes.

    HP math is deterministic: damage (negative ``hp_delta``) is absorbed by
    temp HP first, then by HP, floored at 0; healing is clamped to ``max_hp``.
    An absolute ``hp`` (when given) wins over ``hp_delta``. Setting ``dead``
    forces HP to 0; clearing ``dead`` does not restore HP (the GM heals
    explicitly).
    """
    doc = _load_session_combat(params.universe_id, params.session_id)
    if doc is None:
        raise ValueError(
            f"No combat encounter for session {params.session_id} in universe {params.universe_id}"
        )
    combatants = doc.get("combatants", [])
    target = next((c for c in combatants if c["id"] == str(params.combatant_id)), None)
    if target is None:
        raise ValueError(f"Combatant {params.combatant_id} not found in encounter")

    max_hp = int(target["max_hp"])
    hp = int(target["hp"])
    temp_hp = int(target.get("temp_hp", 0))

    if params.hp is not None:
        hp = max(0, min(params.hp, max_hp))
    elif params.hp_delta is not None:
        if params.hp_delta < 0:
            damage = -params.hp_delta
            absorbed = min(temp_hp, damage)
            temp_hp -= absorbed
            hp = max(0, hp - (damage - absorbed))
        else:
            hp = min(max_hp, hp + params.hp_delta)

    if params.temp_hp is not None:
        temp_hp = params.temp_hp

    conditions = list(target.get("conditions", []))
    for name in params.conditions_add:
        if name not in conditions:
            conditions.append(name)
    conditions = [c for c in conditions if c not in params.conditions_remove]

    if params.dead:
        hp = 0
        temp_hp = 0

    target["hp"] = hp
    target["temp_hp"] = temp_hp
    target["conditions"] = conditions
    if params.dead is not None:
        target["dead"] = params.dead
    if params.unconscious is not None:
        target["unconscious"] = params.unconscious
    if params.concentration is not None:
        target["concentration"] = params.concentration or None
    if params.notes is not None:
        target["notes"] = params.notes

    doc["combatants"] = combatants
    return _save_session_combat(doc)


def mongodb_combat_set_initiative(params: CombatSetInitiative) -> CombatSessionState:
    """Record initiative rolls and compute the turn order.

    Ties break on the explicit ``tiebreak`` score (higher wins), then on the
    combatant's name (alphabetical) so the order is fully deterministic.
    Combatants with no entry keep ``initiative=None`` and sort after all
    rolled combatants.
    """
    doc = _load_session_combat(params.universe_id, params.session_id)
    if doc is None:
        raise ValueError(
            f"No combat encounter for session {params.session_id} in universe {params.universe_id}"
        )
    by_id = {str(e.combatant_id): e for e in params.entries}
    combatants = doc.get("combatants", [])
    known = {c["id"] for c in combatants}
    unknown = set(by_id) - known
    if unknown:
        raise ValueError(f"Unknown combatant id(s) in initiative: {', '.join(sorted(unknown))}")

    for c in combatants:
        entry = by_id.get(c["id"])
        c["initiative"] = entry.initiative if entry else None

    def _sort_key(c: dict[str, Any]) -> tuple[float, float, str]:
        entry = by_id.get(c["id"])
        if entry is None:
            # Unrolled combatants sink to the bottom, name-stable among themselves.
            return (float("inf"), 0.0, str(c["name"]).lower())
        return (-entry.initiative, -entry.tiebreak, str(c["name"]).lower())

    ordered = sorted(combatants, key=_sort_key)
    doc["combatants"] = ordered
    doc["turn_order"] = [c["id"] for c in ordered]
    doc["status"] = CombatStatus.ACTIVE.value
    return _save_session_combat(doc)


def mongodb_combat_next_round(params: CombatNextRound) -> CombatSessionState:
    """Advance the round counter by one."""
    doc = _load_session_combat(params.universe_id, params.session_id)
    if doc is None:
        raise ValueError(
            f"No combat encounter for session {params.session_id} in universe {params.universe_id}"
        )
    if doc.get("status") == CombatStatus.RESOLVED.value:
        raise ValueError("Encounter has already ended")
    doc["round"] = int(doc.get("round", 1)) + 1
    return _save_session_combat(doc)


def mongodb_combat_end(params: CombatEnd) -> CombatSessionState:
    """End the encounter: status → RESOLVED, stamp ``ended_at``."""
    doc = _load_session_combat(params.universe_id, params.session_id)
    if doc is None:
        raise ValueError(
            f"No combat encounter for session {params.session_id} in universe {params.universe_id}"
        )
    doc["status"] = CombatStatus.RESOLVED.value
    doc["ended_at"] = datetime.now(UTC)
    return _save_session_combat(doc)
