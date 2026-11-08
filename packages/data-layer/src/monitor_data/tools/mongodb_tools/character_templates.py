"""
MongoDB tools for portable character templates (G-6).

LAYER: 1 (data-layer)
Authority: MongoDB
Use Case: G-6 / P&F §6

Templates live in the existing ``characters`` collection with ``is_template:
true`` — one collection, so a persona already used in OOC chat stays reachable
and the live character readers keep working unchanged. The character list
excludes templates, so a template never shows up as a playable character.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.character_templates import (
    CharacterTemplateCreate,
    CharacterTemplateFilter,
    CharacterTemplateListResponse,
    CharacterTemplateResponse,
    CharacterTemplateUpdate,
)

# Marker that distinguishes a template document from a character document.
TEMPLATE_MARKER = {"is_template": True}


def _collection() -> Any:
    return get_mongodb_client().get_collection("characters")


def _to_response(doc: dict[str, Any]) -> CharacterTemplateResponse:
    """Map a stored document onto the response shape."""
    return CharacterTemplateResponse(
        template_id=str(doc.get("id") or doc.get("template_id") or ""),
        name=str(doc.get("name") or ""),
        concept=str(doc.get("concept") or ""),
        personality=str(doc.get("personality") or ""),
        backstory_beats=[str(beat) for beat in (doc.get("backstory_beats") or [])],
        voice=str(doc.get("voice") or ""),
        portrait_url=doc.get("portrait_url") or doc.get("avatar_url"),
        first_message=str(doc.get("first_message") or ""),
        gm_notes=str(doc.get("gm_notes") or ""),
        usage_count=int(doc.get("usage_count") or 0),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


def mongodb_create_character_template(
    params: CharacterTemplateCreate,
) -> CharacterTemplateResponse:
    """Create a portable character template."""
    now = datetime.now(UTC)
    template_id = str(uuid4())
    doc = params.model_dump()
    doc.update(
        {
            "id": template_id,
            "template_id": template_id,
            "is_template": True,
            # Mirror the portrait onto the character field so any
            # character-oriented reader still finds it.
            "avatar_url": params.portrait_url,
            "usage_count": 0,
            "created_at": now,
            "updated_at": now,
        }
    )
    _collection().insert_one(doc)
    return _to_response(doc)


def mongodb_get_character_template(template_id: UUID | str) -> CharacterTemplateResponse | None:
    """Fetch one character template."""
    doc = _collection().find_one({"id": str(template_id), **TEMPLATE_MARKER})
    return _to_response(doc) if doc else None


def mongodb_list_character_templates(
    filters: CharacterTemplateFilter,
) -> CharacterTemplateListResponse:
    """List character templates, most recently updated first."""
    query: dict[str, Any] = dict(TEMPLATE_MARKER)
    if filters.name_contains:
        query["name"] = {"$regex": filters.name_contains, "$options": "i"}
    coll = _collection()
    total = coll.count_documents(query)
    cursor = coll.find(query).sort("updated_at", -1).skip(filters.offset).limit(filters.limit)
    templates = [_to_response(doc) for doc in cursor]
    return CharacterTemplateListResponse(
        templates=templates,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


def mongodb_update_character_template(
    template_id: UUID | str,
    params: CharacterTemplateUpdate,
) -> CharacterTemplateResponse | None:
    """Update a character template. Only the provided fields change."""
    updates = params.model_dump(exclude_unset=True, exclude_none=True)
    if "portrait_url" in params.model_fields_set:
        updates["portrait_url"] = params.portrait_url
    if not updates:
        return mongodb_get_character_template(template_id)
    if "portrait_url" in updates:
        updates["avatar_url"] = updates["portrait_url"]
    updates["updated_at"] = datetime.now(UTC)
    _collection().update_one({"id": str(template_id), **TEMPLATE_MARKER}, {"$set": updates})
    return mongodb_get_character_template(template_id)


def mongodb_delete_character_template(template_id: UUID | str) -> bool:
    """Delete a character template. Returns True when a document was removed."""
    result = _collection().delete_one({"id": str(template_id), **TEMPLATE_MARKER})
    return bool(getattr(result, "deleted_count", 0))


def mongodb_increment_character_template_usage(
    template_id: UUID | str,
) -> CharacterTemplateResponse | None:
    """Count one instantiation of the template."""
    _collection().update_one(
        {"id": str(template_id), **TEMPLATE_MARKER},
        {"$inc": {"usage_count": 1}, "$set": {"updated_at": datetime.now(UTC)}},
    )
    return mongodb_get_character_template(template_id)
