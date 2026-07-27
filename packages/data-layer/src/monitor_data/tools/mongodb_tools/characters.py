"""Character CRUD operations for MongoDB."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client


def mongodb_get_character(character_id: UUID | str) -> dict[str, Any] | None:
    """Fetch a single standalone character by ID from MongoDB."""
    coll = get_mongodb_client().get_collection("characters")
    return coll.find_one({"id": str(character_id)})


def mongodb_resolve_character(character_id: str) -> dict[str, Any]:
    """
    Resolve a character ID into a unified context dict.

    Checks MongoDB standalone characters first, then Neo4j entities.
    Returns a dict with 'source' ('standalone' or 'entity'), 'id', 'name',
    'personality', 'description', 'role', 'state_tags', 'attributes',
    'skills', 'resources', and 'is_ooc_persona'.

    Authority: ["*"] (read-only)

    Use Case: GAP-A — unified character resolution for agents layer.
    """
    # 1. Check MongoDB standalone characters
    try:
        standalone = mongodb_get_character(character_id)
        if standalone:
            return {
                "source": "standalone",
                "id": standalone.get("id", character_id),
                "name": standalone.get("name", "Unknown"),
                "personality": standalone.get("personality", ""),
                "description": standalone.get("description", ""),
                "is_ooc_persona": standalone.get("is_ooc_persona", False),
                "role": "pc",
                "state_tags": ["pc", "standalone"],
                "attributes": {},
                "skills": {},
                "resources": {},
            }
    except Exception:
        pass

    # 2. Check Neo4j entities
    try:
        neo = get_neo4j_client()
        rows = neo.execute_read(
            "MATCH (e:Entity {entity_id: $id}) RETURN e",
            {"id": str(character_id)},
        )
        if rows:
            e = rows[0]["e"]
            props = e.get("properties", {})
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except Exception:
                    props = {}

            eid = e.get("entity_id") or e.get("id") or character_id
            return {
                "source": "entity",
                "id": str(eid),
                "name": e.get("name", "Unknown"),
                "personality": props.get("personality", ""),
                "description": e.get("description", ""),
                "is_ooc_persona": False,
                "role": str(props.get("role", "pc")).lower(),
                "state_tags": list(e.get("state_tags", [])),
                "attributes": dict(props.get("attributes", {})),
                "skills": dict(props.get("skills", {})),
                "resources": dict(props.get("resources", {})),
            }
    except Exception:
        pass

    raise ValueError(f"Character {character_id} not found in MongoDB or Neo4j")
