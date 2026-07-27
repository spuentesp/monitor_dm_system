"""MongoDB tools for Tone Profile operations.

LAYER: 1 (data-layer)
IMPORTS FROM: monitor_data.schemas.tone_profiles, monitor_data.db.mongodb
CALLED BY: ToneResolver (Layer 2), UI routers (Layer 3)

These tools provide CRUD operations for ToneProfiles, which are reusable
narrative style definitions stored in MongoDB.

Authority:
- ToneResolver (Layer 2): Reads ToneProfiles to resolve tone_tags
- UI routers (Layer 3): Create/Update/Delete user-created ToneProfiles
- Seed scripts: Create built-in ToneProfiles

Collection: tone_profiles
Indexes: profile_id (unique), pack_id, is_builtin
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.tone_profiles import (
    ToneProfileCreate,
    ToneProfileListResponse,
    ToneProfileResponse,
    ToneProfileUpdate,
)

# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _convert_tone_profile_doc(doc: dict[str, Any]) -> ToneProfileResponse:
    """Convert a MongoDB document to ToneProfileResponse."""
    return ToneProfileResponse(
        profile_id=UUID(doc["profile_id"]),
        name=doc["name"],
        description=doc.get("description", ""),
        instruction=doc["instruction"],
        trigger_tags=doc.get("trigger_tags", []),
        category=doc.get("category", "narrative"),
        language=doc.get("language", "en"),
        pack_id=UUID(doc["pack_id"]) if doc.get("pack_id") else None,
        is_builtin=doc.get("is_builtin", False),
        example_output=doc.get("example_output"),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


# =============================================================================
# TONE PROFILE CRUD TOOLS
# =============================================================================


def mongodb_create_tone_profile(params: ToneProfileCreate) -> ToneProfileResponse:
    """
    Create a new Tone Profile in MongoDB.

    Authority: UI routers (Layer 3) or seed scripts.

    Args:
        params: ToneProfileCreate with profile data.

    Returns:
        ToneProfileResponse with created profile data.
    """
    client = get_mongodb_client()
    profile_id = uuid4()

    doc = {
        "profile_id": str(profile_id),
        "name": params.name,
        "description": params.description,
        "instruction": params.instruction,
        "trigger_tags": params.trigger_tags,
        "category": params.category,
        "language": params.language,
        "pack_id": str(params.pack_id) if params.pack_id else None,
        "is_builtin": params.is_builtin,
        "example_output": params.example_output,
        "created_at": datetime.now(UTC).isoformat(),
    }

    client["tone_profiles"].insert_one(doc)
    return _convert_tone_profile_doc(doc)


def mongodb_get_tone_profile(profile_id: UUID) -> ToneProfileResponse | None:
    """
    Retrieve a Tone Profile by ID.

    Authority: ToneResolver (Layer 2), UI routers (Layer 3).

    Args:
        profile_id: ID of the ToneProfile to retrieve.

    Returns:
        ToneProfileResponse if found, None otherwise.
    """
    client = get_mongodb_client()
    doc = client["tone_profiles"].find_one({"profile_id": str(profile_id)})
    if not doc:
        return None
    return _convert_tone_profile_doc(doc)


def mongodb_list_tone_profiles(
    pack_id: UUID | None = None,
    category: str | None = None,
    language: str | None = None,
    is_builtin: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ToneProfileListResponse:
    """
    List Tone Profiles with optional filters.

    Authority: UI routers (Layer 3), ToneResolver (Layer 2).

    Args:
        pack_id: Filter by pack_id (if provided).
        category: Filter by category (if provided).
        language: Filter by language (if provided).
        is_builtin: Filter by is_builtin flag (if provided).
        limit: Maximum number of results.
        offset: Pagination offset.

    Returns:
        ToneProfileListResponse with matching profiles.
    """
    client = get_mongodb_client()

    query: dict[str, Any] = {}
    if pack_id:
        query["pack_id"] = str(pack_id)
    if category:
        query["category"] = category
    if language:
        query["language"] = language
    if is_builtin is not None:
        query["is_builtin"] = is_builtin

    cursor = client["tone_profiles"].find(query).sort("created_at", -1).skip(offset).limit(limit)

    profiles = [_convert_tone_profile_doc(doc) for doc in cursor]
    total = client["tone_profiles"].count_documents(query)

    return ToneProfileListResponse(
        profiles=profiles,
        total=total,
        page=offset // limit + 1,
        page_size=limit,
    )


def mongodb_update_tone_profile(profile_id: UUID, params: ToneProfileUpdate) -> ToneProfileResponse | None:
    """
    Update an existing Tone Profile.

    Authority: UI routers (Layer 3). Built-in profiles are protected.

    Args:
        profile_id: ID of the ToneProfile to update.
        params: ToneProfileUpdate with fields to update.

    Returns:
        Updated ToneProfileResponse if found, None otherwise.

    Raises:
        ValueError: If trying to update a built-in profile with protected fields.
    """
    client = get_mongodb_client()

    # Check if profile exists and is built-in
    existing = client["tone_profiles"].find_one({"profile_id": str(profile_id)})
    if not existing:
        return None

    if existing.get("is_builtin") and params.name:
        # Prevent renaming built-in profiles
        params.name = None

    update_doc: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
    if params.name:
        update_doc["name"] = params.name
    if params.description is not None:
        update_doc["description"] = params.description
    if params.instruction is not None:
        update_doc["instruction"] = params.instruction
    if params.trigger_tags is not None:
        update_doc["trigger_tags"] = params.trigger_tags
    if params.category is not None:
        update_doc["category"] = params.category
    if params.language is not None:
        update_doc["language"] = params.language
    if params.example_output is not None:
        update_doc["example_output"] = params.example_output

    client["tone_profiles"].update_one(
        {"profile_id": str(profile_id)},
        {"$set": update_doc},
    )

    updated = client["tone_profiles"].find_one({"profile_id": str(profile_id)})
    if not updated:
        raise ValueError(f"ToneProfile {profile_id} not found after update")

    return _convert_tone_profile_doc(updated)


def mongodb_delete_tone_profile(profile_id: UUID) -> bool:
    """
    Delete a Tone Profile.

    Authority: UI routers (Layer 3). Built-in profiles cannot be deleted.

    Args:
        profile_id: ID of the ToneProfile to delete.

    Returns:
        True if deleted, False if not found.

    Raises:
        ValueError: If trying to delete a built-in profile.
    """
    client = get_mongodb_client()

    # Check if profile exists and is built-in
    existing = client["tone_profiles"].find_one({"profile_id": str(profile_id)})
    if not existing:
        return False

    if existing.get("is_builtin"):
        raise ValueError("Cannot delete built-in ToneProfile")

    result = client["tone_profiles"].delete_one({"profile_id": str(profile_id)})
    return result.deleted_count > 0


def mongodb_get_tone_profiles_batch(profile_ids: list[UUID]) -> list[ToneProfileResponse]:
    """
    Retrieve multiple Tone Profiles by IDs.

    Authority: ToneResolver (Layer 2) for batch loading.

    Args:
        profile_ids: List of ToneProfile IDs to retrieve.

    Returns:
        List of ToneProfileResponse objects (may be less than requested if some not found).
    """
    if not profile_ids:
        return []

    client = get_mongodb_client()
    query = {"profile_id": {"$in": [str(pid) for pid in profile_ids]}}
    cursor = client["tone_profiles"].find(query)

    return [_convert_tone_profile_doc(doc) for doc in cursor]
