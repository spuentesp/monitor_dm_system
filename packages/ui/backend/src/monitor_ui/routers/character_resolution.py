from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.tools.mongodb_tools import mongodb_get_character
from pydantic import BaseModel


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
            )
    except Exception:
        pass

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
                except Exception:
                    props = {}

            # Neo4j Entity IDs can be string or UUID in the driver
            eid = e.get("id")
            if not eid:
                return None

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
            )
    except Exception:
        pass

    return None
