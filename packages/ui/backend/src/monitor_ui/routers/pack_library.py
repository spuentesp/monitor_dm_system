"""Pack Library routes extracted from `ingest.py` to keep concerns focused.

These endpoints manage KnowledgePack CRUD, merging, export/import, and world
application while `ingest.py` stays focused on source uploads and job status.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.services.pack_service import KnowledgePackService
from monitor_data.schemas.base import ProposalStatus
from monitor_data.schemas.knowledge_packs import (  # type: ignore
    ChunkSummaryArtifact,
    EmbeddedGameSystem,
    EmbeddedSourceProfile,
    ExtractedAgenda,
    ExtractedAxiom,
    ExtractedCharacterProfile,
    ExtractedEntityArchetype,
    ExtractedGenerationTemplate,
    ExtractedLoreFact,
    ExtractedRandomTable,
    ExtractedRelationship,
    ExtractedToneProfile,
    ExtractedTopology,
    KnowledgePackCreate,
    KnowledgePackFilter,
    KnowledgePackStatus,
    KnowledgePackType,
    KnowledgePackUpdate,
    PackExportEnvelope,
    SectionSummaryArtifact,
    SourceMindscapeArtifact,
)
from monitor_data.schemas.proposed_changes import (
    DecisionMetadata,
    ProposedChangeFilter,
    ProposedChangeUpdate,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_count_pack_dependents,
    mongodb_create_knowledge_pack,
    mongodb_delete_knowledge_pack,
    mongodb_get_ingestion_job,
    mongodb_get_knowledge_pack,
    mongodb_list_knowledge_packs,
    mongodb_list_proposed_changes,
    mongodb_update_knowledge_pack,
    mongodb_update_proposed_change,
)
from pydantic import BaseModel, Field

from .ingest_shared import (
    _create_setting,
    _pack_to_dict,
    db_op,
    validate_uuid,
)

router = APIRouter()


def _assert_pack_not_building(pack, *, action: str) -> None:  # type: ignore
    """Block use/edit operations while the backing ingest job is still running."""
    job = None
    if getattr(pack, "ingestion_job_id", None):
        with db_op("Database unavailable"):
            job = mongodb_get_ingestion_job(pack.ingestion_job_id)

    live_statuses = {"pending", "running", "retrying", "backing_off"}
    if job is not None and getattr(job.status, "value", None) in live_statuses:
        stage = job.current_stage.value if getattr(job, "current_stage", None) else job.status.value  # type: ignore
        raise HTTPException(
            409,
            f"KnowledgePack '{pack.name}' is still being built from '{job.source_title}' "
            f"(stage={stage}). Wait until the ingestion job finishes before {action}.",
        )

    if pack.status == KnowledgePackStatus.PENDING:
        raise HTTPException(
            409,
            f"KnowledgePack '{pack.name}' is still being built. Wait until it reaches ready status before {action}.",
        )


# _propagate_system_to_universe was moved to KnowledgePackService


@router.get("/packs")
async def list_packs(status: str | None = None, limit: int = 30) -> list[dict]:  # type: ignore
    pack_status = None
    if status:
        with suppress(ValueError):
            pack_status = KnowledgePackStatus(status)
    with db_op("Database unavailable"):
        result = await asyncio.to_thread(
            mongodb_list_knowledge_packs,
            KnowledgePackFilter(status=pack_status, tag=None, limit=limit),
        )
    return [_pack_to_dict(p) for p in result.packs]


@router.get("/packs/{pack_id}")
async def get_pack(pack_id: str) -> dict:  # type: ignore
    uid = validate_uuid(pack_id, "pack_id")
    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    return _pack_to_dict(pack)


class PackUpdateRequest(BaseModel):
    """Body for PUT /packs/{pack_id} — all fields optional."""

    name: str | None = None
    axioms: list[dict] | None = None  # type: ignore
    entity_archetypes: list[dict] | None = None  # type: ignore
    lore_facts: list[dict] | None = None  # type: ignore
    entity_relationships: list[dict] | None = None  # type: ignore
    random_tables: list[dict] | None = None  # type: ignore
    agendas: list[dict] | None = None  # type: ignore
    topologies: list[dict] | None = None  # type: ignore
    tone_profiles: list[dict] | None = None  # type: ignore
    character_profiles: list[dict] | None = None  # type: ignore
    generation_templates: list[dict] | None = None  # type: ignore
    source_profile_data: dict | None = None  # type: ignore
    chunk_summaries: list[dict] | None = None  # type: ignore
    section_summaries: list[dict] | None = None  # type: ignore
    source_mindscape: dict | None = None  # type: ignore
    tags: list[str] | None = None
    status: str | None = None
    game_system_id: str | None = None
    plot_threads: list[dict] | None = None  # type: ignore
    source_document_ids: list[str] | None = None


@router.put("/packs/{pack_id}")
async def update_pack(pack_id: str, body: PackUpdateRequest) -> dict:  # type: ignore
    """Update a KnowledgePack's extracted content for World Forge editing."""
    uid = validate_uuid(pack_id, "pack_id")

    update_kwargs: dict = {}  # type: ignore
    if body.name is not None:
        update_kwargs["name"] = body.name
    if body.tags is not None:
        update_kwargs["tags"] = body.tags
    if body.status is not None:
        from monitor_data.schemas.knowledge_packs import KnowledgePackStatus as KPS

        try:
            update_kwargs["status"] = KPS(body.status)
        except ValueError as exc:
            raise HTTPException(422, f"Unknown status: {body.status}") from exc
    if body.axioms is not None:
        try:
            update_kwargs["axioms"] = [ExtractedAxiom(**a) for a in body.axioms]
        except Exception as exc:
            raise HTTPException(422, f"Invalid axiom data: {exc}") from exc
    if body.entity_archetypes is not None:
        try:
            update_kwargs["entity_archetypes"] = [ExtractedEntityArchetype(**e) for e in body.entity_archetypes]
        except Exception as exc:
            raise HTTPException(422, f"Invalid entity data: {exc}") from exc
    if body.lore_facts is not None:
        try:
            update_kwargs["lore_facts"] = [ExtractedLoreFact(**f) for f in body.lore_facts]
        except Exception as exc:
            raise HTTPException(422, f"Invalid lore_fact data: {exc}") from exc
    if body.entity_relationships is not None:
        try:
            update_kwargs["entity_relationships"] = [ExtractedRelationship(**r) for r in body.entity_relationships]
        except Exception as exc:
            raise HTTPException(422, f"Invalid relationship data: {exc}") from exc
    if body.random_tables is not None:
        try:
            update_kwargs["random_tables"] = [ExtractedRandomTable(**t) for t in body.random_tables]
        except Exception as exc:
            raise HTTPException(422, f"Invalid random table data: {exc}") from exc
    if body.agendas is not None:
        try:
            update_kwargs["agendas"] = [ExtractedAgenda(**a) for a in body.agendas]
        except Exception as exc:
            raise HTTPException(422, f"Invalid agenda data: {exc}") from exc
    if body.topologies is not None:
        try:
            update_kwargs["topologies"] = [ExtractedTopology(**t) for t in body.topologies]
        except Exception as exc:
            raise HTTPException(422, f"Invalid topology data: {exc}") from exc
    if body.tone_profiles is not None:
        try:
            update_kwargs["tone_profiles"] = [ExtractedToneProfile(**t) for t in body.tone_profiles]
        except Exception as exc:
            raise HTTPException(422, f"Invalid tone profile data: {exc}") from exc
    if body.character_profiles is not None:
        try:
            update_kwargs["character_profiles"] = [ExtractedCharacterProfile(**p) for p in body.character_profiles]
        except Exception as exc:
            raise HTTPException(422, f"Invalid character profile data: {exc}") from exc
    if body.generation_templates is not None:
        try:
            update_kwargs["generation_templates"] = [
                ExtractedGenerationTemplate(**g) for g in body.generation_templates
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid generation template data: {exc}") from exc
    if body.source_profile_data is not None:
        try:
            update_kwargs["source_profile_data"] = EmbeddedSourceProfile(**body.source_profile_data)
        except Exception as exc:
            raise HTTPException(422, f"Invalid source profile data: {exc}") from exc
    if body.chunk_summaries is not None:
        try:
            update_kwargs["chunk_summaries"] = [ChunkSummaryArtifact(**c) for c in body.chunk_summaries]
        except Exception as exc:
            raise HTTPException(422, f"Invalid chunk summary data: {exc}") from exc
    if body.section_summaries is not None:
        try:
            update_kwargs["section_summaries"] = [SectionSummaryArtifact(**s) for s in body.section_summaries]
        except Exception as exc:
            raise HTTPException(422, f"Invalid section summary data: {exc}") from exc
    if body.source_mindscape is not None:
        try:
            update_kwargs["source_mindscape"] = SourceMindscapeArtifact(**body.source_mindscape)
        except Exception as exc:
            raise HTTPException(422, f"Invalid source mindscape data: {exc}") from exc
    if body.game_system_id is not None:
        from uuid import UUID as _UUID

        try:
            update_kwargs["game_system_id"] = _UUID(body.game_system_id)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid game_system_id: {exc}") from exc
    if body.plot_threads is not None:
        try:
            from monitor_data.schemas.plot_threads import ExtractedPlotThread as _EPT

            update_kwargs["plot_threads"] = [_EPT(**t) for t in body.plot_threads]
        except Exception as exc:
            raise HTTPException(422, f"Invalid plot thread data: {exc}") from exc
    if body.source_document_ids is not None:
        from uuid import UUID as _UUID

        try:
            update_kwargs["source_document_ids"] = [_UUID(sid) for sid in body.source_document_ids]
        except ValueError as exc:
            raise HTTPException(422, f"Invalid source_document_ids: {exc}") from exc

    with db_op("Database unavailable"):
        existing_pack = mongodb_get_knowledge_pack(uid)
    if not existing_pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(existing_pack, action="editing it")

    try:
        updated = await asyncio.to_thread(mongodb_update_knowledge_pack, uid, KnowledgePackUpdate(**update_kwargs))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc
    return _pack_to_dict(updated)


class PromoteRequest(BaseModel):
    """Move an item between axioms and lore_facts arrays.

    - direction="to_axiom": remove lore_fact at `source_index`, insert as axiom
    - direction="to_lore": remove axiom at `source_index`, insert as lore_fact
    """

    direction: str  # "to_axiom" | "to_lore"
    source_index: int


@router.post("/packs/{pack_id}/promote", status_code=200)
async def promote_pack_item(pack_id: str, body: PromoteRequest) -> dict:  # type: ignore
    """Promote a lore_fact to axiom, or demote an axiom to lore_fact."""
    uid = validate_uuid(pack_id, "pack_id")
    if body.direction not in ("to_axiom", "to_lore"):
        raise HTTPException(422, "direction must be 'to_axiom' or 'to_lore'")

    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(pack, action="promoting items in")

    axioms = list(pack.axioms or [])
    lore = list(pack.lore_facts or [])

    if body.direction == "to_axiom":
        if body.source_index < 0 or body.source_index >= len(lore):
            raise HTTPException(
                422,
                f"lore_fact index {body.source_index} out of range (0..{len(lore) - 1})",
            )
        item = lore.pop(body.source_index)
        axiom = ExtractedAxiom(
            statement=item.statement,
            domain=item.domain if hasattr(item, "domain") else "general",
            confidence=item.confidence if hasattr(item, "confidence") else 0.8,
            source_ref=item.source_ref if hasattr(item, "source_ref") else None,
        )
        axioms.append(axiom)
    else:  # to_lore
        if body.source_index < 0 or body.source_index >= len(axioms):
            raise HTTPException(
                422,
                f"axiom index {body.source_index} out of range (0..{len(axioms) - 1})",
            )
        item = axioms.pop(body.source_index)  # type: ignore
        lore_fact = ExtractedLoreFact(
            statement=item.statement,
            confidence=item.confidence if hasattr(item, "confidence") else 0.8,
            source_ref=item.source_ref if hasattr(item, "source_ref") else None,
            tags=getattr(item, "tags", None) or [],
        )
        lore.append(lore_fact)

    with db_op("Database unavailable"):
        updated = mongodb_update_knowledge_pack(
            uid,
            KnowledgePackUpdate(
                axioms=[a.model_dump() for a in axioms],
                lore_facts=[f.model_dump() for f in lore],
            ),
        )
    return _pack_to_dict(updated)


class UpdateEntityInPackRequest(BaseModel):
    """Body for PATCH /packs/{pack_id}/entities/{index}."""

    name: str | None = None
    entity_type: str | None = None
    sub_type: str | None = None
    description: str | None = None
    properties: dict | None = None  # type: ignore
    entity_roles: list[str] | None = None
    is_container: bool | None = None
    tags: list[str] | None = None
    confidence: float | None = None


class UpdateRelationshipInPackRequest(BaseModel):
    """Body for PATCH /packs/{pack_id}/relationships/{index}."""

    from_entity: str | None = None
    rel_type: str | None = None
    to_entity: str | None = None
    description: str | None = None
    confidence: float | None = None
    tags: list[str] | None = None
    properties: dict | None = None  # type: ignore


class AddRelationshipToPackRequest(BaseModel):
    """Body for POST /packs/{pack_id}/relationships — add a new relationship."""

    from_entity: str
    rel_type: str
    to_entity: str
    description: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    properties: dict = Field(default_factory=dict)  # type: ignore


@router.patch("/packs/{pack_id}/entities/{index}", status_code=200)
async def update_entity_in_pack(
    pack_id: str,
    index: int,
    body: UpdateEntityInPackRequest,
) -> dict:  # type: ignore
    """Edit a single entity archetype within a KnowledgePack.

    Supports changing entity_type, name, description, and other fields
    without resending the entire entity array.
    """
    uid = validate_uuid(pack_id, "pack_id")

    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(pack, action="editing entities in")

    entities = list(pack.entity_archetypes or [])
    if index < 0 or index >= len(entities):
        raise HTTPException(422, f"entity index {index} out of range (0..{len(entities) - 1})")

    entity = entities[index]
    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.entity_type is not None:
        updates["entity_type"] = body.entity_type
    if body.sub_type is not None:
        updates["sub_type"] = body.sub_type
    if body.description is not None:
        updates["description"] = body.description
    if body.properties is not None:
        updates["properties"] = body.properties
    if body.entity_roles is not None:
        updates["entity_roles"] = body.entity_roles
    if body.is_container is not None:
        updates["is_container"] = body.is_container
    if body.tags is not None:
        updates["tags"] = body.tags
    if body.confidence is not None:
        updates["confidence"] = body.confidence

    merged = {**entity.model_dump(), **updates}
    entities[index] = ExtractedEntityArchetype(**merged)

    with db_op("Database unavailable"):
        updated = mongodb_update_knowledge_pack(
            uid,
            KnowledgePackUpdate(
                entity_archetypes=[e.model_dump() for e in entities],
            ),
        )
    return _pack_to_dict(updated)


@router.patch("/packs/{pack_id}/relationships/{index}", status_code=200)
async def update_relationship_in_pack(
    pack_id: str,
    index: int,
    body: UpdateRelationshipInPackRequest,
) -> dict:  # type: ignore
    """Edit a single relationship within a KnowledgePack.

    Supports changing from_entity, rel_type, to_entity, description, tags,
    properties, and confidence without resending the entire relationships array.
    """
    uid = validate_uuid(pack_id, "pack_id")

    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(pack, action="editing relationships in")

    relationships = list(pack.entity_relationships or [])
    if index < 0 or index >= len(relationships):
        raise HTTPException(
            422,
            f"relationship index {index} out of range (0..{len(relationships) - 1})",
        )

    rel = relationships[index]
    updates: dict[str, Any] = {}
    if body.from_entity is not None:
        updates["from_entity"] = body.from_entity
    if body.rel_type is not None:
        updates["rel_type"] = body.rel_type
    if body.to_entity is not None:
        updates["to_entity"] = body.to_entity
    if body.description is not None:
        updates["description"] = body.description
    if body.confidence is not None:
        updates["confidence"] = body.confidence
    if body.tags is not None:
        updates["tags"] = body.tags
    if body.properties is not None:
        updates["properties"] = body.properties

    merged = {**rel.model_dump(), **updates}
    relationships[index] = ExtractedRelationship(**merged)

    with db_op("Database unavailable"):
        updated = mongodb_update_knowledge_pack(
            uid,
            KnowledgePackUpdate(
                entity_relationships=[r.model_dump() for r in relationships],
            ),
        )
    return _pack_to_dict(updated)


@router.post("/packs/{pack_id}/relationships", status_code=201)
async def add_relationship_to_pack(
    pack_id: str,
    body: AddRelationshipToPackRequest,
) -> dict:  # type: ignore
    """Add a new relationship to a KnowledgePack."""
    uid = validate_uuid(pack_id, "pack_id")

    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(pack, action="adding relationships to")

    relationships = list(pack.entity_relationships or [])
    new_rel = ExtractedRelationship(
        from_entity=body.from_entity,
        rel_type=body.rel_type,
        to_entity=body.to_entity,
        description=body.description,
        confidence=body.confidence,
        source_ref=body.source_ref,
        tags=body.tags,
        properties=body.properties,
    )
    relationships.append(new_rel)

    with db_op("Database unavailable"):
        updated = mongodb_update_knowledge_pack(
            uid,
            KnowledgePackUpdate(
                entity_relationships=[r.model_dump() for r in relationships],
            ),
        )
    return _pack_to_dict(updated)


class DeleteItemInPackRequest(BaseModel):
    """Body for DELETE /packs/{pack_id}/{collection}/{index}."""

    pass  # index is in the URL


@router.delete("/packs/{pack_id}/{collection}/{index}", status_code=200)
async def delete_item_from_pack(
    pack_id: str,
    collection: str,
    index: int,
) -> dict:  # type: ignore
    """Delete a single item from a KnowledgePack's axiom, lore_fact, entity, or relationship array.

    Valid collections: entities, axioms, lore_facts, relationships
    """
    uid = validate_uuid(pack_id, "pack_id")
    valid = {"entities", "axioms", "lore_facts", "relationships"}
    if collection not in valid:
        raise HTTPException(422, f"collection must be one of: {', '.join(sorted(valid))}")

    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(pack, action="deleting items from")

    if collection == "entities":
        items = list(pack.entity_archetypes or [])
    elif collection == "axioms":
        items = list(pack.axioms or [])  # type: ignore
    elif collection == "lore_facts":
        items = list(pack.lore_facts or [])  # type: ignore
    else:
        items = list(pack.entity_relationships or [])  # type: ignore

    if index < 0 or index >= len(items):
        raise HTTPException(422, f"{collection} index {index} out of range (0..{len(items) - 1})")

    items.pop(index)

    kwargs: dict[str, Any] = {}
    if collection == "entities":
        kwargs["entity_archetypes"] = [e.model_dump() for e in items]
    elif collection == "axioms":
        kwargs["axioms"] = [a.model_dump() for a in items]
    elif collection == "lore_facts":
        kwargs["lore_facts"] = [f.model_dump() for f in items]
    else:
        kwargs["entity_relationships"] = [r.model_dump() for r in items]

    with db_op("Database unavailable"):
        updated = await asyncio.to_thread(mongodb_update_knowledge_pack, uid, KnowledgePackUpdate(**kwargs))
    return _pack_to_dict(updated)


class MergePacksRequest(BaseModel):
    """Merge two or more packs into one, deduplicating by name/statement."""

    pack_ids: list[str]
    name: str | None = None
    strategy: str = "first_wins"


@router.post("/packs/merge", status_code=201)
async def merge_packs(body: MergePacksRequest) -> dict:  # type: ignore
    """Merge multiple KnowledgePacks into a new deduplicated pack."""
    uids = [validate_uuid(pid, f"pack_id ({pid})") for pid in body.pack_ids]
    try:
        new_pack = KnowledgePackService.merge_packs(
            pack_uids=uids,
            strategy=body.strategy,
            merged_name=body.name,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as exc:
        raise HTTPException(503, f"Database error creating merged pack: {exc}") from exc

    return _pack_to_dict(new_pack)


class CreatePackRequest(BaseModel):
    """Body for POST /packs — manual pack creation (MP-1)."""

    name: str
    description: str = ""
    pack_type: str = "custom"
    system_name: str | None = None
    tags: list[str] = []


@router.post("/packs", status_code=201)
async def create_pack(body: CreatePackRequest) -> dict:  # type: ignore
    """Create an empty KnowledgePack manually (MP-1)."""
    try:
        pack_type_enum = KnowledgePackType(body.pack_type)
    except ValueError:
        pack_type_enum = KnowledgePackType.CUSTOM
    try:
        pack = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name=body.name,
                description=body.description,
                pack_type=pack_type_enum,
                status=KnowledgePackStatus.READY,
                system_name=body.system_name,
                ingestion_job_id=None,
                tags=body.tags,
                game_system_id=None,
            )
        )
    except Exception as exc:
        raise HTTPException(503, f"Database error: {exc}") from exc
    return _pack_to_dict(pack)


