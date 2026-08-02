"""
Image asset gallery + approval router (Task 6).

Thin validation/serialization layer over the Task 2 data-layer MongoDB tools
(``monitor_data.tools.mongodb_tools.generated_assets`` /
``visual_identities``). All business rules — default gallery exclusion of
rejected assets, single-primary-per-scope demotion (never deleting the
previous primary), reference eligibility, and visual-identity optimistic
locking — live in those tools; this router only maps HTTP shapes and error
classes (404 unknown, 400 invalid, 409 version conflict).

Mounted under the existing ``/api/image`` prefix alongside ``image_gen.py``.
The generation router persists every asset as PENDING (the Task 5
``auto_approve_legacy`` flag was removed in Task 8); these endpoints own the
approval workflow, including the only avatar-mutation path
(``use_as_avatar``).
"""

from __future__ import annotations

import os
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from monitor_data.db.minio import get_minio_client
from monitor_data.schemas.generated_assets import (
    ApprovalStatus,
    AssetType,
    GeneratedAsset,
    GeneratedAssetFilter,
    ReferenceStatus,
    TriggerSource,
)
from monitor_data.schemas.base import ProposalType
from monitor_data.schemas.image_settings import ImageGenerationSettings
from monitor_data.schemas.proposed_changes import ProposedChangeCreate
from monitor_data.schemas.visual_identity import (
    VisualIdentity,
    VisualIdentityFilter,
    VisualIdentityStatus,
    VisualIdentityUpdate,
)
from monitor_data.tools.mongodb_tools.generated_assets import (
    mongodb_approve_generated_asset,
    mongodb_get_generated_asset,
    mongodb_list_generated_assets,
    mongodb_reject_generated_asset,
)
from monitor_data.tools.mongodb_tools.image_settings import (
    mongodb_get_image_generation_settings,
    mongodb_update_image_generation_settings,
)
from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change
from monitor_data.tools.mongodb_tools.visual_identities import (
    VisualIdentityConflictError,
    VisualIdentityNotFoundError,
    mongodb_get_visual_identity,
    mongodb_list_visual_identities,
    mongodb_upsert_visual_identity,
)
from pydantic import BaseModel

from .character_storage import get_character, set_character_avatar

log = structlog.get_logger()

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AssetApprovalRequest(BaseModel):
    approved_by: str = "local"
    use_as_avatar: bool = False
    reference_status: ReferenceStatus = ReferenceStatus.NONE


class AssetRejectRequest(BaseModel):
    rejected_by: str = "local"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_asset_or_404(asset_id: UUID) -> GeneratedAsset:
    asset = mongodb_get_generated_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Generated asset not found")
    return asset


def _require_settings_admin(
    x_monitor_admin_key: str | None = Header(default=None, alias="X-Monitor-Admin-Key"),
) -> None:
    """Gate image-settings writes behind an admin key.

    The brief marks these settings as admin/auth-scoped: the data-layer
    tool ``mongodb_update_image_generation_settings`` is listed in the
    authority matrix under ``["ImageRouter", "CanonKeeper"]``, but the
    router was calling the tool directly and so bypassing the matrix.
    This dependency closes the gap: when ``IMAGE_SETTINGS_ADMIN_KEY`` is
    set in the environment, the caller must present the same value in the
    ``X-Monitor-Admin-Key`` header.

    When the env var is unset, the deployment hasn't opted into the
    policy yet — we still log a warning so operators can see the gap in
    the logs, but we keep the endpoint reachable for local development.
    """
    expected = os.environ.get("IMAGE_SETTINGS_ADMIN_KEY", "")
    if not expected:
        log.warning("image_assets.settings_admin_key_unset")
        return
    if not x_monitor_admin_key or x_monitor_admin_key != expected:
        raise HTTPException(
            status_code=401,
            detail="Admin key required to modify image-generation settings.",
        )


# ---------------------------------------------------------------------------
# Asset gallery
# ---------------------------------------------------------------------------


