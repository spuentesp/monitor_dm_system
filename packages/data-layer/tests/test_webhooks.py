"""
Tests for webhook schemas and webhook_tools.

P1-5: CanonKeeper Auto-Commit Trigger
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from monitor_data.schemas.webhooks import (
    WebhookEventType,
    WebhookDeliveryStatus,
    CommitWebhookCreate,
    CommitWebhookUpdate,
    CommitWebhookResponse,
    WebhookDeliveryLog,
)


class TestWebhookEventType:
    def test_pack_applied_value(self):
        assert WebhookEventType.PACK_APPLIED.value == "pack_applied"

    def test_is_string_enum(self):
        assert isinstance(WebhookEventType.PACK_APPLIED, str)


class TestWebhookDeliveryStatus:
    def test_all_status_values(self):
        assert WebhookDeliveryStatus.PENDING.value == "pending"
        assert WebhookDeliveryStatus.DELIVERED.value == "delivered"
        assert WebhookDeliveryStatus.FAILED.value == "failed"
        assert WebhookDeliveryStatus.DISABLED.value == "disabled"

    def test_is_string_enum(self):
        assert isinstance(WebhookDeliveryStatus.DELIVERED, str)


class TestCommitWebhookCreate:
    def test_required_fields(self):
        multiverse_id = uuid4()
        params = CommitWebhookCreate(
            multiverse_id=multiverse_id,
            callback_url="https://example.com/webhook",
        )
        assert params.multiverse_id == multiverse_id
        assert params.callback_url == "https://example.com/webhook"
        assert params.universe_id is None
        assert params.trigger_event == WebhookEventType.PACK_APPLIED
        assert params.enabled is True

    def test_all_fields(self):
        multiverse_id = uuid4()
        universe_id = uuid4()
        params = CommitWebhookCreate(
            multiverse_id=multiverse_id,
            universe_id=universe_id,
            trigger_event=WebhookEventType.PACK_APPLIED,
            callback_url="https://example.com/callback",
            description="Test webhook",
            enabled=False,
        )
        assert params.multiverse_id == multiverse_id
        assert params.universe_id == universe_id
        assert params.trigger_event == WebhookEventType.PACK_APPLIED
        assert params.callback_url == "https://example.com/callback"
        assert params.description == "Test webhook"
        assert params.enabled is False

    def test_url_max_length_enforced(self):
        """URL exceeding 500 chars raises ValidationError."""
        from pydantic import ValidationError

        multiverse_id = uuid4()
        long_url = "https://example.com/" + "a" * 500
        with pytest.raises(ValidationError) as exc_info:
            CommitWebhookCreate(multiverse_id=multiverse_id, callback_url=long_url)
        assert "string_too_long" in str(exc_info.value)


class TestCommitWebhookUpdate:
    def test_partial_update_callback_url(self):
        params = CommitWebhookUpdate(callback_url="https://new.example.com")
        assert params.callback_url == "https://new.example.com"
        assert params.description is None
        assert params.enabled is None

    def test_partial_update_enabled(self):
        params = CommitWebhookUpdate(enabled=False)
        assert params.enabled is False
        assert params.callback_url is None

    def test_all_fields(self):
        params = CommitWebhookUpdate(
            callback_url="https://new.example.com",
            description="Updated description",
            enabled=True,
        )
        assert params.callback_url == "https://new.example.com"
        assert params.description == "Updated description"
        assert params.enabled is True

    def test_empty_update(self):
        params = CommitWebhookUpdate()
        assert params.callback_url is None
        assert params.description is None
        assert params.enabled is None


class TestCommitWebhookResponse:
    def test_full_response(self):
        webhook_id = uuid4()
        multiverse_id = uuid4()
        universe_id = uuid4()
        now = datetime.now(timezone.utc)
        last_triggered = datetime.now(timezone.utc)

        response = CommitWebhookResponse(
            webhook_id=webhook_id,
            multiverse_id=multiverse_id,
            universe_id=universe_id,
            trigger_event=WebhookEventType.PACK_APPLIED,
            callback_url="https://example.com/webhook",
            description="Test webhook",
            enabled=True,
            created_at=now,
            last_triggered_at=last_triggered,
            last_delivery_status=WebhookDeliveryStatus.DELIVERED,
            last_delivery_at=last_triggered,
            consecutive_failures=0,
        )
        assert response.webhook_id == webhook_id
        assert response.multiverse_id == multiverse_id
        assert response.universe_id == universe_id
        assert response.trigger_event == WebhookEventType.PACK_APPLIED
        assert response.last_delivery_status == WebhookDeliveryStatus.DELIVERED
        assert response.consecutive_failures == 0

    def test_response_from_attributes(self):
        webhook_id = uuid4()
        multiverse_id = uuid4()
        now = datetime.now(timezone.utc)

        response = CommitWebhookResponse(
            webhook_id=webhook_id,
            multiverse_id=multiverse_id,
            universe_id=None,
            trigger_event=WebhookEventType.PACK_APPLIED,
            callback_url="https://example.com",
            description="",
            enabled=True,
            created_at=now,
        )
        assert response.universe_id is None
        assert response.last_triggered_at is None


class TestWebhookDeliveryLog:
    def test_success_delivery(self):
        delivery_id = uuid4()
        webhook_id = uuid4()
        now = datetime.now(timezone.utc)
        payload = {"multiverse_id": str(uuid4()), "pack_id": str(uuid4())}

        log = WebhookDeliveryLog(
            delivery_id=delivery_id,
            webhook_id=webhook_id,
            event_type=WebhookEventType.PACK_APPLIED,
            payload=payload,
            response_status=200,
            response_body="OK",
            error=None,
            delivered_at=now,
        )
        assert log.delivery_id == delivery_id
        assert log.response_status == 200
        assert log.error is None
        assert log.payload == payload

    def test_failed_delivery(self):
        delivery_id = uuid4()
        webhook_id = uuid4()
        now = datetime.now(timezone.utc)

        log = WebhookDeliveryLog(
            delivery_id=delivery_id,
            webhook_id=webhook_id,
            event_type=WebhookEventType.PACK_APPLIED,
            payload={},
            response_status=None,
            response_body=None,
            error="Connection refused",
            delivered_at=now,
        )
        assert log.error == "Connection refused"
        assert log.response_status is None

    def test_non_2xx_response(self):
        delivery_id = uuid4()
        webhook_id = uuid4()
        now = datetime.now(timezone.utc)

        log = WebhookDeliveryLog(
            delivery_id=delivery_id,
            webhook_id=webhook_id,
            event_type=WebhookEventType.PACK_APPLIED,
            payload={},
            response_status=500,
            response_body="Internal Server Error",
            error=None,
            delivered_at=now,
        )
        assert log.response_status == 500
        assert log.error is None
