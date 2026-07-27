"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.character_sheets import (
    CharacterSheetCreate,
    CharacterSheetFilter,
    CharacterSheetListResponse,
    CharacterSheetResponse,
    CharacterSheetUpdate,
    SheetHistoryEntry,
)

# =============================================================================
# CHARACTER SHEET OPERATIONS
# =============================================================================


def _character_sheet_doc_to_response(doc: dict[str, Any]) -> CharacterSheetResponse:
    """Convert a MongoDB character sheet document into the API response model."""
    return CharacterSheetResponse(
        sheet_id=UUID(doc["sheet_id"]),
        entity_id=UUID(doc["entity_id"]),
        game_system_id=UUID(doc["game_system_id"]) if doc.get("game_system_id") else None,
        system_source_type=doc.get("system_source_type"),
        system_source_id=doc.get("system_source_id"),
        system_name=doc.get("system_name"),
        source_persona_id=doc.get("source_persona_id"),
        stats=doc.get("stats", {}),
        resources=doc.get("resources", {}),
        skills=doc.get("skills", {}),
        class_levels=doc.get("class_levels", {}),
        total_level=doc.get("total_level", 1),
        experience_points=doc.get("experience_points", 0),
        background=doc.get("background"),
        alignment=doc.get("alignment"),
        equipment=doc.get("equipment", []),
        special_abilities=doc.get("special_abilities", []),
        spells_known=doc.get("spells_known", []),
        notes=doc.get("notes"),
        is_active=doc.get("is_active", True),
        history_log=[
            SheetHistoryEntry(**entry) if isinstance(entry, dict) else entry for entry in doc.get("history_log", [])
        ],
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


def mongodb_create_character_sheet(params: CharacterSheetCreate) -> CharacterSheetResponse:
    """Create a durable character sheet for an existing entity instance."""
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()
    sheets = mongo_client["character_sheets"]

    verify_result = neo4j_client.execute_read(
        "MATCH (e:Entity {id: $entity_id}) RETURN e.id as id",
        {"entity_id": str(params.entity_id)},
    )
    if not verify_result:
        raise ValueError(f"Entity {params.entity_id} not found")

    duplicate_query: dict[str, Any] = {"entity_id": str(params.entity_id)}
    if params.game_system_id is not None:
        duplicate_query["game_system_id"] = str(params.game_system_id)
    elif params.system_source_id:
        duplicate_query["system_source_type"] = params.system_source_type
        duplicate_query["system_source_id"] = params.system_source_id

    existing = sheets.find_one(duplicate_query)
    if existing:
        return _character_sheet_doc_to_response(existing)

    if params.game_system_id is not None:
        # system_id is stored as a string; querying with a native uuid.UUID
        # raises "cannot encode native uuid.UUID" under the default
        # UuidRepresentation, so match on the string form only.
        system_doc = mongo_client["game_systems"].find_one({"system_id": str(params.game_system_id)})
        if not system_doc:
            raise ValueError(f"Game system {params.game_system_id} not found")

    now = datetime.now(UTC)
    sheet_id = uuid4()
    doc = {
        "sheet_id": str(sheet_id),
        "entity_id": str(params.entity_id),
        "game_system_id": str(params.game_system_id) if params.game_system_id else None,
        "system_source_type": params.system_source_type,
        "system_source_id": params.system_source_id,
        "system_name": params.system_name,
        "source_persona_id": params.source_persona_id,
        "stats": params.stats,
        "resources": params.resources,
        "skills": params.skills,
        "class_levels": params.class_levels,
        "total_level": params.total_level,
        "experience_points": params.experience_points,
        "background": params.background,
        "alignment": params.alignment,
        "equipment": params.equipment,
        "special_abilities": params.special_abilities,
        "spells_known": params.spells_known,
        "notes": params.notes,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    sheets.insert_one(doc)
    return _character_sheet_doc_to_response(doc)


def mongodb_get_character_sheet(sheet_id: UUID) -> CharacterSheetResponse | None:
    """Fetch a character sheet by its sheet id."""
    mongo_client = get_mongodb_client()
    doc = mongo_client["character_sheets"].find_one({"sheet_id": str(sheet_id)})
    if not doc:
        return None
    return _character_sheet_doc_to_response(doc)


def mongodb_update_character_sheet(
    sheet_id: UUID,
    params: CharacterSheetUpdate,
) -> CharacterSheetResponse:
    """Update an existing character sheet and append to its history log."""
    mongo_client = get_mongodb_client()
    sheets = mongo_client["character_sheets"]

    existing = sheets.find_one({"sheet_id": str(sheet_id)})
    if not existing:
        raise ValueError(f"Character sheet {sheet_id} not found")

    update_fields: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    for field_name in (
        "stats",
        "resources",
        "skills",
        "class_levels",
        "total_level",
        "experience_points",
        "background",
        "alignment",
        "equipment",
        "special_abilities",
        "spells_known",
        "notes",
    ):
        value = getattr(params, field_name)
        if value is not None:
            update_fields[field_name] = value

    history_log = list(existing.get("history_log", []))
    if params.change_description:
        history_log.append(
            {
                "timestamp": datetime.now(UTC),
                "change": params.change_description,
                "scene_id": None,
                "old_value": None,
                "new_value": None,
                "field": None,
            }
        )
        update_fields["history_log"] = history_log

    sheets.update_one(
        {"sheet_id": str(sheet_id)},
        {"$set": update_fields},
    )

    updated = sheets.find_one({"sheet_id": str(sheet_id)})
    if not updated:
        raise ValueError(f"Character sheet {sheet_id} not found after update")
    return _character_sheet_doc_to_response(updated)


def mongodb_list_character_sheets(
    params: CharacterSheetFilter,
) -> CharacterSheetListResponse:
    """List character sheets with filtering by entity or system source."""
    mongo_client = get_mongodb_client()
    sheets = mongo_client["character_sheets"]

    query: dict[str, Any] = {}
    if params.entity_id:
        query["entity_id"] = str(params.entity_id)
    if params.game_system_id:
        query["game_system_id"] = str(params.game_system_id)
    if params.system_source_type:
        query["system_source_type"] = params.system_source_type
    if params.system_source_id:
        query["system_source_id"] = params.system_source_id
    if params.is_active is not None:
        query["is_active"] = params.is_active

    total = sheets.count_documents(query)
    docs = sheets.find(query).sort("updated_at", -1).skip(params.offset).limit(params.limit)
    results = [_character_sheet_doc_to_response(doc) for doc in docs]
    return CharacterSheetListResponse(
        sheets=results,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
