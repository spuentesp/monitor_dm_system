"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.game_systems import (
    AttributeDefinition,
    CharacterCreationProcedure,
    ConditionDefinition,
    CoreMechanic,
    GameRule,
    GameSystemCreate,
    GameSystemListResponse,
    GameSystemResponse,
    GameSystemUpdate,
    NPCCreationRules,
    NPCStatBlock,
    ResourceDefinition,
    RuleOverrideCreate,
    RuleOverrideListResponse,
    RuleOverrideResponse,
    RuleOverrideScope,
    RuleOverrideUpdate,
    SceneryRule,
    SkillDefinition,
)

# =============================================================================
# GAME SYSTEMS & RULES (DL-20)
# =============================================================================


def _load_builtin_game_systems() -> list[dict[str, Any]]:
    """Load built-in game systems from seed data."""
    import json
    import os

    seed_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "builtin_systems.json")
    try:
        with open(seed_file, encoding="utf-8") as f:
            return cast(list[dict[str, Any]], json.load(f))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Builtin game systems seed file not found: {seed_file}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Builtin game systems seed file contains invalid JSON: {seed_file}") from exc
    except OSError as exc:
        raise RuntimeError(f"Error reading builtin game systems seed file: {seed_file}") from exc


def _ensure_builtin_systems_seeded() -> None:
    """Ensure built-in game systems are seeded in the database.

    Uses atomic upsert to prevent race conditions when multiple processes
    attempt to seed simultaneously.
    """
    mongodb = get_mongodb_client()
    systems_collection = mongodb.get_collection("game_systems")

    # Load and upsert builtin systems atomically to avoid race conditions
    builtin_systems = _load_builtin_game_systems()
    now = datetime.now(UTC)

    for system_data in builtin_systems:
        # Use name (and is_builtin) to uniquely identify each builtin system.
        # The upsert ensures only one document is inserted per system, even if
        # multiple processes run this seeding code concurrently.
        filter_doc = {
            "is_builtin": True,
            "name": system_data.get("name"),
        }
        doc: dict[str, Any] = {
            "system_id": str(uuid4()),
            "is_builtin": True,
            **system_data,
            "created_at": now,
            "updated_at": None,
        }
        systems_collection.update_one(
            filter_doc,
            {"$setOnInsert": doc},
            upsert=True,
        )


