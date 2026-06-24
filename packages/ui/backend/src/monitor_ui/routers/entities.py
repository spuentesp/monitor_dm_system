"""
Entities router — NPCs, RPG systems, and characters.

Queries MongoDB and Neo4j for entity data.  Falls back to empty lists
when databases are not available.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from monitor_data.schemas.character_sheets import (
    CharacterSheetFilter,
    CharacterSheetListResponse,
    CharacterSheetResponse,
    CharacterSheetUpdate,
)
from monitor_data.schemas.game_systems import GameRule, GameRuleType, GameSystemUpdate
from monitor_data.tools.mongodb_tools import mongodb_update_game_system
from monitor_ui.config import get_settings

from .character_storage import (
    create_character as _create_character_doc,
    delete_character as _delete_character_doc,
    get_character as _get_character_doc,
    increment_memory_count as _increment_memory_count,
    list_characters as _list_characters_docs,
    update_character as _update_character_doc,
)
from .entities_schemas import (
    NPC,
    NPCDetail,
    AttributeInfo,
    Character,
    CharacterCreate,
    CardDraftRequest,
    CardDraftResponse,
    CharacterDetail,
    CharacterExpandResponse,
    CharacterImportRequest,
    CharacterUpdate,
    CharacterVersion,
    CharacterVersionCreateRequest,
    ConversationReply,
    ConversationSendRequest,
    ConversationStartRequest,
    ConversationStartResponse,
    ConversationSummary,
    CoreMechanicInfo,
    GenerateEntityRequest,
    PaginatedNPCs,
    ResourceInfo,
    RPGSystem,
    RPGSystemUpdateRequest,
    RuleInfo,
    SkillInfo,
)
from .ingest_shared import db_op, validate_uuid

router = APIRouter()
_settings = get_settings()


# ---------------------------------------------------------------------------
# MongoDB query helpers
# ---------------------------------------------------------------------------


async def _query_npcs(
    q: str | None, limit: int, offset: int, entity_types: list[str] | None = None
) -> tuple[list[NPC], int]:
    """Query Neo4j for entities of any type."""
    try:
        from monitor_data.db.neo4j import get_neo4j_client

        client = get_neo4j_client()

        where_parts: list[str] = []
        params: dict[str, Any] = {}

        if entity_types:
            where_parts.append("e.entity_type IN $entity_types")
            params["entity_types"] = entity_types

        if q:
            params["q"] = " ".join(q.split())

        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        if q:
            count_result = client.execute_read(
                "CALL db.index.fulltext.queryNodes('entity_text_idx', $q) YIELD node AS e, score "
                f"{where} RETURN count(DISTINCT e) AS total",
                params,
            )
            total: int = count_result[0]["total"] if count_result else 0

            rows = client.execute_read(
                "CALL db.index.fulltext.queryNodes('entity_text_idx', $q) YIELD node AS e, score "
                f"{where} RETURN e ORDER BY score DESC, e.name "
                "SKIP $offset LIMIT $limit",
                {**params, "offset": offset, "limit": limit},
            )
        else:
            count_result = client.execute_read(
                f"MATCH (e:Entity) {where} RETURN count(e) AS total", params
            )
            total = count_result[0]["total"] if count_result else 0

            rows = client.execute_read(
                f"MATCH (e:Entity) {where} "
                "RETURN e ORDER BY e.name "
                "SKIP $offset LIMIT $limit",
                {**params, "offset": offset, "limit": limit},
            )

        import json as _json

        npcs = [
            NPC(
                id=str(row["e"].get("id", "")),
                name=row["e"].get("name", "Unknown"),
                entity_type=row["e"].get("entity_type", "character"),
                universe_id=str(row["e"].get("universe_id", "")),
                description=row["e"].get("description"),
                state_tags=row["e"].get("state_tags", []),
                properties=(
                    _json.loads(row["e"]["properties"])
                    if isinstance(row["e"].get("properties"), str)
                    else row["e"].get("properties", {})
                ),
                canon_level=row["e"].get("canon_level", "canon"),
                is_archetype=row["e"].get("is_archetype", False),
            )
            for row in rows
        ]
        return npcs, total

    except Exception:
        return [], 0


async def _query_systems() -> list[RPGSystem]:
    """Query MongoDB for RPG system definitions."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore

        client: AsyncIOMotorClient = AsyncIOMotorClient(
            _settings.mongodb_uri, serverSelectionTimeoutMS=2000
        )
        db = client[_settings.mongodb_database]
        coll = db["game_systems"]
        docs = await coll.find({}).to_list(length=100)
        client.close()

        systems = []
        for doc in docs:
            cm_raw = doc.get("core_mechanic")
            core_mechanic = None
            if cm_raw:
                core_mechanic = CoreMechanicInfo(
                    mechanic_type=cm_raw.get(
                        "type", cm_raw.get("mechanic_type", "custom")
                    ),
                    formula=cm_raw.get("formula"),
                    success_type=cm_raw.get("success_type"),
                    target_number=cm_raw.get("target_number"),
                    description=cm_raw.get("description"),
                )

            attributes = [
                AttributeInfo(
                    name=a.get("name", ""),
                    abbreviation=a.get("abbreviation"),
                    min_value=a.get("min_value"),
                    max_value=a.get("max_value"),
                    description=a.get("description"),
                )
                for a in doc.get("attributes", [])
                if isinstance(a, dict)
            ]

            skills = [
                SkillInfo(
                    name=s.get("name", ""),
                    linked_attribute=s.get("linked_attribute"),
                    description=s.get("description"),
                    untrained_allowed=s.get("untrained_allowed", True),
                )
                for s in doc.get("skills", [])
                if isinstance(s, dict)
            ]

            resources = [
                ResourceInfo(
                    name=r.get("name", ""),
                    abbreviation=r.get("abbreviation"),
                    max_value=r.get("max_value"),
                    recovers_on=r.get("recovers_on"),
                    depleted_effect=r.get("depleted_effect"),
                )
                for r in doc.get("resources", [])
                if isinstance(r, dict)
            ]

            rules = [
                RuleInfo(
                    name=ru.get("name", ""),
                    rule_type=ru.get("rule_type", "custom"),
                    description=ru.get("description"),
                    formula=ru.get("formula"),
                    examples=ru.get("examples", []),
                    exceptions=ru.get("exceptions", []),
                )
                for ru in doc.get("rules", [])
                if isinstance(ru, dict)
            ]

            systems.append(
                RPGSystem(
                    id=str(doc.get("system_id", doc.get("_id", ""))),
                    name=doc.get("name", "Unknown System"),
                    description=doc.get("description"),
                    version=doc.get("version"),
                    core_mechanic=core_mechanic,
                    attributes=attributes,
                    skills=skills,
                    resources=resources,
                    rules=rules,
                    is_builtin=doc.get("is_builtin", False),
                    source_document_id=doc.get("source_document_id"),
                    character_count=0,
                    session_count=0,
                )
            )

        return systems
    except Exception:
        return []


