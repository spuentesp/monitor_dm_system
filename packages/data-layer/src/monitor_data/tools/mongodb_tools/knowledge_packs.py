"""Auto-extracted MongoDB tools sub-module."""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

import structlog

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.base import (
    Authority,
    ProposalStatus,
    ProposalType,
)
from monitor_data.schemas.agendas import ExtractedAgenda
from monitor_data.schemas.contradiction import ContradictionResult
from monitor_data.schemas.knowledge_packs import (
    AppliedToEntry,
    ApplyKnowledgePackRequest,
    ChunkSummaryArtifact,
    EmbeddedGameSystem,
    EmbeddedSourceProfile,
    ExtractedAxiom,
    ExtractedCharacterProfile,
    ExtractedEntityArchetype,
    ExtractedGenerationTemplate,
    ExtractedLoreFact,
    ExtractedRelationship,
    ExtractedRandomTable,
    ExtractedToneProfile,
    ExtractedTopology,
    KnowledgePackCreate,
    KnowledgePackFilter,
    KnowledgePackListResponse,
    KnowledgePackResponse,
    KnowledgePackStatus,
    KnowledgePackUpdate,
    SectionSummaryArtifact,
    SourceMindscapeArtifact,
)

log = structlog.get_logger()
# =============================================================================
# KNOWLEDGE PACK TOOLS
# =============================================================================