def mongodb_create_game_system(params: GameSystemCreate) -> GameSystemResponse:
    """
    Create a new game system, or update an existing one if a system with the
    same name and source_document_id already exists (upsert).

    Args:
        params: Game system creation parameters

    Returns:
        GameSystemResponse with created/updated system data

    Raises:
        ValueError: If is_builtin is True (only allowed for seed data)
    """
    if getattr(params, "is_builtin", False):
        raise ValueError("Cannot manually create builtin systems")

    # [G-8] Enforce provenance at the tool choke point. Every persisted
    # game system must carry either the source_document_id (ingested)
    # OR ``hand_authored=True`` (deliberately hand-curated) — otherwise
    # we can't tell where the rulebook came from and the field-level
    # audit can't surface it. Production paths already comply (ingestion
    # sets source_document_id, the UI hand-author editor sets
    # hand_authored=True). Direct callers (tests, scripts) must do the
    # same. See INGESTION_PIPELINE_AUDIT.md Finding 3.
    if not params.source_document_id and not getattr(params, "hand_authored", False):
        raise ValueError(
            "Game system requires provenance: set source_document_id (ingested) "
            "or hand_authored=True (deliberately hand-curated) — see "
            "INGESTION_PIPELINE_AUDIT.md Finding 3."
        )

    mongodb = get_mongodb_client()
    systems_collection = mongodb.get_collection("game_systems")

    now = datetime.now(UTC)

    # Dedup: check for existing system with same name + source_document_id
    existing_doc = None
    if params.source_document_id:
        existing_doc = systems_collection.find_one(
            {
                "name": params.name,
                "source_document_id": str(params.source_document_id),
            }
        )

    system_id = UUID(existing_doc["system_id"]) if existing_doc else uuid4()

    system_doc: dict[str, Any] = {
        "system_id": str(system_id),
        "name": params.name,
        "description": params.description,
        "version": params.version,
        "core_mechanic": params.core_mechanic.model_dump(mode="json"),
        "attributes": [attr.model_dump(mode="json") for attr in params.attributes],
        "skills": [skill.model_dump(mode="json") for skill in params.skills],
        "resources": [res.model_dump(mode="json") for res in params.resources],
        "conditions": [c.model_dump(mode="json") for c in (params.conditions or [])],
        "scenery_rules": [s.model_dump(mode="json") for s in (params.scenery_rules or [])],
        "custom_dice": params.custom_dice,
        "rules": [r.model_dump(mode="json") for r in params.rules],
        "agendas": [a.model_dump(mode="json") for a in params.agendas],
        "topologies": [t.model_dump(mode="json") for t in params.topologies],
        "character_profiles": [p.model_dump(mode="json") for p in params.character_profiles],
        "generation_templates": [g.model_dump(mode="json") for g in params.generation_templates],
        "character_creation": (
            params.character_creation.model_dump(mode="json") if params.character_creation else None
        ),
        "npc_stat_blocks": [b.model_dump(mode="json") for b in params.npc_stat_blocks],
        "npc_creation_rules": (
            params.npc_creation_rules.model_dump(mode="json") if params.npc_creation_rules else None
        ),
        "source_document_id": (str(params.source_document_id) if params.source_document_id else None),
        "is_builtin": False,
        "hand_authored": params.hand_authored,
        "needs_review": params.needs_review,
        "degenerate_reason": params.degenerate_reason,
    }

    if existing_doc:
        system_doc["created_at"] = existing_doc["created_at"]
        system_doc["updated_at"] = now
        systems_collection.replace_one({"system_id": str(system_id)}, system_doc)
    else:
        system_doc["created_at"] = now
        system_doc["updated_at"] = None
        systems_collection.insert_one(system_doc)

    return GameSystemResponse(
        id=system_id,
        name=params.name,
        description=params.description,
        version=params.version,
        core_mechanic=params.core_mechanic,
        attributes=params.attributes,
        skills=params.skills,
        resources=params.resources,
        conditions=params.conditions or [],
        scenery_rules=params.scenery_rules or [],
        custom_dice=params.custom_dice or {},
        rules=params.rules,
        agendas=params.agendas,
        topologies=params.topologies,
        character_profiles=params.character_profiles,
        generation_templates=params.generation_templates,
        character_creation=params.character_creation,
        npc_stat_blocks=params.npc_stat_blocks,
        npc_creation_rules=params.npc_creation_rules,
        source_document_id=params.source_document_id,
        is_builtin=False,
        hand_authored=params.hand_authored,
        needs_review=params.needs_review,
        degenerate_reason=params.degenerate_reason,
        created_at=system_doc["created_at"],
        updated_at=system_doc.get("updated_at"),
    )


def mongodb_get_game_system(system_id: UUID) -> GameSystemResponse | None:
    """
    Get a game system by ID.

    Args:
        system_id: Game system UUID

    Returns:
        GameSystemResponse or None if not found
    """
    # Ensure builtin systems are seeded
    _ensure_builtin_systems_seeded()

    mongodb = get_mongodb_client()
    systems_collection = mongodb.get_collection("game_systems")

    system_doc = systems_collection.find_one({"system_id": str(system_id)})
    if not system_doc:
        return None

    return GameSystemResponse(
        id=UUID(system_doc["system_id"]),
        name=system_doc["name"],
        description=system_doc["description"],
        version=system_doc.get("version"),
        core_mechanic=CoreMechanic(**system_doc["core_mechanic"]),
        attributes=[AttributeDefinition(**attr) for attr in system_doc.get("attributes", [])],
        skills=[SkillDefinition(**skill) for skill in system_doc.get("skills", [])],
        resources=[ResourceDefinition(**res) for res in system_doc.get("resources", [])],
        conditions=[ConditionDefinition(**c) for c in system_doc.get("conditions", [])],
        scenery_rules=[SceneryRule(**s) for s in system_doc.get("scenery_rules", [])],
        custom_dice=system_doc.get("custom_dice", {}),
        rules=[GameRule(**r) for r in system_doc.get("rules", [])],
        agendas=system_doc.get("agendas", []),
        topologies=system_doc.get("topologies", []),
        character_profiles=system_doc.get("character_profiles", []),
        generation_templates=system_doc.get("generation_templates", []),
        character_creation=(
            CharacterCreationProcedure(**system_doc["character_creation"])
            if system_doc.get("character_creation")
            else None
        ),
        npc_stat_blocks=[NPCStatBlock(**b) for b in system_doc.get("npc_stat_blocks", [])],
        npc_creation_rules=(
            NPCCreationRules(**system_doc["npc_creation_rules"]) if system_doc.get("npc_creation_rules") else None
        ),
        source_document_id=(UUID(system_doc["source_document_id"]) if system_doc.get("source_document_id") else None),
        is_builtin=system_doc["is_builtin"],
        hand_authored=system_doc.get("hand_authored", False),
        needs_review=system_doc.get("needs_review", False),
        degenerate_reason=system_doc.get("degenerate_reason"),
        created_at=system_doc["created_at"],
        updated_at=system_doc.get("updated_at"),
    )


