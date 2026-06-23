"""MongoDB tools for Tone Library operations.

LAYER: 1 (data-layer)
IMPORTS FROM: monitor_data.schemas.tone_libraries, monitor_data.db.mongodb
CALLED BY: ToneResolver (Layer 2), UI routers (Layer 3)

These tools provide CRUD operations for ToneLibraries, which are collections
of ToneProfiles that can be used together for tone resolution.

Authority:
- ToneResolver (Layer 2): Loads ToneLibraries to resolve tone_tags
- UI routers (Layer 3): Create/Update/Delete user-created ToneLibraries
- Seed scripts: Create built-in ToneLibraries

Collection: tone_libraries
Indexes: library_id (unique), pack_id, universe_id, is_default, priority
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.tone_libraries import (
    ToneLibraryCreate,
    ToneLibraryResponse,
    ToneLibraryUpdate,
    ToneLibraryListResponse,
)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _convert_tone_library_doc(doc: Dict[str, Any]) -> ToneLibraryResponse:
    """Convert a MongoDB document to ToneLibraryResponse."""
    return ToneLibraryResponse(
        library_id=UUID(doc["library_id"]),
        name=doc["name"],
        description=doc.get("description", ""),
        tone_profile_ids=[UUID(pid) for pid in doc.get("tone_profile_ids", [])],
        pack_id=UUID(doc["pack_id"]) if doc.get("pack_id") else None,
        universe_id=UUID(doc["universe_id"]) if doc.get("universe_id") else None,
        priority=doc.get("priority", 100),
        is_default=doc.get("is_default", False),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


# =============================================================================
# TONE LIBRARY CRUD TOOLS
# =============================================================================


def mongodb_create_tone_library(params: ToneLibraryCreate) -> ToneLibraryResponse:
    """
    Create a new Tone Library in MongoDB.

    Authority: UI routers (Layer 3) or seed scripts.

    Args:
        params: ToneLibraryCreate with library data.

    Returns:
        ToneLibraryResponse with created library data.
    """
    client = get_mongodb_client()
    library_id = uuid4()

    doc = {
        "library_id": str(library_id),
        "name": params.name,
        "description": params.description,
        "tone_profile_ids": [str(pid) for pid in params.tone_profile_ids],
        "pack_id": str(params.pack_id) if params.pack_id else None,
        "universe_id": str(params.universe_id) if params.universe_id else None,
        "priority": params.priority,
        "is_default": params.is_default,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    client["tone_libraries"].insert_one(doc)
    return _convert_tone_library_doc(doc)


def mongodb_get_tone_library(library_id: UUID) -> Optional[ToneLibraryResponse]:
    """
    Retrieve a Tone Library by ID.

    Authority: ToneResolver (Layer 2), UI routers (Layer 3).

    Args:
        library_id: ID of the ToneLibrary to retrieve.

    Returns:
        ToneLibraryResponse if found, None otherwise.
    """
    client = get_mongodb_client()
    doc = client["tone_libraries"].find_one({"library_id": str(library_id)})
    if not doc:
        return None
    return _convert_tone_library_doc(doc)


def mongodb_get_default_tone_library() -> Optional[ToneLibraryResponse]:
    """
    Retrieve the default Tone Library (fallback when no specific library is set).

    Authority: ToneResolver (Layer 2).

    Returns:
        ToneLibraryResponse if default library exists, None otherwise.

    Note:
        There should be only one default library in the system.
        If multiple exist, the one with highest priority is returned.
    """
    client = get_mongodb_client()
    try:
        doc = (
            client["tone_libraries"].find({"is_default": True}).sort("priority", -1).limit(1).next()
        )
    except StopIteration:
        doc = None
    if not doc:
        return None
    return _convert_tone_library_doc(doc)


def mongodb_list_tone_libraries(
    pack_id: Optional[UUID] = None,
    universe_id: Optional[UUID] = None,
    is_default: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> ToneLibraryListResponse:
    """
    List Tone Libraries with optional filters.

    Authority: UI routers (Layer 3), ToneResolver (Layer 2).

    Args:
        pack_id: Filter by pack_id (if provided).
        universe_id: Filter by universe_id (if provided).
        is_default: Filter by is_default flag (if provided).
        limit: Maximum number of results.
        offset: Pagination offset.

    Returns:
        ToneLibraryListResponse with matching libraries.
    """
    client = get_mongodb_client()

    query: Dict[str, Any] = {}
    if pack_id:
        query["pack_id"] = str(pack_id)
    if universe_id:
        query["universe_id"] = str(universe_id)
    if is_default is not None:
        query["is_default"] = is_default

    cursor = client["tone_libraries"].find(query).sort("priority", -1).skip(offset).limit(limit)

    libraries = [_convert_tone_library_doc(doc) for doc in cursor]
    total = client["tone_libraries"].count_documents(query)

    return ToneLibraryListResponse(
        libraries=libraries,
        total=total,
        page=offset // limit + 1,
        page_size=limit,
    )


def mongodb_update_tone_library(
    library_id: UUID, params: ToneLibraryUpdate
) -> Optional[ToneLibraryResponse]:
    """
    Update an existing Tone Library.

    Authority: UI routers (Layer 3).

    Args:
        library_id: ID of the ToneLibrary to update.
        params: ToneLibraryUpdate with fields to update.

    Returns:
        Updated ToneLibraryResponse if found, None otherwise.
    """
    client = get_mongodb_client()

    update_doc: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if params.name:
        update_doc["name"] = params.name
    if params.description is not None:
        update_doc["description"] = params.description
    if params.tone_profile_ids is not None:
        update_doc["tone_profile_ids"] = [str(pid) for pid in params.tone_profile_ids]
    if params.universe_id is not None:
        update_doc["universe_id"] = str(params.universe_id) if params.universe_id else None
    if params.priority is not None:
        update_doc["priority"] = params.priority
    if params.is_default is not None:
        update_doc["is_default"] = params.is_default

    client["tone_libraries"].update_one(
        {"library_id": str(library_id)},
        {"$set": update_doc},
    )

    updated = client["tone_libraries"].find_one({"library_id": str(library_id)})
    if not updated:
        raise ValueError(f"ToneLibrary {library_id} not found after update")

    return _convert_tone_library_doc(updated)


def mongodb_delete_tone_library(library_id: UUID) -> bool:
    """
    Delete a Tone Library.

    Authority: UI routers (Layer 3).

    Args:
        library_id: ID of the ToneLibrary to delete.

    Returns:
        True if deleted, False if not found.

    Raises:
        ValueError: If trying to delete the default library.
    """
    client = get_mongodb_client()

    # Check if library exists and is default
    existing = client["tone_libraries"].find_one({"library_id": str(library_id)})
    if not existing:
        return False

    if existing.get("is_default"):
        raise ValueError("Cannot delete default ToneLibrary")

    result = client["tone_libraries"].delete_one({"library_id": str(library_id)})
    return result.deleted_count > 0
