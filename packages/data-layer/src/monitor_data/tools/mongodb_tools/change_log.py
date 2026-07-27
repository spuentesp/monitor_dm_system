"""
MongoDB tools for the append-only ChangeLog audit trail (Q-10).

LAYER: 1 (data-layer)
IMPORTS FROM: db.mongodb, schemas.change_log
CALLED BY: CanonKeeper (write) and the UI change-log router (read).

The ``change_log`` collection records every canonical change CanonKeeper
commits to Neo4j. It is APPEND-ONLY — entries are never updated or deleted.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.change_log import (
    ChangeLogEntry,
    ChangeLogFilter,
    ChangeLogListResponse,
    ChangeSubjectType,
    ChangeType,
)

logger = logging.getLogger(__name__)

_COLLECTION = "change_log"


def _entry_to_doc(entry: ChangeLogEntry) -> dict[str, Any]:
    """Serialize a ChangeLogEntry into a Mongo document (UUIDs → str)."""
    return {
        "change_id": str(entry.change_id),
        "subject_type": entry.subject_type.value,
        "subject_id": str(entry.subject_id),
        "change_type": entry.change_type.value,
        "timestamp": entry.timestamp,
        "field_path": entry.field_path,
        "old_value": entry.old_value,
        "new_value": entry.new_value,
        "author": entry.author,
        "authority": entry.authority.value,
        "evidence_type": entry.evidence_type,
        "evidence_id": str(entry.evidence_id) if entry.evidence_id else None,
        "reason": entry.reason,
        "transaction_id": str(entry.transaction_id) if entry.transaction_id else None,
    }


def _doc_to_entry(doc: dict[str, Any]) -> ChangeLogEntry:
    return ChangeLogEntry(
        change_id=UUID(doc["change_id"]),
        subject_type=ChangeSubjectType(doc["subject_type"]),
        subject_id=UUID(doc["subject_id"]),
        change_type=ChangeType(doc["change_type"]),
        timestamp=doc["timestamp"],
        field_path=doc.get("field_path"),
        old_value=doc.get("old_value"),
        new_value=doc.get("new_value"),
        author=doc["author"],
        authority=doc["authority"],
        evidence_type=doc.get("evidence_type"),
        evidence_id=UUID(doc["evidence_id"]) if doc.get("evidence_id") else None,
        reason=doc.get("reason"),
        transaction_id=UUID(doc["transaction_id"]) if doc.get("transaction_id") else None,
    )


def mongodb_append_change_log(entry: ChangeLogEntry) -> None:
    """Append a single audit entry. Best-effort — never raises to the caller.

    Auditing must never break a canon commit, so any failure here is logged
    and swallowed.
    """
    try:
        coll = get_mongodb_client().get_collection(_COLLECTION)
        coll.insert_one(_entry_to_doc(entry))
    except Exception:  # pragma: no cover — auditing is non-critical
        logger.warning("Failed to append change_log entry", exc_info=True)


def mongodb_list_change_log(filters: ChangeLogFilter) -> ChangeLogListResponse:
    """Query the append-only change log (read-only)."""
    coll = get_mongodb_client().get_collection(_COLLECTION)

    query: dict[str, Any] = {}
    if filters.subject_type:
        query["subject_type"] = filters.subject_type.value
    if filters.subject_id:
        query["subject_id"] = str(filters.subject_id)
    if filters.change_type:
        query["change_type"] = filters.change_type.value
    if filters.author:
        query["author"] = filters.author
    if filters.transaction_id:
        query["transaction_id"] = str(filters.transaction_id)
    if filters.since or filters.until:
        ts: dict[str, datetime] = {}
        if filters.since:
            ts["$gte"] = filters.since
        if filters.until:
            ts["$lte"] = filters.until
        query["timestamp"] = ts

    total = coll.count_documents(query)
    direction = -1 if filters.sort_order == "desc" else 1
    cursor = coll.find(query).sort("timestamp", direction).skip(filters.offset).limit(filters.limit)
    entries = []
    for doc in cursor:
        try:
            entries.append(_doc_to_entry(doc))
        except Exception:  # pragma: no cover — skip malformed legacy rows
            logger.warning("Skipping malformed change_log doc", exc_info=True)

    return ChangeLogListResponse(
        entries=entries,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


def make_change_log_entry(
    *,
    subject_type: ChangeSubjectType,
    subject_id: UUID,
    change_type: ChangeType = ChangeType.CREATED,
    author: str = "CanonKeeper",
    authority: str = "system",
    evidence_type: str | None = None,
    evidence_id: UUID | None = None,
    reason: str | None = None,
    transaction_id: UUID | None = None,
) -> ChangeLogEntry:
    """Convenience builder for a freshly-timestamped entry with a new id."""
    from uuid import uuid4

    return ChangeLogEntry(
        change_id=uuid4(),
        subject_type=subject_type,
        subject_id=subject_id,
        change_type=change_type,
        timestamp=datetime.now(UTC),
        author=author,
        authority=authority,
        evidence_type=evidence_type,
        evidence_id=evidence_id,
        reason=reason,
        transaction_id=transaction_id,
    )