def mongodb_list_game_systems(include_builtin: bool = True, limit: int = 50, offset: int = 0) -> GameSystemListResponse:
    """
    List game systems with optional filtering.

    Args:
        include_builtin: Whether to include built-in systems
        limit: Maximum number of systems to return
        offset: Number of systems to skip

    Returns:
        GameSystemListResponse with matching systems
    """
    # Ensure builtin systems are seeded
    _ensure_builtin_systems_seeded()

    mongodb = get_mongodb_client()
    systems_collection = mongodb.get_collection("game_systems")

    # Build query
    query = {}
    if not include_builtin:
        query["is_builtin"] = False

    # Get total count
    total = systems_collection.count_documents(query)

    # Get paginated results
    systems_docs = (
        systems_collection.find(query).sort("name", 1).skip(offset).limit(limit)  # Alphabetical
    )

    systems = [
        GameSystemResponse(
            id=UUID(doc["system_id"]),
            name=doc["name"],
            description=doc["description"],
            version=doc.get("version"),
            core_mechanic=CoreMechanic(**doc["core_mechanic"]),
            attributes=[AttributeDefinition(**attr) for attr in doc.get("attributes", [])],
            skills=[SkillDefinition(**skill) for skill in doc.get("skills", [])],
            resources=[ResourceDefinition(**res) for res in doc.get("resources", [])],
            custom_dice=doc.get("custom_dice", {}),
            rules=[GameRule(**r) for r in doc.get("rules", [])],
            agendas=doc.get("agendas", []),
            topologies=doc.get("topologies", []),
            character_profiles=doc.get("character_profiles", []),
            generation_templates=doc.get("generation_templates", []),
            character_creation=(
                CharacterCreationProcedure(**doc["character_creation"]) if doc.get("character_creation") else None
            ),
            npc_stat_blocks=[NPCStatBlock(**b) for b in doc.get("npc_stat_blocks", [])],
            npc_creation_rules=(
                NPCCreationRules(**doc["npc_creation_rules"]) if doc.get("npc_creation_rules") else None
            ),
            source_document_id=(UUID(doc["source_document_id"]) if doc.get("source_document_id") else None),
            is_builtin=doc["is_builtin"],
            hand_authored=doc.get("hand_authored", False),
            needs_review=doc.get("needs_review", False),
            degenerate_reason=doc.get("degenerate_reason"),
            created_at=doc["created_at"],
            updated_at=doc.get("updated_at"),
        )
        for doc in systems_docs
    ]

    return GameSystemListResponse(
        systems=systems,
        total=total,
        limit=limit,
        offset=offset,
    )


