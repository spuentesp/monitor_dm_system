"""Gather what a universe holds, to ground the world-seed start options.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libs.

Reads Neo4j (entities, facts, axioms, agendas) and MongoDB (applied packs:
character_profiles, topologies, agendas, plot_threads). Read-only — the
CanonKeeper write rule is not involved here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from monitor_agents.world_seed.models import UniverseMaterial

logger = logging.getLogger(__name__)


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _clean(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


async def gather_universe_material(
    universe_id: str | UUID,
    *,
    pack_ids: list[str] | None = None,
) -> UniverseMaterial:
    """Collect grounding material for one universe.

    ``pack_ids`` are knowledge packs known to belong to the session (its
    ``pack_id`` / ``system_source_id``); packs already applied to the
    universe are discovered from their ``applied_to`` entries as well.
    """
    uid = _uuid(universe_id)
    if uid is None:
        return UniverseMaterial(universe_id=str(universe_id))

    material = UniverseMaterial(universe_id=str(uid))
    await asyncio.gather(
        _load_universe(uid, material),
        _load_graph_content(uid, material),
        _load_pack_content(uid, material, [_uuid(p) for p in (pack_ids or []) if _uuid(p)]),
    )
    return material


async def _load_universe(uid: UUID, material: UniverseMaterial) -> None:
    try:
        from monitor_data.tools.neo4j_tools.core import neo4j_get_universe

        universe = await asyncio.to_thread(neo4j_get_universe, uid)
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _load_universe)
        logger.debug("world_seed: universe load failed: %s", exc)
        return
    if universe is None:
        return
    material.universe_name = _clean(getattr(universe, "name", ""), 200)
    material.description = _clean(getattr(universe, "description", ""), 1000)
    material.genre = getattr(universe, "genre", None)
    material.tone = getattr(universe, "tone", None)
    material.system_name = getattr(universe, "default_system_name", None)


async def _load_graph_content(uid: UUID, material: UniverseMaterial) -> None:
    try:
        from monitor_data.schemas.base import EntityType
        from monitor_data.schemas.entities import EntityFilter
        from monitor_data.schemas.facts import AxiomFilter, FactFilter
        from monitor_data.tools.neo4j_tools.agendas import neo4j_list_agendas
        from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities
        from monitor_data.tools.neo4j_tools.facts import neo4j_list_axioms, neo4j_list_facts

        locations, characters, factions, axioms, facts, agendas = await asyncio.gather(
            asyncio.to_thread(
                neo4j_list_entities,
                EntityFilter(universe_id=uid, entity_type=EntityType.LOCATION, limit=12),
            ),
            asyncio.to_thread(
                neo4j_list_entities,
                EntityFilter(universe_id=uid, entity_type=EntityType.CHARACTER, limit=20),
            ),
            asyncio.to_thread(
                neo4j_list_entities,
                EntityFilter(universe_id=uid, entity_type=EntityType.FACTION, limit=10),
            ),
            asyncio.to_thread(neo4j_list_axioms, AxiomFilter(universe_id=uid, limit=5)),
            asyncio.to_thread(neo4j_list_facts, FactFilter(universe_id=uid, limit=10)),
            asyncio.to_thread(neo4j_list_agendas, uid, "active"),
        )
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _load_graph_content)
        logger.debug("world_seed: graph read failed: %s", exc)
        return

    for entity in getattr(locations, "entities", []) or []:
        material.locations.append({"name": _clean(entity.name, 200), "description": _clean(entity.description, 500)})
    for entity in getattr(characters, "entities", []) or []:
        want = ""
        properties = getattr(entity, "properties", None)
        if isinstance(properties, dict):
            want = _clean(properties.get("want"), 300)
        material.characters.append(
            {
                "name": _clean(entity.name, 200),
                "description": _clean(entity.description, 500),
                "want": want,
                "is_archetype": str(bool(getattr(entity, "is_archetype", False))),
            }
        )
    for entity in getattr(factions, "entities", []) or []:
        material.factions.append({"name": _clean(entity.name, 200), "description": _clean(entity.description, 500)})
    for axiom in axioms or []:
        statement = _clean(getattr(axiom, "statement", ""), 500)
        if statement:
            material.axioms.append(statement)
    for fact in facts or []:
        statement = _clean(getattr(fact, "statement", ""), 500)
        if statement:
            material.facts.append(statement)
    for agenda in agendas or []:
        title = _clean(agenda.get("title"), 200)
        if title:
            material.agendas.append(
                {
                    "title": title,
                    "description": _clean(agenda.get("description"), 500),
                    "agenda_type": _clean(agenda.get("agenda_type"), 50),
                }
            )


async def _load_pack_content(uid: UUID, material: UniverseMaterial, known_pack_ids: list[UUID]) -> None:
    try:
        from monitor_data.schemas.knowledge_packs import KnowledgePackFilter
        from monitor_data.tools.mongodb_tools import (
            mongodb_get_knowledge_pack,
            mongodb_list_knowledge_packs,
        )

        pack_ids: list[UUID] = list(known_pack_ids)
        listing = await asyncio.to_thread(mongodb_list_knowledge_packs, KnowledgePackFilter(limit=200))
        for pack in getattr(listing, "packs", []) or []:
            pack_uid = _uuid(getattr(pack, "id", None))
            if pack_uid is None or pack_uid in pack_ids:
                continue
            applied_to = getattr(pack, "applied_to", None) or []
            for entry in applied_to:
                entry_universe = entry.get("universe_id") if isinstance(entry, dict) else None
                if _uuid(entry_universe) == uid:
                    pack_ids.append(pack_uid)
                    break

        for pack_uid in pack_ids:
            pack = await asyncio.to_thread(mongodb_get_knowledge_pack, pack_uid)
            if pack is None:
                continue
            _absorb_pack(pack, material)
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _load_pack_content)
        logger.debug("world_seed: pack read failed: %s", exc)


def _absorb_pack(pack: Any, material: UniverseMaterial) -> None:
    for profile in getattr(pack, "character_profiles", []) or []:
        name = _clean(getattr(profile, "name", ""), 200)
        if not name:
            continue
        desires = [str(d) for d in (getattr(profile, "desires", []) or []) if str(d).strip()]
        summary = "; ".join(desires[:3]) or _clean(getattr(profile, "speech_style", ""), 200)
        material.character_profiles.append({"name": name, "summary": summary})
    for top in getattr(pack, "topologies", []) or []:
        from_location = _clean(getattr(top, "from_location", ""), 200)
        to_location = _clean(getattr(top, "to_location", ""), 200)
        if from_location and to_location:
            material.topologies.append(
                {
                    "from_location": from_location,
                    "to_location": to_location,
                    "description": _clean(getattr(top, "description", ""), 500),
                }
            )
    for agenda in getattr(pack, "agendas", []) or []:
        title = _clean(getattr(agenda, "title", ""), 200)
        if title:
            material.agendas.append(
                {
                    "title": title,
                    "description": _clean(getattr(agenda, "description", ""), 500),
                    "agenda_type": _clean(getattr(agenda, "agenda_type", ""), 50),
                }
            )
    for thread in getattr(pack, "plot_threads", []) or []:
        title = _clean(getattr(thread, "title", ""), 200)
        if title:
            material.plot_threads.append(
                {
                    "title": title,
                    "description": _clean(getattr(thread, "description", ""), 500),
                    "category": _clean(getattr(thread, "category", ""), 50) or "mystery",
                    "urgency": _clean(getattr(thread, "urgency", ""), 50) or "medium",
                }
            )
