"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.gm_profiles import (
    GMProfileCreate,
    GMProfileFilter,
    GMProfileListResponse,
    GMProfileResponse,
    GMProfileUpdate,
)
from monitor_data.schemas.knowledge_packs import EmbeddedWorldProfile

# =============================================================================
# WORLD PROFILE PERSISTENCE
# Stores the live EmbeddedWorldProfile for a universe so World Architect sessions
# accumulate knowledge across turns and across separate sessions.
# Collection: world_profiles  —  one document per universe_id.
# =============================================================================


def mongodb_upsert_world_profile(
    universe_id: UUID,
    profile: EmbeddedWorldProfile,
) -> None:
    """
    Persist (insert or replace) the EmbeddedWorldProfile for a universe.

    Authority: WorldArchitect (Layer 2) — called after each turn so the profile
    grows richer as more world elements are defined.

    Args:
        universe_id: The universe this profile belongs to.
        profile:     The current EmbeddedWorldProfile to store.
    """
    client = get_mongodb_client()
    doc = {
        "universe_id": str(universe_id),
        "profile_data": profile.model_dump(mode="json"),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    client["world_profiles"].replace_one(
        {"universe_id": str(universe_id)},
        doc,
        upsert=True,
    )


def mongodb_get_world_profile(universe_id: UUID) -> EmbeddedWorldProfile | None:
    """
    Load the persisted EmbeddedWorldProfile for a universe, if one exists.

    Authority: WorldArchitect (Layer 2) — called at the start of each turn so
    the prior session's accumulated profile is available for merging.

    Args:
        universe_id: The universe to look up.

    Returns:
        EmbeddedWorldProfile if found, else None.
    """
    client = get_mongodb_client()
    doc = client["world_profiles"].find_one({"universe_id": str(universe_id)})
    if not doc:
        return None
    profile_data = doc.get("profile_data")
    if not isinstance(profile_data, dict):
        return None
    try:
        return EmbeddedWorldProfile(**profile_data)
    except Exception:
        return None


# =============================================================================
# GM PROFILE TOOLS
# =============================================================================


def _convert_gm_profile_doc(doc: dict[str, Any]) -> GMProfileResponse:
    """Convert a MongoDB document to GMProfileResponse."""
    return GMProfileResponse(
        profile_id=UUID(doc["profile_id"]),
        name=doc["name"],
        description=doc.get("description", ""),
        tone_tags=doc.get("tone_tags", []),
        theme_tags=doc.get("theme_tags", []),
        style_tags=doc.get("style_tags", []),
        concept_tags=doc.get("concept_tags", []),
        tone_instructions=doc.get("tone_instructions"),
        narrator_constraints=doc.get("narrator_constraints"),
        tone_library_id=UUID(doc["tone_library_id"]) if doc.get("tone_library_id") else None,
        merge_with_default_library=doc.get("merge_with_default_library", True),
        universe_id=UUID(doc["universe_id"]) if doc.get("universe_id") else None,
        game_system_id=UUID(doc["game_system_id"]) if doc.get("game_system_id") else None,
        is_builtin=doc.get("is_builtin", False),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


def mongodb_create_gm_profile(params: GMProfileCreate) -> GMProfileResponse:
    """
    Create a new GM Profile.

    Authority: WorldArchitect, Narrator (for runtime adaptation)
    Use Case: GM tone/style/concept configuration

    Args:
        params: GM Profile creation parameters

    Returns:
        GMProfileResponse with created profile data
    """
    mongo_client = get_mongodb_client()

    profile_id = params.profile_id or uuid4()
    created_at = datetime.now(UTC)

    profile_doc = {
        "profile_id": str(profile_id),
        "name": params.name,
        "description": params.description,
        "tone_tags": params.tone_tags,
        "theme_tags": params.theme_tags,
        "style_tags": params.style_tags,
        "concept_tags": params.concept_tags,
        "tone_instructions": params.tone_instructions,
        "narrator_constraints": params.narrator_constraints,
        "tone_library_id": str(params.tone_library_id) if params.tone_library_id else None,
        "merge_with_default_library": params.merge_with_default_library,
        "universe_id": str(params.universe_id) if params.universe_id else None,
        "game_system_id": str(params.game_system_id) if params.game_system_id else None,
        "is_builtin": params.is_builtin,
        "created_at": created_at,
        "updated_at": created_at,
    }

    collection = mongo_client.get_collection("gm_profiles")
    collection.insert_one(profile_doc)

    return GMProfileResponse(
        profile_id=profile_id,
        name=params.name,
        description=params.description,
        tone_tags=params.tone_tags,
        theme_tags=params.theme_tags,
        style_tags=params.style_tags,
        concept_tags=params.concept_tags,
        tone_instructions=params.tone_instructions,
        narrator_constraints=params.narrator_constraints,
        tone_library_id=params.tone_library_id,
        merge_with_default_library=params.merge_with_default_library,
        universe_id=params.universe_id,
        game_system_id=params.game_system_id,
        is_builtin=params.is_builtin,
        created_at=created_at,
        updated_at=created_at,
    )


def mongodb_get_gm_profile(profile_id: UUID) -> GMProfileResponse | None:
    """
    Retrieve a GM Profile by ID.

    Authority: All agents
    Use Case: GM tone/style/concept configuration

    Args:
        profile_id: UUID of the profile to retrieve

    Returns:
        GMProfileResponse if found, None otherwise
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("gm_profiles")

    doc = collection.find_one({"profile_id": str(profile_id)})
    if not doc:
        return None

    return _convert_gm_profile_doc(doc)


def mongodb_update_gm_profile(profile_id: UUID, params: GMProfileUpdate) -> GMProfileResponse | None:
    """
    Update a GM Profile (partial update).

    Authority: WorldArchitect, Narrator
    Use Case: GM tone/style/concept configuration

    Built-in profiles (is_builtin=True) cannot have their core fields
    (name, tone_tags) changed, but constraints and overrides can be updated.

    Args:
        profile_id: UUID of the profile to update
        params: Update parameters (all optional)

    Returns:
        Updated GMProfileResponse if found, None otherwise

    Raises:
        ValueError: If attempting to modify protected built-in profile fields
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("gm_profiles")

    # Check if profile exists and is built-in
    existing = collection.find_one({"profile_id": str(profile_id)})
    if not existing:
        return None

    update_fields = params.model_dump(exclude_unset=True)
    if not update_fields:
        return _convert_gm_profile_doc(existing)

    # Protect built-in profiles from core field changes
    if existing.get("is_builtin"):
        protected = {"name", "tone_tags"}
        attempted = set(update_fields.keys()) & protected
        if attempted:
            raise ValueError(
                f"Cannot modify {attempted} on built-in profile '{existing['name']}'. Duplicate it to customize."
            )

    # Convert UUID fields to strings for MongoDB
    if "universe_id" in update_fields:
        update_fields["universe_id"] = str(update_fields["universe_id"]) if update_fields["universe_id"] else None
    if "game_system_id" in update_fields:
        update_fields["game_system_id"] = (
            str(update_fields["game_system_id"]) if update_fields["game_system_id"] else None
        )
    if "tone_library_id" in update_fields:
        update_fields["tone_library_id"] = (
            str(update_fields["tone_library_id"]) if update_fields["tone_library_id"] else None
        )

    update_fields["updated_at"] = datetime.now(UTC)

    collection.update_one(
        {"profile_id": str(profile_id)},
        {"$set": update_fields},
    )

    updated_doc = collection.find_one({"profile_id": str(profile_id)})
    if updated_doc is None:
        raise ValueError(f"GMProfile {profile_id} not found after update")
    return _convert_gm_profile_doc(updated_doc)


def mongodb_list_gm_profiles(
    params: GMProfileFilter,
) -> GMProfileListResponse:
    """
    List GM Profiles with filtering and pagination.

    Authority: All agents
    Use Case: GM tone/style/concept configuration

    Args:
        params: Filter parameters

    Returns:
        GMProfileListResponse with matching profiles
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("gm_profiles")

    # Build filter
    query: dict[str, Any] = {}
    if params.universe_id:
        query["$or"] = [
            {"universe_id": str(params.universe_id)},
            {"universe_id": None},
        ]
    if params.game_system_id:
        if "$or" in query:
            # Already has universe scope, add system suggestion
            query["game_system_id"] = str(params.game_system_id)
        else:
            query["$or"] = [
                {"game_system_id": str(params.game_system_id)},
                {"game_system_id": None},
            ]
    if params.tone_tag:
        query["tone_tags"] = params.tone_tag
    if params.is_builtin is not None:
        query["is_builtin"] = params.is_builtin

    # Count total
    total = collection.count_documents(query)

    # Fetch with pagination
    cursor = collection.find(query).sort("created_at", -1).skip(params.offset).limit(params.limit)

    profiles = [_convert_gm_profile_doc(doc) for doc in cursor]

    return GMProfileListResponse(
        profiles=profiles,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_delete_gm_profile(profile_id: UUID) -> bool:
    """
    Delete a GM Profile.

    Built-in profiles (is_builtin=True) cannot be deleted.

    Args:
        profile_id: UUID of the profile to delete

    Returns:
        True if deleted, False if not found

    Raises:
        ValueError: If attempting to delete a built-in profile
    """
    mongo_client = get_mongodb_client()
    collection = mongo_client.get_collection("gm_profiles")

    # Check if built-in
    existing = collection.find_one({"profile_id": str(profile_id)})
    if not existing:
        return False

    if existing.get("is_builtin"):
        raise ValueError(
            f"Cannot delete built-in profile '{existing['name']}'. Set active profile to a custom one instead."
        )

    result = collection.delete_one({"profile_id": str(profile_id)})
    return result.deleted_count > 0
