"""
Tone router — CRUD for ToneProfiles, ToneLibraries, and TagDefinitions.

Provides a UI-accessible API for managing the narrative tone system.
All operations delegate to the existing MongoDB tools in monitor_data.

LAYER: 3 (UI)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query
from monitor_data.schemas.tag_registry import (
    TagCategory,
    TagDefinitionCreate,
    TagDefinitionListResponse,
    TagDefinitionResponse,
    TagDefinitionUpdate,
    TagSuggestionRequest,
    TagSuggestionResponse,
)
from monitor_data.schemas.tone_libraries import (
    ToneLibraryCreate,
    ToneLibraryListResponse,
    ToneLibraryResponse,
    ToneLibraryUpdate,
)
from monitor_data.schemas.tone_profiles import (
    ToneProfileCreate,
    ToneProfileListResponse,
    ToneProfileResponse,
    ToneProfileUpdate,
)
from monitor_data.tools.mongodb_tools.tag_registry import (
    mongodb_create_tag_definition,
    mongodb_delete_tag_definition,
    mongodb_get_tag_definition,
    mongodb_list_tag_definitions,
    mongodb_suggest_tags,
    mongodb_update_tag_definition,
)
from monitor_data.tools.mongodb_tools.tone_libraries import (
    mongodb_create_tone_library,
    mongodb_delete_tone_library,
    mongodb_get_default_tone_library,
    mongodb_get_tone_library,
    mongodb_list_tone_libraries,
    mongodb_update_tone_library,
)
from monitor_data.tools.mongodb_tools.tone_profiles import (
    mongodb_create_tone_profile,
    mongodb_delete_tone_profile,
    mongodb_get_tone_profile,
    mongodb_list_tone_profiles,
    mongodb_update_tone_profile,
)

router = APIRouter()


# =============================================================================
# TONE PROFILES
# =============================================================================


@router.get("/profiles", response_model=ToneProfileListResponse)
def list_tone_profiles(
    pack_id: UUID | None = None,
    category: str | None = None,
    language: str | None = None,
    is_builtin: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> ToneProfileListResponse:
    """List Tone Profiles with optional filters and pagination."""
    offset = (page - 1) * page_size
    return mongodb_list_tone_profiles(
        pack_id=pack_id,
        category=category,
        language=language,
        is_builtin=is_builtin,
        limit=page_size,
        offset=offset,
    )


@router.get("/profiles/builtin", response_model=ToneProfileListResponse)
def list_builtin_tone_profiles(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> ToneProfileListResponse:
    """List only built-in Tone Profiles (for tone picker UI)."""
    return mongodb_list_tone_profiles(
        is_builtin=True,
        limit=page_size,
        offset=(page - 1) * page_size,
    )


@router.get("/profiles/{profile_id}", response_model=ToneProfileResponse)
def get_tone_profile(
    profile_id: UUID = Path(description="ID of the ToneProfile to retrieve"),
) -> ToneProfileResponse:
    """Retrieve a single Tone Profile by ID."""
    result = mongodb_get_tone_profile(profile_id)
    if not result:
        raise HTTPException(status_code=404, detail="ToneProfile not found")
    return result


@router.post("/profiles", response_model=ToneProfileResponse, status_code=201)
def create_tone_profile(body: ToneProfileCreate) -> ToneProfileResponse:
    """Create a new Tone Profile."""
    return mongodb_create_tone_profile(body)


@router.put("/profiles/{profile_id}", response_model=ToneProfileResponse)
def update_tone_profile(
    profile_id: UUID = Path(description="ID of the ToneProfile to update"),
    body: ToneProfileUpdate = ...,  # type: ignore[assignment]
) -> ToneProfileResponse:
    """Update an existing Tone Profile."""
    try:
        result = mongodb_update_tone_profile(profile_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="ToneProfile not found")
    return result


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_tone_profile(
    profile_id: UUID = Path(description="ID of the ToneProfile to delete"),
) -> None:
    """Delete a Tone Profile. Built-in profiles cannot be deleted."""
    try:
        deleted = mongodb_delete_tone_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="ToneProfile not found")


# =============================================================================
# TONE LIBRARIES
# =============================================================================


@router.get("/libraries", response_model=ToneLibraryListResponse)
def list_tone_libraries(
    pack_id: UUID | None = None,
    universe_id: UUID | None = None,
    is_default: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> ToneLibraryListResponse:
    """List Tone Libraries with optional filters and pagination."""
    offset = (page - 1) * page_size
    return mongodb_list_tone_libraries(
        pack_id=pack_id,
        universe_id=universe_id,
        is_default=is_default,
        limit=page_size,
        offset=offset,
    )


@router.get("/libraries/default", response_model=ToneLibraryResponse)
def get_default_tone_library() -> ToneLibraryResponse:
    """Retrieve the default Tone Library (fallback when no specific library is set)."""
    result = mongodb_get_default_tone_library()
    if not result:
        raise HTTPException(status_code=404, detail="No default ToneLibrary found")
    return result


@router.get("/libraries/{library_id}", response_model=ToneLibraryResponse)
def get_tone_library(
    library_id: UUID = Path(description="ID of the ToneLibrary to retrieve"),
) -> ToneLibraryResponse:
    """Retrieve a single Tone Library by ID."""
    result = mongodb_get_tone_library(library_id)
    if not result:
        raise HTTPException(status_code=404, detail="ToneLibrary not found")
    return result


@router.post("/libraries", response_model=ToneLibraryResponse, status_code=201)
def create_tone_library(body: ToneLibraryCreate) -> ToneLibraryResponse:
    """Create a new Tone Library."""
    return mongodb_create_tone_library(body)


@router.put("/libraries/{library_id}", response_model=ToneLibraryResponse)
def update_tone_library(
    library_id: UUID = Path(description="ID of the ToneLibrary to update"),
    body: ToneLibraryUpdate = ...,  # type: ignore[assignment]
) -> ToneLibraryResponse:
    """Update an existing Tone Library."""
    try:
        result = mongodb_update_tone_library(library_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="ToneLibrary not found")
    return result


@router.delete("/libraries/{library_id}", status_code=204)
def delete_tone_library(
    library_id: UUID = Path(description="ID of the ToneLibrary to delete"),
) -> None:
    """Delete a Tone Library. The default library cannot be deleted."""
    try:
        deleted = mongodb_delete_tone_library(library_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="ToneLibrary not found")


# =============================================================================
# TAG DEFINITIONS
# =============================================================================


@router.get("/tags", response_model=TagDefinitionListResponse)
def list_tag_definitions(
    category: TagCategory | None = None,
    pack_id: UUID | None = None,
    is_builtin: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> TagDefinitionListResponse:
    """List Tag Definitions with optional filters and pagination."""
    offset = (page - 1) * page_size
    return mongodb_list_tag_definitions(
        category=category,
        pack_id=pack_id,
        is_builtin=is_builtin,
        limit=page_size,
        offset=offset,
    )


@router.get("/tags/suggest", response_model=TagSuggestionResponse)
def suggest_tags(
    partial: str = Query(..., min_length=1, max_length=50, description="Partial tag to search for"),
    category: TagCategory | None = None,
    limit: int = Query(10, ge=1, le=50),
) -> TagSuggestionResponse:
    """Get tag suggestions for autocomplete (prefix match)."""
    request = TagSuggestionRequest(partial=partial, category=category, limit=limit)
    return mongodb_suggest_tags(request)


@router.get("/tags/{tag}", response_model=TagDefinitionResponse)
def get_tag_definition(
    tag: str = Path(description="Tag name to retrieve (case-insensitive)"),
) -> TagDefinitionResponse:
    """Retrieve a single Tag Definition by name."""
    result = mongodb_get_tag_definition(tag)
    if not result:
        raise HTTPException(status_code=404, detail="TagDefinition not found")
    return result


@router.post("/tags", response_model=TagDefinitionResponse, status_code=201)
def create_tag_definition(body: TagDefinitionCreate) -> TagDefinitionResponse:
    """Create a new Tag Definition."""
    return mongodb_create_tag_definition(body)


@router.put("/tags/{tag}", response_model=TagDefinitionResponse)
def update_tag_definition(
    tag: str = Path(description="Tag name to update (case-insensitive)"),
    body: TagDefinitionUpdate = ...,  # type: ignore[assignment]
) -> TagDefinitionResponse:
    """Update an existing Tag Definition. Built-in tags can only update synonyms/description."""
    result = mongodb_update_tag_definition(tag, body)
    if not result:
        raise HTTPException(status_code=404, detail="TagDefinition not found")
    return result


@router.delete("/tags/{tag}", status_code=204)
def delete_tag_definition(
    tag: str = Path(description="Tag name to delete (case-insensitive)"),
) -> None:
    """Delete a Tag Definition. Built-in tags cannot be deleted."""
    try:
        deleted = mongodb_delete_tag_definition(tag)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="TagDefinition not found")
