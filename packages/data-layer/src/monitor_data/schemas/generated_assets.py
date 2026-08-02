"""
Pydantic schemas for GeneratedAsset (Layer 1, Task 1).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, decimal) and base schemas
CALLED BY: mongodb_tools/generated_assets.py (Task 2) and the UI backend.

A ``GeneratedAsset`` records that an image was generated: the MinIO object
key, the prompt that produced it, the provider/model used, and durable
provenance links (visual identity version, canon fact IDs, source
messages, reference asset IDs).

A ``GeneratedAsset`` is NOT a Neo4j node. Approval makes it visible and
eligible as a reference; it does not write to the canonical graph. Only
CanonKeeper commits canonical visual identity changes to Neo4j.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class AssetType(StrEnum):
    """Kind of image asset."""

    PORTRAIT = "portrait"
    SCENE = "scene"
    LOCATION = "location"
    OBJECT = "object"


class ApprovalStatus(StrEnum):
    """Human/operator approval state of an asset."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReferenceStatus(StrEnum):
    """Whether/how an approved asset is used as a prompt reference."""

    NONE = "none"
    PRIMARY = "primary"
    SUPPORTING = "supporting"


class ModerationStatus(StrEnum):
    """Outcome reported by the provider's moderation surface."""

    PROVIDER_DEFAULT = "provider_default"
    ALLOWED = "allowed"
    BLOCKED = "blocked"


class TriggerSource(StrEnum):
    """What triggered the generation."""

    USER = "user"  # Direct user request from the UI
    LOOP_SUGGESTION = "loop_suggestion"  # A scene-loop suggestion accepted by the user


# =============================================================================
# GENERATED ASSET SCHEMAS
# =============================================================================


class GeneratedAssetCreate(BaseModel):
    """Request to persist a newly generated asset."""

    asset_type: AssetType = Field(description="Kind of image (portrait, scene, ...)")
    minio_key: str = Field(
        min_length=1,
        max_length=500,
        description="Stable MinIO object key; never an expiring presigned URL",
    )
    content_type: str = Field(default="image/png", max_length=100)
    byte_size: int = Field(ge=1, description="Stored object size in bytes; must be > 0")
    character_id: str | None = Field(default=None, max_length=200)
    entity_id: UUID | None = None
    universe_id: UUID | None = None
    story_id: UUID | None = None
    scene_id: UUID | None = None
    conversation_id: UUID | None = None
    source_message_ids: list[str] = Field(default_factory=list)
    visual_identity_id: UUID | None = None
    visual_identity_version: int | None = Field(default=None, ge=1)
    canon_fact_ids: list[UUID] = Field(default_factory=list)
    prompt: str = Field(min_length=1, description="Final prompt sent to the provider")
    negative_prompt: str | None = Field(default=None, max_length=2000)
    prompt_warnings: list[str] = Field(default_factory=list)
    reference_asset_ids: list[UUID] = Field(default_factory=list)
    provider_id: str = Field(min_length=1, max_length=100)
    provider_model: str = Field(min_length=1, max_length=200)
    provider_capabilities: dict[str, Any] = Field(default_factory=dict)
    trigger: TriggerSource = TriggerSource.USER
    moderation_status: ModerationStatus = ModerationStatus.PROVIDER_DEFAULT
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    reference_status: ReferenceStatus = ReferenceStatus.NONE
    estimated_cost_usd: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        description="Provider-reported USD cost when available; never fabricated",
    )


class GeneratedAssetUpdate(BaseModel):
    """Mutable fields on a GeneratedAsset (review/approval/lifecycle)."""

    approval_status: ApprovalStatus | None = None
    reference_status: ReferenceStatus | None = None
    approved_by: str | None = Field(default=None, max_length=200)
    approved_at: datetime | None = None
    moderation_status: ModerationStatus | None = None
    prompt_warnings: list[str] | None = None
    estimated_cost_usd: Decimal | None = Field(default=None, ge=Decimal("0"))


class GeneratedAsset(BaseModel):
    """Persisted generated-asset record (response shape)."""

    asset_id: UUID = Field(default_factory=uuid4)
    asset_type: AssetType
    minio_key: str = Field(min_length=1, max_length=500)
    content_type: str = "image/png"
    byte_size: int = Field(ge=1)
    character_id: str | None = None
    entity_id: UUID | None = None
    universe_id: UUID | None = None
    story_id: UUID | None = None
    scene_id: UUID | None = None
    conversation_id: UUID | None = None
    source_message_ids: list[str] = Field(default_factory=list)
    visual_identity_id: UUID | None = None
    visual_identity_version: int | None = Field(default=None, ge=1)
    canon_fact_ids: list[UUID] = Field(default_factory=list)
    prompt: str = Field(min_length=1)
    negative_prompt: str | None = None
    prompt_warnings: list[str] = Field(default_factory=list)
    reference_asset_ids: list[UUID] = Field(default_factory=list)
    provider_id: str
    provider_model: str
    provider_capabilities: dict[str, Any] = Field(default_factory=dict)
    trigger: TriggerSource = TriggerSource.USER
    moderation_status: ModerationStatus = ModerationStatus.PROVIDER_DEFAULT
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    reference_status: ReferenceStatus = ReferenceStatus.NONE
    approved_by: str | None = None
    approved_at: datetime | None = None
    estimated_cost_usd: Decimal | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GeneratedAssetFilter(BaseModel):
    """Filter for listing generated assets."""

    character_id: str | None = None
    entity_id: UUID | None = None
    universe_id: UUID | None = None
    story_id: UUID | None = None
    scene_id: UUID | None = None
    conversation_id: UUID | None = None
    asset_type: AssetType | None = None
    approval_status: ApprovalStatus | None = None
    reference_status: ReferenceStatus | None = None
    trigger: TriggerSource | None = None
    include_rejected: bool = Field(
        default=False,
        description="Include rejected assets when no explicit approval_status filter is given",
    )
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