@router.delete("/packs/{pack_id}", status_code=200)
async def delete_pack(pack_id: str, hard: bool = False) -> dict:  # type: ignore
    """Archive or hard-delete a KnowledgePack."""
    uid = validate_uuid(pack_id, "pack_id")

    if hard:
        with db_op("Database unavailable"):
            dependents = mongodb_count_pack_dependents(uid)
        if dependents > 0:
            raise HTTPException(
                409,
                f"Cannot hard-delete: {dependents} pack(s) reference this pack as a parent. "
                "Archive it instead or remove the lineage references first.",
            )

    with db_op("Database unavailable"):
        found = mongodb_delete_knowledge_pack(uid, soft=not hard)

    if not found:
        raise HTTPException(404, "KnowledgePack not found")

    action = "deleted" if hard else "archived"
    return {"pack_id": pack_id, "action": action}


@router.get("/packs/{pack_id}/export")
async def export_pack(pack_id: str) -> Response:
    """Download a `.monitorpack` file."""
    uid = validate_uuid(pack_id, "pack_id")
    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")

    envelope = PackExportEnvelope(
        exported_at=datetime.now(UTC),
        pack=_pack_to_dict(pack),
    )
    filename = pack.name.replace(" ", "_").replace("/", "-") + ".monitorpack"
    return Response(
        content=envelope.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class ImportPackRequest(BaseModel):
    """Body for POST /packs/import — JSON envelope from a `.monitorpack` file."""

    schema_version: str
    exported_at: str
    pack: dict  # type: ignore


@router.post("/packs/import", status_code=201)
async def import_pack(body: ImportPackRequest) -> dict:  # type: ignore
    """Import a `.monitorpack` JSON envelope as a new KnowledgePack."""
    if body.schema_version != "1.0":
        raise HTTPException(
            422,
            f"Unsupported schema_version '{body.schema_version}'. Only '1.0' is supported.",
        )
    pack_data = body.pack
    try:
        pack_type_enum = KnowledgePackType(pack_data.get("pack_type", "custom"))
    except ValueError:
        pack_type_enum = KnowledgePackType.CUSTOM
    try:
        new_pack = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name=pack_data.get("name", "Imported Pack"),
                description=pack_data.get("description", ""),
                pack_type=pack_type_enum,
                status=KnowledgePackStatus.READY,
                system_name=pack_data.get("system_name"),
                ingestion_job_id=None,
                tags=pack_data.get("tags", []),
                parent_pack_ids=pack_data.get("parent_pack_ids", []),
                axioms=[ExtractedAxiom(**a) for a in pack_data.get("axioms", [])],
                entity_archetypes=[ExtractedEntityArchetype(**e) for e in pack_data.get("entity_archetypes", [])],
                lore_facts=[ExtractedLoreFact(**f) for f in pack_data.get("lore_facts", [])],
                entity_relationships=[ExtractedRelationship(**r) for r in pack_data.get("entity_relationships", [])],
                random_tables=[ExtractedRandomTable(**t) for t in pack_data.get("random_tables", [])],
                agendas=[ExtractedAgenda(**a) for a in pack_data.get("agendas", [])],
                topologies=[ExtractedTopology(**t) for t in pack_data.get("topologies", [])],
                tone_profiles=[ExtractedToneProfile(**t) for t in pack_data.get("tone_profiles", [])],
                character_profiles=[ExtractedCharacterProfile(**p) for p in pack_data.get("character_profiles", [])],
                generation_templates=[
                    ExtractedGenerationTemplate(**g) for g in pack_data.get("generation_templates", [])
                ],
                game_system_data=EmbeddedGameSystem(**pack_data["game_system_data"])
                if pack_data.get("game_system_data")
                else None,
                source_profile_data=EmbeddedSourceProfile(**pack_data["source_profile_data"])
                if pack_data.get("source_profile_data")
                else None,
                chunk_summaries=[ChunkSummaryArtifact(**c) for c in pack_data.get("chunk_summaries", [])],
                section_summaries=[SectionSummaryArtifact(**s) for s in pack_data.get("section_summaries", [])],
                source_mindscape=SourceMindscapeArtifact(**pack_data["source_mindscape"])
                if pack_data.get("source_mindscape")
                else None,
                game_system_id=None,
            )
        )
    except Exception as exc:
        raise HTTPException(422, f"Invalid pack data: {exc}") from exc
    return _pack_to_dict(new_pack)