def mongodb_update_game_system(system_id: UUID, params: GameSystemUpdate) -> GameSystemResponse:
    """
    Update a game system.

    Args:
        system_id: Game system UUID
        params: Update parameters

    Returns:
        GameSystemResponse with updated system data

    Raises:
        ValueError: If system not found or is a builtin system
    """
    mongodb = get_mongodb_client()
    systems_collection = mongodb.get_collection("game_systems")

    # Check if system exists
    system_doc = systems_collection.find_one({"system_id": str(system_id)})
    if not system_doc:
        raise ValueError(f"Game system {system_id} not found")

    # Prevent modification of builtin systems
    if system_doc["is_builtin"]:
        raise ValueError("Cannot modify builtin game systems")

    # Build update document
    update_doc: dict[str, Any] = {}
    if params.name is not None:
        update_doc["name"] = params.name
    if params.description is not None:
        update_doc["description"] = params.description
    if params.version is not None:
        update_doc["version"] = params.version
    if params.core_mechanic is not None:
        update_doc["core_mechanic"] = params.core_mechanic.model_dump(mode="json")
    if params.attributes is not None:
        update_doc["attributes"] = [attr.model_dump(mode="json") for attr in params.attributes]
    if params.skills is not None:
        update_doc["skills"] = [skill.model_dump(mode="json") for skill in params.skills]
    if params.resources is not None:
        update_doc["resources"] = [res.model_dump(mode="json") for res in params.resources]
    if params.conditions is not None:
        update_doc["conditions"] = [c.model_dump(mode="json") for c in params.conditions]
    if params.scenery_rules is not None:
        update_doc["scenery_rules"] = [s.model_dump(mode="json") for s in params.scenery_rules]
    if params.custom_dice is not None:
        update_doc["custom_dice"] = params.custom_dice
    if params.rules is not None:
        update_doc["rules"] = [r.model_dump(mode="json") for r in params.rules]
    if params.agendas is not None:
        update_doc["agendas"] = [a.model_dump(mode="json") for a in params.agendas]
    if params.topologies is not None:
        update_doc["topologies"] = [t.model_dump(mode="json") for t in params.topologies]
    if params.character_profiles is not None:
        update_doc["character_profiles"] = [p.model_dump(mode="json") for p in params.character_profiles]
    if params.generation_templates is not None:
        update_doc["generation_templates"] = [g.model_dump(mode="json") for g in params.generation_templates]
    if params.character_creation is not None:
        update_doc["character_creation"] = params.character_creation.model_dump(mode="json")
    if params.npc_stat_blocks is not None:
        update_doc["npc_stat_blocks"] = [b.model_dump(mode="json") for b in params.npc_stat_blocks]
    if params.npc_creation_rules is not None:
        update_doc["npc_creation_rules"] = params.npc_creation_rules.model_dump(mode="json")

    if update_doc:
        update_doc["updated_at"] = datetime.now(UTC)
        systems_collection.update_one({"system_id": str(system_id)}, {"$set": update_doc})

    # Return updated system
    updated_system = mongodb_get_game_system(system_id)
    if not updated_system:
        raise ValueError(f"Failed to retrieve updated system {system_id}")
    return updated_system


def mongodb_delete_game_system(system_id: UUID) -> None:
    """
    Delete a game system.

    Args:
        system_id: Game system UUID

    Raises:
        ValueError: If system not found or is a builtin system
    """
    mongodb = get_mongodb_client()
    systems_collection = mongodb.get_collection("game_systems")

    # Check if system exists
    system_doc = systems_collection.find_one({"system_id": str(system_id)})
    if not system_doc:
        raise ValueError(f"Game system {system_id} not found")

    # Prevent deletion of builtin systems
    if system_doc["is_builtin"]:
        raise ValueError("Cannot delete builtin game systems")

    systems_collection.delete_one({"system_id": str(system_id)})


def mongodb_create_rule_override(params: RuleOverrideCreate) -> RuleOverrideResponse:
    """
    Create a new rule override.

    Args:
        params: Rule override creation parameters

    Returns:
        RuleOverrideResponse with created override data
    """
    mongodb = get_mongodb_client()
    overrides_collection = mongodb.get_collection("rule_overrides")

    now = datetime.now(UTC)
    override_id = uuid4()

    override_doc = {
        "override_id": str(override_id),
        "scope": params.scope.value,
        "scope_id": str(params.scope_id),
        "target": params.target,
        "original": params.original,
        "override": params.override,
        "reason": params.reason,
        "times_used": 0,
        "active": True,
        "created_at": now,
    }

    overrides_collection.insert_one(override_doc)

    return RuleOverrideResponse(
        id=override_id,
        scope=params.scope,
        scope_id=params.scope_id,
        target=params.target,
        original=params.original,
        override=params.override,
        reason=params.reason,
        times_used=0,
        active=True,
        created_at=now,
    )


