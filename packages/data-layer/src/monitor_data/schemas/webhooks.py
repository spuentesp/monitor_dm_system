"""
Pydantic schemas for auto-commit webhooks.

LAYER: 1 (data-layer)

These schemas support P1-5: CanonKeeper Auto-Commit Trigger.
After mongodb_apply_knowledge_pack() creates pending ProposedChanges,
an optional webhook can fire to trigger CanonKeeper evaluation asynchronously
instead of requiring the synchronous commit call in canonkeeper.py.

Webhooks are registered per-multiverse and stored in MongoDB so they
persist across restarts. The pipeline fires the webhook after apply;
CanonKeeper listens and processes pending proposals at its own pace.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WebhookEventType(StrEnum):
    """What event triggers this webhook."""

    PACK_APPLIED = "pack_applied"  # After proposals created from KnowledgePack apply


class WebhookDeliveryStatus(StrEnum):
    """Result of the last delivery attempt."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DISABLED = "disabled"


class CommitWebhookCreate(BaseModel):
    """Request to register an auto-commit webhook."""

    multiverse_id: UUID
    universe_id: UUID | None = Field(None, description="Optional scope to this universe")
    trigger_event: WebhookEventType = Field(default=WebhookEventType.PACK_APPLIED)
    callback_url: str = Field(max_length=500, description="URL to call when event fires")
    description: str = Field(default="", max_length=300)
    enabled: bool = Field(default=True)


class CommitWebhookResponse(BaseModel):
    """Registered webhook record."""

    webhook_id: UUID
    multiverse_id: UUID
    universe_id: UUID | None
    trigger_event: WebhookEventType
    callback_url: str
    description: str
    enabled: bool
    created_at: datetime
    last_triggered_at: datetime | None = None
    last_delivery_status: WebhookDeliveryStatus | None = None
    last_delivery_at: datetime | None = None
    consecutive_failures: int = 0

    model_config = {"from_attributes": True}


class CommitWebhookUpdate(BaseModel):
    """Fields that can be updated on an existing webhook."""

    callback_url: str | None = Field(None, max_length=500)
    description: str | None = Field(None, max_length=300)
    enabled: bool | None = None


class WebhookDeliveryLog(BaseModel):
    """Record of one webhook delivery attempt."""

    delivery_id: UUID
    webhook_id: UUID
    event_type: WebhookEventType
    payload: dict[str, Any]  # What was sent
    response_status: int | None = None
    response_body: str | None = None
    error: str | None = None
    delivered_at: datetime

    model_config = {"from_attributes": True}