class ClonePackRequest(BaseModel):
    """Body for POST /packs/{id}/clone."""

    name: str | None = None
    with_lineage: bool = True


@router.post("/packs/{pack_id}/clone", status_code=201)
async def clone_pack(pack_id: str, body: ClonePackRequest) -> dict:  # type: ignore
    """Clone a KnowledgePack into a new editable copy."""
    uid = validate_uuid(pack_id, "pack_id")
    with db_op("Database unavailable"):
        src = mongodb_get_knowledge_pack(uid)
    if not src:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(src, action="cloning it")

    parent_ids = [pack_id] if body.with_lineage else []
    new_name = body.name or f"{src.name} (clone)"
    try:
        clone = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name=new_name,
                description=src.description,
                pack_type=src.pack_type,
                status=KnowledgePackStatus.READY,
                system_name=src.system_name,
                ingestion_job_id=None,
                tags=src.tags,
                parent_pack_ids=parent_ids,
                axioms=src.axioms,
                entity_archetypes=src.entity_archetypes,
                lore_facts=src.lore_facts,
                entity_relationships=src.entity_relationships,
                random_tables=src.random_tables,
                agendas=src.agendas,
                topologies=src.topologies,
                tone_profiles=src.tone_profiles,
                character_profiles=src.character_profiles,
                generation_templates=src.generation_templates,
                game_system_id=src.game_system_id,
                game_system_data=src.game_system_data,
                source_profile_data=src.source_profile_data,
                chunk_summaries=src.chunk_summaries,
                section_summaries=src.section_summaries,
                source_mindscape=src.source_mindscape,
            )
        )
    except Exception as exc:
        raise HTTPException(503, f"Database error: {exc}") from exc
    return _pack_to_dict(clone)