def mongodb_get_rule_override(override_id: UUID) -> RuleOverrideResponse | None:
    """
    Get a rule override by ID.

    Args:
        override_id: Rule override UUID

    Returns:
        RuleOverrideResponse or None if not found
    """
    mongodb = get_mongodb_client()
    overrides_collection = mongodb.get_collection("rule_overrides")

    override_doc = overrides_collection.find_one({"override_id": str(override_id)})
    if not override_doc:
        return None

    return RuleOverrideResponse(
        id=UUID(override_doc["override_id"]),
        scope=RuleOverrideScope(override_doc["scope"]),
        scope_id=UUID(override_doc["scope_id"]),
        target=override_doc["target"],
        original=override_doc["original"],
        override=override_doc["override"],
        reason=override_doc.get("reason"),
        times_used=override_doc["times_used"],
        active=override_doc["active"],
        created_at=override_doc["created_at"],
    )


def mongodb_list_rule_overrides(
    scope: str | None = None,
    scope_id: UUID | None = None,
    active_only: bool = True,
) -> RuleOverrideListResponse:
    """
    List rule overrides with filtering.

    Args:
        scope: Filter by scope type
        scope_id: Filter by scope ID
        active_only: Only return active overrides

    Returns:
        RuleOverrideListResponse with matching overrides
    """
    mongodb = get_mongodb_client()
    overrides_collection = mongodb.get_collection("rule_overrides")

    # Build query
    query: dict[str, Any] = {}
    if scope is not None:
        query["scope"] = scope
    if scope_id is not None:
        query["scope_id"] = str(scope_id)
    if active_only:
        query["active"] = True

    # Get total count
    total = overrides_collection.count_documents(query)

    # Get all matching overrides (no pagination for now)
    overrides_docs = overrides_collection.find(query).sort("created_at", -1)

    overrides = [
        RuleOverrideResponse(
            id=UUID(doc["override_id"]),
            scope=RuleOverrideScope(doc["scope"]),
            scope_id=UUID(doc["scope_id"]),
            target=doc["target"],
            original=doc["original"],
            override=doc["override"],
            reason=doc.get("reason"),
            times_used=doc["times_used"],
            active=doc["active"],
            created_at=doc["created_at"],
        )
        for doc in overrides_docs
    ]

    return RuleOverrideListResponse(
        overrides=overrides,
        total=total,
    )


def mongodb_update_rule_override(override_id: UUID, params: RuleOverrideUpdate) -> RuleOverrideResponse:
    """
    Update a rule override.

    Args:
        override_id: Rule override UUID
        params: Update parameters

    Returns:
        RuleOverrideResponse with updated override data

    Raises:
        ValueError: If override not found
    """
    mongodb = get_mongodb_client()
    overrides_collection = mongodb.get_collection("rule_overrides")

    # Check if override exists
    override_doc = overrides_collection.find_one({"override_id": str(override_id)})
    if not override_doc:
        raise ValueError(f"Rule override {override_id} not found")

    # Build update document
    update_doc: dict[str, Any] = {}
    if params.active is not None:
        update_doc["active"] = params.active
    if params.times_used is not None:
        update_doc["times_used"] = params.times_used
    if params.reason is not None:
        update_doc["reason"] = params.reason

    if update_doc:
        overrides_collection.update_one({"override_id": str(override_id)}, {"$set": update_doc})

    # Return updated override
    updated_override = mongodb_get_rule_override(override_id)
    if not updated_override:
        raise ValueError(f"Failed to retrieve updated override {override_id}")
    return updated_override


def mongodb_delete_rule_override(override_id: UUID) -> None:
    """
    Delete a rule override.

    Args:
        override_id: Rule override UUID

    Raises:
        ValueError: If override not found
    """
    mongodb = get_mongodb_client()
    overrides_collection = mongodb.get_collection("rule_overrides")

    # Check if override exists
    override_doc = overrides_collection.find_one({"override_id": str(override_id)})
    if not override_doc:
        raise ValueError(f"Rule override {override_id} not found")

    overrides_collection.delete_one({"override_id": str(override_id)})


# PARTY INVENTORY OPERATIONS (DL-16)
