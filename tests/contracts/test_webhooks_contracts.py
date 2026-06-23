"""
Contract tests for Webhook schemas.

Covers:
- WebhookEventType enum
- WebhookDeliveryStatus enum
- CommitWebhookCreate: register webhook
- CommitWebhookResponse: webhook record
- CommitWebhookUpdate: update
- WebhookDeliveryLog: delivery attempt log

Use Cases: DL-21 (Commit webhooks for auto-commit pipelines)
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from typing import Any, Dict

import pytest

from monitor_data.schemas.webhooks import (
    WebhookEventType,
    WebhookDeliveryStatus,
    CommitWebhookCreate,
    CommitWebhookResponse,
    CommitWebhookUpdate,
    WebhookDeliveryLog,
)


# =============================================================================
# Enums
# =============================================================================


class TestWebhookEventTypeEnum:
    def test_pack_applied(self):
        assert WebhookEventType.PACK_APPLIED.value == "pack_applied"


class TestWebhookDeliveryStatusEnum:
    def test_all_values(self):
        assert WebhookDeliveryStatus.PENDING.value == "pending"
        assert WebhookDeliveryStatus.DELIVERED.value == "delivered"
        assert WebhookDeliveryStatus.FAILED.value == "failed"
        assert WebhookDeliveryStatus.DISABLED.value == "disabled"


# =============================================================================
# CommitWebhookCreate
# =============================================================================


class TestCommitWebhookCreate:
    def test_minimal(self):
        w = CommitWebhookCreate(
            multiverse_id=uuid4(),
            callback_url="https://example.com/hook",
        )
        assert w.multiverse_id
        assert w.callback_url == "https://example.com/hook"
        assert w.trigger_event == WebhookEventType.PACK_APPLIED  # default
        assert w.enabled is True  # default
        assert w.description == ""  # default
        assert w.universe_id is None  # default

    def test_with_universe_scope(self):
        w = CommitWebhookCreate(
            multiverse_id=uuid4(),
            universe_id=uuid4(),
            callback_url="https://example.com/hook",
            description="Auto-commit on pack apply",
            enabled=False,
        )
        assert w.universe_id is not None
        assert w.enabled is False

    def test_callback_url_required(self):
        with pytest.raises(Exception):
            CommitWebhookCreate(multiverse_id=uuid4())


# =============================================================================
# CommitWebhookResponse
# =============================================================================


class TestCommitWebhookResponse:
    def test_minimal(self):
        w = CommitWebhookResponse(
            webhook_id=uuid4(),
            multiverse_id=uuid4(),
            universe_id=None,
            trigger_event=WebhookEventType.PACK_APPLIED,
            callback_url="https://example.com",
            description="",
            enabled=True,
            created_at=datetime.now(),
        )
        assert w.consecutive_failures == 0  # default
        assert w.last_triggered_at is None
        assert w.last_delivery_status is None


# =============================================================================
# CommitWebhookUpdate
# =============================================================================


class TestCommitWebhookUpdate:
    def test_empty(self):
        u = CommitWebhookUpdate()
        assert u.callback_url is None
        assert u.enabled is None
        assert u.description is None

    def test_disable(self):
        u = CommitWebhookUpdate(enabled=False)
        assert u.enabled is False

    def test_update_callback(self):
        u = CommitWebhookUpdate(
            callback_url="https://new-url.com/hook",
            description="Updated",
        )
        assert "new-url" in u.callback_url


# =============================================================================
# WebhookDeliveryLog
# =============================================================================


class TestWebhookDeliveryLog:
    def test_successful_delivery(self):
        log = WebhookDeliveryLog(
            delivery_id=uuid4(),
            webhook_id=uuid4(),
            event_type=WebhookEventType.PACK_APPLIED,
            payload={"pack_id": str(uuid4())},
            response_status=200,
            response_body="OK",
            delivered_at=datetime.now(),
        )
        assert log.response_status == 200
        assert log.error is None

    def test_failed_delivery(self):
        log = WebhookDeliveryLog(
            delivery_id=uuid4(),
            webhook_id=uuid4(),
            event_type=WebhookEventType.PACK_APPLIED,
            payload={},
            response_status=500,
            response_body="Internal Server Error",
            error="Connection refused",
            delivered_at=datetime.now(),
        )
        assert log.error == "Connection refused"
        assert log.response_status == 500
