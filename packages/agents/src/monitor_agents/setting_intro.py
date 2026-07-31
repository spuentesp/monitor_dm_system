"""Canon-grounded setting introduction for autonomous-GM pre-play."""

from __future__ import annotations

import asyncio
from typing import Any, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, Field

from monitor_data.schemas.base import CanonLevel, EntityType
from monitor_data.schemas.entities import EntityFilter
from monitor_data.schemas.facts import AxiomFilter, FactFilter
from monitor_data.tools.mongodb_tools import mongodb_get_knowledge_pack
from monitor_data.tools.neo4j_tools.core import neo4j_get_universe
from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities
from monitor_data.tools.neo4j_tools.facts import neo4j_list_axioms, neo4j_list_facts

log = structlog.get_logger()


class SessionIntroAnchor(BaseModel):
    """One sourced statement used by the explanatory setting introduction."""

    kind: Literal["universe", "pack", "axiom", "fact", "location", "faction"]
    statement: str
    object_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    canon_level: str | None = None
    confidence: float | None = None


class SessionIntro(BaseModel):
    """Persisted, non-fictional setting frame shown before story agreements."""

    universe_id: str
    universe_name: str
    intro_text: str
    genre: str | None = None
    tone: str | None = None
    system_name: str | None = None
    source: Literal["pack_intro", "canon_synthesis", "universe_description"]
    anchors: list[SessionIntroAnchor] = Field(default_factory=list)
    unverified: bool = False
    schema_version: int = 1


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _source_ids(values: Any) -> list[str]:
    return [str(value) for value in (values or []) if value]


