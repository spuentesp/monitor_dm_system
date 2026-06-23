"""Pack Library routes extracted from `ingest.py` to keep concerns focused.

These endpoints manage KnowledgePack CRUD, merging, export/import, and world
application while `ingest.py` stays focused on source uploads and job status.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from monitor_agents.canonkeeper import CanonKeeper
from monitor_data.schemas.knowledge_packs import (
    ChunkSummaryArtifact,
    EmbeddedGameSystem,
    EmbeddedSourceProfile,
    ExtractedAxiom,
    ExtractedAgenda,
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
from monitor_data.schemas.universe import UniverseFilter
from monitor_data.schemas.base import ProposalStatus
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
from monitor_data.tools.neo4j_tools import neo4j_list_universes

from .ingest_shared import (
    _create_setting,
    _ensure_universe_for_multiverse,
    _pack_to_dict,
    db_op,
    validate_uuid,
)

router = APIRouter()


def _assert_pack_not_building(pack, *, action: str) -> None:
    """Block use/edit operations while the backing ingest job is still running."""
    job = None
    if getattr(pack, "ingestion_job_id", None):
        with db_op("Database unavailable"):
            job = mongodb_get_ingestion_job(pack.ingestion_job_id)

    live_statuses = {"pending", "running", "retrying", "backing_off"}
    if job is not None and getattr(job.status, "value", None) in live_statuses:
        stage = (
            job.current_stage.value
            if getattr(job, "current_stage", None)
            else job.status.value
        )
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


def _propagate_system_to_universe(pack: Any, universe_id: UUID) -> None:
    """Best-effort: bind the universe to the pack's authoritative rules source."""
    if not universe_id:
        return

    gsid = getattr(pack, "game_system_id", None)
    embedded = getattr(pack, "game_system_data", None)
    system_name = (
        getattr(embedded, "name", None)
        or getattr(pack, "system_name", None)
        or getattr(pack, "name", None)
    )
    pack_source_id = getattr(pack, "id", None) or getattr(pack, "pack_id", None)

    update_kwargs: dict[str, object] = {
        "default_system_name": system_name,
    }
    if gsid:
        update_kwargs["default_game_system_id"] = gsid

    if embedded is not None:
        update_kwargs["default_system_source_type"] = "pack_embedded"
        if pack_source_id:
            update_kwargs["default_system_source_id"] = str(pack_source_id)
    elif gsid:
        update_kwargs["default_system_source_type"] = "generic_library"
        update_kwargs["default_system_source_id"] = str(gsid)
    else:
        return

    try:
        from monitor_data.schemas.universe import UniverseUpdate as DLUniverseUpdate
        from monitor_data.tools.neo4j_tools import neo4j_update_universe

        neo4j_update_universe(universe_id, DLUniverseUpdate(**update_kwargs))
    except Exception:  # noqa: BLE001
        pass  # best-effort; the pack apply itself already succeeded


@router.get("/packs")
async def list_packs(status: Optional[str] = None, limit: int = 30) -> list[dict]:
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
async def get_pack(pack_id: str) -> dict:
    uid = validate_uuid(pack_id, "pack_id")
    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    return _pack_to_dict(pack)


class PackUpdateRequest(BaseModel):
    """Body for PUT /packs/{pack_id} — all fields optional."""

    name: Optional[str] = None
    axioms: Optional[list[dict]] = None
    entity_archetypes: Optional[list[dict]] = None
    lore_facts: Optional[list[dict]] = None
    entity_relationships: Optional[list[dict]] = None
    random_tables: Optional[list[dict]] = None
    agendas: Optional[list[dict]] = None
    topologies: Optional[list[dict]] = None
    tone_profiles: Optional[list[dict]] = None
    character_profiles: Optional[list[dict]] = None
    generation_templates: Optional[list[dict]] = None
    source_profile_data: Optional[dict] = None
    chunk_summaries: Optional[list[dict]] = None
    section_summaries: Optional[list[dict]] = None
    source_mindscape: Optional[dict] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = None
    game_system_id: Optional[str] = None
    plot_threads: Optional[list[dict]] = None
    source_document_ids: Optional[list[str]] = None


