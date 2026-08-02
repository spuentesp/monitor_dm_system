"""
Entities router — NPCs, RPG systems, and characters.

Queries MongoDB and Neo4j for entity data.  Falls back to empty lists
when databases are not available.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from monitor_data.schemas.entities import LevelUpResponse, LevelUpRequest, DowntimeResponse
from monitor_agents.services.entity_service import EntityProgressionService

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from monitor_agents.analyzer._game_system_persistence import (
    _build_attributes,
    _build_character_creation,
    _build_core_mechanic,
    _build_resources,
    _build_skills,
)
from monitor_data.schemas.base import CanonLevel, SimulationScope
from monitor_data.schemas.character_sheets import (
    CharacterSheetFilter,
    CharacterSheetListResponse,
    CharacterSheetResponse,
    CharacterSheetUpdate,
)
from monitor_data.schemas.facts import (
    AxiomUpdate,
    EventUpdate,
    FactStatus,
    FactType,
    FactUpdate,
)
from monitor_data.schemas.game_systems import (
    GameRule,
    GameRuleType,
    GameSystemCreate,
    GameSystemResponse,
    GameSystemUpdate,
)
from monitor_data.schemas.relationships import RelationshipUpdate
from monitor_data.tools.mongodb_tools import (
    mongodb_create_game_system,
    mongodb_delete_game_system,
    mongodb_update_game_system,
)
from pydantic import BaseModel

from monitor_ui.config import get_settings

from .character_storage import (
    create_character as _create_character_doc,
)
from .character_storage import (
    delete_character as _delete_character_doc,
)
from .character_storage import (
    get_character as _get_character_doc,
)
from .character_storage import (
    increment_memory_count as _increment_memory_count,
)
from .character_storage import (
    list_characters as _list_characters_docs,
)
from .character_storage import (
    update_character as _update_character_doc,
)
from .entities_schemas import (
    NPC,
    AttributeInfo,
    AxiomCreateRequest,
    CardDraftRequest,
    CardDraftResponse,
    Character,
    CharacterCreate,
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
    EventCreateRequest,
    FactCreateRequest,
    GenerateEntityRequest,
    NPCDetail,
    NPCProfileUpsertRequest,
    PaginatedNPCs,
    ResourceInfo,
    RPGSystem,
    RPGSystemCreateRequest,
    RPGSystemUpdateRequest,
    RuleInfo,
    SkillInfo,
)
from .ingest_shared import validate_uuid

logger = structlog.get_logger()

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
            count_result = client.execute_read(f"MATCH (e:Entity) {where} RETURN count(e) AS total", params)
            total = count_result[0]["total"] if count_result else 0

            rows = client.execute_read(
                f"MATCH (e:Entity) {where} RETURN e ORDER BY e.name SKIP $offset LIMIT $limit",
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
        from motor.motor_asyncio import AsyncIOMotorClient

        client: AsyncIOMotorClient = AsyncIOMotorClient(_settings.mongodb_uri, serverSelectionTimeoutMS=2000)    # type: ignore
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
                    mechanic_type=cm_raw.get("type", cm_raw.get("mechanic_type", "custom")),
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
                    needs_review=doc.get("needs_review", False),
                    degenerate_reason=doc.get("degenerate_reason"),
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
                "game_system_id": str(pack.game_system_id) if pack.game_system_id else None,
                "doc": embedded_system.model_dump(mode="json"),
            }

        if pack.game_system_id:
            system = mongodb_get_game_system(pack.game_system_id)
            if not system:
                raise HTTPException(status_code=404, detail="Linked game system not found")
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
        raise HTTPException(status_code=400, detail="Either system_id or pack_id is required")

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
    state_tags = [str(tag) for tag in dict.fromkeys([*(preview.get("tags") or []), kind, "generated"])]
    role = "PC" if kind == "pc" else "NPC"

    entity = neo4j_create_entity(
        EntityCreate(
            universe_id=universe_uuid,
            name=str(preview.get("name") or ("Generated NPC" if kind == "npc" else "Generated Character")),
            entity_type=EntityType.CHARACTER,
            sub_type=None,
            is_archetype=False,
            description=str(preview.get("description") or ""),
            properties={
                "role": role,
                "concept": preview.get("concept") or preview.get("description") or "",
                "generation_source": source_meta.get("source_type"),
                "system_name": preview.get("system_name") or source_meta.get("source_label"),
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
            game_system_id=UUID(source_meta["system_id"]) if source_meta.get("system_id") else None,
            system_source_type=str(source_meta.get("source_type") or "narrative_only"),
            system_source_id=str(
                source_meta.get("pack_id")
                or source_meta.get("system_id")
                or source_meta.get("game_system_id")
                or entity.id
            ),
            system_name=str(preview.get("system_name") or source_meta.get("source_label") or "Narrative"),
            source_persona_id=preview.get("source_persona_id"),
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
    entity_type: str | None = Query(default=None, description="Comma-separated entity types to include"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedNPCs:
    entity_types = [t.strip() for t in entity_type.split(",") if t.strip()] if entity_type else None
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
# NPC profile read/edit (F2-2 phase 5)
# ---------------------------------------------------------------------------


@router.get("/npcs/{npc_id}/profile")
async def get_npc_profile(npc_id: str) -> dict[str, Any]:
    """Fetch the Mongo NPCProfile for a world NPC (keyed by Neo4j entity id).

    The profile is the psychological backbone (traits, values, triggers,
    GM secrets) maintained separately from the Neo4j EntityInstance.
    """
    from monitor_data.tools.mongodb_tools import mongodb_get_npc_profile

    uid = validate_uuid(npc_id)
    try:
        profile = mongodb_get_npc_profile(uid)
    except Exception as exc:
        raise HTTPException(503, f"Profile lookup failed: {exc}") from exc
    if profile is None:
        raise HTTPException(404, "NPC profile not found")
    return profile.model_dump(mode="json")


@router.put("/npcs/{npc_id}/profile")
async def upsert_npc_profile(npc_id: str, body: NPCProfileUpsertRequest) -> dict[str, Any]:
    """Create-or-update the NPCProfile for a world NPC (F2-2 phase 5).

    Writes through the data layer's ``mongodb_update_npc_profile``, which
    upserts an empty profile document when none exists yet.
    """
    from monitor_data.schemas.npc_profiles import NPCProfileUpdate
    from monitor_data.tools.mongodb_tools import mongodb_update_npc_profile

    uid = validate_uuid(npc_id)
    try:
        profile = mongodb_update_npc_profile(uid, NPCProfileUpdate(**body.model_dump(exclude_unset=True)))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Profile update failed: {exc}") from exc
    return profile.model_dump(mode="json")


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


def _build_game_system_create(body: RPGSystemCreateRequest) -> GameSystemCreate:
    """Build a validated ``GameSystemCreate`` from a hand-author request.

    Runs through the same builders ingestion uses (``_build_attributes`` /
    ``_build_core_mechanic`` / ``_build_character_creation``) so a
    hand-authored system is structurally identical to, and passes the same
    semantic validation as, one produced by the ingestion pipeline.
    """
    if body.core_mechanic is not None:
        core_mechanic = _build_core_mechanic(
            {
                "core_mechanic": {
                    "type": body.core_mechanic.mechanic_type,
                    "formula": body.core_mechanic.formula,
                    "success_type": body.core_mechanic.success_type,
                }
            }
        )
    else:
        core_mechanic = _build_core_mechanic({})

    character_creation = _build_character_creation(body.character_creation) if body.character_creation else None

    return GameSystemCreate(
        name=body.name,
        description=body.description,
        version=body.version,
        core_mechanic=core_mechanic,
        attributes=_build_attributes({"attributes": [a.model_dump(exclude_none=True) for a in body.attributes]}),
        skills=_build_skills({"skills": [s.model_dump(exclude_none=True) for s in body.skills]}),
        resources=_build_resources({"resources": [r.model_dump(exclude_none=True) for r in body.resources]}),
        character_creation=character_creation,
        hand_authored=True,
        degenerate_reason=None,
    )


def _build_game_system_update(body: RPGSystemUpdateRequest) -> GameSystemUpdate:
    """Build a ``GameSystemUpdate`` touching only the fields the caller sent."""
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
    if body.attributes is not None:
        update_kwargs["attributes"] = _build_attributes(
            {"attributes": [a.model_dump(exclude_none=True) for a in body.attributes]}
        )
    if body.skills is not None:
        update_kwargs["skills"] = _build_skills({"skills": [s.model_dump(exclude_none=True) for s in body.skills]})
    if body.resources is not None:
        update_kwargs["resources"] = _build_resources(
            {"resources": [r.model_dump(exclude_none=True) for r in body.resources]}
        )
    if body.core_mechanic is not None:
        update_kwargs["core_mechanic"] = _build_core_mechanic(
            {
                "core_mechanic": {
                    "type": body.core_mechanic.mechanic_type,
                    "formula": body.core_mechanic.formula,
                    "success_type": body.core_mechanic.success_type,
                }
            }
        )
    if body.character_creation is not None:
        # Same builder ingestion uses — Finding 2's step_type/content
        # semantic check applies here too, so a hand-patch can't
        # introduce the same mismatch a bad LLM extraction did.
        update_kwargs["character_creation"] = _build_character_creation(body.character_creation)
    return GameSystemUpdate(**update_kwargs)


def _rpg_system_from_response(system: GameSystemResponse) -> RPGSystem:
    """Map a data-layer ``GameSystemResponse`` to the router's RPGSystem DTO."""
    core = system.core_mechanic
    return RPGSystem(
        id=str(system.id),
        name=system.name,
        description=system.description,
        version=system.version,
        core_mechanic=(
            CoreMechanicInfo(
                mechanic_type=core.type.value if hasattr(core.type, "value") else str(core.type),
                formula=core.formula,
                success_type=core.success_type.value if hasattr(core.success_type, "value") else str(core.success_type),
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
            for a in system.attributes
        ],
        skills=[
            SkillInfo(
                name=s.name,
                linked_attribute=s.linked_attribute,
                description=s.description,
                untrained_allowed=True,
            )
            for s in system.skills
        ],
        resources=[
            ResourceInfo(
                name=r.name,
                abbreviation=r.abbreviation,
                max_value=None,
                recovers_on=r.recovers_on,
                depleted_effect=r.depleted_effect,
            )
            for r in system.resources
        ],
        rules=[
            RuleInfo(
                name=r.name,
                rule_type=r.rule_type.value if hasattr(r.rule_type, "value") else str(r.rule_type),
                description=r.description,
                formula=r.formula,
                examples=[],
                exceptions=[],
            )
            for r in system.rules
        ],
        is_builtin=system.is_builtin,
        source_document_id=str(system.source_document_id) if system.source_document_id else None,
        character_count=0,
        session_count=0,
        needs_review=system.needs_review,
        degenerate_reason=system.degenerate_reason,
    )


@router.post("/systems", response_model=RPGSystem, status_code=201)
async def create_system(body: RPGSystemCreateRequest) -> RPGSystem:
    """Hand-author a game system with no source PDF (Finding 8, second gap).

    Runs through the same builders ingestion uses (``_build_attributes`` /
    ``_build_core_mechanic`` / ``_build_character_creation``) so a
    hand-authored system is structurally identical to, and passes the same
    semantic validation as, one produced by the ingestion pipeline.
    """
    try:
        created = await asyncio.to_thread(mongodb_create_game_system, _build_game_system_create(body))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _rpg_system_from_response(created)


@router.put("/systems/{system_id}", response_model=RPGSystem)
async def update_system(system_id: str, body: RPGSystemUpdateRequest) -> RPGSystem:
    uid = validate_uuid(system_id, "system id")

    try:
        updated = await asyncio.to_thread(mongodb_update_game_system, uid, _build_game_system_update(body))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _rpg_system_from_response(updated)


@router.delete("/systems/{system_id}", status_code=204)
async def delete_system(system_id: str) -> None:
    """Delete a game system from MongoDB."""
    uid = validate_uuid(system_id, "system id")
    try:
        await asyncio.to_thread(mongodb_delete_game_system, uid)
    except ValueError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 422
        raise HTTPException(status_code=status, detail=msg) from exc


@router.post("/systems/{system_id}/test")
async def test_system(system_id: str) -> dict[str, Any]:
    """Roll a test character for this system using `GameSystemRuntime`."""
    try:
        source_meta = await asyncio.to_thread(_resolve_system_source, system_id=system_id)
        from monitor_agents.game_system import GameSystemRuntime

        gsr = GameSystemRuntime(source_meta["doc"])
        candidate = await asyncio.to_thread(gsr.build_character_candidate, name="Test Character")
        return {
            "system_name": candidate.get("system_name", source_meta.get("source_label", "")),
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
async def test_system_npc(system_id: str, body: GenerateEntityRequest | None = None) -> dict[str, Any]:
    """Generate a test NPC for a generic library system."""
    try:
        source_meta = await asyncio.to_thread(_resolve_system_source, system_id=system_id)
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
            "system_name": candidate.get("system_name", source_meta.get("source_label", "")),
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
        source_meta = _resolve_system_source(system_id=body.system_id, pack_id=body.pack_id)
        from monitor_agents.game_system import GameSystemRuntime

        gsr = GameSystemRuntime(source_meta["doc"])
        if body.kind == "npc":
            preview = gsr.generate_npc(name=body.name, tier=body.tier, concept=body.concept or body.description)
        else:
            preview = gsr.build_character_candidate(
                name=body.name or "Generated Character",
                description=body.description or "",
                concept=body.concept,
            )

        if body.state_tags:
            preview["tags"] = list(dict.fromkeys([*(preview.get("tags") or []), *body.state_tags]))

        saved = None
        if body.save:
            if not body.universe_id:
                raise HTTPException(status_code=422, detail="universe_id is required when save=true")
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
                name=getattr(entities_by_id.get(str(sheet.entity_id)), "name", "Unknown"),
                system_id=str(sheet.game_system_id) if sheet.game_system_id else system_id,
                system_name=sheet.system_name,
                universe_id=str(getattr(entities_by_id.get(str(sheet.entity_id)), "universe_id", "")),
                description=getattr(entities_by_id.get(str(sheet.entity_id)), "description", None),
                attributes=sheet.stats,
                state_tags=list(getattr(entities_by_id.get(str(sheet.entity_id)), "state_tags", [])),
                canon_level=str(getattr(entities_by_id.get(str(sheet.entity_id)), "canon_level", "canon")),
            )
            for sheet in sheets.sheets
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Standalone Character CRUD (Roleplay UI)
# ---------------------------------------------------------------------------


def _character_entity_ids(char: dict[str, Any]) -> list[str]:
    """All entity ids a standalone character's memories may be filed under.

    Light-RP conversations write memories against the incarnation's
    per-universe entity id (versions[].entity_id), not the character id.
    """
    ids = [str(v["entity_id"]) for v in char.get("versions", []) or [] if v.get("entity_id")]
    if char.get("entity_id"):
        ids.append(str(char["entity_id"]))
    return ids


def _count_character_memories(entity_ids: list[str]) -> int:
    """Live memory count across a character's incarnation entity ids."""
    if not entity_ids:
        return 0
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        coll = get_mongodb_client().get_collection("character_memories")
        return int(coll.count_documents({"entity_id": {"$in": entity_ids}}))
    except Exception:
        return 0


def _serialise_character(doc: dict) -> dict:    # type: ignore
    """Convert MongoDB document fields to JSON-safe strings for CharacterDetail.

    Adds defaults for fields introduced by the Character Versions feature so
    legacy character docs (created before versions existed) serialize cleanly.
    """
    doc["created_at"] = (
        doc["created_at"].isoformat() if hasattr(doc["created_at"], "isoformat") else str(doc["created_at"])
    )
    doc["updated_at"] = (
        doc["updated_at"].isoformat() if hasattr(doc["updated_at"], "isoformat") else str(doc["updated_at"])
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
                nv[ts_field] = ts.isoformat()    # type: ignore
            elif ts is not None:
                nv[ts_field] = str(ts)
        out_versions.append(nv)
    doc["versions"] = out_versions
    # Memory badge: count live from character_memories (the doc's stored
    # memory_count is only ever reset, never incremented on writes).
    doc["memory_count"] = _count_character_memories(_character_entity_ids(doc))
    return doc


@router.post("/characters", response_model=CharacterDetail, status_code=201)
async def create_character_endpoint(body: CharacterCreate) -> CharacterDetail:
    """Create a standalone character (stored in MongoDB, no universe required)."""
    doc = _create_character_doc(body.model_dump())
    return CharacterDetail(**_serialise_character(doc))


@router.post("/characters/import-card", response_model=CharacterDetail, status_code=201)
async def import_character_card(file: UploadFile = File(...)) -> CharacterDetail:
    """Import a SillyTavern/Tavern character card (chara_card_v2 JSON, PNG, or CharX).

    Also imports any embedded ``character_book`` lorebook entries. For CharX
    archives, the icon asset is uploaded to MinIO and bound as the avatar.
    """
    from monitor_data.tools.mongodb_tools.lorebook_tools import (
        mongodb_bulk_create_lorebook_entries,
        mongodb_save_scan_config,
    )
    from .character_cards import (
        extract_charx_assets,
        is_charx_file,
        parse_character_card_with_book,
        resolve_charx_icon,
        sniff_image_type,
    )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Empty file.")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Card file too large (max 20MB).")
    try:
        create, lorebook_entries, scan_config = parse_character_card_with_book(
            raw, content_type=file.content_type or "", filename=file.filename or ""
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # CharX: lift the icon asset into MinIO and bind it as the avatar.
    if is_charx_file(raw, content_type=file.content_type or "", filename=file.filename or ""):
        try:
            from monitor_data.db.minio import get_minio_client

            from .character_cards import extract_charx_card

            card = extract_charx_card(raw)
            icon = resolve_charx_icon(card, extract_charx_assets(raw))
            if icon:
                content_type, ext = sniff_image_type(icon)
                key = f"assets/avatar/imported/{uuid4()}.{ext}"
                await get_minio_client().upload(key, icon, content_type=content_type)
                create.avatar_url = key
        except Exception as exc:
            # Asset extraction is best-effort: a card without its icon is
            # still a valid import.
            logger.warning("charx asset extraction failed, importing without avatar: %s", exc)

    doc = _create_character_doc(create.model_dump())
    character_id = doc.get("id") or doc.get("_id")
    if character_id and lorebook_entries:
        mongodb_bulk_create_lorebook_entries(character_id=str(character_id), entries=lorebook_entries)
        mongodb_save_scan_config(str(character_id), scan_config)

    return CharacterDetail(**_serialise_character(doc))


@router.get("/characters/{character_id}/export-card")
async def export_character_card(character_id: str) -> dict:    # type: ignore
    """Export a standalone character as a chara_card_v2 object.

    Includes the character's lorebook as an embedded ``character_book``.
    """
    from monitor_data.tools.mongodb_tools.lorebook_tools import (
        mongodb_get_lorebook_entries,
        mongodb_get_scan_config,
    )
    from .character_cards import build_character_card

    doc = _get_character_doc(character_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Character not found")

    entries = mongodb_get_lorebook_entries(character_id, sort_by="order", ascending=True)
    scan_config = mongodb_get_scan_config(character_id)
    return build_character_card(
        _serialise_character(doc),
        lorebook_entries=[e.model_dump() for e in entries],
        scan_config=scan_config,
    )


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


@router.post("/characters/{character_id}/import-from-universe", response_model=CharacterDetail)
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
async def save_template(character_id: str, template_name: str):    # type: ignore
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
) -> dict:    # type: ignore
    """List memories for a character (from MongoDB character_memories collection)."""
    char = _get_character_doc(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    entity_ids = _character_entity_ids(char)
    if not entity_ids:
        return {"memories": [], "total": 0}

    try:
        from monitor_data.db.mongodb import get_mongodb_client

        coll = get_mongodb_client().get_collection("character_memories")
        query: dict[str, Any] = {"entity_id": {"$in": entity_ids}}
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
    entity_ids = _character_entity_ids(char)
    if not entity_ids:
        return
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        get_mongodb_client().get_collection("character_memories").delete_many(
            {"entity_id": {"$in": entity_ids}}
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
    except Exception as exc:
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
    except Exception as exc:
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
async def create_character_version(character_id: str, body: CharacterVersionCreateRequest) -> CharacterExpandResponse:
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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Delete failed: {exc}")
    if not ok:
        raise HTTPException(status_code=404, detail="Version not found")


@router.get(
    "/characters/{character_id}/profile",
    response_model=dict,
)
async def get_character_profile(character_id: str) -> dict:    # type: ignore
    """Return the NPCProfile doc for the character's default incarnation.

    Read-only introspection — primarily used by e2e property tests and
    debug tools that need to verify per-universe partitions are populated.
    """
    from monitor_data.tools.mongodb_tools import mongodb_get_npc_profile

    if not _get_character_doc(character_id):
        raise HTTPException(status_code=404, detail="Character not found")
    # Ensure backing entity exists; don't auto-provision (read-only).
    char = _get_character_doc(character_id)
    entity_id = char.get("entity_id")    # type: ignore
    if not entity_id:
        raise HTTPException(
            status_code=409,
            detail="Character has no incarnation yet (light card not expanded).",
        )
    try:
        profile = mongodb_get_npc_profile(UUID(entity_id))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Mongo read failed: {exc}")
    if profile is None:
        raise HTTPException(status_code=404, detail="NPCProfile not found in MongoDB")
    # Serialise the Pydantic response model so the per-universe partition
    # maps and timestamps survive the JSON roundtrip.
    return profile.model_dump(mode="json")


@router.post("/characters/{character_id}/conversations", response_model=ConversationStartResponse)
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
    persona_id = body.persona_character_id if body else None
    try:
        result = await cc.start_conversation(
            character_id, target_universe, persona_character_id=persona_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
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

    Sessions are process-local; if the backend restarted since this
    conversation was last used, it is transparently rebuilt from the
    persisted transcript (resume).
    """
    from . import character_conversation as cc

    try:
        reply = await cc.send_message(
            conversation_id, body.text, body.include_cross_incarnation, character_id=character_id
        )
    except KeyError:
        raise HTTPException(
            status_code=409,
            detail="Conversation is no longer active. Start a new one.",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply failed: {exc}")
    return ConversationReply(**reply)


@router.post("/characters/{character_id}/conversations/{conversation_id}/end")
async def end_character_conversation(character_id: str, conversation_id: str) -> dict:    # type: ignore
    """Close a conversatory session (persist working state + stage proposals).

    If the loop was lost to a backend restart, it is rebuilt from the
    persisted transcript first so accumulated proposals still stage.
    """
    from . import character_conversation as cc

    return await cc.end_conversation(conversation_id, character_id=character_id)


@router.post("/characters/{character_id}/conversations/{conversation_id}/redistill")
async def redistill_character_conversation(
    character_id: str, conversation_id: str, force: bool = False
) -> dict:    # type: ignore
    """Rebuild episodic event proposals from the persisted transcript.

    Use after a close-time extraction failure, or with force=true to
    regenerate proposals that already exist.
    """
    from . import character_conversation as cc

    try:
        return await cc.redistill_conversation(character_id, conversation_id, force=force)
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversation not found for this character.")


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
async def save_entity_as_template(entity_id: UUID, template_name: str) -> dict:    # type: ignore
    """Clone an entity as an EntityTemplate in Neo4j."""
    from monitor_data.tools.neo4j_tools.entities import neo4j_save_entity_as_template

    try:
        result = neo4j_save_entity_as_template(entity_id=entity_id, template_name=template_name)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Character Archetype Linking (GAP-C)
# ---------------------------------------------------------------------------


@router.post("/entities/{entity_id}/link-archetype/{archetype_id}")
async def link_entity_to_archetype(entity_id: UUID, archetype_id: UUID) -> dict:    # type: ignore
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
    properties: dict | None = None    # type: ignore


class EntityPatchRequest(BaseModel):
    """Partial update of an entity from the graph inspector (M-36).

    ``tags`` is the *desired* full set of state tags; the diff against the
    entity's current tags is computed server-side so the client never has to
    reason about add/remove.
    """

    name: str | None = None
    description: str | None = None
    properties: dict | None = None    # type: ignore
    tags: list[str] | None = None


@router.post("/entities", status_code=201)
async def create_entity(body: EntityCreateRequest) -> dict:    # type: ignore
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
    except Exception as exc:
        raise HTTPException(503, f"Create failed: {exc}") from exc

    return created.model_dump(mode="json")


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str) -> dict:    # type: ignore
    """Fetch a single entity by ID for the graph inspector (M-36)."""
    from monitor_data.tools.neo4j_tools.entities import neo4j_get_entity

    uid = validate_uuid(entity_id)
    try:
        entity = neo4j_get_entity(uid)
    except Exception as exc:
        raise HTTPException(503, f"Lookup failed: {exc}") from exc

    if not entity:
        raise HTTPException(404, "Entity not found")
    return entity.model_dump(mode="json")


@router.patch("/entities/{entity_id}")
async def update_entity(entity_id: str, body: EntityPatchRequest) -> dict:    # type: ignore
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
    has_field_update = any(v is not None for v in (body.name, body.description, body.properties))

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
                result = neo4j_set_state_tags(uid, StateTagsUpdate(add_tags=add, remove_tags=remove))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
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
    properties: dict | None = None,    # type: ignore
) -> dict:    # type: ignore
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
    category: str | None = None
    properties: dict | None = None    # type: ignore


@router.post("/entities/edges", status_code=201)
async def create_edge(body: EdgeCreateRequest) -> dict:    # type: ignore
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
    except Exception as exc:
        raise HTTPException(503, f"Edge creation failed: {exc}") from exc

    return rel.model_dump(mode="json")


@router.get("/entities/{entity_id}/edges")
async def list_edges(entity_id: str) -> dict:    # type: ignore
    """List relationships touching an entity, both directions (M-37)."""
    from monitor_data.schemas.relationships import Direction, RelationshipFilter
    from monitor_data.tools.neo4j_tools.relationships import neo4j_list_relationships

    uid = validate_uuid(entity_id)
    try:
        result = neo4j_list_relationships(RelationshipFilter(entity_id=uid, direction=Direction.BOTH, limit=200))
    except Exception as exc:
        raise HTTPException(503, f"Edge lookup failed: {exc}") from exc

    return result.model_dump(mode="json")


@router.get("/entities/universes/{universe_id}/relationships")
async def list_universe_relationships(
    universe_id: UUID,
    rel_type: str | None = None,
    category: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List relationships whose endpoints both live in a universe (F2-2 phase 6).

    Backs the Ontology page's Relationships tab. Universe scoping follows the
    graph router's precedent (``routers/graph.py``): entities of the universe
    are listed first, relationships are filtered to pairs inside that set.
    """
    from monitor_data.schemas.entities import EntityFilter
    from monitor_data.schemas.relationships import (
        RelationshipCategory,
        RelationshipFilter,
        RelationshipType,
    )
    from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities
    from monitor_data.tools.neo4j_tools.relationships import neo4j_list_relationships

    rel_type_enum = None
    if rel_type:
        try:
            rel_type_enum = RelationshipType(rel_type)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid rel_type: {rel_type}") from exc
    category_enum = None
    if category:
        try:
            category_enum = RelationshipCategory(category)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid category: {category}") from exc

    try:
        entities_r = neo4j_list_entities(EntityFilter(universe_id=universe_id, limit=1000))
        universe_entity_ids = {str(e.id) for e in entities_r.entities}
        rels_r = neo4j_list_relationships(
            RelationshipFilter(rel_type=rel_type_enum, category=category_enum, limit=1000)
        )
    except Exception as exc:
        raise HTTPException(503, f"Relationship lookup failed: {exc}") from exc

    in_universe = [
        r
        for r in rels_r.relationships
        if str(r.from_entity_id) in universe_entity_ids and str(r.to_entity_id) in universe_entity_ids
    ]
    page = in_universe[offset : offset + limit]
    return {
        "relationships": [r.model_dump(mode="json") for r in page],
        "total": len(in_universe),
        "limit": limit,
        "offset": offset,
    }


@router.patch("/entities/relationships/{relationship_id}")
async def update_relationship(relationship_id: str, body: RelationshipUpdate) -> dict[str, Any]:
    """Update a relationship's properties/category/tags (F2-2 phase 2).

    ``relationship_id`` is the Neo4j internal edge ID (numeric string), as
    returned by the edge list/create endpoints.
    """
    from monitor_data.tools.neo4j_tools.relationships import neo4j_update_relationship

    try:
        rel = neo4j_update_relationship(relationship_id, body)
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Relationship update failed: {exc}") from exc
    return rel.model_dump(mode="json")


@router.delete("/entities/relationships/{relationship_id}")
async def delete_relationship(relationship_id: str) -> dict[str, Any]:
    """Delete a relationship edge by Neo4j internal ID (F2-2 phase 2)."""
    from monitor_data.tools.neo4j_tools.relationships import neo4j_delete_relationship

    try:
        return neo4j_delete_relationship(relationship_id)
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Relationship delete failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Ontology CRUD — facts / axioms / events (F2-2 phase 1, M-12…M-25 family)
# ---------------------------------------------------------------------------


def _http_for_value_error(exc: ValueError) -> HTTPException:
    """Map a data-layer ValueError to 404 for missing nodes, else 400."""
    msg = str(exc)
    status = 404 if "not found" in msg.lower() else 400
    return HTTPException(status, msg)


@router.post("/entities/{universe_id}/facts", status_code=201)
async def create_fact(universe_id: UUID, body: FactCreateRequest) -> dict[str, Any]:
    """Create a fact in a universe (F2-2).

    Writes through the data layer's CanonKeeper-authority fact tool — the
    same direct-write precedent as single-entity create (``POST /entities``).
    """
    from monitor_data.schemas.facts import FactCreate
    from monitor_data.tools.neo4j_tools.facts import neo4j_create_fact

    params = FactCreate(**body.model_dump(exclude={"universe_id"}), universe_id=universe_id)
    try:
        fact = neo4j_create_fact(params)
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Create failed: {exc}") from exc
    return fact.model_dump(mode="json")


@router.get("/entities/{universe_id}/facts")
async def list_facts(
    universe_id: UUID,
    fact_type: FactType | None = None,
    canon_level: CanonLevel | None = None,
    status: FactStatus | None = None,
    scope: SimulationScope | None = None,
    entity_id: UUID | None = None,
    min_magnitude: int = Query(default=1, ge=1, le=10),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List facts in a universe with optional filters (F2-2)."""
    from monitor_data.schemas.facts import FactFilter
    from monitor_data.tools.neo4j_tools.facts import neo4j_list_facts

    filters = FactFilter(
        universe_id=universe_id,
        entity_id=entity_id,
        fact_type=fact_type,
        canon_level=canon_level,
        status=status or FactStatus.ACTIVE,
        min_magnitude=min_magnitude,
        scope=scope,
        limit=limit,
        offset=offset,
    )
    try:
        facts = neo4j_list_facts(filters)
    except Exception as exc:
        raise HTTPException(503, f"Fact lookup failed: {exc}") from exc
    return {
        "facts": [f.model_dump(mode="json") for f in facts],
        "count": len(facts),
        "limit": limit,
        "offset": offset,
    }


@router.patch("/entities/facts/{fact_id}")
async def update_fact(fact_id: UUID, body: FactUpdate) -> dict[str, Any]:
    """Update a fact's mutable fields (F2-2)."""
    from monitor_data.tools.neo4j_tools.facts import neo4j_update_fact

    try:
        fact = neo4j_update_fact(fact_id, body)
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Update failed: {exc}") from exc
    return fact.model_dump(mode="json")


@router.delete("/entities/facts/{fact_id}")
async def delete_fact(fact_id: UUID, force: bool = False) -> dict[str, Any]:
    """Delete a fact; canon facts require ``force=true`` (F2-2)."""
    from monitor_data.tools.neo4j_tools.facts import neo4j_delete_fact

    try:
        return neo4j_delete_fact(fact_id, force=force)
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Delete failed: {exc}") from exc


@router.post("/entities/{universe_id}/axioms", status_code=201)
async def create_axiom(universe_id: UUID, body: AxiomCreateRequest) -> dict[str, Any]:
    """Create an axiom (ontological world truth) in a universe (F2-2)."""
    from monitor_data.schemas.facts import AxiomCreate
    from monitor_data.tools.neo4j_tools.facts import neo4j_create_axiom

    params = AxiomCreate(**body.model_dump(exclude={"universe_id"}), universe_id=universe_id)
    try:
        axiom = neo4j_create_axiom(params)
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Create failed: {exc}") from exc
    return axiom.model_dump(mode="json")


@router.get("/entities/{universe_id}/axioms")
async def list_axioms(
    universe_id: UUID,
    domain: str | None = None,
    canon_level: CanonLevel | None = None,
    scope: SimulationScope | None = None,
    min_magnitude: int = Query(default=1, ge=1, le=10),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List axioms in a universe with optional filters (F2-2)."""
    from monitor_data.schemas.facts import AxiomFilter
    from monitor_data.tools.neo4j_tools.facts import neo4j_list_axioms

    filters = AxiomFilter(
        universe_id=universe_id,
        domain=domain,
        canon_level=canon_level,
        scope=scope,
        min_magnitude=min_magnitude,
        limit=limit,
        offset=offset,
    )
    try:
        axioms = neo4j_list_axioms(filters)
    except Exception as exc:
        raise HTTPException(503, f"Axiom lookup failed: {exc}") from exc
    return {
        "axioms": [a.model_dump(mode="json") for a in axioms],
        "count": len(axioms),
        "limit": limit,
        "offset": offset,
    }


@router.patch("/entities/axioms/{axiom_id}")
async def update_axiom(axiom_id: UUID, body: AxiomUpdate) -> dict[str, Any]:
    """Update an axiom's mutable fields (F2-2)."""
    from monitor_data.tools.neo4j_tools.facts import neo4j_update_axiom

    try:
        axiom = neo4j_update_axiom(axiom_id, body)
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Update failed: {exc}") from exc
    return axiom.model_dump(mode="json")


@router.delete("/entities/axioms/{axiom_id}")
async def delete_axiom(axiom_id: UUID, force: bool = False) -> dict[str, Any]:
    """Delete an axiom; canon axioms require ``force=true`` (F2-2)."""
    from monitor_data.tools.neo4j_tools.facts import neo4j_delete_axiom

    try:
        return neo4j_delete_axiom(axiom_id, force=force)
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Delete failed: {exc}") from exc


@router.post("/entities/{universe_id}/events", status_code=201)
async def create_event(universe_id: UUID, body: EventCreateRequest) -> dict[str, Any]:
    """Create a temporal event via ProposedChange (F2-2)."""
    from monitor_data.schemas.base import Authority, ProposalType
    from monitor_data.schemas.proposed_changes import ProposedChangeCreate
    from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change

    payload = body.model_dump(exclude={"universe_id"})
    payload["universe_id"] = str(universe_id)
    payload["operation"] = "create"

    proposal = ProposedChangeCreate(
        change_type=ProposalType.EVENT,
        content=payload,
        authority=Authority.GM,
        proposer="UI",
    )
    try:
        created = mongodb_create_proposed_change(proposal)
    except Exception as exc:
        raise HTTPException(503, f"Proposal failed: {exc}") from exc
    return created.model_dump(mode="json")


@router.get("/entities/{universe_id}/events")
async def list_events(
    universe_id: UUID,
    scene_id: UUID | None = None,
    entity_id: UUID | None = None,
    canon_level: CanonLevel | None = None,
    scope: SimulationScope | None = None,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List events in a universe with optional temporal/entity filters (F2-2)."""
    from monitor_data.schemas.facts import EventFilter
    from monitor_data.tools.neo4j_tools.facts import neo4j_list_events

    filters = EventFilter(
        universe_id=universe_id,
        scene_id=scene_id,
        entity_id=entity_id,
        canon_level=canon_level,
        scope=scope,
        start_after=start_after,
        start_before=start_before,
    )
    try:
        items, total = neo4j_list_events(filters, limit=limit, offset=offset)    # type: ignore
        return {
            "items": [i.model_dump(mode="json") for i in items],    # type: ignore
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except ValueError as exc:
        raise _http_for_value_error(exc) from exc
    except Exception as exc:
        raise HTTPException(503, f"Query failed: {exc}") from exc


@router.patch("/entities/events/{event_id}")
async def update_event(event_id: UUID, body: EventUpdate) -> dict[str, Any]:
    """Update an event via ProposedChange (F2-2)."""
    from monitor_data.schemas.base import Authority, ProposalType
    from monitor_data.schemas.proposed_changes import ProposedChangeCreate
    from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change

    payload = body.model_dump(exclude_unset=True)
    payload["event_id"] = str(event_id)
    payload["operation"] = "update"

    proposal = ProposedChangeCreate(
        change_type=ProposalType.EVENT,
        content=payload,
        authority=Authority.GM,
        proposer="UI",
    )
    try:
        updated = mongodb_create_proposed_change(proposal)
    except Exception as exc:
        raise HTTPException(503, f"Proposal failed: {exc}") from exc
    return updated.model_dump(mode="json")


@router.delete("/entities/events/{event_id}")
async def delete_event(event_id: UUID, force: bool = False) -> dict[str, Any]:
    """Delete an event via ProposedChange (F2-2)."""
    from monitor_data.schemas.base import Authority, ProposalType
    from monitor_data.schemas.proposed_changes import ProposedChangeCreate
    from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change

    payload = {
        "event_id": str(event_id),
        "force": force,
        "operation": "delete",
    }
    proposal = ProposedChangeCreate(
        change_type=ProposalType.EVENT,
        content=payload,
        authority=Authority.GM,
        proposer="UI",
    )
    try:
        deleted = mongodb_create_proposed_change(proposal)
    except Exception as exc:
        raise HTTPException(503, f"Proposal failed: {exc}") from exc
    return deleted.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Batch Entity Operations (Phase 3.1)
# ---------------------------------------------------------------------------


@router.post("/entities/batch")
async def batch_create_entities(
    body: dict,    # type: ignore
) -> dict:    # type: ignore
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
    body: dict,    # type: ignore
) -> dict:    # type: ignore
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
        update = EntityUpdate(**update_data) if isinstance(update_data, dict) else update_data
        updates.append((entity_id, update))

    try:
        result = neo4j_batch_update_entities(
            updates=updates,    # type: ignore
            continue_on_error=request.continue_on_error,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/entities/batch")
async def batch_delete_entities(
    body: dict,    # type: ignore
) -> dict:    # type: ignore
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
            continue_on_error=request.continue_on_error,    # type: ignore
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
        {"$set": {"is_active": False, "updated_at": datetime.now(UTC)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Character sheet not found")


@router.get("/character-sheets")
async def list_character_sheets(
    entity_id: UUID | None = None,
    game_system_id: UUID | None = None,
    is_active: bool | None = None,
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


@router.post("/characters/{character_id}/level-up", response_model=LevelUpResponse)
async def level_up_character(
    character_id: str,
    body: LevelUpRequest,
) -> LevelUpResponse:
    """Spend accumulated XP to advance a character to the next level (P-21)."""
    try:
        entity_uuid = UUID(character_id)
        return await EntityProgressionService.process_level_up(entity_uuid, body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/characters/{character_id}/downtime", response_model=DowntimeResponse)
async def get_downtime_options(
    character_id: str,
    scene_id: str | None = None,
    system_id: str | None = None,
) -> DowntimeResponse:
    """Get available progression options for a character during downtime (P-21)."""
    try:
        entity_uuid = UUID(character_id)
        return await EntityProgressionService.get_downtime_options(entity_uuid, scene_id, system_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
