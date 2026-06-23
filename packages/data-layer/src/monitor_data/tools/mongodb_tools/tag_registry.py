"""MongoDB tools for Tag Registry operations.

LAYER: 1 (data-layer)
IMPORTS FROM: monitor_data.schemas.tag_registry, monitor_data.db.mongodb
CALLED BY: ToneResolver (Layer 2), UI routers (Layer 3)

These tools provide CRUD operations for TagDefinitions, which provide a
taxonomy of valid tags in the system for validation and suggestions.

Authority:
- ToneResolver (Layer 2): Uses synonyms to normalize user tags
- UI routers (Layer 3): Create/Update/Delete tag definitions, get suggestions
- Seed scripts: Create built-in tag definitions

Collection: tag_definitions
Indexes: tag (unique), category, pack_id, is_builtin
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.tag_registry import (
    TagDefinitionCreate,
    TagDefinitionResponse,
    TagDefinitionUpdate,
    TagDefinitionListResponse,
    TagSuggestionRequest,
    TagSuggestionResponse,
    TagCategory,
)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _convert_tag_definition_doc(doc: Dict[str, Any]) -> TagDefinitionResponse:
    """Convert a MongoDB document to TagDefinitionResponse."""
    return TagDefinitionResponse(
        tag=doc["tag"],
        category=TagCategory(doc["category"]),
        synonyms=doc.get("synonyms", []),
        description=doc.get("description", ""),
        example_tones=[UUID(tid) for tid in doc.get("example_tones", [])],
        pack_id=UUID(doc["pack_id"]) if doc.get("pack_id") else None,
        is_builtin=doc.get("is_builtin", False),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


# =============================================================================
# TAG DEFINITION CRUD TOOLS
# =============================================================================


def mongodb_create_tag_definition(params: TagDefinitionCreate) -> TagDefinitionResponse:
    """
    Create a new Tag Definition in MongoDB.

    Authority: UI routers (Layer 3) or seed scripts.

    Args:
        params: TagDefinitionCreate with tag data.

    Returns:
        TagDefinitionResponse with created tag data.
    """
    client = get_mongodb_client()

    doc = {
        "tag": params.tag.lower().strip(),  # Normalize to lowercase
        "category": params.category.value,
        "synonyms": [s.lower().strip() for s in params.synonyms],
        "description": params.description,
        "example_tones": [str(tid) for tid in params.example_tones],
        "pack_id": str(params.pack_id) if params.pack_id else None,
        "is_builtin": params.is_builtin,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    client["tag_definitions"].insert_one(doc)
    return _convert_tag_definition_doc(doc)


def mongodb_get_tag_definition(tag: str) -> Optional[TagDefinitionResponse]:
    """
    Retrieve a Tag Definition by tag name.

    Authority: ToneResolver (Layer 2), UI routers (Layer 3).

    Args:
        tag: Tag name to retrieve (case-insensitive).

    Returns:
        TagDefinitionResponse if found, None otherwise.
    """
    client = get_mongodb_client()
    doc = client["tag_definitions"].find_one({"tag": tag.lower().strip()})
    if not doc:
        return None
    return _convert_tag_definition_doc(doc)


def mongodb_normalize_tag(tag: str) -> str:
    """
    Normalize a tag to its canonical form using synonyms.

    Authority: ToneResolver (Layer 2).

    Args:
        tag: User-provided tag (may be a synonym).

    Returns:
        Canonical tag name (original if no synonym match found).

    Example:
        mongodb_normalize_tag("dark") → "grim" (if "dark" is a synonym of "grim")
        mongodb_normalize_tag("gritty") → "gritty" (no synonym, return as-is)
    """
    client = get_mongodb_client()
    tag_lower = tag.lower().strip()

    # First, check if it's already a canonical tag
    canonical = client["tag_definitions"].find_one({"tag": tag_lower})
    if canonical:
        return tag_lower

    # Then, check if it's a synonym of a canonical tag
    synonym_match = client["tag_definitions"].find_one({"synonyms": {"$in": [tag_lower]}})
    if synonym_match:
        return synonym_match["tag"]  # type: ignore[no-any-return]

    # No match found, return as-is
    return tag_lower


def mongodb_normalize_tags(tags: List[str]) -> List[str]:
    """
    Normalize a list of tags to their canonical forms.

    Authority: ToneResolver (Layer 2).

    Args:
        tags: List of user-provided tags.

    Returns:
        List of canonical tag names (deduplicated).
    """
    normalized = set()
    for tag in tags:
        normalized.add(mongodb_normalize_tag(tag))
    return sorted(list(normalized))


def mongodb_list_tag_definitions(
    category: Optional[TagCategory] = None,
    pack_id: Optional[UUID] = None,
    is_builtin: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> TagDefinitionListResponse:
    """
    List Tag Definitions with optional filters.

    Authority: UI routers (Layer 3), ToneResolver (Layer 2).

    Args:
        category: Filter by category (if provided).
        pack_id: Filter by pack_id (if provided).
        is_builtin: Filter by is_builtin flag (if provided).
        limit: Maximum number of results.
        offset: Pagination offset.

    Returns:
        TagDefinitionListResponse with matching tags.
    """
    client = get_mongodb_client()

    query: Dict[str, Any] = {}
    if category:
        query["category"] = category.value
    if pack_id:
        query["pack_id"] = str(pack_id)
    if is_builtin is not None:
        query["is_builtin"] = is_builtin

    cursor = client["tag_definitions"].find(query).sort("tag", 1).skip(offset).limit(limit)

    tags = [_convert_tag_definition_doc(doc) for doc in cursor]
    total = client["tag_definitions"].count_documents(query)

    return TagDefinitionListResponse(
        tags=tags,
        total=total,
        page=offset // limit + 1,
        page_size=limit,
    )


def mongodb_update_tag_definition(
    tag: str, params: TagDefinitionUpdate
) -> Optional[TagDefinitionResponse]:
    """
    Update an existing Tag Definition.

    Authority: UI routers (Layer 3). Built-in tags are protected.

    Args:
        tag: Tag name to update (case-insensitive).
        params: TagDefinitionUpdate with fields to update.

    Returns:
        Updated TagDefinitionResponse if found, None otherwise.
    """
    client = get_mongodb_client()

    tag_lower = tag.lower().strip()

    update_doc: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if params.synonyms is not None:
        update_doc["synonyms"] = [s.lower().strip() for s in params.synonyms]
    if params.description is not None:
        update_doc["description"] = params.description
    if params.example_tones is not None:
        update_doc["example_tones"] = [str(tid) for tid in params.example_tones]

    client["tag_definitions"].update_one(
        {"tag": tag_lower},
        {"$set": update_doc},
    )

    updated = client["tag_definitions"].find_one({"tag": tag_lower})
    if not updated:
        raise ValueError(f"TagDefinition {tag} not found after update")

    return _convert_tag_definition_doc(updated)


def mongodb_delete_tag_definition(tag: str) -> bool:
    """
    Delete a Tag Definition.

    Authority: UI routers (Layer 3). Built-in tags cannot be deleted.

    Args:
        tag: Tag name to delete (case-insensitive).

    Returns:
        True if deleted, False if not found.

    Raises:
        ValueError: If trying to delete a built-in tag.
    """
    client = get_mongodb_client()

    tag_lower = tag.lower().strip()

    # Check if tag exists and is built-in
    existing = client["tag_definitions"].find_one({"tag": tag_lower})
    if not existing:
        return False

    if existing.get("is_builtin"):
        raise ValueError("Cannot delete built-in TagDefinition")

    result = client["tag_definitions"].delete_one({"tag": tag_lower})
    return result.deleted_count > 0


# =============================================================================
# TAG SUGGESTIONS
# =============================================================================


def mongodb_suggest_tags(request: TagSuggestionRequest) -> TagSuggestionResponse:
    """
    Get tag suggestions for autocomplete (case-insensitive prefix match).

    Authority: UI routers (Layer 3).

    Args:
        request: TagSuggestionRequest with partial tag and optional filters.

    Returns:
        TagSuggestionResponse with matching tags.
    """
    client = get_mongodb_client()

    query: Dict[str, Any] = {"tag": {"$regex": f"^{request.partial.lower()}", "$options": "i"}}
    if request.category:
        query["category"] = request.category.value

    cursor = client["tag_definitions"].find(query).sort("tag", 1).limit(request.limit)

    suggestions = [_convert_tag_definition_doc(doc) for doc in cursor]
    total = client["tag_definitions"].count_documents(query)

    return TagSuggestionResponse(
        suggestions=suggestions,
        partial=request.partial,
        total_found=total,
    )
