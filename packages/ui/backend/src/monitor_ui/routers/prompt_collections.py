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

from typing import cast

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from monitor_data.db.postgres import PostgresClient
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
from monitor_ui.auth import Principal, get_current_user, get_postgres, require_admin, is_local_mode
from monitor_ui.ownership import require_collection_owner, require_universe_owner, resource_route_guard
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


router = APIRouter(dependencies=[Depends(resource_route_guard)])


@router.post("/prompt-collections", response_model=PromptCollectionResponse, status_code=201)
async def create_prompt_collection(
    body: PromptCollectionCreate,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PromptCollectionResponse:
    """Create a new curated prompt collection (universe-bound: owner; global: admin)."""
    if getattr(body, "universe_id", None) is not None:
        await require_universe_owner(db, principal, body.universe_id)
    else:
        await require_admin(principal)
    result = mongodb_create_prompt_collection(body)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create prompt collection")
    return result


@router.get("/prompt-collections/{collection_id}", response_model=PromptCollectionResponse)
async def get_prompt_collection(
    collection_id: UUID,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PromptCollectionResponse:
    """Get a specific prompt collection by ID (universe-bound ones require ownership)."""
    collection = await require_collection_owner(db, principal, collection_id)
    if collection is None:
        collection = mongodb_get_prompt_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Prompt collection {collection_id} not found")
    return cast("PromptCollectionResponse", collection)


@router.get("/prompt-collections", response_model=PromptCollectionListResponse)
async def list_prompt_collections(
    category: str | None = None,
    system_id: UUID | None = None,
    universe_id: UUID | None = None,
    tag: str | None = None,
    include_builtin: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PromptCollectionListResponse:
    """List prompt collections. With universe_id the caller must own it."""
    if universe_id is not None:
        await require_universe_owner(db, principal, universe_id)
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
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PromptCollectionResponse:
    """Update an existing prompt collection (owner/admin only)."""
    await require_collection_owner(db, principal, collection_id, write=True)
    try:
        return mongodb_update_prompt_collection(collection_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/prompt-collections/{collection_id}", status_code=204)
async def delete_prompt_collection(
    collection_id: UUID,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> None:
    """Delete a prompt collection (owner/admin only)."""
    await require_collection_owner(db, principal, collection_id, write=True)
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
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PromptCollectionVersionResponse:
    """Publish an immutable snapshot of the collection (owner/admin only)."""
    await require_collection_owner(db, principal, collection_id, write=True)
    try:
        return mongodb_publish_prompt_collection(collection_id, body or PromptCollectionPublish())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/prompt-collections/{collection_id}/versions",
    response_model=PromptCollectionVersionListResponse,
)
async def list_prompt_collection_versions(
    collection_id: UUID,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PromptCollectionVersionListResponse:
    """List a collection's published versions, newest first."""
    await require_collection_owner(db, principal, collection_id)
    return mongodb_list_prompt_collection_versions(collection_id)


@router.post(
    "/prompt-collections/versions/{version_id}/restore",
    response_model=PromptCollectionResponse,
)
async def restore_prompt_collection_version(
    version_id: UUID,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PromptCollectionResponse:
    """Restore a published version's content into its live collection (owner/admin only)."""
    if not is_local_mode(principal):
        from monitor_data.db.mongodb import get_mongodb_client

        snapshot = (
            get_mongodb_client().get_collection("prompt_collection_versions").find_one({"version_id": str(version_id)})
        )
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Not found")
        await require_collection_owner(db, principal, UUID(snapshot["collection_id"]), write=True)
    try:
        return mongodb_restore_prompt_collection_version(version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
