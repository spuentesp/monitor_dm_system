"""Canon override audit trail (G08).

When a proposal that carries a contradiction flag is accepted anyway, the
GM has to say why — and that "why" has to survive. This collection is the
record: who let it through, which flags they overrode, and whether the
owner's hard-rejection mode was on at the time.

It is an append-only log. Nothing here is ever updated or deleted: an
override that can be edited is not an audit trail.

LAYER: 1 (data-layer)
IMPORTS FROM: external libraries + data-layer db modules only
CALLED BY: UI backend (Layer 3) via the canon-review router
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.proposed_changes import CanonOverrideRecord

COLLECTION = "canon_override_audit"


def mongodb_record_canon_override(params: CanonOverrideRecord) -> dict[str, Any]:
    """Append one override to the audit trail.

    Authority: * (the UI backend records the GM's decision)
    Collection: canon_override_audit
    """
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)
    now = datetime.now(UTC)
    doc = {
        "proposal_id": str(params.proposal_id),
        "owner_id": params.owner_id,
        "reason": params.reason,
        "universe_id": str(params.universe_id) if params.universe_id else None,
        "story_id": str(params.story_id) if params.story_id else None,
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "flag_kinds": list(params.flag_kinds),
        "hard_mode": params.hard_mode,
        "created_at": now,
    }
    coll.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


def mongodb_list_canon_overrides(
    story_id: str | None = None,
    proposal_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List recorded overrides, newest first.

    Authority: * (read-only; the review UI shows the trail)
    Collection: canon_override_audit
    """
    client = get_mongodb_client()
    coll = client.get_collection(COLLECTION)
    query: dict[str, Any] = {}
    if story_id:
        query["story_id"] = str(story_id)
    if proposal_id:
        query["proposal_id"] = str(proposal_id)
    cursor = coll.find(query, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit, 1000)))
    return [dict(row) for row in cursor]