@router.put("/packs/{pack_id}")
async def update_pack(pack_id: str, body: PackUpdateRequest) -> dict:
    """Update a KnowledgePack's extracted content for World Forge editing."""
    uid = validate_uuid(pack_id, "pack_id")

    update_kwargs: dict = {}
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
            update_kwargs["entity_archetypes"] = [
                ExtractedEntityArchetype(**e) for e in body.entity_archetypes
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid entity data: {exc}") from exc
    if body.lore_facts is not None:
        try:
            update_kwargs["lore_facts"] = [
                ExtractedLoreFact(**f) for f in body.lore_facts
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid lore_fact data: {exc}") from exc
    if body.entity_relationships is not None:
        try:
            update_kwargs["entity_relationships"] = [
                ExtractedRelationship(**r) for r in body.entity_relationships
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid relationship data: {exc}") from exc
    if body.random_tables is not None:
        try:
            update_kwargs["random_tables"] = [
                ExtractedRandomTable(**t) for t in body.random_tables
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid random table data: {exc}") from exc
    if body.agendas is not None:
        try:
            update_kwargs["agendas"] = [ExtractedAgenda(**a) for a in body.agendas]
        except Exception as exc:
            raise HTTPException(422, f"Invalid agenda data: {exc}") from exc
    if body.topologies is not None:
        try:
            update_kwargs["topologies"] = [
                ExtractedTopology(**t) for t in body.topologies
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid topology data: {exc}") from exc
    if body.tone_profiles is not None:
        try:
            update_kwargs["tone_profiles"] = [
                ExtractedToneProfile(**t) for t in body.tone_profiles
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid tone profile data: {exc}") from exc
    if body.character_profiles is not None:
        try:
            update_kwargs["character_profiles"] = [
                ExtractedCharacterProfile(**p) for p in body.character_profiles
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid character profile data: {exc}") from exc
    if body.generation_templates is not None:
        try:
            update_kwargs["generation_templates"] = [
                ExtractedGenerationTemplate(**g) for g in body.generation_templates
            ]
        except Exception as exc:
            raise HTTPException(
                422, f"Invalid generation template data: {exc}"
            ) from exc
    if body.source_profile_data is not None:
        try:
            update_kwargs["source_profile_data"] = EmbeddedSourceProfile(
                **body.source_profile_data
            )
        except Exception as exc:
            raise HTTPException(422, f"Invalid source profile data: {exc}") from exc
    if body.chunk_summaries is not None:
        try:
            update_kwargs["chunk_summaries"] = [
                ChunkSummaryArtifact(**c) for c in body.chunk_summaries
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid chunk summary data: {exc}") from exc
    if body.section_summaries is not None:
        try:
            update_kwargs["section_summaries"] = [
                SectionSummaryArtifact(**s) for s in body.section_summaries
            ]
        except Exception as exc:
            raise HTTPException(422, f"Invalid section summary data: {exc}") from exc
    if body.source_mindscape is not None:
        try:
            update_kwargs["source_mindscape"] = SourceMindscapeArtifact(
                **body.source_mindscape
            )
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
            update_kwargs["source_document_ids"] = [
                _UUID(sid) for sid in body.source_document_ids
            ]
        except ValueError as exc:
            raise HTTPException(422, f"Invalid source_document_ids: {exc}") from exc

    with db_op("Database unavailable"):
        existing_pack = mongodb_get_knowledge_pack(uid)
    if not existing_pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(existing_pack, action="editing it")

    try:
        updated = await asyncio.to_thread(
            mongodb_update_knowledge_pack, uid, KnowledgePackUpdate(**update_kwargs)
        )
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
async def promote_pack_item(pack_id: str, body: PromoteRequest) -> dict:
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
        item = axioms.pop(body.source_index)
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

    name: Optional[str] = None
    entity_type: Optional[str] = None
    sub_type: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[dict] = None
    entity_roles: Optional[list[str]] = None
    is_container: Optional[bool] = None
    tags: Optional[list[str]] = None
    confidence: Optional[float] = None


class UpdateRelationshipInPackRequest(BaseModel):
    """Body for PATCH /packs/{pack_id}/relationships/{index}."""

    from_entity: Optional[str] = None
    rel_type: Optional[str] = None
    to_entity: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[float] = None
    tags: Optional[list[str]] = None
    properties: Optional[dict] = None


class AddRelationshipToPackRequest(BaseModel):
    """Body for POST /packs/{pack_id}/relationships — add a new relationship."""

    from_entity: str
    rel_type: str
    to_entity: str
    description: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_ref: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    properties: dict = Field(default_factory=dict)


@router.patch("/packs/{pack_id}/entities/{index}", status_code=200)
async def update_entity_in_pack(
    pack_id: str,
    index: int,
    body: UpdateEntityInPackRequest,
) -> dict:
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
        raise HTTPException(
            422, f"entity index {index} out of range (0..{len(entities) - 1})"
        )

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
) -> dict:
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
) -> dict:
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
) -> dict:
    """Delete a single item from a KnowledgePack's axiom, lore_fact, entity, or relationship array.

    Valid collections: entities, axioms, lore_facts, relationships
    """
    uid = validate_uuid(pack_id, "pack_id")
    valid = {"entities", "axioms", "lore_facts", "relationships"}
    if collection not in valid:
        raise HTTPException(
            422, f"collection must be one of: {', '.join(sorted(valid))}"
        )

    with db_op("Database unavailable"):
        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(pack, action="deleting items from")

    if collection == "entities":
        items = list(pack.entity_archetypes or [])
    elif collection == "axioms":
        items = list(pack.axioms or [])
    elif collection == "lore_facts":
        items = list(pack.lore_facts or [])
    else:
        items = list(pack.entity_relationships or [])

    if index < 0 or index >= len(items):
        raise HTTPException(
            422, f"{collection} index {index} out of range (0..{len(items) - 1})"
        )

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
        updated = await asyncio.to_thread(
            mongodb_update_knowledge_pack, uid, KnowledgePackUpdate(**kwargs)
        )
    return _pack_to_dict(updated)


class MergePacksRequest(BaseModel):
    """Merge two or more packs into one, deduplicating by name/statement."""

    pack_ids: list[str]
    name: Optional[str] = None
    strategy: str = "first_wins"


# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------
# Dedup helper
# --------------------------------------------------------------------------------------------------

Hashable = TypeVar("Hashable")  # noqa: N803
T = TypeVar("T")


def _deduplicate_by_key(
    packs: list[Any],
    *,
    attr: str,
    key_fn: Callable[[T], Hashable],
    strategy: str = "first_wins",
    desc_len_fn: Callable[[T], int] | None = None,
) -> dict[Hashable, T]:
    """Deduplicate items across packs by a key function.

    Args:
        packs:      KnowledgePacks to merge.
        attr:       Attribute name on each pack to iterate (e.g. "axioms").
        key_fn:     Function to derive a dedup key from each item.
        strategy:   "first_wins" (default) or "longest_description".
        desc_len_fn: Required when strategy="longest_description".
    """
    seen: dict[Hashable, T] = {}
    for pack in packs:
        for item in getattr(pack, attr, None) or []:
            key = key_fn(item)
            if key not in seen:
                seen[key] = item
            elif strategy == "longest_description" and desc_len_fn is not None:
                if desc_len_fn(item) > desc_len_fn(seen[key]):
                    seen[key] = item
    return seen


@router.post("/packs/merge", status_code=201)
async def merge_packs(body: MergePacksRequest) -> dict:
    """Merge multiple KnowledgePacks into a new deduplicated pack."""
    if len(body.pack_ids) < 2:
        raise HTTPException(422, "At least 2 pack_ids required for merge")

    uids = [validate_uuid(pid, f"pack_id ({pid})") for pid in body.pack_ids]

    packs = [mongodb_get_knowledge_pack(uid) for uid in uids]

    first = packs[0]

    # --- deduplicate using generic helper ---
    seen_entities = _deduplicate_by_key(
        packs,
        attr="entity_archetypes",
        key_fn=lambda e: e.name.lower().strip(),
        strategy=body.strategy,
        desc_len_fn=lambda e: len(e.description),
    )
    seen_axioms = _deduplicate_by_key(
        packs,
        attr="axioms",
        key_fn=lambda a: a.statement.lower().strip(),
    )
    seen_lore = _deduplicate_by_key(
        packs,
        attr="lore_facts",
        key_fn=lambda f: f.statement.lower().strip(),
    )
    seen_rels = _deduplicate_by_key(
        packs,
        attr="entity_relationships",
        key_fn=lambda r: (
            r.from_entity.lower().strip(),
            r.rel_type.lower().strip(),
            r.to_entity.lower().strip(),
        ),
    )
    seen_tables = _deduplicate_by_key(
        packs,
        attr="random_tables",
        key_fn=lambda t: t.name.lower().strip(),
    )
    seen_agendas = _deduplicate_by_key(
        packs,
        attr="agendas",
        key_fn=lambda a: a.title.lower().strip(),
    )
    seen_topologies = _deduplicate_by_key(
        packs,
        attr="topologies",
        key_fn=lambda t: (
            t.from_location.lower().strip(),
            t.to_location.lower().strip(),
            t.connection_type.lower().strip(),
        ),
    )
    seen_tones = _deduplicate_by_key(
        packs,
        attr="tone_profiles",
        key_fn=lambda t: t.name.lower().strip(),
    )
    seen_character_profiles = _deduplicate_by_key(
        packs,
        attr="character_profiles",
        key_fn=lambda p: p.name.lower().strip(),
    )
    seen_generation_templates = _deduplicate_by_key(
        packs,
        attr="generation_templates",
        key_fn=lambda g: g.name.lower().strip(),
    )
    seen_plot_threads: dict[str, Any] = _deduplicate_by_key(
        packs,
        attr="plot_threads",
        key_fn=lambda t: t.title.lower().strip(),
    )

    system_names = [pack.system_name for pack in packs if pack.system_name]
    merged_system = system_names[0] if system_names else None
    game_system_ids = [pack.game_system_id for pack in packs if pack.game_system_id]
    merged_gsid = game_system_ids[0] if game_system_ids else None
    source_doc_ids = []
    for pack in packs:
        for document_id in pack.source_document_ids:
            if document_id not in source_doc_ids:
                source_doc_ids.append(document_id)
    merged_name = body.name or f"{first.name} (merged)"

    try:
        new_pack = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name=merged_name,
                description=f"Merged from {len(packs)} packs: "
                + ", ".join(pack.name for pack in packs),
                pack_type=first.pack_type,
                status=KnowledgePackStatus.READY,
                system_name=merged_system,
                source_document_ids=source_doc_ids,
                ingestion_job_id=None,
                tags=["merged"],
                axioms=list(seen_axioms.values()),
                entity_archetypes=list(seen_entities.values()),
                lore_facts=list(seen_lore.values()),
                entity_relationships=list(seen_rels.values()),
                random_tables=list(seen_tables.values()),
                agendas=list(seen_agendas.values()),
                topologies=list(seen_topologies.values()),
                tone_profiles=list(seen_tones.values()),
                character_profiles=list(seen_character_profiles.values()),
                generation_templates=list(seen_generation_templates.values()),
                plot_threads=list(seen_plot_threads.values()),
                game_system_id=merged_gsid,
            )
        )
    except Exception as exc:
        raise HTTPException(503, f"Database error creating merged pack: {exc}") from exc

    return _pack_to_dict(new_pack)


class CanonizeRequest(BaseModel):
    multiverse_id: Optional[str] = None
    universe_id: Optional[str] = None
    new_setting_name: Optional[str] = None
    new_setting_system: Optional[str] = None


@router.post("/packs/{pack_id}/canonize")
async def canonize_pack(pack_id: str, body: CanonizeRequest) -> dict:
    """Apply a KnowledgePack to a new or existing world and commit it to Neo4j."""
    pack_uid = validate_uuid(pack_id, "pack_id")

    mv_uid: Optional[UUID] = None
    universe_uid: Optional[UUID] = None

    if body.new_setting_name and body.new_setting_name.strip():
        try:
            mv_uid, universe_uid = _create_setting(
                name=body.new_setting_name.strip(),
                system_name=(body.new_setting_system or body.new_setting_name).strip(),
            )
        except Exception as exc:
            raise HTTPException(500, f"Could not create world: {exc}") from exc
    else:
        if not body.multiverse_id:
            raise HTTPException(422, "Provide either multiverse_id or new_setting_name")
        mv_uid = validate_uuid(body.multiverse_id, "multiverse_id")
        universe_uid = (
            validate_uuid(body.universe_id, "universe_id") if body.universe_id else None
        )

        if universe_uid is None:
            try:
                universe_uid = _ensure_universe_for_multiverse(mv_uid)
            except Exception as exc:
                raise HTTPException(500, f"Could not resolve universe: {exc}") from exc

    with db_op("Database unavailable"):
        pack = mongodb_get_knowledge_pack(pack_uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    if pack.status not in (KnowledgePackStatus.READY, KnowledgePackStatus.APPLIED):
        raise HTTPException(422, f"Pack is not ready (status={pack.status.value})")

    try:
        keeper = CanonKeeper()
        result = await keeper.apply_pack_to_universe(
            pack_id=pack_uid,
            multiverse_id=mv_uid,
            universe_id=universe_uid,
            auto_accept=True,
        )
    except Exception as exc:
        raise HTTPException(500, f"Canonization failed: {exc}") from exc

    # Propagate game system to the universe if the pack carries one
    _propagate_system_to_universe(pack, universe_uid)

    return {
        "pack_id": pack_id,
        "proposals_created": result["proposals_created"],
        "committed": result["committed"],
        "errors": result["errors"],
        "status": "done" if not result["errors"] else "partial",
    }


class CreatePackRequest(BaseModel):
    """Body for POST /packs — manual pack creation (MP-1)."""

    name: str
    description: str = ""
    pack_type: str = "custom"
    system_name: Optional[str] = None
    tags: list[str] = []


@router.post("/packs", status_code=201)
async def create_pack(body: CreatePackRequest) -> dict:
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
async def delete_pack(pack_id: str, hard: bool = False) -> dict:
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
        exported_at=datetime.now(timezone.utc),
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
    pack: dict


@router.post("/packs/import", status_code=201)
async def import_pack(body: ImportPackRequest) -> dict:
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
                entity_archetypes=[
                    ExtractedEntityArchetype(**e)
                    for e in pack_data.get("entity_archetypes", [])
                ],
                lore_facts=[
                    ExtractedLoreFact(**f) for f in pack_data.get("lore_facts", [])
                ],
                entity_relationships=[
                    ExtractedRelationship(**r)
                    for r in pack_data.get("entity_relationships", [])
                ],
                random_tables=[
                    ExtractedRandomTable(**t)
                    for t in pack_data.get("random_tables", [])
                ],
                agendas=[ExtractedAgenda(**a) for a in pack_data.get("agendas", [])],
                topologies=[
                    ExtractedTopology(**t) for t in pack_data.get("topologies", [])
                ],
                tone_profiles=[
                    ExtractedToneProfile(**t)
                    for t in pack_data.get("tone_profiles", [])
                ],
                character_profiles=[
                    ExtractedCharacterProfile(**p)
                    for p in pack_data.get("character_profiles", [])
                ],
                generation_templates=[
                    ExtractedGenerationTemplate(**g)
                    for g in pack_data.get("generation_templates", [])
                ],
                game_system_data=EmbeddedGameSystem(**pack_data["game_system_data"])
                if pack_data.get("game_system_data")
                else None,
                source_profile_data=EmbeddedSourceProfile(
                    **pack_data["source_profile_data"]
                )
                if pack_data.get("source_profile_data")
                else None,
                chunk_summaries=[
                    ChunkSummaryArtifact(**c)
                    for c in pack_data.get("chunk_summaries", [])
                ],
                section_summaries=[
                    SectionSummaryArtifact(**s)
                    for s in pack_data.get("section_summaries", [])
                ],
                source_mindscape=SourceMindscapeArtifact(
                    **pack_data["source_mindscape"]
                )
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

    name: Optional[str] = None
    with_lineage: bool = True


@router.post("/packs/{pack_id}/clone", status_code=201)
async def clone_pack(pack_id: str, body: ClonePackRequest) -> dict:
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
async def slice_pack(pack_id: str, body: SlicePackRequest) -> dict:
    """Create a new pack from a user-selected subset of an existing pack."""
    uid = validate_uuid(pack_id, "pack_id")
    with db_op("Database unavailable"):
        src = mongodb_get_knowledge_pack(uid)
    if not src:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(src, action="slicing it")

    def _pick(items: list, indices: list[int]) -> list:
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
                entity_relationships=_pick(
                    src.entity_relationships, body.relationship_indices
                ),
                random_tables=_pick(src.random_tables, body.random_table_indices),
                agendas=_pick(src.agendas, body.agenda_indices),
                topologies=_pick(src.topologies, body.topology_indices),
                tone_profiles=_pick(src.tone_profiles, body.tone_profile_indices),
                character_profiles=_pick(
                    src.character_profiles, body.character_profile_indices
                ),
                generation_templates=_pick(
                    src.generation_templates, body.generation_template_indices
                ),
                game_system_id=None,
            )
        )
    except Exception as exc:
        raise HTTPException(503, f"Database error: {exc}") from exc
    return _pack_to_dict(sliced)


class ApplyNewWorldRequest(BaseModel):
    """Body for POST /packs/{id}/apply/new-world."""

    world_name: str
    system_name: Optional[str] = None


@router.post("/packs/{pack_id}/apply/new-world", status_code=201)
async def apply_pack_new_world(pack_id: str, body: ApplyNewWorldRequest) -> dict:
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
    entity_indices: list[int] = []
    axiom_indices: list[int] = []
    lore_indices: list[int] = []
    resolved_conflicts: list[dict] = []


@router.post("/packs/{pack_id}/apply/{universe_id}")
async def apply_pack_existing_world(
    pack_id: str,
    universe_id: str,
    body: ApplyExistingWorldRequest,
) -> dict:
    """Apply a pack to an existing universe."""
    pack_uid = validate_uuid(pack_id, "pack_id")
    universe_uid = validate_uuid(universe_id, "universe_id")

    with db_op("Database unavailable"):
        pack = mongodb_get_knowledge_pack(pack_uid)
    if not pack:
        raise HTTPException(404, "KnowledgePack not found")
    _assert_pack_not_building(pack, action="applying it to a world")
    if pack.status == KnowledgePackStatus.ARCHIVED:
        raise HTTPException(422, "Cannot apply an archived pack")

    if body.resolved_conflicts:
        try:
            keeper = CanonKeeper()
            universes = neo4j_list_universes(UniverseFilter(limit=200))
            mv_id = next(
                (
                    universe.multiverse_id
                    for universe in universes
                    if str(universe.id) == universe_id
                ),
                None,
            )
            if mv_id is None:
                raise HTTPException(404, "Universe not found in graph")
            result = await keeper.apply_pack_to_universe(
                pack_id=pack_uid,
                multiverse_id=mv_id,
                universe_id=universe_uid,
                auto_accept=False,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(500, f"Apply failed: {exc}") from exc
        _propagate_system_to_universe(pack, universe_uid)
        return {
            "status": "review_pending",
            "proposals_created": result["proposals_created"],
            "review_status": result.get("review_status", "pending"),
            "errors": result["errors"],
        }

    try:
        universes = neo4j_list_universes(UniverseFilter(limit=500))
        mv_id = next(
            (
                universe.multiverse_id
                for universe in universes
                if str(universe.id) == universe_id
            ),
            None,
        )
        if mv_id is None:
            raise HTTPException(404, "Universe not found in the graph")
        keeper = CanonKeeper()
        result = await keeper.apply_pack_to_universe(
            pack_id=pack_uid,
            multiverse_id=mv_id,
            universe_id=universe_uid,
            auto_accept=False,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Apply failed: {exc}") from exc

    _propagate_system_to_universe(pack, universe_uid)

    return {
        "status": "review_pending",
        "conflicts": [],
        "proposals_created": result["proposals_created"],
        "review_status": result.get("review_status", "pending"),
        "errors": result["errors"],
        "pack_id": pack_id,
        "universe_id": universe_id,
    }


class CreateKGRequest(BaseModel):
    name: str
    source_ids: list[str]
    universe_id: Optional[str] = None


@router.get("/kgs")
async def list_kgs() -> list[dict]:
    try:
        result = mongodb_list_knowledge_packs(KnowledgePackFilter(tag=None, limit=30))
    except Exception:  # noqa: BLE001
        return []
    return [_pack_to_dict(pack) for pack in result.packs]


@router.post("/kgs", status_code=201)
async def create_knowledge_graph(body: CreateKGRequest) -> dict:
    return {
        "id": "stub",
        "name": body.name,
        "source_ids": body.source_ids,
        "universe_id": body.universe_id,
        "entity_count": 0,
        "relation_count": 0,
        "status": "building",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }


# =========================================================================
# Proposal Review Endpoints (I-4)
# =========================================================================


class ProposalActionRequest(BaseModel):
    """Body for PATCH /proposals/{proposal_id} — single proposal action."""

    action: str = Field(
        ..., pattern="^(accept|reject)$", description="Accept or reject"
    )
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
    status: Optional[str] = None,
    change_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
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
            "authority": p.authority.value
            if hasattr(p.authority, "value")
            else p.authority,
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
async def review_proposal(proposal_id: str, body: ProposalActionRequest) -> dict:
    """Accept or reject a single proposal (I-4).

    Accepted proposals are marked for commit but NOT written to Neo4j yet.
    Call POST /packs/{pack_id}/commit to commit all accepted proposals.
    """
    from uuid import UUID as _UUID

    try:
        uid = _UUID(proposal_id)
    except ValueError:
        raise HTTPException(422, f"Invalid proposal_id: {proposal_id}")

    new_status = (
        ProposalStatus.ACCEPTED if body.action == "accept" else ProposalStatus.REJECTED
    )
    now = datetime.now(timezone.utc)

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
            "decided_by": updated.decision_metadata.decided_by,
            "decided_at": updated.decision_metadata.decided_at.isoformat(),
            "reason": updated.decision_metadata.reason,
        },
    }


@router.post("/proposals/batch")
async def batch_review_proposals(body: BatchProposalRequest) -> dict:
    """Batch accept/reject proposals (I-4).

    Body: { "actions": [{ "proposal_id": "...", "action": "accept|reject", "reason": "..." }] }
    """
    from uuid import UUID as _UUID

    accepted = 0
    rejected = 0
    errors: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)

    for item in body.actions:
        try:
            uid = _UUID(item.proposal_id)
        except ValueError:
            errors.append({"proposal_id": item.proposal_id, "error": "Invalid UUID"})
            continue

        new_status = (
            ProposalStatus.ACCEPTED
            if item.action == "accept"
            else ProposalStatus.REJECTED
        )

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
async def commit_accepted_proposals(pack_id: str) -> dict:
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