def _convert_knowledge_pack_doc(doc: Dict[str, Any]) -> KnowledgePackResponse:
    """Convert MongoDB knowledge pack document to response schema."""
    return KnowledgePackResponse(
        pack_id=UUID(doc["pack_id"]),
        name=doc["name"],
        description=doc.get("description", ""),
        pack_type=doc.get("pack_type", "rulebook"),
        system_name=doc.get("system_name"),
        status=KnowledgePackStatus(doc["status"]),
        source_document_ids=[UUID(d) for d in doc.get("source_document_ids", [])],
        ingestion_job_id=UUID(doc["ingestion_job_id"]) if doc.get("ingestion_job_id") else None,
        tags=doc.get("tags", []),
        parent_pack_ids=doc.get("parent_pack_ids", []),
        axioms=[ExtractedAxiom(**a) for a in doc.get("axioms", [])],
        entity_archetypes=[ExtractedEntityArchetype(**e) for e in doc.get("entity_archetypes", [])],
        lore_facts=[ExtractedLoreFact(**f) for f in doc.get("lore_facts", [])],
        entity_relationships=[
            ExtractedRelationship(**r) for r in doc.get("entity_relationships", [])
        ],
        random_tables=[ExtractedRandomTable(**t) for t in doc.get("random_tables", [])],
        agendas=[ExtractedAgenda(**a) for a in doc.get("agendas", [])],
        topologies=[ExtractedTopology(**t) for t in doc.get("topologies", [])],
        character_profiles=[
            ExtractedCharacterProfile(**p) for p in doc.get("character_profiles", [])
        ],
        generation_templates=[
            ExtractedGenerationTemplate(**g) for g in doc.get("generation_templates", [])
        ],
        tone_profiles=[ExtractedToneProfile(**t) for t in doc.get("tone_profiles", [])],
        game_system_id=UUID(doc["game_system_id"]) if doc.get("game_system_id") else None,
        game_system_data=EmbeddedGameSystem(**doc["game_system_data"])
        if doc.get("game_system_data")
        else None,
        source_profile_data=EmbeddedSourceProfile(**doc["source_profile_data"])
        if doc.get("source_profile_data")
        else None,
        chunk_summaries=[ChunkSummaryArtifact(**c) for c in doc.get("chunk_summaries", [])],
        section_summaries=[SectionSummaryArtifact(**s) for s in doc.get("section_summaries", [])],
        source_mindscape=SourceMindscapeArtifact(**doc["source_mindscape"])
        if doc.get("source_mindscape")
        else None,
        applied_to=[AppliedToEntry(**a) for a in doc.get("applied_to", [])],
        axiom_count=len(doc.get("axioms", [])),
        entity_count=len(doc.get("entity_archetypes", [])),
        lore_fact_count=len(doc.get("lore_facts", [])),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


def mongodb_create_knowledge_pack(params: KnowledgePackCreate) -> KnowledgePackResponse:
    """
    Create a new knowledge pack.

    Called by the Analyzer agent when extraction from a source document is
    complete.  The pack starts in DRAFT status and transitions to READY when
    the Analyzer has finished processing all chunks.

    Args:
        params: KnowledgePack creation parameters

    Returns:
        KnowledgePackResponse with the new pack_id
    """
    mongodb = get_mongodb_client()
    packs_collection = mongodb.get_collection("knowledge_packs")

    now = datetime.now(timezone.utc)
    pack_id = params.pack_id or uuid4()

    doc = {
        "pack_id": str(pack_id),
        "name": params.name,
        "description": params.description,
        "pack_type": params.pack_type.value,
        "system_name": params.system_name,
        "status": params.status.value,
        "source_document_ids": [str(d) for d in params.source_document_ids],
        "ingestion_job_id": str(params.ingestion_job_id) if params.ingestion_job_id else None,
        "tags": params.tags,
        "parent_pack_ids": params.parent_pack_ids,
        "axioms": [a.model_dump(mode="json") for a in params.axioms],
        "entity_archetypes": [e.model_dump(mode="json") for e in params.entity_archetypes],
        "lore_facts": [f.model_dump(mode="json") for f in params.lore_facts],
        "entity_relationships": [r.model_dump(mode="json") for r in params.entity_relationships],
        "random_tables": [t.model_dump(mode="json") for t in params.random_tables],
        "agendas": [a.model_dump(mode="json") for a in params.agendas],
        "topologies": [t.model_dump(mode="json") for t in params.topologies],
        "character_profiles": [p.model_dump(mode="json") for p in params.character_profiles],
        "generation_templates": [g.model_dump(mode="json") for g in params.generation_templates],
        "tone_profiles": [t.model_dump(mode="json") for t in params.tone_profiles],
        "game_system_id": str(params.game_system_id) if params.game_system_id else None,
        "game_system_data": params.game_system_data.model_dump(mode="json")
        if params.game_system_data
        else None,
        "source_profile_data": params.source_profile_data.model_dump(mode="json")
        if params.source_profile_data
        else None,
        "chunk_summaries": [c.model_dump(mode="json") for c in params.chunk_summaries],
        "section_summaries": [s.model_dump(mode="json") for s in params.section_summaries],
        "source_mindscape": params.source_mindscape.model_dump(mode="json")
        if params.source_mindscape
        else None,
        "applied_to": [],
        "created_at": now,
        "updated_at": None,
    }

    packs_collection.insert_one(doc)

    return _convert_knowledge_pack_doc(doc)


def mongodb_get_knowledge_pack(pack_id: UUID) -> Optional[KnowledgePackResponse]:
    """
    Get a knowledge pack by ID.

    Args:
        pack_id: KnowledgePack UUID

    Returns:
        KnowledgePackResponse or None if not found
    """
    mongodb = get_mongodb_client()
    packs_collection = mongodb.get_collection("knowledge_packs")
    doc = packs_collection.find_one({"pack_id": str(pack_id)})
    if not doc:
        return None
    return _convert_knowledge_pack_doc(doc)


def mongodb_update_knowledge_pack(
    pack_id: UUID, params: KnowledgePackUpdate
) -> KnowledgePackResponse:
    """
    Update a knowledge pack.

    Used to mark the pack READY after extraction is complete, add reviewed
    axioms/entities, or update tags.

    Args:
        pack_id: KnowledgePack UUID
        params: Fields to update (all optional)

    Returns:
        Updated KnowledgePackResponse

    Raises:
        ValueError: If pack not found
    """
    mongodb = get_mongodb_client()
    packs_collection = mongodb.get_collection("knowledge_packs")

    update_fields: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if params.name is not None:
        update_fields["name"] = params.name
    if params.description is not None:
        update_fields["description"] = params.description
    if params.status is not None:
        update_fields["status"] = params.status.value
    if params.tags is not None:
        update_fields["tags"] = params.tags
    if params.axioms is not None:
        update_fields["axioms"] = [a.model_dump(mode="json") for a in params.axioms]
    if params.entity_archetypes is not None:
        update_fields["entity_archetypes"] = [
            e.model_dump(mode="json") for e in params.entity_archetypes
        ]
    if params.lore_facts is not None:
        update_fields["lore_facts"] = [f.model_dump(mode="json") for f in params.lore_facts]
    if getattr(params, "entity_relationships", None) is not None:
        update_fields["entity_relationships"] = [
            r.model_dump(mode="json") for r in params.entity_relationships
        ]
    if params.random_tables is not None:
        update_fields["random_tables"] = [t.model_dump(mode="json") for t in params.random_tables]
    if params.agendas is not None:
        update_fields["agendas"] = [a.model_dump(mode="json") for a in params.agendas]
    if params.topologies is not None:
        update_fields["topologies"] = [t.model_dump(mode="json") for t in params.topologies]
    if params.character_profiles is not None:
        update_fields["character_profiles"] = [
            p.model_dump(mode="json") for p in params.character_profiles
        ]
    if params.generation_templates is not None:
        update_fields["generation_templates"] = [
            g.model_dump(mode="json") for g in params.generation_templates
        ]
    if params.tone_profiles is not None:
        update_fields["tone_profiles"] = [t.model_dump(mode="json") for t in params.tone_profiles]
    if params.source_profile_data is not None:
        update_fields["source_profile_data"] = params.source_profile_data.model_dump(mode="json")
    if params.chunk_summaries is not None:
        update_fields["chunk_summaries"] = [
            c.model_dump(mode="json") for c in params.chunk_summaries
        ]
    if params.section_summaries is not None:
        update_fields["section_summaries"] = [
            s.model_dump(mode="json") for s in params.section_summaries
        ]
    if params.source_mindscape is not None:
        update_fields["source_mindscape"] = params.source_mindscape.model_dump(mode="json")
    if params.game_system_id is not None:
        update_fields["game_system_id"] = str(params.game_system_id)
    if params.game_system_data is not None:
        update_fields["game_system_data"] = params.game_system_data.model_dump(mode="json")
    if getattr(params, "system_name", None) is not None:
        update_fields["system_name"] = params.system_name
    if getattr(params, "parent_pack_ids", None) is not None:
        update_fields["parent_pack_ids"] = params.parent_pack_ids

    doc = packs_collection.find_one_and_update(
        {"pack_id": str(pack_id)},
        {"$set": update_fields},
        return_document=True,
    )
    if not doc:
        raise ValueError(f"KnowledgePack {pack_id} not found")
    return _convert_knowledge_pack_doc(doc)


def mongodb_list_knowledge_packs(params: KnowledgePackFilter) -> KnowledgePackListResponse:
    """
    List knowledge packs with optional filtering.

    Args:
        params: Filter options (pack_type, system_name, status, tag, pagination)

    Returns:
        KnowledgePackListResponse with matching packs
    """
    mongodb = get_mongodb_client()
    packs_collection = mongodb.get_collection("knowledge_packs")

    query: Dict[str, Any] = {}
    if params.pack_type:
        query["pack_type"] = params.pack_type.value
    if params.system_name:
        query["system_name"] = {"$regex": params.system_name, "$options": "i"}
    if params.status:
        query["status"] = params.status.value
    if params.tag:
        query["tags"] = params.tag

    total = packs_collection.count_documents(query)
    cursor = (
        packs_collection.find(query).sort("created_at", -1).skip(params.offset).limit(params.limit)
    )

    packs = [_convert_knowledge_pack_doc(doc) for doc in cursor]

    return KnowledgePackListResponse(
        packs=packs,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_delete_knowledge_pack(pack_id: UUID, *, soft: bool = True) -> bool:
    """
    Delete or archive a KnowledgePack.

    When soft=True (default) the pack is archived (status='archived').  A hard
    delete (soft=False) removes the document from MongoDB.  Callers should
    check for dependents before calling with soft=False.

    Args:
        pack_id: KnowledgePack UUID to remove.
        soft: If True, set status='archived'; if False, delete the document.

    Returns:
        True if the pack was found and acted upon, False if not found.
    """
    mongodb = get_mongodb_client()
    packs_collection = mongodb.get_collection("knowledge_packs")
    if soft:
        update_result = packs_collection.update_one(
            {"pack_id": str(pack_id)},
            {
                "$set": {
                    "status": KnowledgePackStatus.ARCHIVED.value,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return update_result.matched_count > 0
    delete_result = packs_collection.delete_one({"pack_id": str(pack_id)})
    return bool(delete_result.deleted_count > 0)


def mongodb_count_pack_dependents(pack_id: UUID) -> int:
    """Return the number of packs that list pack_id in their parent_pack_ids."""
    mongodb = get_mongodb_client()
    return mongodb.get_collection("knowledge_packs").count_documents(
        {"parent_pack_ids": str(pack_id)}
    )


def mongodb_apply_knowledge_pack(
    pack_id: UUID, params: ApplyKnowledgePackRequest
) -> Dict[str, Any]:
    """
    Apply a knowledge pack to a multiverse by creating ProposedChanges.

    For each axiom, entity archetype, and lore fact in the pack, a
    ProposedChange document is written to MongoDB.  CanonKeeper then
    evaluates these proposals and commits accepted ones to Neo4j.

    Conflict resolution (params.conflict_resolution):
        merge  — Proposals marked 'pending', CanonKeeper merges with matching canon
        skip   — Proposals skip items already present in canon
        force  — Proposals override existing canon (use carefully)

    Args:
        pack_id: KnowledgePack UUID to apply
        params: Target multiverse/universe and conflict options

    Returns:
        Dict with 'proposals_created' count and 'job' summary

    Raises:
        ValueError: If pack not found or status is not READY
    """
    mongodb = get_mongodb_client()
    packs_collection = mongodb.get_collection("knowledge_packs")
    proposals_collection = mongodb.get_collection("proposed_changes")

    pack_doc = packs_collection.find_one({"pack_id": str(pack_id)})
    if not pack_doc:
        raise ValueError(f"KnowledgePack {pack_id} not found")

    pack = _convert_knowledge_pack_doc(pack_doc)
    if pack.status not in (KnowledgePackStatus.READY, KnowledgePackStatus.APPLIED):
        raise ValueError(
            f"KnowledgePack {pack_id} is in status '{pack.status.value}' — "
            "only READY or APPLIED packs can be applied"
        )

    # --- EPIC 2: Contradiction detection against existing canon ---
    contradiction_result: Optional[ContradictionResult] = None
    try:
        from monitor_data.tools.ingest_tools.contradiction_detection import (
            detect_contradictions,
        )

        # Fetch existing canon from the proposals collection (committed facts/axioms)
        canon_axioms = list(
            proposals_collection.find(
                {
                    "multiverse_id": str(params.multiverse_id),
                    "proposal_type": {"$in": ["create_axiom"]},
                    "status": "accepted",
                },
                {"statement": 1, "domain": 1, "source_ref": 1, "canon_level": 1, "confidence": 1},
            )
        )
        canon_facts = list(
            proposals_collection.find(
                {
                    "multiverse_id": str(params.multiverse_id),
                    "proposal_type": {"$in": ["create_lore_fact"]},
                    "status": "accepted",
                },
                {
                    "statement": 1,
                    "fact_type": 1,
                    "source_ref": 1,
                    "canon_level": 1,
                    "confidence": 1,
                },
            )
        )
        contradiction_result = detect_contradictions(
            new_pack=pack,
            canon_axioms=canon_axioms,
            canon_facts=canon_facts,
            multiverse_id=params.multiverse_id,
            universe_id=params.universe_id,
        )
        if contradiction_result.total_contradictions > 0:
            log.warning(
                "contradiction_detection_found",
                pack_id=str(pack_id),
                total=contradiction_result.total_contradictions,
                high_severity=contradiction_result.high_severity_count,
                critical=contradiction_result.critical_severity_count,
            )
    except Exception as exc:  # noqa: BLE001
        # Contradiction detection is advisory — never block apply on its failure
        log.warning("contradiction_detection_failed", pack_id=str(pack_id), error=str(exc))

    now = datetime.now(timezone.utc)
    proposals_created = 0
    proposal_docs: list[dict[str, Any]] = []

    # --- Axioms ---
    if params.apply_axioms:
        for axiom in pack.axioms:
            proposal_id = uuid4()
            payload: dict[str, Any] = {
                "statement": axiom.statement,
                "domain": axiom.domain,
                "source_ref": axiom.source_ref,
                "confidence": axiom.confidence,
                "tags": axiom.tags,
            }
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.FACT.value,
                    "proposal_type": "create_axiom",
                    "content": payload,
                    "payload": payload,
                    "confidence": axiom.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Entity archetypes ---
    if params.apply_entities:
        for entity in pack.entity_archetypes:
            proposal_id = uuid4()
            payload_properties = dict(entity.properties)
            if entity.entity_roles:
                payload_properties.setdefault("entity_roles", entity.entity_roles)
            if entity.is_container:
                payload_properties.setdefault("is_container", True)

            payload = {
                "name": entity.name,
                "entity_type": entity.entity_type,
                "sub_type": entity.sub_type,
                "description": entity.description,
                "properties": payload_properties,
                "entity_roles": entity.entity_roles,
                "is_container": entity.is_container,
                "source_ref": entity.source_ref,
                "confidence": entity.confidence,
                "tags": entity.tags,
            }
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.ENTITY.value,
                    "proposal_type": "create_entity_archetype",
                    "content": payload,
                    "payload": payload,
                    "confidence": entity.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

            # If this entity has a known parent, also generate a subtype_of
            # relationship proposal so the SUBTYPE_OF edge is committed to Neo4j
            # once both entity nodes exist (GAP-16 fix).
            if entity.parent_entity_name:
                rel_payload = {
                    "from_entity": entity.name,
                    "rel_type": "subtype_of",
                    "to_entity": entity.parent_entity_name,
                    "description": f"{entity.name} is a subtype of {entity.parent_entity_name}",
                    "confidence": entity.confidence,
                    "source_ref": entity.source_ref,
                }
                proposal_docs.append(
                    {
                        "proposal_id": str(uuid4()),
                        "universe_id": str(params.universe_id) if params.universe_id else None,
                        "multiverse_id": str(params.multiverse_id),
                        "proposer": params.proposer,
                        "change_type": ProposalType.RELATIONSHIP.value,
                        "proposal_type": "entity_relationship",
                        "content": rel_payload,
                        "payload": rel_payload,
                        "confidence": entity.confidence,
                        "authority": Authority.SOURCE.value,
                        "status": ProposalStatus.PENDING.value,
                        "conflict_resolution": params.conflict_resolution,
                        "source": f"knowledge_pack:{pack_id}",
                        "created_at": now,
                        "updated_at": None,
                    }
                )
                proposals_created += 1

    # --- Lore facts ---
    if params.apply_lore_facts:
        for lore_fact in pack.lore_facts:
            proposal_id = uuid4()
            payload = {
                "statement": lore_fact.statement,
                "fact_type": lore_fact.fact_type,
                "entity_names": lore_fact.entity_names,
                "source_ref": lore_fact.source_ref,
                "confidence": lore_fact.confidence,
                "tags": lore_fact.tags,
                "canon_level": lore_fact.canon_level.value,
                "knowledge_scope": lore_fact.knowledge_scope.value,
            }
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.FACT.value,
                    "proposal_type": "create_lore_fact",
                    "content": payload,
                    "payload": payload,
                    "confidence": lore_fact.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Entity relationships ---
    if params.apply_relationships:
        for rel in pack.entity_relationships:
            proposal_id = uuid4()
            payload = {
                "from_entity": rel.from_entity,
                "rel_type": rel.rel_type,
                "to_entity": rel.to_entity,
                "description": rel.description,
                "confidence": rel.confidence,
                "source_ref": rel.source_ref,
            }
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.RELATIONSHIP.value,
                    "proposal_type": "entity_relationship",
                    "content": payload,
                    "payload": payload,
                    "confidence": rel.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Random tables ---
    if params.apply_random_tables:
        for table in pack.random_tables:
            proposal_id = uuid4()
            payload = table.model_dump(mode="json")
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.MECHANIC.value,
                    "proposal_type": "create_random_table",
                    "content": payload,
                    "payload": payload,
                    "confidence": table.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Agendas ---
    if params.apply_agendas:
        for agenda in pack.agendas:
            proposal_id = uuid4()
            payload = agenda.model_dump(mode="json")
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.FACT.value,
                    "proposal_type": "create_agenda",
                    "content": payload,
                    "payload": payload,
                    "confidence": agenda.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Topologies ---
    if params.apply_topologies:
        for top in pack.topologies:
            proposal_id = uuid4()
            payload = top.model_dump(mode="json")
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.RELATIONSHIP.value,
                    "proposal_type": "spatial_topology",
                    "content": payload,
                    "payload": payload,
                    "confidence": top.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Tone Profiles ---
    if params.apply_tone_profiles:
        for tone in pack.tone_profiles:
            proposal_id = uuid4()
            payload = tone.model_dump(mode="json")
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.FACT.value,
                    "proposal_type": "create_tone_profile",
                    "content": payload,
                    "payload": payload,
                    "confidence": tone.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Character Profiles ---
    if params.apply_character_profiles:
        for profile in pack.character_profiles:
            proposal_id = uuid4()
            payload = profile.model_dump(mode="json")
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.ENTITY.value,
                    "proposal_type": "create_character_profile",
                    "content": payload,
                    "payload": payload,
                    "confidence": profile.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Generation Templates ---
    if params.apply_generation_templates:
        for template in pack.generation_templates:
            proposal_id = uuid4()
            payload = template.model_dump(mode="json")
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.MECHANIC.value,
                    "proposal_type": "create_generation_template",
                    "content": payload,
                    "payload": payload,
                    "confidence": template.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    # --- Plot Threads ---
    if params.apply_plot_threads:
        for thread in pack.plot_threads:
            proposal_id = uuid4()
            payload = thread.model_dump(mode="json")
            proposal_docs.append(
                {
                    "proposal_id": str(proposal_id),
                    "universe_id": str(params.universe_id) if params.universe_id else None,
                    "multiverse_id": str(params.multiverse_id),
                    "proposer": params.proposer,
                    "change_type": ProposalType.FACT.value,
                    "proposal_type": "create_plot_thread",
                    "content": payload,
                    "payload": payload,
                    "confidence": thread.confidence,
                    "authority": Authority.SOURCE.value,
                    "status": ProposalStatus.PENDING.value,
                    "conflict_resolution": params.conflict_resolution,
                    "source": f"knowledge_pack:{pack_id}",
                    "created_at": now,
                    "updated_at": None,
                }
            )
            proposals_created += 1

    if proposal_docs:
        proposals_collection.insert_many(proposal_docs)

    # Record this application on the pack
    applied_entry = {
        "multiverse_id": str(params.multiverse_id),
        "universe_id": str(params.universe_id) if params.universe_id else None,
        "applied_at": now,
        "proposals_created": proposals_created,
        "proposals_accepted": 0,
        "applied_by": params.proposer,
    }
    packs_collection.update_one(
        {"pack_id": str(pack_id)},
        {
            "$push": {"applied_to": applied_entry},
            "$set": {
                "status": KnowledgePackStatus.APPLIED.value,
                "updated_at": now,
            },
        },
    )

    return {
        "pack_id": str(pack_id),
        "multiverse_id": str(params.multiverse_id),
        "proposals_created": proposals_created,
        "axioms_proposed": len(pack.axioms) if params.apply_axioms else 0,
        "entities_proposed": len(pack.entity_archetypes) if params.apply_entities else 0,
        "lore_facts_proposed": len(pack.lore_facts) if params.apply_lore_facts else 0,
        "relationships_proposed": len(pack.entity_relationships)
        if params.apply_relationships
        else 0,
        "random_tables_proposed": len(pack.random_tables) if params.apply_random_tables else 0,
        "agendas_proposed": len(pack.agendas) if params.apply_agendas else 0,
        "topologies_proposed": len(pack.topologies) if params.apply_topologies else 0,
        "tone_profiles_proposed": len(pack.tone_profiles) if params.apply_tone_profiles else 0,
        "character_profiles_proposed": len(pack.character_profiles)
        if params.apply_character_profiles
        else 0,
        "generation_templates_proposed": len(pack.generation_templates)
        if params.apply_generation_templates
        else 0,
        "plot_threads_proposed": len(pack.plot_threads) if params.apply_plot_threads else 0,
        "conflict_resolution": params.conflict_resolution,
        "status": "proposals_created",
        "contradictions": (
            {
                "total": contradiction_result.total_contradictions,
                "high_severity": contradiction_result.high_severity_count,
                "critical_severity": contradiction_result.critical_severity_count,
                "matches": [
                    m.model_dump(mode="json") for m in contradiction_result.all_matches[:20]
                ],
            }
            if contradiction_result is not None
            else None
        ),
    }
