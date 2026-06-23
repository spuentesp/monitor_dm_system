"""Game Systems routes – expose extracted game-system data (rules, attributes,
skills, resources, character creation) that lives in the ``game_systems``
MongoDB collection."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from monitor_data.tools.mongodb_tools import (
    mongodb_get_game_system,
    mongodb_list_game_systems,
)

from .ingest_shared import db_op, validate_uuid

router = APIRouter()


def _system_to_dict(system) -> dict:
    """Serialize a GameSystemResponse for the frontend."""
    return {
        "id": str(system.id),
        "name": system.name,
        "description": system.description,
        "version": system.version,
        "core_mechanic": system.core_mechanic.model_dump(mode="json"),
        "attributes": [a.model_dump(mode="json") for a in system.attributes],
        "skills": [s.model_dump(mode="json") for s in system.skills],
        "resources": [r.model_dump(mode="json") for r in system.resources],
        "custom_dice": system.custom_dice,
        "rules": [r.model_dump(mode="json") for r in system.rules],
        "character_creation": (
            system.character_creation.model_dump(mode="json")
            if system.character_creation
            else None
        ),
        "npc_stat_blocks": [b.model_dump(mode="json") for b in system.npc_stat_blocks],
        "npc_creation_rules": (
            system.npc_creation_rules.model_dump(mode="json")
            if system.npc_creation_rules
            else None
        ),
        "source_document_id": (
            str(system.source_document_id) if system.source_document_id else None
        ),
        "is_builtin": system.is_builtin,
        "created_at": system.created_at.isoformat(),
        "updated_at": system.updated_at.isoformat() if system.updated_at else None,
        "rule_count": len(system.rules),
        "attribute_count": len(system.attributes),
        "skill_count": len(system.skills),
        "resource_count": len(system.resources),
    }


def _system_summary(system) -> dict:
    """Lightweight summary for list endpoints (omit large arrays)."""
    return {
        "id": str(system.id),
        "name": system.name,
        "description": system.description,
        "version": system.version,
        "is_builtin": system.is_builtin,
        "source_document_id": (
            str(system.source_document_id) if system.source_document_id else None
        ),
        "rule_count": len(system.rules),
        "attribute_count": len(system.attributes),
        "skill_count": len(system.skills),
        "resource_count": len(system.resources),
        "created_at": system.created_at.isoformat(),
        "updated_at": system.updated_at.isoformat() if system.updated_at else None,
    }


@router.get("/systems")
async def list_systems(
    include_builtin: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List game systems (summaries without full rule/attribute arrays)."""
    with db_op("Database unavailable"):
        result = mongodb_list_game_systems(
            include_builtin=include_builtin, limit=limit, offset=offset
        )
    return {
        "systems": [_system_summary(s) for s in result.systems],
        "total": result.total,
        "limit": result.limit,
        "offset": result.offset,
    }


@router.get("/systems/{system_id}")
async def get_system(system_id: str) -> dict:
    """Get a game system by ID, including all rules and character creation data."""
    uid = validate_uuid(system_id, "system_id")
    with db_op("Database unavailable"):
        system = mongodb_get_game_system(uid)
    if not system:
        raise HTTPException(404, "GameSystem not found")
    return _system_to_dict(system)


@router.get("/systems/{system_id}/rules")
async def get_system_rules(
    system_id: str,
    rule_type: Optional[str] = None,
) -> dict:
    """Get just the rules for a game system, with optional type filter."""
    uid = validate_uuid(system_id, "system_id")
    with db_op("Database unavailable"):
        system = mongodb_get_game_system(uid)
    if not system:
        raise HTTPException(404, "GameSystem not found")

    rules = [r.model_dump(mode="json") for r in system.rules]
    if rule_type:
        rules = [r for r in rules if r.get("rule_type") == rule_type]

    return {
        "system_id": str(system.id),
        "system_name": system.name,
        "rule_count": len(rules),
        "rules": rules,
    }
