"""
MongoDB persistence tools for versioned visual identities.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

Each revision is an immutable document with a fresh identity_id. Replacing
version N inserts N+1 and marks N superseded. UUIDs are stored as strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.visual_identity import (
    VisualIdentity,
    VisualIdentityCreate,
    VisualIdentityFilter,
    VisualIdentityStatus,
    VisualIdentityUpdate,
    transition_visual_identity_status,
)

_COLLECTION = "visual_identities"


class VisualIdentityNotFoundError(ValueError):
    """The targeted visual identity record does not exist."""


class VisualIdentityConflictError(ValueError):
    """Optimistic-lock failure: the targeted version is no longer current."""


def _visual_identity_doc_to_response(doc: Mapping[str, Any]) -> VisualIdentity:
    """Rebuild a typed VisualIdentity from its MongoDB document."""
    payload = dict(doc)
    payload.pop("_id", None)
    return VisualIdentity.model_validate(payload)


def _anchor_query(
    *,
    character_id: str | None,
    entity_id: UUID | str | None,
    universe_id: UUID | str | None,
    include_nulls: bool,
) -> dict[str, Any]:
    """Build the exact anchor query used to identify one identity lineage."""
    query: dict[str, Any] = {}
    values: dict[str, str | None] = {
        "character_id": character_id,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "universe_id": str(universe_id) if universe_id is not None else None,
    }
    for key, value in values.items():
        if include_nulls or value is not None:
            query[key] = value
    return query


def _latest_identity(collection: Any, query: dict[str, Any]) -> dict[str, Any] | None:
    cursor = collection.find(query).sort("version", -1).limit(1)
    return next((dict(doc) for doc in cursor), None)


def _version_conflict(identity_id: object, expected_version: object) -> VisualIdentityConflictError:
    return VisualIdentityConflictError(
        f"Visual identity version conflict for {identity_id}: expected version "
        f"{expected_version} is no longer current"
    )


def _supersede_current(
    collection: Any,
    current: Mapping[str, Any],
    now: datetime,
) -> None:
    """Optimistically mark the exact current version as superseded."""
    result = collection.update_one(
        {
            "identity_id": current["identity_id"],
            "version": current["version"],
            "status": current["status"],
        },
        {
            "$set": {
                "status": VisualIdentityStatus.SUPERSEDED.value,
                "updated_at": now,
            }
        },
    )
    if result.matched_count != 1:
        raise _version_conflict(current["identity_id"], current["version"])


def _insert_revision(
    collection: Any,
    current: Mapping[str, Any],
    revision_fields: Mapping[str, Any],
) -> VisualIdentity:
    """Insert a next-version copy and supersede the source version."""
    now = datetime.now(UTC)
    new_doc = dict(current)
    new_doc.pop("_id", None)
    new_doc.update(revision_fields)
    new_doc.update(
        {
            "identity_id": str(uuid4()),
            "version": int(current["version"]) + 1,
            "created_at": now,
            "updated_at": now,
        }
    )
    if not new_doc.get("status") or new_doc["status"] == VisualIdentityStatus.SUPERSEDED.value:
        new_doc["status"] = VisualIdentityStatus.DRAFT.value

    _supersede_current(collection, current, now)
    collection.insert_one(new_doc)
    return _visual_identity_doc_to_response(new_doc)


def mongodb_upsert_visual_identity(
    params: VisualIdentityCreate | VisualIdentityUpdate,
) -> VisualIdentity:
    """Create an identity or replace one version using optimistic locking."""
    collection = get_mongodb_client().get_collection(_COLLECTION)

    if isinstance(params, VisualIdentityCreate):
        anchor = _anchor_query(
            character_id=params.character_id,
            entity_id=params.entity_id,
            universe_id=params.universe_id,
            include_nulls=True,
        )
        current = _latest_identity(collection, anchor)
        fields = params.model_dump(mode="json")
        if current is not None:
            fields["status"] = VisualIdentityStatus.DRAFT.value
            return _insert_revision(collection, current, fields)

        now = datetime.now(UTC)
        doc = fields | {
            "identity_id": str(uuid4()),
            "version": 1,
            "status": VisualIdentityStatus.DRAFT.value,
            "created_at": now,
            "updated_at": now,
        }
        collection.insert_one(doc)
        return _visual_identity_doc_to_response(doc)

    if params.identity_id is None:
        raise ValueError("VisualIdentityUpdate.identity_id is required")
    if params.expected_version is None:
        raise ValueError("VisualIdentityUpdate.expected_version is required")

    current_raw = collection.find_one({"identity_id": str(params.identity_id)})
    if current_raw is None:
        raise VisualIdentityNotFoundError(f"Visual identity {params.identity_id} not found")
    current = dict(current_raw)

    current_anchor = _anchor_query(
        character_id=current.get("character_id"),
        entity_id=current.get("entity_id"),
        universe_id=current.get("universe_id"),
        include_nulls=True,
    )
    latest = _latest_identity(collection, current_anchor)
    if (
        int(current["version"]) != params.expected_version
        or current.get("status") == VisualIdentityStatus.SUPERSEDED.value
        or latest is None
        or latest.get("identity_id") != current.get("identity_id")
    ):
        raise _version_conflict(params.identity_id, params.expected_version)

    update_fields = params.model_dump(mode="json", exclude_none=True)
    update_fields.pop("identity_id", None)
    update_fields.pop("expected_version", None)
    if "status" not in update_fields:
        update_fields["status"] = VisualIdentityStatus.DRAFT.value
    return _insert_revision(collection, current, update_fields)


def mongodb_get_visual_identity(
    *,
    character_id: str | None = None,
    entity_id: UUID | None = None,
    universe_id: UUID | None = None,
    status: str = "approved",
    card_default_only: bool = False,
) -> VisualIdentity | None:
    """Fetch the latest visual identity matching an anchor and lifecycle status.

    By default the anchor query omits null fields (``include_nulls=False``),
    so a character_id-only lookup matches identities from every anchor —
    including higher-version incarnations.  Pass ``card_default_only=True``
    to match the explicit null anchor (``include_nulls=True`` semantics):
    only the card default lineage (character_id with null entity_id and
    universe_id) is eligible.
    """
    if card_default_only and (character_id is None or entity_id is not None or universe_id is not None):
        raise ValueError("card_default_only lookup requires character_id without entity_id/universe_id")
    if character_id is None and entity_id is None:
        raise ValueError("Visual identity lookup requires a character_id or entity_id anchor")
    if entity_id is not None and universe_id is None:
        raise ValueError("Visual identity entity_id lookup requires universe_id")

    query = _anchor_query(
        character_id=character_id,
        entity_id=entity_id,
        universe_id=universe_id,
        include_nulls=card_default_only,
    )
    query["status"] = status
    doc = _latest_identity(
        get_mongodb_client().get_collection(_COLLECTION),
        query,
    )
    if doc is None:
        return None
    return _visual_identity_doc_to_response(doc)


def mongodb_list_visual_identities(params: VisualIdentityFilter) -> list[VisualIdentity]:
    """List visual identities matching the supplied filters, newest first.

    Exact-match anchor filters; ``status=None`` lists every lifecycle state.
    """
    query: dict[str, Any] = {}
    if params.character_id is not None:
        query["character_id"] = params.character_id
    if params.entity_id is not None:
        query["entity_id"] = str(params.entity_id)
    if params.universe_id is not None:
        query["universe_id"] = str(params.universe_id)
    if params.status is not None:
        query["status"] = params.status.value

    cursor = (
        get_mongodb_client()
        .get_collection(_COLLECTION)
        .find(query)
        .sort("created_at", -1)
        .skip(params.offset)
        .limit(params.limit)
    )
    return [_visual_identity_doc_to_response(doc) for doc in cursor]


def mongodb_update_visual_identity_status(
    identity_id: UUID,
    *,
    status: str,
    decision_proposal_id: UUID | None = None,
) -> VisualIdentity:
    """Record a CanonKeeper proposal outcome on an exact identity version.

    Authority: CanonKeeper only.

    Unlike the versioned upsert, this is an in-place transition used by the
    canon-anchored identity flow (Task 7): acceptance moves draft ->
    approved; rejection keeps the current (draft) status and only stores the
    decision provenance in ``decision_proposal_id``. A same-status call is
    allowed so rejections can record their reference; any other illegal
    transition raises ``VisualIdentityConflictError``.

    ``status`` is a plain string (the MCP wire format can only carry JSON
    strings) and is coerced to ``VisualIdentityStatus`` here.
    """
    coerced_status = VisualIdentityStatus(status)
    collection = get_mongodb_client().get_collection(_COLLECTION)
    raw = collection.find_one({"identity_id": str(identity_id)})
    if raw is None:
        raise VisualIdentityNotFoundError(f"Visual identity {identity_id} not found")

    current = VisualIdentityStatus(raw["status"])
    if coerced_status != current and not transition_visual_identity_status(current, coerced_status):
        raise VisualIdentityConflictError(
            f"Illegal visual identity status transition for {identity_id}: "
            f"{current.value} -> {coerced_status.value}"
        )

    now = datetime.now(UTC)
    update: dict[str, Any] = {"status": coerced_status.value, "updated_at": now}
    if decision_proposal_id is not None:
        update["decision_proposal_id"] = str(decision_proposal_id)
    collection.update_one({"identity_id": str(identity_id)}, {"$set": update})

    doc = dict(raw)
    doc.update(update)
    return _visual_identity_doc_to_response(doc)


__all__ = [
    "VisualIdentityConflictError",
    "VisualIdentityNotFoundError",
    "mongodb_list_visual_identities",
    "mongodb_upsert_visual_identity",
    "mongodb_get_visual_identity",
    "mongodb_update_visual_identity_status",
]
