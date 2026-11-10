from __future__ import annotations

import structlog

import json
from typing import Any, Literal
from uuid import UUID

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.character_sheets import CharacterSheetFilter
from monitor_data.tools.mongodb_tools import mongodb_get_character
from pydantic import BaseModel

log = structlog.get_logger()


class CharacterContext(BaseModel):
    """Unified character reference (standalone OR entity)."""

    source: Literal["standalone", "entity"]
    id: UUID
    name: str
    personality: str = ""
    description: str = ""
    is_ooc_persona: bool = False
    role: str = "pc"
    state_tags: list[str] = []
    attributes: dict[str, Any] = {}
    skills: dict[str, Any] = {}
    resources: dict[str, Any] = {}
    # Persona-to-incarnation link (Phase 4 Task 4): the persona (the user's
    # cross-world identity) this incarnation was instantiated from.
    persona_id: str | None = None
    persona_name: str | None = None


def resolve_persona_link(character_id: str, *, source: str | None = None) -> dict[str, Any] | None:
    """Return ``{"persona_id", "persona_name"}`` for a character incarnation.

    Reads the persona link off the character record (Task 4): standalone
    characters carry ``source_persona_id`` on their document; Neo4j entity
    incarnations carry it on their active character sheet (the
    ``CharacterSheetCreate.source_persona_id`` field). Returns None when the
    character has no persona link.

    Cross-component reads: ``mongodb_get_character`` (standalone doc + persona
    name) and ``mongodb_list_character_sheets`` (entity incarnations).
    """
    persona_id: str | None = None
    if source != "entity":
        try:
            doc = mongodb_get_character(character_id)
            if doc:
                persona_id = doc.get("source_persona_id") or None
        except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in resolve_persona_link)
            log.debug("persona link lookup failed for standalone %s", character_id, exc_info=True)
    if persona_id is None and source != "standalone":
        try:
            from monitor_data.tools.mongodb_tools import mongodb_list_character_sheets

            listing = mongodb_list_character_sheets(CharacterSheetFilter(entity_id=UUID(character_id)))
            sheets = getattr(listing, "sheets", None) or []
            for sheet in sheets:
                candidate = getattr(sheet, "source_persona_id", None)
                if candidate:
                    persona_id = str(candidate)
                    break
        except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in resolve_persona_link)
            log.debug("persona link lookup failed for entity %s", character_id, exc_info=True)
    if not persona_id:
        return None
    persona_name: str | None = None
    try:
        persona_doc = mongodb_get_character(persona_id)
        if persona_doc:
            persona_name = persona_doc.get("name") or None
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in resolve_persona_link)
        log.debug("persona name lookup failed for %s", persona_id, exc_info=True)
    return {"persona_id": str(persona_id), "persona_name": persona_name}


def resolve_controlled_personas(character_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Persona links for a roster of controlled character ids (Task 1/4).

    Returns ``{character_id: {"persona_id", "persona_name"}}`` for the
    characters that have a persona link — consumed by ``build_cast`` so the
    cast panel and prompts can show who the user is behind each incarnation.
    """
    out: dict[str, dict[str, Any]] = {}
    for raw_id in character_ids or []:
        key = str(raw_id).strip()
        if not key:
            continue
        link = resolve_persona_link(key)
        if link:
            out[key] = link
    return out


def resolve_character_names(character_ids: list[str]) -> dict[str, str]:
    """Display names for a roster of character ids (Task 1).

    Standalone characters resolve through their MongoDB document, entity
    incarnations through Neo4j. Ids that resolve to nothing are omitted —
    ``build_cast`` falls back to the id.
    """
    out: dict[str, str] = {}
    for raw_id in character_ids or []:
        key = str(raw_id).strip()
        if not key:
            continue
        try:
            doc = mongodb_get_character(key)
            if doc and doc.get("name"):
                out[key] = str(doc["name"])
                continue
        except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in resolve_character_names)
            log.debug("name lookup failed for standalone %s", key, exc_info=True)
        try:
            neo = get_neo4j_client()
            rows = neo.execute_read("MATCH (e:Entity {id: $id}) RETURN e.name AS name", {"id": key})
            if rows and rows[0].get("name"):
                out[key] = str(rows[0]["name"])
        except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in resolve_character_names)
            log.debug("name lookup failed for entity %s", key, exc_info=True)
    return out


def resolve_actor_character(
    session_data: dict[str, Any],
) -> CharacterContext | None:
    """
    Resolve a character ID into a unified CharacterContext.

    Checks MongoDB standalone characters first, then Neo4j entities.
    Reads speaker_character_id or character_id from session_data.
    """
    actor_id_str = session_data.get("speaker_character_id") or session_data.get("character_id")
    if not actor_id_str:
        return None

    # 1. Check MongoDB standalone characters
    try:
        standalone = mongodb_get_character(actor_id_str)
        if standalone:
            persona_id = standalone.get("source_persona_id") or None
            persona_name: str | None = None
            if persona_id:
                persona_doc = mongodb_get_character(str(persona_id))
                persona_name = persona_doc.get("name") if persona_doc else None
            return CharacterContext(
                source="standalone",
                id=UUID(standalone["id"]),
                name=standalone["name"],
                personality=standalone.get("personality", ""),
                description=standalone.get("description", ""),
                is_ooc_persona=standalone.get("is_ooc_persona", False),
                role="pc",
                state_tags=["pc", "standalone"],
                attributes={},
                skills={},
                resources={},
                persona_id=str(persona_id) if persona_id else None,
                persona_name=persona_name,
            )
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in resolve_actor_character)
        log.debug("character resolution document parse failed", exc_info=True)

    # 2. Check Neo4j entities
    try:
        neo = get_neo4j_client()
        rows = neo.execute_read(
            "MATCH (e:Entity {id: $id}) RETURN e",
            {"id": str(actor_id_str)},
        )
        if rows:
            e = rows[0]["e"]
            props = e.get("properties", {})
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except (
                    ValueError,
                    TypeError,
                ):  # narrowed: JSON/base64/enum failures; RecursionError/MemoryError now propagate
                    props = {}

            # Neo4j Entity IDs can be string or UUID in the driver
            eid = e.get("id")
            if not eid:
                return None

            # Persona-to-incarnation link (Task 4): on the active sheet.
            persona_id: str | None = None
            persona_name: str | None = None
            link = resolve_persona_link(str(eid), source="entity")
            if link:
                persona_id = link.get("persona_id")
                persona_name = link.get("persona_name")

            return CharacterContext(
                source="entity",
                id=UUID(str(eid)),
                name=e.get("name", "Unknown"),
                personality=props.get("personality", ""),
                description=e.get("description", ""),
                is_ooc_persona=False,
                role=str(props.get("role", "pc")).lower(),
                state_tags=list(e.get("state_tags", [])),
                attributes=dict(props.get("attributes", {})),
                skills=dict(props.get("skills", {})),
                resources=dict(props.get("resources", {})),
                persona_id=persona_id,
                persona_name=persona_name,
            )
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in resolve_actor_character)
        log.debug("character resolution document parse failed", exc_info=True)

    return None