class SlicePackRequest(BaseModel):
    """Body for POST /packs/{id}/slice."""

    name: str
    entity_indices: list[int] = []
    axiom_indices: list[int] = []
    lore_indices: list[int] = []
    relationship_indices: list[int] = []
    random_table_indices: list[int] = []
    agenda_indices: list[int] = []
    topology_indices: list[int] = []
    tone_profile_indices: list[int] = []
    character_profile_indices: list[int] = []
    generation_template_indices: list[int] = []
    with_lineage: bool = True


@router.post("/packs/{pack_id}/slice", status_code=201)
async def slice_pack(pack_id: str, body: SlicePackRequest) -> dict:  # type: ignore
    """Create a new pack from a user-selected subset of an existing pack."""
    uid = validate_uuid(pack_id, "pack_id")
    with db_op("Database unavailable"):
        src = mongodb_get_knowledge_pack(uid)
    if not src:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(src, action="slicing it")

    def _pick(items: list, indices: list[int]) -> list:  # type: ignore
        return [items[i] for i in indices if 0 <= i < len(items)]

    parent_ids = [pack_id] if body.with_lineage else []
    try:
        sliced = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name=body.name,
                description=f"Slice of '{src.name}'",
                pack_type=src.pack_type,
                status=KnowledgePackStatus.READY,
                system_name=src.system_name,
                ingestion_job_id=None,
                tags=src.tags,
                parent_pack_ids=parent_ids,
                entity_archetypes=_pick(src.entity_archetypes, body.entity_indices),
                axioms=_pick(src.axioms, body.axiom_indices),
                lore_facts=_pick(src.lore_facts, body.lore_indices),
                entity_relationships=_pick(src.entity_relationships, body.relationship_indices),
                random_tables=_pick(src.random_tables, body.random_table_indices),
                agendas=_pick(src.agendas, body.agenda_indices),
                topologies=_pick(src.topologies, body.topology_indices),
                tone_profiles=_pick(src.tone_profiles, body.tone_profile_indices),
                character_profiles=_pick(src.character_profiles, body.character_profile_indices),
                generation_templates=_pick(src.generation_templates, body.generation_template_indices),
                game_system_id=None,
            )
        )
    except Exception as exc:
        raise HTTPException(503, f"Database error: {exc}") from exc
    return _pack_to_dict(sliced)