def _resolve_system_source(
    system_id: str | None = None,
    pack_id: str | None = None,
) -> dict[str, Any]:
    """Resolve whether generation should use the generic system library or a pack-embedded system."""
    from monitor_data.tools.mongodb_tools import (
        mongodb_get_game_system,
        mongodb_get_knowledge_pack,
    )

    if pack_id:
        pack_uuid = validate_uuid(pack_id, "pack id")

        pack = mongodb_get_knowledge_pack(pack_uuid)
        if not pack:
            raise HTTPException(status_code=404, detail="Pack not found")

        embedded_system = getattr(pack, "game_system_data", None)
        if embedded_system is not None:
            return {
                "source_type": "pack_embedded",
                "source_label": pack.name,
                "pack_id": str(pack.id),
                "game_system_id": str(pack.game_system_id)
                if pack.game_system_id
                else None,
                "doc": embedded_system.model_dump(mode="json"),
            }

        if pack.game_system_id:
            system = mongodb_get_game_system(pack.game_system_id)
            if not system:
                raise HTTPException(
                    status_code=404, detail="Linked game system not found"
                )
            return {
                "source_type": "generic_library",
                "source_label": system.name,
                "system_id": str(system.id),
                "pack_id": str(pack.id),
                "doc": system.model_dump(mode="json"),
            }

        raise HTTPException(
            status_code=422,
            detail="Pack does not contain an integrated or linked game system",
        )

    if not system_id:
        raise HTTPException(
            status_code=400, detail="Either system_id or pack_id is required"
        )

    system_uuid = validate_uuid(system_id, "system id")

    system = mongodb_get_game_system(system_uuid)
    if not system:
        raise HTTPException(status_code=404, detail="System not found")

    return {
        "source_type": "generic_library",
        "source_label": system.name,
        "system_id": str(system.id),
        "doc": system.model_dump(mode="json"),
    }


def _persist_generated_entity(
    *,
    universe_id: str,
    preview: dict[str, Any],
    source_meta: dict[str, Any],
) -> dict[str, Any]:
    """Persist a generated PC/NPC to the selected world using canonical stores."""
    from monitor_data.schemas.base import Authority, CanonLevel, EntityType
    from monitor_data.schemas.character_sheets import CharacterSheetCreate
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.npc_profiles import NPCProfileCreate, NPCProfileUpdate
    from monitor_data.tools.mongodb_tools import (
        mongodb_create_character_sheet,
        mongodb_create_npc_profile,
        mongodb_update_npc_profile,
    )
    from monitor_data.tools.neo4j_tools.entities import neo4j_create_entity

    universe_uuid = validate_uuid(universe_id, "universe id")

    kind = str(preview.get("kind", "pc")).lower()
    state_tags = [
        str(tag)
        for tag in dict.fromkeys([*(preview.get("tags") or []), kind, "generated"])
    ]
    role = "PC" if kind == "pc" else "NPC"

    entity = neo4j_create_entity(
        EntityCreate(
            universe_id=universe_uuid,
            name=str(
                preview.get("name")
                or ("Generated NPC" if kind == "npc" else "Generated Character")
            ),
            entity_type=EntityType.CHARACTER,
            sub_type=None,
            is_archetype=False,
            description=str(preview.get("description") or ""),
            properties={
                "role": role,
                "concept": preview.get("concept") or preview.get("description") or "",
                "generation_source": source_meta.get("source_type"),
                "system_name": preview.get("system_name")
                or source_meta.get("source_label"),
                "tier": preview.get("tier"),
            },
            state_tags=state_tags,
            archetype_id=None,
            authority=Authority.SYSTEM,
            canon_level=CanonLevel.CANON,
            confidence=1.0,
        )
    )

    sheet = mongodb_create_character_sheet(
        CharacterSheetCreate(
            entity_id=entity.id,
            game_system_id=UUID(source_meta["system_id"])
            if source_meta.get("system_id")
            else None,
            system_source_type=str(source_meta.get("source_type") or "narrative_only"),
            system_source_id=str(
                source_meta.get("pack_id")
                or source_meta.get("system_id")
                or source_meta.get("game_system_id")
                or entity.id
            ),
            system_name=str(
                preview.get("system_name")
                or source_meta.get("source_label")
                or "Narrative"
            ),
            stats=dict(preview.get("attributes") or {}),
            resources=dict(preview.get("resources") or {}),
            skills=dict(preview.get("skills") or {}),
            background=None,
            alignment=None,
            notes=str(preview.get("sheet") or preview.get("description") or ""),
            special_abilities=list(preview.get("special_abilities") or []),
        )
    )

    profile_id = None
    if kind == "npc":
        profile_payload = NPCProfileCreate(
            entity_id=entity.id,
            values=list(preview.get("values") or []),
            desires=list(preview.get("desires") or []),
            speech_style=preview.get("speech_style"),
            gm_notes=str(preview.get("sheet") or preview.get("description") or ""),
            current_emotional_state="neutral",
        )
        try:
            profile = mongodb_create_npc_profile(profile_payload)
        except ValueError:
            profile = mongodb_update_npc_profile(
                entity.id,
                NPCProfileUpdate(
                    values=profile_payload.values,
                    desires=profile_payload.desires,
                    speech_style=profile_payload.speech_style,
                    gm_notes=profile_payload.gm_notes,
                    current_emotional_state=profile_payload.current_emotional_state,
                    relationship_states=None,
                    add_preference=None,
                    add_trigger=None,
                    add_secret=None,
                ),
            )
        profile_id = str(profile.profile_id)

    return {
        "entity_id": str(entity.id),
        "sheet_id": str(sheet.sheet_id),
        "profile_id": profile_id,
        "saved_to_universe_id": str(entity.universe_id),
    }


# ---------------------------------------------------------------------------
# NPC endpoints
# ---------------------------------------------------------------------------