async def assemble_session_intro(session: dict[str, Any]) -> SessionIntro:
    """Assemble an explanatory intro from data belonging to one universe only.

    There is deliberately no global lore fallback. Sparse universes produce a
    sparse, explicitly marked introduction rather than borrowing another
    universe's canon or inventing setting facts.
    """

    universe_id = _uuid(session.get("universe_id") or session.get("world_id"))
    if universe_id is None:
        return SessionIntro(
            universe_id="",
            universe_name=session.get("universe_label") or "Unknown setting",
            intro_text=(
                "The setting has not been identified yet. Establish the world before beginning play."
            ),
            system_name=session.get("system_label"),
            source="universe_description",
            unverified=True,
        )

    pack_id = _uuid(session.get("pack_id"))
    universe_task = asyncio.to_thread(neo4j_get_universe, universe_id)
    pack_task = (
        asyncio.to_thread(mongodb_get_knowledge_pack, pack_id)
        if pack_id is not None
        else _completed_none()
    )
    universe, pack = await asyncio.gather(universe_task, pack_task)

    universe_name = (
        getattr(universe, "name", None)
        or session.get("universe_label")
        or "Unknown setting"
    )
    description = (getattr(universe, "description", None) or "").strip()
    genre = getattr(universe, "genre", None)
    tone = getattr(universe, "tone", None) or session.get("tone")
    system_name = (
        getattr(universe, "default_system_name", None)
        or session.get("system_label")
    )
    universe_sources = _source_ids(getattr(universe, "source_ids", []))
    anchors: list[SessionIntroAnchor] = []
    if description:
        anchors.append(
            SessionIntroAnchor(
                kind="universe",
                statement=description,
                object_id=str(universe_id),
                source_ids=universe_sources,
                canon_level=str(getattr(universe, "canon_level", CanonLevel.CANON)),
                confidence=getattr(universe, "confidence", None),
            )
        )

    authored_intro = (getattr(pack, "intro_text", None) or "").strip()
    if len(authored_intro) > 40:
        anchors.append(
            SessionIntroAnchor(
                kind="pack",
                statement=authored_intro,
                object_id=str(getattr(pack, "id", pack_id)),
                source_ids=_source_ids(getattr(pack, "source_document_ids", [])),
                canon_level=CanonLevel.CANON.value,
                confidence=1.0,
            )
        )
        return SessionIntro(
            universe_id=str(universe_id),
            universe_name=universe_name,
            intro_text=authored_intro,
            genre=genre,
            tone=tone,
            system_name=system_name,
            source="pack_intro",
            anchors=anchors,
            unverified=not any(anchor.source_ids for anchor in anchors),
        )

    try:
        axioms, facts, locations, factions = await asyncio.gather(
            asyncio.to_thread(
                neo4j_list_axioms,
                AxiomFilter(
                    universe_id=universe_id,
                    canon_level=CanonLevel.CANON,
                    limit=5,
                ),
            ),
            asyncio.to_thread(
                neo4j_list_facts,
                FactFilter(
                    universe_id=universe_id,
                    canon_level=CanonLevel.CANON,
                    limit=6,
                ),
            ),
            asyncio.to_thread(
                neo4j_list_entities,
                EntityFilter(
                    universe_id=universe_id,
                    entity_type=EntityType.LOCATION,
                    limit=4,
                ),
            ),
            asyncio.to_thread(
                neo4j_list_entities,
                EntityFilter(
                    universe_id=universe_id,
                    entity_type=EntityType.FACTION,
                    limit=4,
                ),
            ),
        )
    except Exception as exc:
        log.warning("session_intro.canon_read_failed", universe_id=str(universe_id), error=str(exc))
        axioms, facts, locations, factions = [], [], None, None

    for axiom in axioms:
        anchors.append(
            SessionIntroAnchor(
                kind="axiom",
                statement=axiom.statement,
                object_id=str(axiom.id),
                source_ids=_source_ids(axiom.source_ids),
                canon_level=str(axiom.canon_level),
                confidence=axiom.confidence,
            )
        )
    for fact in facts:
        anchors.append(
            SessionIntroAnchor(
                kind="fact",
                statement=fact.statement,
                object_id=str(fact.id),
                source_ids=_source_ids(fact.source_ids),
                canon_level=str(fact.canon_level),
                confidence=fact.confidence,
            )
        )
    for kind, listing in (("location", locations), ("faction", factions)):
        for entity in getattr(listing, "entities", []) or []:
            if entity.canon_level != CanonLevel.CANON:
                continue
            statement = entity.name
            if entity.description:
                statement = f"{entity.name}: {entity.description}"
            anchors.append(
                SessionIntroAnchor(
                    kind=kind,
                    statement=statement,
                    object_id=str(entity.id),
                    canon_level=str(entity.canon_level),
                    confidence=entity.confidence,
                )
            )

    intro_text = _compose_intro_text(
        universe_name=universe_name,
        description=description,
        genre=genre,
        tone=tone,
        system_name=system_name,
        anchors=anchors,
    )
    source = "canon_synthesis" if any(a.kind != "universe" for a in anchors) else "universe_description"
    has_provenance = bool(universe_sources) or any(anchor.source_ids for anchor in anchors)
    return SessionIntro(
        universe_id=str(universe_id),
        universe_name=universe_name,
        intro_text=intro_text,
        genre=genre,
        tone=tone,
        system_name=system_name,
        source=source,
        anchors=anchors,
        unverified=not has_provenance,
    )


async def _completed_none() -> None:
    return None


def _compose_intro_text(
    *,
    universe_name: str,
    description: str,
    genre: str | None,
    tone: str | None,
    system_name: str | None,
    anchors: list[SessionIntroAnchor],
) -> str:
    parts = [f"This story takes place in **{universe_name}**."]
    if description:
        parts.append(description.rstrip("." ) + ".")

    supporting = [
        anchor.statement.rstrip(".") + "."
        for anchor in anchors
        if anchor.kind in {"faction", "location", "fact", "axiom"}
    ][:3]
    if supporting:
        parts.append(" ".join(supporting))

    play_terms = [term for term in (tone, genre) if term]
    framing = " ".join(dict.fromkeys(str(term) for term in play_terms))
    if framing and system_name:
        parts.append(f"Expect **{framing}** roleplay using **{system_name}**.")
    elif framing:
        parts.append(f"Expect **{framing}** roleplay.")
    elif system_name:
        parts.append(f"The session uses **{system_name}**.")

    return "\n\n".join(part for part in parts if part)
