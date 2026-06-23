"""Shared helpers for the ingestion and pack-library UI routers.

This keeps `ingest.py` focused on source/job orchestration while the Pack
Library routes reuse the same response shaping and world-bootstrap logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from contextlib import contextmanager
from typing import Generator

from fastapi import HTTPException
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_data.schemas.universe import (
    MultiverseCreate as DLMultiverseCreate,
    UniverseCreate as DLUniverseCreate,
    UniverseFilter,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_get_document,
    mongodb_get_game_system,
)
from monitor_data.tools.neo4j_tools import (
    neo4j_create_multiverse,
    neo4j_create_universe,
    neo4j_ensure_omniverse,
    neo4j_get_multiverse,
    neo4j_get_source,
    neo4j_list_universes,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Shared micro-helpers (DRY elimination across routers)
# -----------------------------------------------------------------------


def validate_uuid(raw: str, field: str = "id") -> UUID:
    """Parse a UUID string or raise HTTP 400."""
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {field} format") from exc


@contextmanager
def db_op(label: str = "Database unavailable") -> Generator[None, None, None]:
    """Context manager that wraps a DB call and translates exceptions to HTTP 503."""
    try:
        yield
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"{label}: {exc}") from exc


_STATUS_MAP: dict[str, str] = {
    # ExtractionStatus values (used by _source_from_doc)
    "pending": "saved",
    "extracting": "processing",
    "completed": "indexed",
    "partial": "indexed",
    "error": "failed",
}


def _default_processing_checklist(pack_type: KnowledgePackType) -> list[str]:
    """Return the default per-layer analysis checklist for a source type."""
    mapping: dict[KnowledgePackType, list[str]] = {
        KnowledgePackType.SETTING_SUPPLEMENT: [
            "axioms",
            "entities",
            "lore",
            "game_system",
            "rules",
        ],
        KnowledgePackType.RULEBOOK: [
            "game_system",
            "rules",
            "entities",
            "lore",
            "axioms",
        ],
        KnowledgePackType.ADVENTURE_MODULE: [
            "entities",
            "lore",
            "axioms",
            "game_system",
            "rules",
        ],
        KnowledgePackType.SESSION_NOTES: [
            "entities",
            "lore",
            "axioms",
            "game_system",
            "rules",
        ],
        KnowledgePackType.HOMEBREW: [
            "axioms",
            "entities",
            "lore",
            "game_system",
            "rules",
        ],
        KnowledgePackType.WIKI: ["axioms", "entities", "lore", "game_system", "rules"],
        KnowledgePackType.CUSTOM: [
            "axioms",
            "entities",
            "lore",
            "game_system",
            "rules",
        ],
    }
    return mapping.get(
        pack_type, ["axioms", "entities", "lore", "game_system", "rules"]
    )


def _create_setting(
    name: str, system_name: str, game_system_id: UUID | None = None
) -> tuple[UUID, UUID]:
    """Create a new Multiverse (is_template=True) plus its canonical Universe."""
    omni = neo4j_ensure_omniverse()
    mv = neo4j_create_multiverse(
        DLMultiverseCreate(
            omniverse_id=UUID(omni["omniverse_id"]),
            name=name,
            system_name=system_name or name,
            description="Setting created from document ingestion.",
            is_template=True,
            source_document_id=None,
            parent_multiverse_id=None,
        )
    )
    universe = neo4j_create_universe(
        DLUniverseCreate(
            multiverse_id=mv.id,
            name=f"{name} — Canon",
            description="Auto-created canonical universe for this setting.",
            genre=None,
            tone=None,
            tech_level=None,
            parent_universe_id=None,
            is_template=True,
            default_game_system_id=game_system_id,
        )
    )
    return mv.id, universe.id


def _ensure_universe_for_multiverse(multiverse_id: UUID) -> UUID:
    """Get or auto-create a canonical Universe under an existing Multiverse."""
    universes = neo4j_list_universes(
        UniverseFilter(multiverse_id=multiverse_id, limit=1)
    )
    if universes:
        return universes[0].id

    mv = neo4j_get_multiverse(multiverse_id)
    mv_name = mv.name if mv else "Setting"
    universe = neo4j_create_universe(
        DLUniverseCreate(
            multiverse_id=multiverse_id,
            name=f"{mv_name} — Canon",
            description="Auto-created canonical universe.",
            genre=None,
            tone=None,
            tech_level=None,
            parent_universe_id=None,
            is_template=True,
            default_game_system_id=None,
        )
    )
    return universe.id


def _source_from_job(job: Any) -> dict:
    """Merge IngestionJobResponse plus Neo4j SourceResponse into the frontend Source shape."""
    source_node = None
    doc = None
    try:
        source_node = neo4j_get_source(job.source_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not fetch Neo4j source node for %s: %s", job.source_id, exc)
    try:
        doc = mongodb_get_document(job.doc_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not fetch document record for job %s: %s", job.job_id, exc)

    title = (source_node.title if source_node else None) or (
        doc.title if doc else "Unknown"
    )
    source_type = (
        doc.file_type
        if doc
        else (source_node.source_type.value if source_node else "txt")
    )
    canon_level = source_node.canon_level.value if source_node else "proposed"
    size_bytes = doc.file_size_bytes or 0 if doc else 0
    filename = doc.filename if doc else title

    if source_node:
        uploaded_at = source_node.created_at.isoformat()
    elif job.started_at:
        uploaded_at = job.started_at.isoformat()
    else:
        uploaded_at = datetime.now(timezone.utc).isoformat()

    return {
        "id": str(job.source_id),
        "title": title,
        "filename": filename,
        "source_type": source_type,
        "status": job.status.value,
        "size_bytes": size_bytes,
        "page_count": None,
        "entity_count": job.entities_extracted,
        "relation_count": 0,
        "canon_level": canon_level,
        "error_message": job.last_error or (job.errors[0] if job.errors else None),
        "uploaded_at": uploaded_at,
        "indexed_at": job.completed_at.isoformat() if job.completed_at else None,
        "tags": [],
        "metadata": {
            "job_id": str(job.job_id),
            "universe_id": str(job.universe_id),
        },
    }


def _source_from_doc(doc: Any) -> dict:
    """Build a source response from a raw DocumentResponse with no ingestion job."""
    return {
        "id": str(doc.source_id),
        "title": doc.title,
        "filename": doc.filename,
        "source_type": doc.file_type or "pdf",
        "status": _STATUS_MAP.get(doc.extraction_status.value, "indexed"),
        "size_bytes": doc.file_size_bytes or 0,
        "page_count": None,
        "entity_count": 0,
        "relation_count": 0,
        "canon_level": "proposed",
        "error_message": doc.extraction_error,
        "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
        "indexed_at": doc.extracted_at.isoformat() if doc.extracted_at else None,
        "tags": [],
        "metadata": {
            "job_id": None,
            "universe_id": str(doc.universe_id),
        },
    }


def _job_to_dict(job: Any) -> dict:
    """Normalize an ingestion job into the frontend-friendly shape."""
    title = job.source_title or str(job.source_id)[:8]
    return {
        "id": str(job.job_id),
        "source_id": str(job.source_id),
        "source_title": title,
        "job_type": "extract",
        "status": job.status.value,
        "progress": int(job.progress * 100),
        "current_stage": job.current_stage.value if job.current_stage else None,
        "stages_completed": [s.value for s in job.stages_completed],
        "processing_checklist": list(job.processing_checklist),
        "activity_log": list(job.activity_log),
        "warnings": list(job.warnings),
        "errors": list(job.errors),
        "snippet_count": job.snippet_count,
        "entities_extracted": job.entities_extracted,
        "axioms_extracted": job.axioms_extracted,
        "proposals_generated": job.proposals_generated,
        "total_batches": job.total_batches,
        "succeeded_batches": job.succeeded_batches,
        "failed_batches": job.failed_batches,
        "retried_batches": job.retried_batches,
        "current_provider": job.current_provider,
        "current_model": job.current_model,
        "last_error": job.last_error,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "partial": job.partial,
        "kill_reason": job.kill_reason,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "duration_seconds": job.duration_seconds,
        "error": job.last_error or (job.errors[0] if job.errors else None),
    }


def _game_system_summary(pack: Any) -> dict | None:
    """Build a lightweight game-system summary for pack responses.

    Prefers inline ``game_system_data`` embedded on the pack.  Falls back to
    fetching from the separate ``game_systems`` collection via
    ``game_system_id``.
    """
    # -- inline embedded data (preferred) --------------------------------
    gsd = getattr(pack, "game_system_data", None)
    if gsd is not None:
        return {
            "name": gsd.name,
            "core_mechanic": gsd.core_mechanic.model_dump(mode="json")
            if gsd.core_mechanic
            else None,
            "rule_count": len(gsd.rules),
            "attribute_count": len(gsd.attributes),
            "skill_count": len(gsd.skills),
            "resource_count": len(gsd.resources),
            "has_character_creation": gsd.character_creation is not None,
            "source": "embedded",
        }

    # -- fallback: separate collection -----------------------------------
    game_system_id = getattr(pack, "game_system_id", None)
    if not game_system_id:
        return None
    try:
        system = mongodb_get_game_system(game_system_id)
    except Exception:  # noqa: BLE001
        return None
    if not system:
        return None
    return {
        "id": str(system.id),
        "name": system.name,
        "core_mechanic": system.core_mechanic.model_dump(mode="json"),
        "rule_count": len(system.rules),
        "attribute_count": len(system.attributes),
        "skill_count": len(system.skills),
        "resource_count": len(system.resources),
        "has_character_creation": system.character_creation is not None,
        "source": "referenced",
    }


def _dump_model_list(items: Any) -> list:
    """Serialize a list of Pydantic models or plain dicts."""
    return [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        for item in (items or [])
    ]


def _pack_to_dict(pack: Any) -> dict:
    """Serialize a KnowledgePack, preserving richer entity metadata for the UI."""
    # Build embedded system/profile payloads for the response
    gsd = getattr(pack, "game_system_data", None)
    source_profile = getattr(pack, "source_profile_data", None)
    source_mindscape = getattr(pack, "source_mindscape", None)
    game_system_data_dict = gsd.model_dump(mode="json") if gsd else None
    source_profile_data_dict = (
        source_profile.model_dump(mode="json") if source_profile else None
    )
    source_mindscape_dict = (
        source_mindscape.model_dump(mode="json") if source_mindscape else None
    )
    chunk_summaries = [
        chunk.model_dump(mode="json") if hasattr(chunk, "model_dump") else chunk
        for chunk in (getattr(pack, "chunk_summaries", None) or [])
    ]
    section_summaries = [
        section.model_dump(mode="json") if hasattr(section, "model_dump") else section
        for section in (getattr(pack, "section_summaries", None) or [])
    ]
    random_tables = _dump_model_list(getattr(pack, "random_tables", None))
    agendas = _dump_model_list(getattr(pack, "agendas", None))
    topologies = _dump_model_list(getattr(pack, "topologies", None))
    tone_profiles = _dump_model_list(getattr(pack, "tone_profiles", None))
    character_profiles = _dump_model_list(getattr(pack, "character_profiles", None))
    generation_templates = _dump_model_list(getattr(pack, "generation_templates", None))
    plot_threads = _dump_model_list(getattr(pack, "plot_threads", None))

    # KnowledgePackResponse exposes `id` (pack_id is an input alias only)
    pack_id = getattr(pack, "id", None) or getattr(pack, "pack_id", None)
    return {
        "id": str(pack_id),
        "name": pack.name,
        "description": pack.description,
        "pack_type": pack.pack_type.value,
        "status": pack.status.value,
        "system_name": pack.system_name,
        "game_system_id": str(pack.game_system_id) if pack.game_system_id else None,
        "game_system": _game_system_summary(pack),
        "game_system_data": game_system_data_dict,
        "source_profile_data": source_profile_data_dict,
        "chunk_summaries": chunk_summaries,
        "section_summaries": section_summaries,
        "source_mindscape": source_mindscape_dict,
        "axiom_count": pack.axiom_count,
        "entity_count": pack.entity_count,
        "lore_fact_count": pack.lore_fact_count,
        "axioms": [
            {
                "statement": a.statement,
                "domain": a.domain,
                "confidence": a.confidence,
                "source_ref": a.source_ref,
                "tags": a.tags,
                "evidence_refs": [
                    er.model_dump(mode="json") if hasattr(er, "model_dump") else er
                    for er in (a.evidence_refs or [])
                ],
            }
            for a in pack.axioms
        ],
        "entity_archetypes": [
            {
                "name": e.name,
                "entity_type": e.entity_type,
                "sub_type": e.sub_type,
                "description": e.description,
                "properties": e.properties,
                "entity_roles": list(getattr(e, "entity_roles", []) or []),
                "is_container": bool(getattr(e, "is_container", False)),
                "parent_entity_name": e.parent_entity_name,
                "source_ref": e.source_ref,
                "confidence": e.confidence,
                "tags": e.tags,
                "aliases": list(getattr(e, "aliases", []) or []),
                "evidence_refs": [
                    er.model_dump(mode="json") if hasattr(er, "model_dump") else er
                    for er in (e.evidence_refs or [])
                ],
            }
            for e in pack.entity_archetypes
        ],
        "lore_facts": [
            {
                "statement": f.statement,
                "fact_type": f.fact_type,
                "entity_names": f.entity_names,
                "source_ref": f.source_ref,
                "confidence": f.confidence,
                "tags": f.tags,
                "canon_level": f.canon_level.value,
                "knowledge_scope": f.knowledge_scope.value,
                "evidence_refs": [
                    er.model_dump(mode="json") if hasattr(er, "model_dump") else er
                    for er in (f.evidence_refs or [])
                ],
            }
            for f in pack.lore_facts
        ],
        "entity_relationships": [
            {
                "from_entity": r.from_entity,
                "rel_type": r.rel_type,
                "to_entity": r.to_entity,
                "description": r.description,
                "confidence": r.confidence,
                "source_ref": r.source_ref,
            }
            for r in (pack.entity_relationships or [])
        ],
        "random_tables": random_tables,
        "agendas": agendas,
        "topologies": topologies,
        "tone_profiles": tone_profiles,
        "character_profiles": character_profiles,
        "generation_templates": generation_templates,
        "plot_threads": plot_threads,
        "random_table_count": len(random_tables),
        "agenda_count": len(agendas),
        "topology_count": len(topologies),
        "tone_profile_count": len(tone_profiles),
        "character_profile_count": len(character_profiles),
        "generation_template_count": len(generation_templates),
        "plot_thread_count": len(plot_threads),
        "created_at": pack.created_at.isoformat(),
        "updated_at": pack.updated_at.isoformat() if pack.updated_at else None,
        "applied_to": [str(a.universe_id) for a in pack.applied_to if a.universe_id],
        "parent_pack_ids": pack.parent_pack_ids,
        "source_document_ids": [str(sid) for sid in (pack.source_document_ids or [])],
    }
