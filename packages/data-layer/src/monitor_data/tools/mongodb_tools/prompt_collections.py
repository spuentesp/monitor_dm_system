"""
MongoDB MCP tools for PromptCollection CRUD.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) and UI backend (Layer 3) via MCP protocol

A PromptCollection is a curated set of authored interview questions / prompts
(see schemas/prompt_collections.py). These tools follow the flat CRUD pattern
of character_sheets.py — UUIDs are stored as strings, and a `_doc_to_response`
helper rebuilds the typed model on read.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.prompt_collections import (
    PromptCollectionCreate,
    PromptCollectionFilter,
    PromptCollectionListResponse,
    PromptCollectionPublish,
    PromptCollectionResponse,
    PromptCollectionUpdate,
    PromptCollectionVersionListResponse,
    PromptCollectionVersionResponse,
    PromptEntry,
)

_COLLECTION = "prompt_collections"
_VERSIONS = "prompt_collection_versions"

# =============================================================================
# SERIALIZATION HELPERS
# =============================================================================


def _entry_to_doc(entry: PromptEntry) -> dict[str, Any]:
    """Serialize a PromptEntry into a plain dict (entry_id as string)."""
    return {
        "entry_id": str(entry.entry_id),
        "order": entry.order,
        "category": entry.category,
        "question_text": entry.question_text,
        "answer_options": list(entry.answer_options),
        "guidance": entry.guidance,
        "is_final": entry.is_final,
    }


def _doc_to_entry(raw: dict[str, Any]) -> PromptEntry:
    """Rebuild a PromptEntry from a stored dict."""
    return PromptEntry(
        entry_id=UUID(raw["entry_id"]) if raw.get("entry_id") else uuid4(),
        order=raw.get("order", 0),
        category=raw.get("category", "custom"),
        question_text=raw.get("question_text", ""),
        answer_options=raw.get("answer_options", []),
        guidance=raw.get("guidance"),
        is_final=raw.get("is_final", False),
    )


def _prompt_collection_doc_to_response(doc: dict[str, Any]) -> PromptCollectionResponse:
    """Convert a MongoDB prompt-collection document into the API response model."""
    return PromptCollectionResponse(
        collection_id=UUID(doc["collection_id"]),
        name=doc["name"],
        description=doc.get("description"),
        category=doc.get("category", "session_zero"),
        system_id=UUID(doc["system_id"]) if doc.get("system_id") else None,
        universe_id=UUID(doc["universe_id"]) if doc.get("universe_id") else None,
        tags=doc.get("tags", []),
        entries=[_doc_to_entry(e) for e in doc.get("entries", [])],
        version=doc.get("version"),
        is_builtin=doc.get("is_builtin", False),
        hand_authored=doc.get("hand_authored", True),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


# =============================================================================
# CRUD OPERATIONS
# =============================================================================


def mongodb_create_prompt_collection(
    params: PromptCollectionCreate,
) -> PromptCollectionResponse:
    """Create a curated prompt/question collection."""
    mongo_client = get_mongodb_client()
    collections = mongo_client[_COLLECTION]

    now = datetime.now(UTC)
    collection_id = uuid4()
    doc = {
        "collection_id": str(collection_id),
        "name": params.name,
        "description": params.description,
        "category": params.category,
        "system_id": str(params.system_id) if params.system_id else None,
        "universe_id": str(params.universe_id) if params.universe_id else None,
        "tags": list(params.tags),
        "entries": [_entry_to_doc(e) for e in params.entries],
        "version": params.version,
        "is_builtin": params.is_builtin,
        "hand_authored": params.hand_authored,
        "created_at": now,
        "updated_at": now,
    }

    collections.insert_one(doc)
    return _prompt_collection_doc_to_response(doc)


def mongodb_get_prompt_collection(
    collection_id: UUID,
) -> PromptCollectionResponse | None:
    """Fetch a prompt collection by its collection id."""
    mongo_client = get_mongodb_client()
    doc = mongo_client[_COLLECTION].find_one({"collection_id": str(collection_id)})
    if not doc:
        return None
    return _prompt_collection_doc_to_response(doc)


def mongodb_update_prompt_collection(
    collection_id: UUID,
    params: PromptCollectionUpdate,
) -> PromptCollectionResponse:
    """Update an existing prompt collection. Only provided fields are written."""
    mongo_client = get_mongodb_client()
    collections = mongo_client[_COLLECTION]

    existing = collections.find_one({"collection_id": str(collection_id)})
    if not existing:
        raise ValueError(f"Prompt collection {collection_id} not found")

    update_fields: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if params.name is not None:
        update_fields["name"] = params.name
    if params.description is not None:
        update_fields["description"] = params.description
    if params.category is not None:
        update_fields["category"] = params.category
    if params.system_id is not None:
        update_fields["system_id"] = str(params.system_id)
    if params.universe_id is not None:
        update_fields["universe_id"] = str(params.universe_id)
    if params.tags is not None:
        update_fields["tags"] = list(params.tags)
    if params.entries is not None:
        update_fields["entries"] = [_entry_to_doc(e) for e in params.entries]
    if params.version is not None:
        update_fields["version"] = params.version

    collections.update_one(
        {"collection_id": str(collection_id)},
        {"$set": update_fields},
    )

    updated = collections.find_one({"collection_id": str(collection_id)})
    if not updated:
        raise ValueError(f"Prompt collection {collection_id} not found after update")
    return _prompt_collection_doc_to_response(updated)


def mongodb_delete_prompt_collection(collection_id: UUID) -> bool:
    """Delete a prompt collection. Returns True if a document was removed."""
    mongo_client = get_mongodb_client()
    result = mongo_client[_COLLECTION].delete_one({"collection_id": str(collection_id)})
    return result.deleted_count > 0


def mongodb_list_prompt_collections(
    params: PromptCollectionFilter,
) -> PromptCollectionListResponse:
    """List prompt collections with filtering by category / system / universe / tag."""
    mongo_client = get_mongodb_client()
    collections = mongo_client[_COLLECTION]

    query: dict[str, Any] = {}
    if params.category:
        query["category"] = params.category
    if params.system_id:
        query["system_id"] = str(params.system_id)
    if params.universe_id:
        query["universe_id"] = str(params.universe_id)
    if params.tag:
        query["tags"] = params.tag
    if not params.include_builtin:
        query["is_builtin"] = False

    total = collections.count_documents(query)
    docs = collections.find(query).sort("updated_at", -1).skip(params.offset).limit(params.limit)
    results = [_prompt_collection_doc_to_response(doc) for doc in docs]
    return PromptCollectionListResponse(
        collections=results,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


# =============================================================================
# VERSIONING (immutable published snapshots)
# =============================================================================


def _version_doc_to_response(doc: dict[str, Any]) -> PromptCollectionVersionResponse:
    return PromptCollectionVersionResponse(
        version_id=UUID(doc["version_id"]),
        collection_id=UUID(doc["collection_id"]),
        version=doc["version"],
        name=doc["name"],
        description=doc.get("description"),
        category=doc.get("category", "session_zero"),
        tags=doc.get("tags", []),
        entries=[_doc_to_entry(e) for e in doc.get("entries", [])],
        note=doc.get("note"),
        published_at=doc["published_at"],
    )


def mongodb_publish_prompt_collection(
    collection_id: UUID,
    params: PromptCollectionPublish,
) -> PromptCollectionVersionResponse:
    """Snapshot a prompt collection into an immutable version.

    The version label is auto-assigned (``v1``, ``v2``, …) when not supplied.
    Also stamps the live collection's freeform ``version`` label to match.
    """
    mongo_client = get_mongodb_client()
    collections = mongo_client[_COLLECTION]
    versions = mongo_client[_VERSIONS]

    live = collections.find_one({"collection_id": str(collection_id)})
    if not live:
        raise ValueError(f"Prompt collection {collection_id} not found")

    existing_count = versions.count_documents({"collection_id": str(collection_id)})
    version_label = (params.version or "").strip() or f"v{existing_count + 1}"

    now = datetime.now(UTC)
    version_id = uuid4()
    doc = {
        "version_id": str(version_id),
        "collection_id": str(collection_id),
        "version": version_label,
        "name": live["name"],
        "description": live.get("description"),
        "category": live.get("category", "session_zero"),
        "tags": live.get("tags", []),
        "entries": live.get("entries", []),
        "note": params.note,
        "published_at": now,
    }
    versions.insert_one(doc)

    # Stamp the live collection's freeform version label to the published one.
    collections.update_one(
        {"collection_id": str(collection_id)},
        {"$set": {"version": version_label, "updated_at": now}},
    )
    return _version_doc_to_response(doc)


def mongodb_list_prompt_collection_versions(
    collection_id: UUID,
) -> PromptCollectionVersionListResponse:
    """List a collection's published versions, newest first."""
    mongo_client = get_mongodb_client()
    versions = mongo_client[_VERSIONS]
    query = {"collection_id": str(collection_id)}
    total = versions.count_documents(query)
    docs = versions.find(query).sort("published_at", -1)
    return PromptCollectionVersionListResponse(
        versions=[_version_doc_to_response(d) for d in docs],
        total=total,
    )


def mongodb_restore_prompt_collection_version(
    version_id: UUID,
) -> PromptCollectionResponse:
    """Restore a published version's content back into its live collection."""
    mongo_client = get_mongodb_client()
    versions = mongo_client[_VERSIONS]
    collections = mongo_client[_COLLECTION]

    snapshot = versions.find_one({"version_id": str(version_id)})
    if not snapshot:
        raise ValueError(f"Prompt collection version {version_id} not found")

    collection_id = snapshot["collection_id"]
    if not collections.find_one({"collection_id": collection_id}):
        raise ValueError(f"Prompt collection {collection_id} no longer exists")

    collections.update_one(
        {"collection_id": collection_id},
        {
            "$set": {
                "name": snapshot["name"],
                "description": snapshot.get("description"),
                "category": snapshot.get("category", "session_zero"),
                "tags": snapshot.get("tags", []),
                "entries": snapshot.get("entries", []),
                "version": snapshot.get("version"),
                "updated_at": datetime.now(UTC),
            }
        },
    )
    restored = collections.find_one({"collection_id": collection_id})
    if not restored:
        raise ValueError(f"Prompt collection {collection_id} not found after update")
    return _prompt_collection_doc_to_response(restored)
