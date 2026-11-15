"""Session Recorder entry tools (CF-1 / G03) over Mongo ``chat_messages``.

A "session entry" is one logged GM message in a ``gm_assistant`` recording
(the Session Recorder transcript). G03 lets the GM correct the record at the
table:

- ``mongodb_update_session_entry`` — edit the entry text in place.
- ``mongodb_delete_session_entry`` — soft-delete ("strike"): the doc is kept
  with ``struck=True`` plus audit fields so CF-8 and the recorder's struck
  list can still show why it disappeared. v1 is soft-delete only.
- ``mongodb_restore_session_entry`` — undo a strike (the "one undo" from the
  G03 open decision); returns the proposal ids retracted with the strike so
  the caller can restore them too.

Every write invalidates the shared Redis message cache for the session
(``chat_messages:<session_id>``) so the UI's next read reflects the change.

LAYER: 1 (data-layer)
IMPORTS FROM: external libraries + data-layer db modules only
CALLED BY: agents (Layer 2) via MCP, UI backend (Layer 3) directly
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from monitor_data.db.mongodb import get_mongodb_client

log = structlog.get_logger()

_COLLECTION = "chat_messages"

# Default strike reason. Retracted proposals carry this in their decision
# metadata so CF-8 shows *why* the proposal disappeared, and the undo path
# matches on it before flipping anything back to pending.
STRIKE_REASON = "struck at the table"


def _cache_key(session_id: str) -> str:
    return f"chat_messages:{session_id}"


def _invalidate_cache(session_id: str) -> None:
    """Drop the Redis message cache for the session (best-effort)."""
    if not session_id:
        return
    try:
        from monitor_data.db.redis import get_redis_client

        get_redis_client().delete(_cache_key(session_id))
    except Exception as exc:  # noqa: BLE001  # reason: cache miss only costs a refetch (in _invalidate_cache)
        log.debug("session_entry_cache_invalidate_failed", session_id=session_id, error=str(exc))


def _find_doc(entry_id: str) -> dict[str, Any] | None:
    coll = get_mongodb_client().get_collection(_COLLECTION)
    doc = coll.find_one({"id": entry_id})
    return dict(doc) if doc else None


def _public_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Strip Mongo's ``_id`` and normalize the strike fields for consumers."""
    out = {k: v for k, v in doc.items() if k != "_id"}
    out.setdefault("struck", bool(doc.get("struck")))
    out.setdefault("struck_at", doc.get("struck_at"))
    out.setdefault("struck_reason", doc.get("struck_reason"))
    out.setdefault("struck_proposal_ids", list(doc.get("struck_proposal_ids") or []))
    out.setdefault("edited_at", doc.get("edited_at"))
    return out


def mongodb_get_session_entry(entry_id: str) -> dict[str, Any] | None:
    """Return one logged session entry by id, or None if it does not exist.

    Authority: * (reads are open)
    """
    doc = _find_doc(entry_id)
    return _public_doc(doc) if doc else None


def mongodb_list_session_entries(
    session_id: str,
    include_struck: bool = False,
) -> list[dict[str, Any]]:
    """List a recording's entries in log order, optionally including struck ones.

    Authority: * (reads are open)
    """
    coll = get_mongodb_client().get_collection(_COLLECTION)
    query: dict[str, Any] = {"session_id": session_id}
    if not include_struck:
        # Missing ``struck`` (legacy docs) is not struck.
        query["struck"] = {"$ne": True}
    rows = list(coll.find(query, {"_id": 0}, sort=[("timestamp", 1)]))
    return [_public_doc(dict(r)) for r in rows]


def mongodb_update_session_entry(entry_id: str, text: str) -> dict[str, Any]:
    """Edit a logged entry's text in place (the recorder transcript update).

    Struck entries are frozen: restore them first, so the audit trail cannot
    be rewritten from the struck list.

    Authority: SessionIngestAgent / CaptureInsightAgent (GM correction flow)

    Raises:
        ValueError: entry missing, text empty, or entry is struck.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("text must not be empty")

    doc = _find_doc(entry_id)
    if doc is None:
        raise ValueError(f"Session entry {entry_id} not found")
    if doc.get("struck"):
        raise ValueError(f"Session entry {entry_id} is struck; restore it before editing")

    coll = get_mongodb_client().get_collection(_COLLECTION)
    now = datetime.now(UTC).isoformat()
    coll.update_one(
        {"id": entry_id},
        {"$set": {"content": cleaned, "edited_at": now}},
    )
    _invalidate_cache(str(doc.get("session_id") or ""))
    log.info("session_entry_updated", entry_id=entry_id, session_id=doc.get("session_id"))
    updated = _find_doc(entry_id)
    return _public_doc(updated or {**doc, "content": cleaned, "edited_at": now})


def mongodb_delete_session_entry(
    entry_id: str,
    soft: bool = True,
    reason: str = STRIKE_REASON,
    retracted_proposal_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Strike (soft-delete) a logged entry so it leaves the recorder view.

    The document is kept with ``struck=True`` and audit fields — CF-8 and the
    recorder's struck list need the history (G03 open decision: v1 is
    soft-delete only; hard delete is rejected). ``retracted_proposal_ids``
    records which queued proposals were retracted with this strike so the
    undo can restore exactly those.

    Authority: SessionIngestAgent / CaptureInsightAgent (GM correction flow)

    Raises:
        ValueError: entry missing, or ``soft=False`` (not supported in v1).
    """
    if not soft:
        raise ValueError("hard delete of session entries is not supported in v1; strike (soft=True) instead")

    doc = _find_doc(entry_id)
    if doc is None:
        raise ValueError(f"Session entry {entry_id} not found")

    coll = get_mongodb_client().get_collection(_COLLECTION)
    now = datetime.now(UTC).isoformat()
    coll.update_one(
        {"id": entry_id},
        {
            "$set": {
                "struck": True,
                "struck_at": now,
                "struck_reason": reason or STRIKE_REASON,
                "struck_proposal_ids": list(retracted_proposal_ids or []),
            }
        },
    )
    _invalidate_cache(str(doc.get("session_id") or ""))
    log.info(
        "session_entry_struck",
        entry_id=entry_id,
        session_id=doc.get("session_id"),
        retracted_proposals=len(retracted_proposal_ids or []),
    )
    updated = _find_doc(entry_id)
    return _public_doc(updated or {**doc, "struck": True, "struck_at": now})


def mongodb_restore_session_entry(entry_id: str) -> dict[str, Any]:
    """Undo a strike: the entry returns to the recorder view.

    Returns the public doc plus ``restored_proposal_ids`` — the proposals
    retracted with the strike — so the caller can flip them back to pending
    (the "one undo" from the G03 open decision).

    Authority: SessionIngestAgent / CaptureInsightAgent (GM correction flow)

    Raises:
        ValueError: entry missing.
    """
    doc = _find_doc(entry_id)
    if doc is None:
        raise ValueError(f"Session entry {entry_id} not found")

    restored_ids = [str(p) for p in (doc.get("struck_proposal_ids") or [])]
    coll = get_mongodb_client().get_collection(_COLLECTION)
    coll.update_one(
        {"id": entry_id},
        {
            "$set": {
                "struck": False,
                "struck_at": None,
                "struck_reason": None,
                "struck_proposal_ids": [],
            }
        },
    )
    _invalidate_cache(str(doc.get("session_id") or ""))
    log.info("session_entry_restored", entry_id=entry_id, proposals=len(restored_ids))
    updated = _find_doc(entry_id)
    out = _public_doc(updated or {**doc, "struck": False})
    out["restored_proposal_ids"] = restored_ids
    return out
