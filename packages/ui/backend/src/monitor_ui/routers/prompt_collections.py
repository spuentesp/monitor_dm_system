"""
Prompt Collections router — CRUD for curated Session Zero / character-creation
prompt sets.

A PromptCollection is an authorable set of interview questions (and optional
answer options) that drives story onboarding. This router exposes the full
lifecycle to the Forge "Prompts" authoring UI. Backed by MongoDB.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from monitor_data.schemas.prompt_collections import (
    PromptCollectionCreate,
    PromptCollectionFilter,
    PromptCollectionListResponse,
    PromptCollectionPublish,
    PromptCollectionResponse,
    PromptCollectionUpdate,
    PromptCollectionVersionListResponse,
    PromptCollectionVersionResponse,
)
from monitor_data.tools.mongodb_tools.prompt_collections import (
    mongodb_create_prompt_collection,
    mongodb_delete_prompt_collection,
    mongodb_get_prompt_collection,
    mongodb_list_prompt_collection_versions,
    mongodb_list_prompt_collections,
    mongodb_publish_prompt_collection,
    mongodb_restore_prompt_collection_version,
    mongodb_update_prompt_collection,
)

router = APIRouter()


@router.post("/prompt-collections", response_model=PromptCollectionResponse, status_code=201)
async def create_prompt_collection(body: PromptCollectionCreate) -> PromptCollectionResponse:
    """Create a new curated prompt collection."""
    result = mongodb_create_prompt_collection(body)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create prompt collection")
    return result


@router.get("/prompt-collections/{collection_id}", response_model=PromptCollectionResponse)
async def get_prompt_collection(collection_id: UUID) -> PromptCollectionResponse:
    """Get a specific prompt collection by ID."""
    result = mongodb_get_prompt_collection(collection_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Prompt collection {collection_id} not found")
    return result


@router.get("/prompt-collections", response_model=PromptCollectionListResponse)
async def list_prompt_collections(
    category: str | None = None,
    system_id: UUID | None = None,
    universe_id: UUID | None = None,
    tag: str | None = None,
    include_builtin: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PromptCollectionListResponse:
    """List prompt collections with optional filtering."""
    filters = PromptCollectionFilter(
        category=category,
        system_id=system_id,
        universe_id=universe_id,
        tag=tag,
        include_builtin=include_builtin,
        limit=limit,
        offset=offset,
    )
    return mongodb_list_prompt_collections(filters)


@router.patch("/prompt-collections/{collection_id}", response_model=PromptCollectionResponse)
async def update_prompt_collection(
    collection_id: UUID,
    body: PromptCollectionUpdate,
) -> PromptCollectionResponse:
    """Update an existing prompt collection."""
    try:
        return mongodb_update_prompt_collection(collection_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/prompt-collections/{collection_id}", status_code=204)
async def delete_prompt_collection(collection_id: UUID) -> None:
    """Delete a prompt collection."""
    deleted = mongodb_delete_prompt_collection(collection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Prompt collection {collection_id} not found")


# ---------------------------------------------------------------------------
# Versioning (immutable published snapshots)
# ---------------------------------------------------------------------------


@router.post(
    "/prompt-collections/{collection_id}/publish",
    response_model=PromptCollectionVersionResponse,
    status_code=201,
)
async def publish_prompt_collection(
    collection_id: UUID,
    body: PromptCollectionPublish | None = None,
) -> PromptCollectionVersionResponse:
    """Publish an immutable snapshot of the collection (auto-versioned)."""
    try:
        return mongodb_publish_prompt_collection(collection_id, body or PromptCollectionPublish())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/prompt-collections/{collection_id}/versions",
    response_model=PromptCollectionVersionListResponse,
)
async def list_prompt_collection_versions(collection_id: UUID) -> PromptCollectionVersionListResponse:
    """List a collection's published versions, newest first."""
    return mongodb_list_prompt_collection_versions(collection_id)


@router.post(
    "/prompt-collections/versions/{version_id}/restore",
    response_model=PromptCollectionResponse,
)
async def restore_prompt_collection_version(version_id: UUID) -> PromptCollectionResponse:
    """Restore a published version's content into its live collection."""
    try:
        return mongodb_restore_prompt_collection_version(version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
