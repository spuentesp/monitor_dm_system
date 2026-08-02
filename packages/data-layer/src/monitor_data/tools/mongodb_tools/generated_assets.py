"""
MongoDB persistence tools for generated image assets.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

UUIDs are stored as strings. GeneratedAsset remains a MongoDB record; these
operations never write to Neo4j.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.generated_assets import (
    ApprovalStatus,
    GeneratedAsset,
    GeneratedAssetCreate,
    GeneratedAssetFilter,
    GeneratedAssetUpdate,
    ReferenceStatus,
)

_COLLECTION = "generated_assets"
_REFERENCE_ELIGIBLE = {ReferenceStatus.PRIMARY.value, ReferenceStatus.SUPPORTING.value}
# Anchor scopes that define "same subject" for the single-primary invariant.
_REFERENCE_SCOPES = ("character_id", "entity_id", "scene_id", "conversation_id")


def _generated_asset_doc_to_response(doc: Mapping[str, Any]) -> GeneratedAsset:
    """Rebuild a typed GeneratedAsset from its MongoDB document."""
    payload = dict(doc)
    payload.pop("_id", None)
    return GeneratedAsset.model_validate(payload)


def _status_value(value: object) -> str:
    """Normalize StrEnum/string values for Mongo comparisons."""
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)


def _ensure_reference_eligible(approval_status: object, reference_status: object) -> None:
    """Reject reference roles on assets whose resulting state is not approved."""
    if (
        _status_value(reference_status) in _REFERENCE_ELIGIBLE
        and _status_value(approval_status) != ApprovalStatus.APPROVED.value
    ):
        raise ValueError("Only approved generated assets may be primary or supporting references")


def _get_asset_doc(asset_id: UUID) -> dict[str, Any]:
    collection = get_mongodb_client().get_collection(_COLLECTION)
    doc = collection.find_one({"asset_id": str(asset_id)})
    if doc is None:
        raise ValueError(f"Generated asset {asset_id} not found")
    return dict(doc)


def _shares_reference_scope(doc: Mapping[str, Any], asset: Mapping[str, Any]) -> bool:
    """True when both docs share at least one non-null reference anchor."""
    return any(
        asset.get(key) is not None and doc.get(key) == asset.get(key)
        for key in _REFERENCE_SCOPES
    )


def _demote_other_primaries(collection: Any, asset: Mapping[str, Any]) -> None:
    """Demote every other primary in the asset's scope(s) to supporting.

    Keeps the single-primary-per-scope invariant without ever deleting the
    previous reference — it stays approved as a supporting reference.
    """
    now = datetime.now(UTC)
    cursor = collection.find({"reference_status": ReferenceStatus.PRIMARY.value})
    for doc in cursor:
        if doc.get("asset_id") == asset.get("asset_id"):
            continue
        if not _shares_reference_scope(doc, asset):
            continue
        collection.update_one(
            {"asset_id": doc["asset_id"]},
            {"$set": {"reference_status": ReferenceStatus.SUPPORTING.value, "updated_at": now}},
        )


def mongodb_create_generated_asset(params: GeneratedAssetCreate) -> GeneratedAsset:
    """Persist a newly generated asset and return its typed record."""
    _ensure_reference_eligible(params.approval_status, params.reference_status)

    now = datetime.now(UTC)
    doc = params.model_dump(mode="json")
    doc.update(
        {
            "asset_id": str(uuid4()),
            "approved_by": None,
            "approved_at": None,
            "created_at": now,
            "updated_at": now,
        }
    )
    get_mongodb_client().get_collection(_COLLECTION).insert_one(doc)
    return _generated_asset_doc_to_response(doc)


def mongodb_get_generated_asset(asset_id: UUID) -> GeneratedAsset | None:
    """Fetch a generated asset by ID, returning None when absent."""
    doc = get_mongodb_client().get_collection(_COLLECTION).find_one(
        {"asset_id": str(asset_id)}
    )
    if doc is None:
        return None
    return _generated_asset_doc_to_response(doc)


def mongodb_list_generated_assets(params: GeneratedAssetFilter) -> list[GeneratedAsset]:
    """List generated assets matching the supplied filters, newest first."""
    query: dict[str, Any] = {}
    for field_name in (
        "character_id",
        "entity_id",
        "universe_id",
        "story_id",
        "scene_id",
        "conversation_id",
        "asset_type",
        "approval_status",
        "reference_status",
        "trigger",
    ):
        value = getattr(params, field_name)
        if value is not None:
            query[field_name] = _status_value(value) if not isinstance(value, str) else value

    # Default listings hide rejected assets unless the caller explicitly
    # filters on approval_status or opts in via include_rejected.
    if params.approval_status is None and not params.include_rejected:
        query["approval_status"] = {"$ne": ApprovalStatus.REJECTED.value}

    cursor = (
        get_mongodb_client()
        .get_collection(_COLLECTION)
        .find(query)
        .sort("created_at", -1)
        .skip(params.offset)
        .limit(params.limit)
    )
    return [_generated_asset_doc_to_response(doc) for doc in cursor]
def mongodb_update_generated_asset(
    asset_id: UUID,
    params: GeneratedAssetUpdate,
) -> GeneratedAsset:
    """Update mutable generated-asset fields while preserving reference safety."""
    collection = get_mongodb_client().get_collection(_COLLECTION)
    existing = collection.find_one({"asset_id": str(asset_id)})
    if existing is None:
        raise ValueError(f"Generated asset {asset_id} not found")

    update_fields = params.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    if "approved_at" in update_fields and params.approved_at is not None:
        update_fields["approved_at"] = params.approved_at

    resulting_approval = update_fields.get(
        "approval_status", existing.get("approval_status", ApprovalStatus.PENDING.value)
    )
    resulting_reference = update_fields.get(
        "reference_status", existing.get("reference_status", ReferenceStatus.NONE.value)
    )
    _ensure_reference_eligible(resulting_approval, resulting_reference)

    update_fields["updated_at"] = datetime.now(UTC)
    collection.update_one(
        {"asset_id": str(asset_id)},
        {"$set": update_fields},
    )
    updated = collection.find_one({"asset_id": str(asset_id)})
    if updated is None:
        raise ValueError(f"Generated asset {asset_id} not found after update")
    if _status_value(resulting_reference) == ReferenceStatus.PRIMARY.value:
        _demote_other_primaries(collection, updated)
    updated = collection.find_one({"asset_id": str(asset_id)})
    if updated is None:
        raise ValueError(f"Generated asset {asset_id} not found after update")
    return _generated_asset_doc_to_response(updated)


def mongodb_approve_generated_asset(
    asset_id: UUID,
    *,
    approved_by: str,
    reference_status: ReferenceStatus,
) -> GeneratedAsset:
    """Approve an asset and optionally make it a primary/supporting reference."""
    collection = get_mongodb_client().get_collection(_COLLECTION)
    if collection.find_one({"asset_id": str(asset_id)}) is None:
        raise ValueError(f"Generated asset {asset_id} not found")

    normalized_reference = ReferenceStatus(reference_status)
    now = datetime.now(UTC)
    collection.update_one(
        {"asset_id": str(asset_id)},
        {
            "$set": {
                "approval_status": ApprovalStatus.APPROVED.value,
                "reference_status": normalized_reference.value,
                "approved_by": approved_by,
                "approved_at": now,
                "rejected_by": None,
                "rejected_at": None,
                "updated_at": now,
            }
        },
    )
    updated = collection.find_one({"asset_id": str(asset_id)})
    if updated is None:
        raise ValueError(f"Generated asset {asset_id} not found after approval")
    if normalized_reference == ReferenceStatus.PRIMARY:
        _demote_other_primaries(collection, updated)
        updated = collection.find_one({"asset_id": str(asset_id)})
        if updated is None:
            raise ValueError(f"Generated asset {asset_id} not found after approval")
    return _generated_asset_doc_to_response(updated)


def mongodb_reject_generated_asset(
    asset_id: UUID,
    *,
    rejected_by: str,
) -> GeneratedAsset:
    """Reject an asset, removing any reference role and recording the reviewer."""
    collection = get_mongodb_client().get_collection(_COLLECTION)
    if collection.find_one({"asset_id": str(asset_id)}) is None:
        raise ValueError(f"Generated asset {asset_id} not found")

    now = datetime.now(UTC)
    collection.update_one(
        {"asset_id": str(asset_id)},
        {
            "$set": {
                "approval_status": ApprovalStatus.REJECTED.value,
                "reference_status": ReferenceStatus.NONE.value,
                "approved_by": None,
                "approved_at": None,
                "rejected_by": rejected_by,
                "rejected_at": now,
                "updated_at": now,
            }
        },
    )
    updated = collection.find_one({"asset_id": str(asset_id)})
    if updated is None:
        raise ValueError(f"Generated asset {asset_id} not found after rejection")
    return _generated_asset_doc_to_response(updated)


__all__ = [
    "mongodb_create_generated_asset",
    "mongodb_get_generated_asset",
    "mongodb_list_generated_assets",
    "mongodb_update_generated_asset",
    "mongodb_approve_generated_asset",
    "mongodb_reject_generated_asset",
]