class ApplyNewWorldRequest(BaseModel):
    """Body for POST /packs/{id}/apply/new-world."""

    world_name: str
    system_name: str | None = None


@router.post("/packs/{pack_id}/apply/new-world", status_code=201)
async def apply_pack_new_world(pack_id: str, body: ApplyNewWorldRequest) -> dict:  # type: ignore
    """Create a new Multiverse+Universe and commit all pack items to canon."""
    pack_uid = validate_uuid(pack_id, "pack_id")
    with db_op("Database unavailable"):
        pack = mongodb_get_knowledge_pack(pack_uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(pack, action="applying it to a world")
    if pack.status == KnowledgePackStatus.ARCHIVED:
        raise HTTPException(422, "Cannot apply an archived pack")

    try:
        mv_id, universe_uid = _create_setting(
            name=body.world_name,
            system_name=body.system_name or body.world_name,
            game_system_id=pack.game_system_id,
        )
    except Exception as exc:
        raise HTTPException(500, f"Could not create world: {exc}") from exc

    try:
        keeper = CanonKeeper()
        result = await keeper.apply_pack_to_universe(
            pack_id=pack_uid,
            multiverse_id=mv_id,
            universe_id=universe_uid,
            auto_accept=False,
        )
    except Exception as exc:
        raise HTTPException(500, f"Apply failed: {exc}") from exc

    return {
        "pack_id": pack_id,
        "multiverse_id": str(mv_id),
        "universe_id": str(universe_uid),
        "world_name": body.world_name,
        "proposals_created": result["proposals_created"],
        "committed": result["committed"],
        "errors": result["errors"],
        "review_status": result.get("review_status", "pending"),
        "status": "review_pending",
    }


class ApplyExistingWorldRequest(BaseModel):
    """Body for POST /packs/{id}/apply/{universe_id}."""

    mode: str = "full"
    auto_commit_llm: bool = False
    # Subset selection: an empty list means "apply all" (the wizard never
    # sends these); a non-empty list restricts application to those indices.
    entity_indices: list[int] = []
    axiom_indices: list[int] = []
    lore_indices: list[int] = []
    resolved_conflicts: list[dict] = []  # type: ignore


@router.post("/packs/{pack_id}/apply/{universe_id}")
async def apply_pack_existing_world(
    pack_id: str,
    universe_id: str,
    body: ApplyExistingWorldRequest,
) -> dict:  # type: ignore
    """Apply a pack to an existing universe (MP-7 / MP-8)."""
    pack_uid = validate_uuid(pack_id, "pack_id")
    universe_uid = validate_uuid(universe_id, "universe_id")

    try:
        return await KnowledgePackService.apply_pack_to_existing_world(
            pack_uid=pack_uid,
            universe_uid=universe_uid,
            resolved_conflicts=[c for c in body.resolved_conflicts] if body.resolved_conflicts else [],
            entity_indices=body.entity_indices or [],
            axiom_indices=body.axiom_indices or [],
            lore_indices=body.lore_indices or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Apply failed: {exc}") from exc


class CreateKGRequest(BaseModel):
    name: str
    source_ids: list[str]
    universe_id: str | None = None


@router.get("/kgs")
async def list_kgs() -> list[dict]:  # type: ignore
    try:
        result = mongodb_list_knowledge_packs(KnowledgePackFilter(tag=None, limit=30))
    except Exception:
        return []
    return [_pack_to_dict(pack) for pack in result.packs]


@router.post("/kgs", status_code=201)
async def create_knowledge_graph(body: CreateKGRequest) -> dict:  # type: ignore
    return {
        "id": "stub",
        "name": body.name,
        "source_ids": body.source_ids,
        "universe_id": body.universe_id,
        "entity_count": 0,
        "relation_count": 0,
        "status": "building",
        "created_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
    }


# =========================================================================
# Proposal Review Endpoints (I-4)
# =========================================================================


class ProposalActionRequest(BaseModel):
    """Body for PATCH /proposals/{proposal_id} — single proposal action."""

    action: str = Field(..., pattern="^(accept|reject)$", description="Accept or reject")
    reason: str = Field(default="", max_length=2000)


class BatchProposalAction(BaseModel):
    """One item in a batch action request."""

    proposal_id: str
    action: str = Field(..., pattern="^(accept|reject)$")
    reason: str = Field(default="", max_length=2000)


class BatchProposalRequest(BaseModel):
    """Body for POST /proposals/batch — batch accept/reject."""

    actions: list[BatchProposalAction]


class CommitAcceptedRequest(BaseModel):
    """Body for POST /packs/{pack_id}/commit — commit accepted proposals."""

    pack_id: str


@router.get("/packs/{pack_id}/proposals")
async def list_pack_proposals(
    pack_id: str,
    status: str | None = None,
    change_type: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:  # type: ignore
    """List proposals for a KnowledgePack, grouped by type.

    Query params:
        status:      pending | accepted | rejected (default: all)
        change_type: fact | entity | relationship | mechanic
        page:        1-based page number
        per_page:    items per page
    """
    pack_uid = validate_uuid(pack_id, "pack_id")

    with db_op("Database unavailable"):
        pack = mongodb_get_knowledge_pack(pack_uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")

    proposal_status = None
    if status:
        try:
            proposal_status = ProposalStatus(status)
        except ValueError:
            raise HTTPException(422, f"Invalid status: {status}")

    from monitor_data.schemas.base import ProposalType

    proposal_type = None
    if change_type:
        try:
            proposal_type = ProposalType(change_type)
        except ValueError:
            raise HTTPException(422, f"Invalid change_type: {change_type}")

    offset = (page - 1) * per_page
    with db_op("Database unavailable"):
        result = mongodb_list_proposed_changes(
            ProposedChangeFilter(
                source=f"knowledge_pack:{pack_uid}",
                status=proposal_status,
                change_type=proposal_type,
                limit=per_page,
                offset=offset,
            )
        )

    # Summary counts
    from monitor_data.db.mongodb import get_mongodb_client

    source_key = f"knowledge_pack:{pack_uid}"
    mongo = get_mongodb_client()
    coll = mongo.get_collection("proposed_changes")
    summary = {
        "total": coll.count_documents({"source": source_key}),
        "pending": coll.count_documents({"source": source_key, "status": "pending"}),
        "accepted": coll.count_documents({"source": source_key, "status": "accepted"}),
        "rejected": coll.count_documents({"source": source_key, "status": "rejected"}),
    }

    proposals_out = [
        {
            "proposal_id": str(p.proposal_id),
            "change_type": p.change_type.value,
            "content": p.content,
            "confidence": p.confidence,
            "authority": p.authority.value if hasattr(p.authority, "value") else p.authority,
            "proposer": p.proposer,
            "status": p.status.value,
            "evidence": [{"type": e.type, "ref_id": str(e.ref_id)} for e in p.evidence],
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in result.proposed_changes
    ]

    return {
        "pack_id": pack_id,
        "proposals": proposals_out,
        "summary": summary,
        "total": result.total,
        "page": page,
        "per_page": per_page,
    }


@router.patch("/proposals/{proposal_id}")
async def review_proposal(proposal_id: str, body: ProposalActionRequest) -> dict:  # type: ignore
    """Accept or reject a single proposal (I-4).

    Accepted proposals are marked for commit but NOT written to Neo4j yet.
    Call POST /packs/{pack_id}/commit to commit all accepted proposals.
    """
    from uuid import UUID as _UUID

    try:
        uid = _UUID(proposal_id)
    except ValueError:
        raise HTTPException(422, f"Invalid proposal_id: {proposal_id}")

    new_status = ProposalStatus.ACCEPTED if body.action == "accept" else ProposalStatus.REJECTED
    now = datetime.now(UTC)

    with db_op("Database unavailable"):
        updated = mongodb_update_proposed_change(
            uid,
            ProposedChangeUpdate(
                status=new_status,
                decision_metadata=DecisionMetadata(
                    decided_by="user",
                    decided_at=now,
                    reason=body.reason or f"User {body.action}ed",
                    canonical_ref=None,
                ),
            ),
        )

    return {
        "proposal_id": str(updated.proposal_id),
        "status": updated.status.value,
        "decision_metadata": {
            "decided_by": updated.decision_metadata.decided_by,  # type: ignore
            "decided_at": updated.decision_metadata.decided_at.isoformat(),  # type: ignore
            "reason": updated.decision_metadata.reason,  # type: ignore
        },
    }


@router.post("/proposals/batch")
async def batch_review_proposals(body: BatchProposalRequest) -> dict:  # type: ignore
    """Batch accept/reject proposals (I-4).

    Body: { "actions": [{ "proposal_id": "...", "action": "accept|reject", "reason": "..." }] }
    """
    from uuid import UUID as _UUID

    accepted = 0
    rejected = 0
    errors: list[dict[str, str]] = []
    now = datetime.now(UTC)

    for item in body.actions:
        try:
            uid = _UUID(item.proposal_id)
        except ValueError:
            errors.append({"proposal_id": item.proposal_id, "error": "Invalid UUID"})
            continue

        new_status = ProposalStatus.ACCEPTED if item.action == "accept" else ProposalStatus.REJECTED

        try:
            with db_op("Database unavailable"):
                mongodb_update_proposed_change(
                    uid,
                    ProposedChangeUpdate(
                        status=new_status,
                        decision_metadata=DecisionMetadata(
                            decided_by="user",
                            decided_at=now,
                            reason=item.reason or f"Batch {item.action}",
                            canonical_ref=None,
                        ),
                    ),
                )
            if item.action == "accept":
                accepted += 1
            else:
                rejected += 1
        except Exception as exc:
            errors.append({"proposal_id": item.proposal_id, "error": str(exc)})

    return {
        "accepted": accepted,
        "rejected": rejected,
        "errors": errors,
    }


@router.post("/packs/{pack_id}/commit")
async def commit_accepted_proposals(pack_id: str) -> dict:  # type: ignore
    """Commit all accepted proposals for a pack to Neo4j (I-4 final step).

    Only proposals in 'accepted' status are committed. Rejected proposals
    are left in MongoDB for audit. Pack status transitions to APPLIED.
    """
    pack_uid = validate_uuid(pack_id, "pack_id")

    with db_op("Database unavailable"):
        pack = mongodb_get_knowledge_pack(pack_uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")

    try:
        keeper = CanonKeeper()
        result = await keeper.commit_accepted(pack_uid)
    except Exception as exc:
        raise HTTPException(500, f"Commit failed: {exc}") from exc

    return {
        "pack_id": pack_id,
        "committed": result["committed"],
        "errors": result["errors"],
        "status": "done" if not result["errors"] else "partial",
    }
