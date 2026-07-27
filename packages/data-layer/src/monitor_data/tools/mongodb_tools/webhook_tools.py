"""
MongoDB tools for auto-commit webhook management (P1-5).

LAYER: 1 (data-layer)
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.webhooks import (
    CommitWebhookCreate,
    CommitWebhookResponse,
    CommitWebhookUpdate,
    WebhookDeliveryLog,
    WebhookDeliveryStatus,
    WebhookEventType,
)

# =============================================================================
# WEBHOOK REGISTRATION
# =============================================================================


def mongodb_create_commit_webhook(
    params: CommitWebhookCreate,
) -> CommitWebhookResponse:
    """
    Register an auto-commit webhook for a multiverse.

    When a KnowledgePack is applied to the multiverse and proposals are created,
    the registered webhook URL is called asynchronously to trigger CanonKeeper
    evaluation instead of requiring a synchronous commit call.

    Args:
        params: Webhook registration details

    Returns:
        The created webhook record
    """
    mongodb = get_mongodb_client()
    coll = mongodb.get_collection("commit_webhooks")

    now = datetime.now(UTC)
    doc = {
        "webhook_id": str(uuid4()),
        "multiverse_id": str(params.multiverse_id),
        "universe_id": str(params.universe_id) if params.universe_id else None,
        "trigger_event": params.trigger_event.value,
        "callback_url": params.callback_url,
        "description": params.description,
        "enabled": params.enabled,
        "created_at": now,
        "last_triggered_at": None,
        "last_delivery_status": None,
        "last_delivery_at": None,
        "consecutive_failures": 0,
    }
    coll.insert_one(doc)

    return CommitWebhookResponse(
        webhook_id=UUID(str(doc["webhook_id"])),
        multiverse_id=params.multiverse_id,
        universe_id=params.universe_id,
        trigger_event=params.trigger_event,
        callback_url=params.callback_url,
        description=params.description,
        enabled=params.enabled,
        created_at=now,
        last_triggered_at=None,
        last_delivery_status=None,
        last_delivery_at=None,
        consecutive_failures=0,
    )


def mongodb_get_commit_webhook(webhook_id: UUID) -> CommitWebhookResponse | None:
    """
    Fetch a webhook by ID.

    Args:
        webhook_id: Webhook UUID

    Returns:
        Webhook record or None if not found
    """
    mongodb = get_mongodb_client()
    coll = mongodb.get_collection("commit_webhooks")
    doc = coll.find_one({"webhook_id": str(webhook_id)})
    if not doc:
        return None

    return _convert_webhook_doc(doc)


def mongodb_list_commit_webhooks(
    multiverse_id: UUID,
    universe_id: UUID | None = None,
    enabled_only: bool = False,
) -> list[CommitWebhookResponse]:
    """
    List webhooks registered for a multiverse (and optionally a universe).

    Args:
        multiverse_id: Target multiverse
        universe_id: Optional universe scope filter
        enabled_only: If True, only return enabled webhooks

    Returns:
        List of matching webhook records
    """
    mongodb = get_mongodb_client()
    coll = mongodb.get_collection("commit_webhooks")

    query: dict[str, Any] = {"multiverse_id": str(multiverse_id)}
    if universe_id:
        query["universe_id"] = str(universe_id)
    if enabled_only:
        query["enabled"] = True

    docs = coll.find(query).sort("created_at", -1)
    return [_convert_webhook_doc(d) for d in docs]


def mongodb_update_commit_webhook(
    webhook_id: UUID,
    params: CommitWebhookUpdate,
) -> CommitWebhookResponse | None:
    """
    Update an existing webhook (enable/disable, change URL, etc.).

    Args:
        webhook_id: Webhook to update
        params: Fields to update

    Returns:
        Updated webhook record or None if not found
    """
    mongodb = get_mongodb_client()
    coll = mongodb.get_collection("commit_webhooks")

    update: dict[str, Any] = {}
    if params.callback_url is not None:
        update["callback_url"] = params.callback_url
    if params.description is not None:
        update["description"] = params.description
    if params.enabled is not None:
        update["enabled"] = params.enabled

    if not update:
        return mongodb_get_commit_webhook(webhook_id)

    result = coll.find_one_and_update(
        {"webhook_id": str(webhook_id)},
        {"$set": update},
        return_document=True,
    )
    if not result:
        return None

    return _convert_webhook_doc(result)


def mongodb_delete_commit_webhook(webhook_id: UUID) -> bool:
    """
    Delete a webhook registration.

    Args:
        webhook_id: Webhook to delete

    Returns:
        True if deleted, False if not found
    """
    mongodb = get_mongodb_client()
    coll = mongodb.get_collection("commit_webhooks")
    result = coll.delete_one({"webhook_id": str(webhook_id)})
    return result.deleted_count > 0


# =============================================================================
# WEBHOOK DELIVERY LOGGING
# =============================================================================


def mongodb_record_webhook_delivery(
    webhook_id: UUID,
    event_type: WebhookEventType,
    payload: dict[str, Any],
    response_status: int | None = None,
    response_body: str | None = None,
    error: str | None = None,
) -> WebhookDeliveryLog:
    """
    Record the result of a webhook delivery attempt.

    Called by the async delivery executor after attempting to fire a webhook.
    Also updates the webhook's last_triggered_at and consecutive failure count.

    Args:
        webhook_id: Which webhook was triggered
        event_type: What event triggered this delivery
        payload: What was sent in the POST body
        response_status: HTTP status code from the callback endpoint
        response_body: Response body from the callback endpoint
        error: Error message if delivery failed

    Returns:
        The created delivery log record
    """
    mongodb = get_mongodb_client()
    delivery_coll = mongodb.get_collection("webhook_delivery_logs")
    webhook_coll = mongodb.get_collection("commit_webhooks")

    now = datetime.now(UTC)
    delivery_id = uuid4()

    # Determine delivery status
    if error:
        status = WebhookDeliveryStatus.FAILED
    elif response_status and 200 <= response_status < 300:
        status = WebhookDeliveryStatus.DELIVERED
    else:
        status = WebhookDeliveryStatus.FAILED

    delivery_doc = {
        "delivery_id": str(delivery_id),
        "webhook_id": str(webhook_id),
        "event_type": event_type.value,
        "payload": payload,
        "response_status": response_status,
        "response_body": (response_body or "")[:2000] if response_body else None,
        "error": error,
        "delivered_at": now,
    }
    delivery_coll.insert_one(delivery_doc)

    # Update webhook delivery stats
    webhook_update: dict[str, Any] = {
        "last_triggered_at": now,
        "last_delivery_status": status.value,
        "last_delivery_at": now,
    }
    if status == WebhookDeliveryStatus.FAILED:
        webhook_update["consecutive_failures"] = 1
    else:
        webhook_update["consecutive_failures"] = 0

    webhook_coll.update_one(
        {"webhook_id": str(webhook_id)},
        {"$set": webhook_update},
    )

    return WebhookDeliveryLog(
        delivery_id=delivery_id,
        webhook_id=webhook_id,
        event_type=event_type,
        payload=payload,
        response_status=response_status,
        response_body=response_body,
        error=error,
        delivered_at=now,
    )


# =============================================================================
# HELPERS
# =============================================================================


def _convert_webhook_doc(doc: dict[str, Any]) -> CommitWebhookResponse:
    """Convert MongoDB webhook document to response schema."""
    return CommitWebhookResponse(
        webhook_id=UUID(doc["webhook_id"]),
        multiverse_id=UUID(doc["multiverse_id"]),
        universe_id=UUID(doc["universe_id"]) if doc.get("universe_id") else None,
        trigger_event=WebhookEventType(doc["trigger_event"]),
        callback_url=doc["callback_url"],
        description=doc.get("description", ""),
        enabled=doc.get("enabled", True),
        created_at=doc["created_at"],
        last_triggered_at=doc.get("last_triggered_at"),
        last_delivery_status=(
            WebhookDeliveryStatus(doc["last_delivery_status"]) if doc.get("last_delivery_status") else None
        ),
        last_delivery_at=doc.get("last_delivery_at"),
        consecutive_failures=doc.get("consecutive_failures", 0),
    )