@router.get("/npcs", response_model=PaginatedNPCs)
async def list_npcs(
    q: str | None = Query(default=None, description="Search term"),
    entity_type: str | None = Query(
        default=None, description="Comma-separated entity types to include"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedNPCs:
    entity_types = (
        [t.strip() for t in entity_type.split(",") if t.strip()]
        if entity_type
        else None
    )
    items, total = await _query_npcs(q, limit, offset, entity_types)
    return PaginatedNPCs(items=items, total=total, limit=limit, offset=offset)


@router.get("/npcs/{npc_id}", response_model=NPCDetail)
async def get_npc(npc_id: str) -> NPCDetail:
    try:
        import json as _json
        from monitor_data.db.neo4j import get_neo4j_client

        client = get_neo4j_client()

        rows = client.execute_read(
            "MATCH (e:Entity {id: $id}) RETURN e LIMIT 1",
            {"id": npc_id},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Entity not found")

        e = rows[0]["e"]
        name = e.get("name", "Unknown")
        universe_id = str(e.get("universe_id", ""))

        # Fetch facts from the same universe that mention this entity's name
        fact_rows = client.execute_read(
            "CALL db.index.fulltext.queryNodes('fact_statement_idx', $name) YIELD node AS f, score "
            "WHERE f:Fact AND f.universe_id = $uid "
            "RETURN f ORDER BY score DESC, f.confidence DESC LIMIT 15",
            {"uid": universe_id, "name": " ".join(name.split())},
        )
        facts = [
            {
                "id": str(r["f"].get("id", "")),
                "statement": r["f"].get("statement", ""),
                "fact_type": r["f"].get("fact_type", ""),
                "confidence": r["f"].get("confidence", 0.5),
            }
            for r in fact_rows
        ]

        props = e.get("properties", {})
        if isinstance(props, str):
            try:
                props = _json.loads(props)
            except Exception:
                props = {}

        return NPCDetail(
            id=npc_id,
            name=name,
            entity_type=e.get("entity_type", "character"),
            universe_id=universe_id,
            description=e.get("description"),
            state_tags=e.get("state_tags", []),
            properties=props,
            canon_level=e.get("canon_level", "canon"),
            is_archetype=e.get("is_archetype", False),
            facts=facts,
            memories=[],
            stats={},
            relationships=[],
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# RPG system endpoints
# ---------------------------------------------------------------------------


@router.get("/systems", response_model=list[RPGSystem])
async def list_systems() -> list[RPGSystem]:
    return await _query_systems()


@router.get("/systems/{system_id}", response_model=RPGSystem)
async def get_system(system_id: str) -> RPGSystem:
    systems = await _query_systems()
    for s in systems:
        if s.id == system_id:
            return s
    raise HTTPException(status_code=404, detail="System not found")


@router.put("/systems/{system_id}", response_model=RPGSystem)
async def update_system(system_id: str, body: RPGSystemUpdateRequest) -> RPGSystem:
    uid = validate_uuid(system_id, "system id")

    update_kwargs: dict[str, Any] = {}
    if body.name is not None:
        update_kwargs["name"] = body.name
    if body.description is not None:
        update_kwargs["description"] = body.description
    if body.version is not None:
        update_kwargs["version"] = body.version
    if body.rules is not None:
        typed_rules: list[GameRule] = []
        for rule in body.rules:
            try:
                rule_type = GameRuleType(str(rule.rule_type or "custom").lower())
            except ValueError:
                rule_type = GameRuleType.CUSTOM
            typed_rules.append(
                GameRule(
                    name=rule.name or "Untitled Rule",
                    rule_type=rule_type,
                    description=rule.description or "",
                    formula=rule.formula,
                    source_ref=None,
                    tags=[],
                )
            )
        update_kwargs["rules"] = typed_rules

    try:
        updated = await asyncio.to_thread(
            mongodb_update_game_system, uid, GameSystemUpdate(**update_kwargs)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    core = updated.core_mechanic
    return RPGSystem(
        id=str(updated.id),
        name=updated.name,
        description=updated.description,
        version=updated.version,
        core_mechanic=(
            CoreMechanicInfo(
                mechanic_type=core.type.value
                if hasattr(core.type, "value")
                else str(core.type),
                formula=core.formula,
                success_type=core.success_type.value
                if hasattr(core.success_type, "value")
                else str(core.success_type),
                target_number=None,
                description=None,
            )
            if core
            else None
        ),
        attributes=[
            AttributeInfo(
                name=a.name,
                abbreviation=a.abbreviation,
                min_value=a.min_value,
                max_value=a.max_value,
                description=None,
            )
            for a in updated.attributes
        ],
        skills=[
            SkillInfo(
                name=s.name,
                linked_attribute=s.linked_attribute,
                description=s.description,
                untrained_allowed=True,
            )
            for s in updated.skills
        ],
        resources=[
            ResourceInfo(
                name=r.name,
                abbreviation=r.abbreviation,
                max_value=None,
                recovers_on=r.recovers_on,
                depleted_effect=r.depleted_effect,
            )
            for r in updated.resources
        ],
        rules=[
            RuleInfo(
                name=r.name,
                rule_type=r.rule_type.value
                if hasattr(r.rule_type, "value")
                else str(r.rule_type),
                description=r.description,
                formula=r.formula,
                examples=[],
                exceptions=[],
            )
            for r in updated.rules
        ],
        is_builtin=updated.is_builtin,
        source_document_id=str(updated.source_document_id)
        if updated.source_document_id
        else None,
        character_count=0,
        session_count=0,
    )


@router.delete("/systems/{system_id}", status_code=204)
async def delete_system(system_id: str) -> None:
    """Delete a game system from MongoDB."""
    uid = validate_uuid(system_id, "system id")
    with db_op("Database unavailable"):
        from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore

        client: AsyncIOMotorClient = AsyncIOMotorClient(
            _settings.mongodb_uri, serverSelectionTimeoutMS=2000
        )
        db = client[_settings.mongodb_database]
        result = await db["game_systems"].delete_one({"system_id": uid})
        if result.deleted_count == 0:
            # Try by string id field too
            result = await db["game_systems"].delete_one({"id": system_id})
        client.close()
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="System not found")


@router.post("/systems/{system_id}/test")
async def test_system(system_id: str) -> dict[str, Any]:
    """Roll a test character for this system using `GameSystemRuntime`."""
    try:
        source_meta = await asyncio.to_thread(
            _resolve_system_source, system_id=system_id
        )
        from monitor_agents.game_system import GameSystemRuntime

        gsr = GameSystemRuntime(source_meta["doc"])
        candidate = await asyncio.to_thread(
            gsr.build_character_candidate, name="Test Character"
        )
        return {
            "system_name": candidate.get(
                "system_name", source_meta.get("source_label", "")
            ),
            "sheet": candidate.get("sheet", ""),
            "attributes": candidate.get("attributes", {}),
            "resources": candidate.get("resources", {}),
            "source": {
                "type": source_meta.get("source_type"),
                "label": source_meta.get("source_label"),
            },
            "preview": candidate,
        }
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=503, detail="Agents layer not available")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/systems/{system_id}/test-npc")
async def test_system_npc(
    system_id: str, body: GenerateEntityRequest | None = None
) -> dict[str, Any]:
    """Generate a test NPC for a generic library system."""
    try:
        source_meta = await asyncio.to_thread(
            _resolve_system_source, system_id=system_id
        )
        from monitor_agents.game_system import GameSystemRuntime

        request = body or GenerateEntityRequest(system_id=system_id, kind="npc")
        gsr = GameSystemRuntime(source_meta["doc"])
        candidate = await asyncio.to_thread(
            gsr.generate_npc,
            name=request.name,
            tier=request.tier,
            concept=request.concept,
        )
        return {
            "system_name": candidate.get(
                "system_name", source_meta.get("source_label", "")
            ),
            "sheet": candidate.get("sheet", ""),
            "attributes": candidate.get("attributes", {}),
            "resources": candidate.get("resources", {}),
            "source": {
                "type": source_meta.get("source_type"),
                "label": source_meta.get("source_label"),
            },
            "preview": candidate,
        }
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=503, detail="Agents layer not available")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate")
async def generate_entity(body: GenerateEntityRequest) -> dict[str, Any]:
    """Preview or persist a playable PC/NPC from either a generic or pack-integrated system source."""
    try:
        source_meta = _resolve_system_source(
            system_id=body.system_id, pack_id=body.pack_id
        )
        from monitor_agents.game_system import GameSystemRuntime

        gsr = GameSystemRuntime(source_meta["doc"])
        if body.kind == "npc":
            preview = gsr.generate_npc(
                name=body.name, tier=body.tier, concept=body.concept or body.description
            )
        else:
            preview = gsr.build_character_candidate(
                name=body.name or "Generated Character",
                description=body.description or "",
                concept=body.concept,
            )

        if body.state_tags:
            preview["tags"] = list(
                dict.fromkeys([*(preview.get("tags") or []), *body.state_tags])
            )

        saved = None
        if body.save:
            if not body.universe_id:
                raise HTTPException(
                    status_code=422, detail="universe_id is required when save=true"
                )
            saved = _persist_generated_entity(
                universe_id=body.universe_id,
                preview=preview,
                source_meta=source_meta,
            )

        return {
            "source": {
                "type": source_meta.get("source_type"),
                "label": source_meta.get("source_label"),
                "system_id": source_meta.get("system_id"),
                "pack_id": source_meta.get("pack_id"),
            },
            "preview": preview,
            "saved": saved,
        }
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=503, detail="Agents layer not available")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/systems/{system_id}/characters", response_model=list[Character])
async def list_characters(system_id: str) -> list[Character]:
    try:
        from monitor_data.schemas.character_sheets import CharacterSheetFilter
        from monitor_data.schemas.entities import EntityFilter
        from monitor_data.tools.mongodb_tools import mongodb_list_character_sheets
        from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities

        system_uuid = UUID(system_id)
        sheets = mongodb_list_character_sheets(
            CharacterSheetFilter(
                entity_id=None,
                game_system_id=system_uuid,
                system_source_type=None,
                system_source_id=None,
                is_active=None,
                limit=200,
                offset=0,
            )
        )
        if not sheets.sheets:
            return []

        entities = neo4j_list_entities(EntityFilter(limit=500)).entities
        entities_by_id: dict[str, Any] = {str(entity.id): entity for entity in entities}

        return [
            Character(
                id=str(sheet.entity_id),
                name=getattr(
                    entities_by_id.get(str(sheet.entity_id)), "name", "Unknown"
                ),
                system_id=str(sheet.game_system_id)
                if sheet.game_system_id
                else system_id,
                system_name=sheet.system_name,
                universe_id=str(
                    getattr(entities_by_id.get(str(sheet.entity_id)), "universe_id", "")
                ),
                description=getattr(
                    entities_by_id.get(str(sheet.entity_id)), "description", None
                ),
                attributes=sheet.stats,
                state_tags=list(
                    getattr(entities_by_id.get(str(sheet.entity_id)), "state_tags", [])
                ),
                canon_level=str(
                    getattr(
                        entities_by_id.get(str(sheet.entity_id)), "canon_level", "canon"
                    )
                ),
            )
            for sheet in sheets.sheets
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Standalone Character CRUD (Roleplay UI)
# ---------------------------------------------------------------------------


def _serialise_character(doc: dict) -> dict:
    """Convert MongoDB document fields to JSON-safe strings for CharacterDetail.

    Adds defaults for fields introduced by the Character Versions feature so
    legacy character docs (created before versions existed) serialize cleanly.
    """
    doc["created_at"] = (
        doc["created_at"].isoformat()
        if hasattr(doc["created_at"], "isoformat")
        else str(doc["created_at"])
    )
    doc["updated_at"] = (
        doc["updated_at"].isoformat()
        if hasattr(doc["updated_at"], "isoformat")
        else str(doc["updated_at"])
    )
    doc.setdefault("versions", [])
    doc.setdefault("default_universe_id", doc.get("source_universe_id"))
    # version entries carry datetimes — stringify any nested ts.
    out_versions = []
    for v in doc.get("versions", []) or []:
        nv = dict(v)
        for ts_field in ("created_at", "last_chatted_at"):
            ts = nv.get(ts_field)
            if hasattr(ts, "isoformat"):
                nv[ts_field] = ts.isoformat()
            elif ts is not None:
                nv[ts_field] = str(ts)
        out_versions.append(nv)
    doc["versions"] = out_versions
    return doc


@router.post("/characters", response_model=CharacterDetail, status_code=201)
async def create_character_endpoint(body: CharacterCreate) -> CharacterDetail:
    """Create a standalone character (stored in MongoDB, no universe required)."""
    doc = _create_character_doc(body.model_dump())
    return CharacterDetail(**_serialise_character(doc))


@router.post("/characters/import-card", response_model=CharacterDetail, status_code=201)
async def import_character_card(file: UploadFile = File(...)) -> CharacterDetail:
    """Import a SillyTavern/Tavern character card (chara_card_v2 JSON or PNG)."""
    from .character_cards import parse_character_card

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Empty file.")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Card file too large (max 20MB).")
    try:
        create = parse_character_card(
            raw, content_type=file.content_type or "", filename=file.filename or ""
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    doc = _create_character_doc(create.model_dump())
    return CharacterDetail(**_serialise_character(doc))


@router.get("/characters/{character_id}/export-card")
async def export_character_card(character_id: str) -> dict:
    """Export a standalone character as a chara_card_v2 object."""
    from .character_cards import build_character_card

    doc = _get_character_doc(character_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Character not found")
    return build_character_card(_serialise_character(doc))


@router.get("/characters", response_model=list[CharacterDetail])
async def list_characters_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CharacterDetail]:
    chars, _total = _list_characters_docs(limit=limit, offset=offset)
    return [CharacterDetail(**_serialise_character(c)) for c in chars]


@router.get("/characters/{character_id}", response_model=CharacterDetail)
async def get_character_endpoint(character_id: str) -> CharacterDetail:
    doc = _get_character_doc(character_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterDetail(**_serialise_character(doc))


@router.put("/characters/{character_id}", response_model=CharacterDetail)
async def update_character_endpoint(
    character_id: str,
    body: CharacterUpdate,
) -> CharacterDetail:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    doc = _update_character_doc(character_id, updates)
    if not doc:
        raise HTTPException(status_code=404, detail="Character not found")
    # update_character may not return all fields — re-fetch
    fresh = _get_character_doc(character_id)
    return CharacterDetail(**_serialise_character(fresh or doc))


@router.delete("/characters/{character_id}", status_code=204)
async def delete_character_endpoint(character_id: str) -> None:
    deleted = _delete_character_doc(character_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Character not found")


@router.post(
    "/characters/{character_id}/import-from-universe", response_model=CharacterDetail
)
async def import_character_from_universe(
    character_id: str,
    body: CharacterImportRequest,
) -> CharacterDetail:
    """Import an existing universe NPC as a standalone character."""
    try:
        from monitor_data.db.neo4j import get_neo4j_client

        client = get_neo4j_client()
        rows = client.execute_read(
            "MATCH (e:EntityInstance {id: $id}) RETURN e",
            {"id": body.source_entity_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Neo4j lookup failed: {exc}")

    if not rows:
        raise HTTPException(status_code=404, detail="NPC not found in universe")
    entity = rows[0]["e"]

    doc = _create_character_doc(
        {
            "name": entity.get("name", "Unknown"),
            "description": entity.get("description", ""),
            "personality": entity.get("properties", {}).get("personality", ""),
            "gm_notes": entity.get("properties", {}).get("gm_notes", ""),
            "is_ooc_persona": body.as_ooc_persona,
            "entity_id": body.source_entity_id,
        }
    )
    return CharacterDetail(**_serialise_character(doc))


@router.post("/characters/{character_id}/save-template")
async def save_template(character_id: str, template_name: str):
    from monitor_data.tools.neo4j_tools.entities import neo4j_save_template

    tid = neo4j_save_template(character_id, template_name)
    if not tid:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Entity not found")
    return {"template_id": tid}


@router.get("/characters/{character_id}/memories")
async def get_character_memories(
    character_id: str,
    min_importance: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List memories for a character (from MongoDB character_memories collection)."""
    char = _get_character_doc(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    entity_id = char.get("entity_id")
    if not entity_id:
        return {"memories": [], "total": 0}

    try:
        from monitor_data.db.mongodb import get_mongodb_client

        coll = get_mongodb_client().get_collection("memories")
        query: dict[str, Any] = {"entity_id": entity_id}
        if min_importance > 0:
            query["importance"] = {"$gte": min_importance}
        total = coll.count_documents(query)
        cursor = coll.find(query).sort("created_at", -1).limit(limit)
        memories = [
            {
                "id": str(m.get("memory_id", m.get("id", ""))),
                "text": m.get("text", m.get("content", "")),
                "importance": m.get("importance", 0.0),
                "created_at": m["created_at"].isoformat()
                if hasattr(m.get("created_at"), "isoformat")
                else str(m.get("created_at", "")),
            }
            for m in cursor
        ]
    except Exception:
        memories = []
        total = 0

    return {"memories": memories, "total": total}


@router.delete("/characters/{character_id}/memories", status_code=204)
async def clear_character_memories(character_id: str) -> None:
    """Delete all memories for a character."""
    char = _get_character_doc(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    entity_id = char.get("entity_id")
    if not entity_id:
        return
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        get_mongodb_client().get_collection("memories").delete_many(
            {"entity_id": entity_id}
        )
        _increment_memory_count(character_id, delta=-char.get("memory_count", 0))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Conversatory — MONITOR-backed chat with a roster character
# ---------------------------------------------------------------------------


@router.post("/characters/draft", response_model=CardDraftResponse)
async def draft_character_card(body: CardDraftRequest) -> CardDraftResponse:
    """LLM-assisted: draft card fields from a concept (does not persist)."""
    from . import character_conversation as cc

    try:
        draft = await cc.draft_card(
            concept=body.concept,
            name=body.name,
            description=body.description,
            personality=body.personality,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Draft failed: {exc}")
    return CardDraftResponse(**draft)


@router.post("/characters/{character_id}/expand", response_model=CharacterExpandResponse)
async def expand_character(
    character_id: str, body: CharacterVersionCreateRequest | None = None
) -> CharacterExpandResponse:
    """Promote a light card into a MONITOR-backed character (entity + NPCProfile).

    Optional body {universe_id} routes expansion to a specific universe.
    """
    from . import character_conversation as cc

    if not _get_character_doc(character_id):
        raise HTTPException(status_code=404, detail="Character not found")
    target_universe = body.universe_id if body else None
    try:
        backing = await cc.ensure_character_backed(character_id, target_universe)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Expansion failed: {exc}")
    return CharacterExpandResponse(
        character_id=character_id,
        version_id=str(backing["version_id"]),
        entity_id=backing["entity_id"],
        universe_id=backing["universe_id"],
    )


@router.post(
    "/characters/{character_id}/versions",
    response_model=CharacterExpandResponse,
)
async def create_character_version(
    character_id: str, body: CharacterVersionCreateRequest
) -> CharacterExpandResponse:
    """Create (or fetch) a per-universe incarnation of the character."""
    return await expand_character(character_id, body)


@router.get(
    "/characters/{character_id}/versions",
    response_model=list[CharacterVersion],
)
async def list_character_versions(character_id: str) -> list[CharacterVersion]:
    """List all per-universe incarnations of a character (newest first)."""
    from .character_storage import list_versions

    if not _get_character_doc(character_id):
        raise HTTPException(status_code=404, detail="Character not found")
    return [CharacterVersion(**v) for v in list_versions(character_id)]


@router.delete(
    "/characters/{character_id}/versions/{universe_id}",
    status_code=204,
)
async def delete_character_version(character_id: str, universe_id: str) -> None:
    """Tear down a Character Version (deletes the EntityInstance + NPCProfile)."""
    from . import character_conversation as cc

    if not _get_character_doc(character_id):
        raise HTTPException(status_code=404, detail="Character not found")
    try:
        ok = await cc.delete_incarnation(character_id, universe_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Delete failed: {exc}")
    if not ok:
        raise HTTPException(status_code=404, detail="Version not found")


@router.post(
    "/characters/{character_id}/conversations", response_model=ConversationStartResponse
)
async def start_character_conversation(
    character_id: str, body: ConversationStartRequest | None = None
) -> ConversationStartResponse:
    """Open a story-less conversatory session.

    Body {universe_id} picks the incarnation. If omitted, the character's
    default incarnation is used (or the hidden Conversatory for light cards).
    """
    from . import character_conversation as cc

    if not _get_character_doc(character_id):
        raise HTTPException(status_code=404, detail="Character not found")
    target_universe = body.universe_id if body else None
    try:
        result = await cc.start_conversation(character_id, target_universe)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not start conversation: {exc}")
    return ConversationStartResponse(**result)


@router.post(
    "/characters/{character_id}/conversations/{conversation_id}/send",
    response_model=ConversationReply,
)
async def send_character_message(
    character_id: str, conversation_id: str, body: ConversationSendRequest
) -> ConversationReply:
    """Send one line; return the character's reply + emotional/relationship read.

    Set include_cross_incarnation=true to broaden NPC memory recall to all
    universes of this character (default false — strict universe partition).
    """
    from . import character_conversation as cc

    try:
        reply = await cc.send_message(
            conversation_id, body.text, body.include_cross_incarnation
        )
    except KeyError:
        raise HTTPException(
            status_code=409,
            detail="Conversation is no longer active. Start a new one.",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Reply failed: {exc}")
    return ConversationReply(**reply)


@router.post("/characters/{character_id}/conversations/{conversation_id}/end")
async def end_character_conversation(character_id: str, conversation_id: str) -> dict:
    """Close a conversatory session (persist working state + stage proposals)."""
    from . import character_conversation as cc

    return await cc.end_conversation(conversation_id)


@router.get(
    "/characters/{character_id}/conversations",
    response_model=list[ConversationSummary],
)
async def list_character_conversations(
    character_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ConversationSummary]:
    """List past conversatory sessions for this character (newest first)."""
    from . import character_conversation as cc

    char = _get_character_doc(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    entity_id = char.get("entity_id")
    if not entity_id:
        return []
    sessions = await asyncio.to_thread(cc.list_conversations, str(entity_id), limit)
    return [ConversationSummary(**s) for s in sessions]


# ---------------------------------------------------------------------------
# Entity Template Cloning (M-31)
# ---------------------------------------------------------------------------


@router.post("/entities/{entity_id}/save-template")
async def save_entity_as_template(entity_id: UUID, template_name: str) -> dict:
    """Clone an entity as an EntityTemplate in Neo4j."""
    from monitor_data.tools.neo4j_tools.entities import neo4j_save_entity_as_template

    try:
        result = neo4j_save_entity_as_template(
            entity_id=entity_id, template_name=template_name
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Character Archetype Linking (GAP-C)
# ---------------------------------------------------------------------------


@router.post("/entities/{entity_id}/link-archetype/{archetype_id}")
async def link_entity_to_archetype(entity_id: UUID, archetype_id: UUID) -> dict:
    """Link an entity to an archetype via DERIVES_FROM relationship."""
    from monitor_data.tools.neo4j_tools.entities import neo4j_link_to_archetype

    try:
        result = neo4j_link_to_archetype(entity_id=entity_id, archetype_id=archetype_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Single-entity CRUD — direct graph manipulation (M-36 / M-38)
# ---------------------------------------------------------------------------


class EntityCreateRequest(BaseModel):
    """Create a single entity on the graph canvas (M-38)."""

    universe_id: UUID
    name: str
    entity_type: str = "concept"
    description: str = ""
    properties: Optional[dict] = None


class EntityPatchRequest(BaseModel):
    """Partial update of an entity from the graph inspector (M-36).

    ``tags`` is the *desired* full set of state tags; the diff against the
    entity's current tags is computed server-side so the client never has to
    reason about add/remove.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[dict] = None
    tags: Optional[list[str]] = None


@router.post("/entities", status_code=201)
async def create_entity(body: EntityCreateRequest) -> dict:
    """Create a single canon entity in a universe (M-38).

    Writes through the data layer's CanonKeeper-authority entity tool so the
    graph stays the single source of truth.
    """
    from monitor_data.schemas.base import Authority, CanonLevel, EntityType
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.tools.neo4j_tools.entities import neo4j_create_entity

    try:
        entity_type = EntityType(body.entity_type)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid entity_type: {body.entity_type}") from exc

    try:
        created = neo4j_create_entity(
            EntityCreate(
                universe_id=body.universe_id,
                name=body.name,
                entity_type=entity_type,
                is_archetype=False,
                description=body.description,
                properties=body.properties or {},
                authority=Authority.GM,
                canon_level=CanonLevel.CANON,
                confidence=1.0,
            )
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Create failed: {exc}") from exc

    return created.model_dump(mode="json")


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str) -> dict:
    """Fetch a single entity by ID for the graph inspector (M-36)."""
    from monitor_data.tools.neo4j_tools.entities import neo4j_get_entity

    uid = validate_uuid(entity_id)
    try:
        entity = neo4j_get_entity(uid)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Lookup failed: {exc}") from exc

    if not entity:
        raise HTTPException(404, "Entity not found")
    return entity.model_dump(mode="json")


@router.patch("/entities/{entity_id}")
async def update_entity(entity_id: str, body: EntityPatchRequest) -> dict:
    """Update a single entity from the graph inspector (M-36).

    Mutable fields (``name``/``description``/``properties``) go through
    ``neo4j_update_entity``; ``tags`` are diffed against current state and
    applied atomically via ``neo4j_set_state_tags``.  Both tools carry
    CanonKeeper authority at the data layer.
    """
    from monitor_data.schemas.entities import EntityUpdate, StateTagsUpdate
    from monitor_data.tools.neo4j_tools.entities import (
        neo4j_get_entity,
        neo4j_set_state_tags,
        neo4j_update_entity,
    )

    uid = validate_uuid(entity_id)

    existing = neo4j_get_entity(uid)
    if not existing:
        raise HTTPException(404, "Entity not found")

    result = existing
    has_field_update = any(
        v is not None for v in (body.name, body.description, body.properties)
    )

    try:
        if has_field_update:
            result = neo4j_update_entity(
                uid,
                EntityUpdate(
                    name=body.name,
                    description=body.description,
                    properties=body.properties,
                ),
            )

        if body.tags is not None and not existing.is_archetype:
            desired = set(body.tags)
            current = set(existing.state_tags or [])
            add = sorted(desired - current)
            remove = sorted(current - desired)
            if add or remove:
                result = neo4j_set_state_tags(
                    uid, StateTagsUpdate(add_tags=add, remove_tags=remove)
                )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Update failed: {exc}") from exc

    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Character Relationships (GAP-F)
# ---------------------------------------------------------------------------


@router.post("/entities/relationships")
async def create_character_relationship(
    from_id: UUID,
    to_id: UUID,
    rel_type: str,
    properties: Optional[dict] = None,
) -> dict:
    """Create a relationship between two characters in Neo4j."""
    from monitor_data.tools.neo4j_tools.entities import (
        neo4j_create_character_relationship,
    )

    try:
        result = neo4j_create_character_relationship(
            from_id=from_id,
            to_id=to_id,
            rel_type=rel_type,
            properties=properties,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Graph edges — inline relationship creation between any entities (M-37)
# ---------------------------------------------------------------------------

# Default category for each relationship type, so the graph UI only has to send
# a rel_type when the user draws an edge.
_REL_TYPE_CATEGORY = {
    "KNOWS": "social",
    "ALLIED_WITH": "social",
    "HOSTILE_TO": "social",
    "MEMBER_OF": "membership",
    "PART_OF": "membership",
    "SUBGROUP_OF": "membership",
    "WORKS_FOR": "membership",
    "OWNS": "ownership",
    "LOCATED_IN": "spatial",
    "CONTAINS": "spatial",
    "PARTICIPATES_IN": "temporal",
    "SUBTYPE_OF": "taxonomic",
    "INSTANCE_OF": "taxonomic",
    "DERIVES_FROM": "taxonomic",
    "LEADS": "power",
    "CONTROLS": "power",
    "CONTROLLED_BY": "power",
    "REVERES": "power",
    "RELATED_TO": "generic",
    "AFFILIATED_WITH": "generic",
}


class EdgeCreateRequest(BaseModel):
    """Create a typed relationship between any two entities (M-37)."""

    from_id: UUID
    to_id: UUID
    rel_type: str = "RELATED_TO"
    category: Optional[str] = None
    properties: Optional[dict] = None


@router.post("/entities/edges", status_code=201)
async def create_edge(body: EdgeCreateRequest) -> dict:
    """Create a relationship edge between two canon entities (M-37).

    Drawn by dragging between nodes on the graph; ``category`` is inferred from
    ``rel_type`` when omitted. Writes via the CanonKeeper-authority data tool.
    """
    from monitor_data.schemas.relationships import (
        RelationshipCategory,
        RelationshipCreate,
        RelationshipType,
    )
    from monitor_data.tools.neo4j_tools.relationships import neo4j_create_relationship

    try:
        rel_type = RelationshipType(body.rel_type)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid rel_type: {body.rel_type}") from exc

    category_value = body.category or _REL_TYPE_CATEGORY.get(rel_type.value, "generic")
    try:
        category = RelationshipCategory(category_value)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid category: {category_value}") from exc

    try:
        rel = neo4j_create_relationship(
            RelationshipCreate(
                from_entity_id=body.from_id,
                to_entity_id=body.to_id,
                rel_type=rel_type,
                category=category,
                properties=body.properties or {},
            )
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Edge creation failed: {exc}") from exc

    return rel.model_dump(mode="json")


@router.get("/entities/{entity_id}/edges")
async def list_edges(entity_id: str) -> dict:
    """List relationships touching an entity, both directions (M-37)."""
    from monitor_data.schemas.relationships import Direction, RelationshipFilter
    from monitor_data.tools.neo4j_tools.relationships import neo4j_list_relationships

    uid = validate_uuid(entity_id)
    try:
        result = neo4j_list_relationships(
            RelationshipFilter(entity_id=uid, direction=Direction.BOTH, limit=200)
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Edge lookup failed: {exc}") from exc

    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Batch Entity Operations (Phase 3.1)
# ---------------------------------------------------------------------------


@router.post("/entities/batch")
async def batch_create_entities(
    body: dict,
) -> dict:
    """Create multiple entities in a single operation.

    Request body:
        - universe_id: UUID (required for all entities)
        - entities: list of EntityCreate dicts (1-100)
        - continue_on_error: bool (default False)

    Returns:
        Dict with created entities, counts, and errors
    """
    from monitor_data.schemas.entities import EntityBatchCreateRequest
    from monitor_data.tools.neo4j_tools.entities import neo4j_batch_create_entities

    try:
        request = EntityBatchCreateRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = neo4j_batch_create_entities(
            requests=request.entities,
            continue_on_error=request.continue_on_error,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/entities/batch")
async def batch_update_entities(
    body: dict,
) -> dict:
    """Update multiple entities in a single operation.

    Request body:
        - updates: list of {entity_id: UUID, update: EntityUpdate dict} (1-100)
        - continue_on_error: bool (default False)

    Returns:
        Dict with updated entities, counts, and errors
    """
    from uuid import UUID

    from monitor_data.schemas.entities import EntityBatchUpdateRequest, EntityUpdate
    from monitor_data.tools.neo4j_tools.entities import neo4j_batch_update_entities

    try:
        request = EntityBatchUpdateRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    updates = []
    for item in request.updates:
        entity_id = item.get("entity_id")
        update_data = item.get("update", {})
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)
        update = (
            EntityUpdate(**update_data)
            if isinstance(update_data, dict)
            else update_data
        )
        updates.append((entity_id, update))

    try:
        result = neo4j_batch_update_entities(
            updates=updates,
            continue_on_error=request.continue_on_error,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/entities/batch")
async def batch_delete_entities(
    body: dict,
) -> dict:
    """Delete multiple entities in a single operation.

    Request body:
        - entity_ids: list of UUIDs (1-100)
        - force: bool (default False) - force delete even with relationships
        - continue_on_error: bool (default False)

    Returns:
        Dict with deleted IDs, counts, and errors
    """
    from monitor_data.schemas.entities import EntityBatchDeleteRequest
    from monitor_data.tools.neo4j_tools.entities import neo4j_batch_delete_entities

    try:
        request = EntityBatchDeleteRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = neo4j_batch_delete_entities(
            entity_ids=request.entity_ids,
            force=request.force,
            continue_on_error=request.continue_on_error,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Character Sheet CRUD (GAP-B)
# ---------------------------------------------------------------------------


@router.get("/character-sheets/{sheet_id}")
async def get_character_sheet(sheet_id: UUID) -> CharacterSheetResponse:
    """Get a character sheet by ID."""
    from monitor_data.tools.mongodb_tools.character_sheets import (
        mongodb_get_character_sheet,
    )

    sheet = mongodb_get_character_sheet(sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Character sheet not found")
    return sheet


@router.patch("/character-sheets/{sheet_id}")
async def update_character_sheet(
    sheet_id: UUID,
    body: CharacterSheetUpdate,
) -> CharacterSheetResponse:
    """Update a character sheet (stats, resources, equipment, etc.)."""
    from monitor_data.tools.mongodb_tools.character_sheets import (
        mongodb_update_character_sheet,
    )

    try:
        return mongodb_update_character_sheet(sheet_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/character-sheets/{sheet_id}", status_code=204)
async def delete_character_sheet(sheet_id: UUID) -> None:
    """Delete (deactivate) a character sheet."""
    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("character_sheets")
    result = coll.update_one(
        {"sheet_id": str(sheet_id)},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Character sheet not found")


@router.get("/character-sheets")
async def list_character_sheets(
    entity_id: Optional[UUID] = None,
    game_system_id: Optional[UUID] = None,
    is_active: Optional[bool] = None,
    limit: int = 20,
    offset: int = 0,
) -> CharacterSheetListResponse:
    """List character sheets with optional filters."""
    from monitor_data.tools.mongodb_tools.character_sheets import (
        mongodb_list_character_sheets,
    )

    if is_active is not None:
        if isinstance(is_active, str):
            is_active_bool = is_active.lower() == "true"
        else:
            is_active_bool = is_active
    else:
        is_active_bool = None
    params = CharacterSheetFilter(
        entity_id=entity_id,
        game_system_id=game_system_id,
        is_active=is_active_bool,
        limit=limit,
        offset=offset,
    )
    return mongodb_list_character_sheets(params)


# ---------------------------------------------------------------------------
# Character Level-Up (P-21 Downtime & Progression)
# ---------------------------------------------------------------------------


class LevelUpResponse(BaseModel):
    """Result of a level-up operation."""

    entity_id: str
    old_level: int
    new_level: int
    xp_remaining: int
    features_gained: list[str] = []
    resource_increases: dict[str, Any] = {}
    message: str = ""


class LevelUpRequest(BaseModel):
    """Request to level up a character."""

    scene_id: Optional[str] = None
    system_id: Optional[str] = None


@router.post("/characters/{character_id}/level-up", response_model=LevelUpResponse)
async def level_up_character(
    character_id: str,
    body: LevelUpRequest,
) -> LevelUpResponse:
    """Spend accumulated XP to advance a character to the next level (P-21).

    Reads the character's current XP/level from their working state (if a
    scene_id is provided) or from their character sheet. Checks the bound
    game system's advancement model to determine if enough XP has been
    accumulated. If yes, applies the level-up: increments level, applies
    resource increases, and records features gained.
    """
    import anyio

    entity_uuid: UUID
    try:
        entity_uuid = UUID(character_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid character_id") from exc

    # 1. Get current XP/level from working state or character sheet
    current_xp = 0
    current_level = 1
    state_id: UUID | None = None

    if body.scene_id:
        from monitor_data.tools.mongodb_tools.working_state import (
            mongodb_get_working_state,
        )
        try:
            scene_uuid = UUID(body.scene_id)
            ws = await anyio.to_thread.run_sync(
                lambda: mongodb_get_working_state(entity_uuid, scene_uuid)
            )
            if ws and getattr(ws, "state", None):
                current_xp = int(ws.state.xp or 0)
                current_level = int(ws.state.level or 1)
                state_id = ws.state.state_id
        except Exception:
            pass  # Fall through to character sheet

    if current_xp == 0 and not state_id:
        # Try character sheet
        from monitor_data.tools.mongodb_tools.character_sheets import (
            mongodb_list_character_sheets,
        )
        try:
            sheets = await anyio.to_thread.run_sync(
                lambda: mongodb_list_character_sheets(
                    CharacterSheetFilter(entity_id=entity_uuid, is_active=True, limit=1)
                )
            )
            if sheets.sheets:
                sheet = sheets.sheets[0]
                current_xp = int(sheet.properties.get("xp", 0))
                current_level = int(sheet.properties.get("level", 1))
        except Exception:
            pass

    # 2. Load the game system's advancement model
    system_id_str = body.system_id
    if not system_id_str:
        # Try to find the system from the character sheet
        from monitor_data.tools.mongodb_tools.character_sheets import (
            mongodb_list_character_sheets,
        )
        try:
            sheets = await anyio.to_thread.run_sync(
                lambda: mongodb_list_character_sheets(
                    CharacterSheetFilter(entity_id=entity_uuid, is_active=True, limit=1)
                )
            )
            if sheets.sheets and sheets.sheets[0].game_system_id:
                system_id_str = str(sheets.sheets[0].game_system_id)
        except Exception:
            pass

    if not system_id_str:
        raise HTTPException(
            status_code=400,
            detail="No game system specified and none found on character sheet",
        )

    from monitor_data.tools.mongodb_tools import mongodb_get_game_system

    try:
        system = await anyio.to_thread.run_sync(
            lambda: mongodb_get_game_system(UUID(system_id_str))
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Game system not found: {exc}") from exc

    advancement = getattr(system, "advancement", None) if system else None
    if not advancement:
        raise HTTPException(
            status_code=422,
            detail="Game system has no advancement model — cannot level up",
        )

    # 3. Check if XP is sufficient for next level
    next_level = current_level + 1
    progression_table = advancement.progression_table or []

    # Find the next level entry
    next_entry = None
    for entry in progression_table:
        if entry.level == next_level:
            next_entry = entry
            break

    if next_entry and next_entry.xp_required is not None:
        if current_xp < next_entry.xp_required:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient XP: have {current_xp}, need {next_entry.xp_required} for level {next_level}",
            )

    # Check max level
    if advancement.max_level and current_level >= advancement.max_level:
        raise HTTPException(
            status_code=422,
            detail=f"Already at max level {advancement.max_level}",
        )

    # 4. Apply level-up
    features_gained = list(next_entry.features_gained) if next_entry else []
    resource_increases = dict(next_entry.resource_increases) if next_entry else {}

    # Update working state if we have one
    if state_id:
        from monitor_data.schemas.working_state import WorkingStateUpdate
        from monitor_data.tools.mongodb_tools.working_state import (
            mongodb_update_working_state,
        )
        new_stats = {"xp": current_xp, "level": next_level}
        await anyio.to_thread.run_sync(
            lambda: mongodb_update_working_state(
                state_id,
                WorkingStateUpdate(current_stats=new_stats),
            )
        )

    return LevelUpResponse(
        entity_id=character_id,
        old_level=current_level,
        new_level=next_level,
        xp_remaining=current_xp - (next_entry.xp_required if next_entry and next_entry.xp_required else 0),
        features_gained=features_gained,
        resource_increases=resource_increases,
        message=f"Level up! {current_level} → {next_level}",
    )


# ---------------------------------------------------------------------------
# Character Downtime / Progression Options (P-21)
# ---------------------------------------------------------------------------


class DowntimeResponse(BaseModel):
    """Available progression options during a downtime phase."""

    entity_id: str
    current_xp: int
    current_level: int
    can_level_up: bool
    next_level_xp_required: int | None = None
    available_features: list[str] = []
    available_resource_increases: dict[str, Any] = {}
    message: str = ""


@router.get("/characters/{character_id}/downtime", response_model=DowntimeResponse)
async def get_downtime_options(
    character_id: str,
    scene_id: str | None = None,
    system_id: str | None = None,
) -> DowntimeResponse:
    """Get available progression options for a character during downtime (P-21).

    Reads current XP/level from working state (if scene_id provided) or
    character sheet, then checks the advancement model to determine if
    level-up is available and what features/resource increases would be gained.
    """
    import anyio

    entity_uuid: UUID
    try:
        entity_uuid = UUID(character_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid character_id") from exc

    # 1. Get current XP/level
    current_xp = 0
    current_level = 1

    if scene_id:
        from monitor_data.tools.mongodb_tools.working_state import (
            mongodb_get_working_state,
        )
        try:
            scene_uuid = UUID(scene_id)
            ws = await anyio.to_thread.run_sync(
                lambda: mongodb_get_working_state(entity_uuid, scene_uuid)
            )
            if ws and getattr(ws, "state", None):
                current_xp = int(ws.state.xp or 0)
                current_level = int(ws.state.level or 1)
        except Exception:
            pass

    if current_xp == 0:
        from monitor_data.tools.mongodb_tools.character_sheets import (
            mongodb_list_character_sheets,
        )
        try:
            sheets = await anyio.to_thread.run_sync(
                lambda: mongodb_list_character_sheets(
                    CharacterSheetFilter(entity_id=entity_uuid, is_active=True, limit=1)
                )
            )
            if sheets.sheets:
                sheet = sheets.sheets[0]
                current_xp = int(sheet.properties.get("xp", 0))
                current_level = int(sheet.properties.get("level", 1))
                if not system_id and sheet.game_system_id:
                    system_id = str(sheet.game_system_id)
        except Exception:
            pass

    # 2. Load advancement model
    if not system_id:
        return DowntimeResponse(
            entity_id=character_id,
            current_xp=current_xp,
            current_level=current_level,
            can_level_up=False,
            message="No game system found — cannot evaluate progression",
        )

    from monitor_data.tools.mongodb_tools import mongodb_get_game_system

    try:
        system = await anyio.to_thread.run_sync(
            lambda: mongodb_get_game_system(UUID(system_id))
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Game system not found: {exc}") from exc

    advancement = getattr(system, "advancement", None) if system else None
    if not advancement:
        return DowntimeResponse(
            entity_id=character_id,
            current_xp=current_xp,
            current_level=current_level,
            can_level_up=False,
            message="Game system has no advancement model",
        )

    # 3. Check if level-up is available
    next_level = current_level + 1
    next_entry = None
    for entry in (advancement.progression_table or []):
        if entry.level == next_level:
            next_entry = entry
            break

    if advancement.max_level and current_level >= advancement.max_level:
        return DowntimeResponse(
            entity_id=character_id,
            current_xp=current_xp,
            current_level=current_level,
            can_level_up=False,
            message=f"Already at max level {advancement.max_level}",
        )

    xp_required = next_entry.xp_required if next_entry else None
    can_level = xp_required is None or current_xp >= xp_required

    return DowntimeResponse(
        entity_id=character_id,
        current_xp=current_xp,
        current_level=current_level,
        can_level_up=can_level,
        next_level_xp_required=xp_required,
        available_features=list(next_entry.features_gained) if next_entry else [],
        available_resource_increases=dict(next_entry.resource_increases) if next_entry else {},
        message="Progression available" if can_level else f"Need {xp_required - current_xp} more XP" if xp_required else "No progression table",
    )