@router.get("/assets", response_model=list[GeneratedAsset])
def list_assets(
    character_id: str | None = None,
    entity_id: UUID | None = None,
    universe_id: UUID | None = None,
    story_id: UUID | None = None,
    scene_id: UUID | None = None,
    conversation_id: UUID | None = None,
    asset_type: AssetType | None = None,
    approval_status: ApprovalStatus | None = None,
    reference_status: ReferenceStatus | None = None,
    trigger: TriggerSource | None = None,
    include_rejected: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[GeneratedAsset]:
    """List generated assets, newest first. Rejected assets are hidden unless
    ``approval_status`` is explicit or ``include_rejected=true``."""
    return mongodb_list_generated_assets(
        GeneratedAssetFilter(
            character_id=character_id,
            entity_id=entity_id,
            universe_id=universe_id,
            story_id=story_id,
            scene_id=scene_id,
            conversation_id=conversation_id,
            asset_type=asset_type,
            approval_status=approval_status,
            reference_status=reference_status,
            trigger=trigger,
            include_rejected=include_rejected,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/assets/{asset_id}", response_model=GeneratedAsset)
def get_asset(asset_id: UUID) -> GeneratedAsset:
    """Fetch a single generated asset's metadata."""
    return _get_asset_or_404(asset_id)


@router.get("/assets/{asset_id}/file")
async def asset_file(asset_id: UUID) -> RedirectResponse:
    """Redirect to a fresh presigned URL for the asset's MinIO object."""
    asset = _get_asset_or_404(asset_id)
    url = await get_minio_client().presigned_url(asset.minio_key, expires_in=3600)
    return RedirectResponse(url)


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------


@router.post("/assets/{asset_id}/approve", response_model=GeneratedAsset)
def approve_asset(asset_id: UUID, body: AssetApprovalRequest | None = None) -> GeneratedAsset:
    """Approve an asset, optionally as a reference and/or character avatar.

    ``reference_status=primary`` demotes any previous primary in the same
    scope to supporting (handled by the data-layer tool; never deletes).
    ``use_as_avatar=true`` requires a portrait anchored to an existing
    character and updates only that character's avatar.
    """
    body = body or AssetApprovalRequest()
    asset = _get_asset_or_404(asset_id)

    avatar_character_id: str | None = None
    if body.use_as_avatar:
        if asset.asset_type != AssetType.PORTRAIT or not asset.character_id:
            raise HTTPException(
                status_code=400,
                detail="use_as_avatar requires a portrait asset anchored to a character",
            )
        if get_character(asset.character_id) is None:
            raise HTTPException(status_code=404, detail="Character not found")
        avatar_character_id = asset.character_id

    try:
        approved = mongodb_approve_generated_asset(
            asset_id,
            approved_by=body.approved_by,
            reference_status=body.reference_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if avatar_character_id is not None:
        set_character_avatar(avatar_character_id, asset.minio_key)
        log.info(
            "image_assets.avatar_updated",
            character_id=avatar_character_id,
            asset_id=str(asset_id),
        )
    return approved


@router.post("/assets/{asset_id}/reject", response_model=GeneratedAsset)
def reject_asset(asset_id: UUID, body: AssetRejectRequest | None = None) -> GeneratedAsset:
    """Reject an asset: clears any reference role and hides it from galleries."""
    body = body or AssetRejectRequest()
    _get_asset_or_404(asset_id)
    try:
        rejected = mongodb_reject_generated_asset(asset_id, rejected_by=body.rejected_by)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    log.info("image_assets.asset_rejected", asset_id=str(asset_id), rejected_by=body.rejected_by)
    return rejected


# ---------------------------------------------------------------------------
# Visual identities
# ---------------------------------------------------------------------------


@router.get("/visual-identities", response_model=list[VisualIdentity])
def list_visual_identities(
    character_id: str | None = None,
    entity_id: UUID | None = None,
    universe_id: UUID | None = None,
    status: VisualIdentityStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[VisualIdentity]:
    """List visual identities, newest first; ``status`` omitted lists all."""
    return mongodb_list_visual_identities(
        VisualIdentityFilter(
            character_id=character_id,
            entity_id=entity_id,
            universe_id=universe_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/visual-identities/current", response_model=VisualIdentity)
def get_current_visual_identity(
    character_id: str | None = None,
    entity_id: UUID | None = None,
    universe_id: UUID | None = None,
    status: str = "approved",
    card_default_only: bool = False,
) -> VisualIdentity:
    """Fetch the current visual identity for a character/entity/universe anchor."""
    try:
        identity = mongodb_get_visual_identity(
            character_id=character_id,
            entity_id=entity_id,
            universe_id=universe_id,
            status=status,
            card_default_only=card_default_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if identity is None:
        raise HTTPException(status_code=404, detail="No visual identity found for this anchor")
    return identity


@router.put("/visual-identities/current", response_model=VisualIdentity)
def update_current_visual_identity(body: VisualIdentityUpdate) -> VisualIdentity:
    """Replace an identity version with optimistic locking.

    ``identity_id`` + ``expected_version`` identify the version being
    replaced; a stale writer gets HTTP 409.

    When the edited identity has a canonical entity target (``entity_id``
    present — canonical or entity-anchored incarnation), a pending
    ``ProposedChange(change_type="entity", proposer="UI")`` is staged so
    CanonKeeper can canonize it onto the Neo4j entity. Card-default and
    entity-less incarnation identities have no canon target and stage no
    proposal. The router never touches Neo4j.
    """
    try:
        identity = mongodb_upsert_visual_identity(body)
    except VisualIdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except VisualIdentityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if identity.entity_id is not None:
        _stage_visual_identity_proposal(identity)
    return identity


def _stage_visual_identity_proposal(identity: VisualIdentity) -> None:
    """Stage a pending ProposedChange for a canon-anchored identity edit."""
    proposal = mongodb_create_proposed_change(
        ProposedChangeCreate(
            change_type=ProposalType.ENTITY,
            proposer="UI",
            content={
                "entity_id": str(identity.entity_id),
                "universe_id": str(identity.universe_id),
                "operation": "set_visual_identity",
                "visual_identity": identity.model_dump(mode="json"),
                "visual_identity_version": identity.version,
            },
        )
    )
    log.info(
        "image_assets.visual_identity_proposal_staged",
        proposal_id=str(proposal.proposal_id),
        identity_id=str(identity.identity_id),
        version=identity.version,
        entity_id=str(identity.entity_id),
    )


# ---------------------------------------------------------------------------
# Image-generation settings (Task 10)
# ---------------------------------------------------------------------------
#
# Settings live in a MongoDB singleton (``_id="global"``) merged over the
# ``monitor_data.config`` env defaults. The endpoints are thin pass-throughs
# to the data-layer tools; Pydantic bounds (``Field(ge=0, le=100)`` etc.)
# are enforced at the schema level so out-of-range payloads surface as 422
# before the document is written. Auth authority for the underlying tools
# matches the other image settings (``mongodb_update_image_generation_settings``
# is reserved for ImageRouter / CanonKeeper agents; reading is open).


@router.get("/settings", response_model=ImageGenerationSettings)
def get_image_generation_settings() -> ImageGenerationSettings:
    """Return the merged image-generation settings.

    Per the brief, this is a global UI configuration surface (auth-scoped
    settings management follows the existing pattern for other tunables).
    """
    return mongodb_get_image_generation_settings()


@router.put("/settings", response_model=ImageGenerationSettings)
def update_image_generation_settings(
    body: ImageGenerationSettings,
    _admin: None = Depends(_require_settings_admin),
) -> ImageGenerationSettings:
    """Merge ``body`` over the singleton and return the new merged view.

    The PUT body is the full :class:`ImageGenerationSettings` model — every
    field is validated against the schema's bounds before the write. The
    data-layer tool applies ``exclude_unset=True`` semantics so a partial
    payload only writes the fields the caller explicitly set.

    Auth: when ``IMAGE_SETTINGS_ADMIN_KEY`` is set in the environment, the
    caller must present the same value in the ``X-Monitor-Admin-Key``
    header. Reads (the matching ``GET`` above) remain open per the brief.
    """
    return mongodb_update_image_generation_settings(body)
