"""
MongoDB tools for GM notebook (per-universe scratchpad) operations.

LAYER: 1 (data-layer)
Authority: MongoDB
Use Case: GM Assistant mode (P2.3)

A single document per universe, keyed on ``universe_id``. The notebook is
user-owned — no canon, no Neo4j, no CanonKeeper gate. The frontend treats
this as the persistence backing for the GM Assistant's session notepad.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.gm_notes import GmNoteResponse, GmNoteUpsert

logger = logging.getLogger(__name__)

# =============================================================================
# GM NOTE OPERATIONS (P2.3)
# =============================================================================


def mongodb_get_gm_note(universe_id: UUID) -> GmNoteResponse | None:
    """Retrieve the GM notebook for a universe, or ``None`` if absent."""
    client = get_mongodb_client()
    collection = client.get_collection("gm_notes")

    doc = collection.find_one({"universe_id": str(universe_id)})
    if not doc:
        return None

    return GmNoteResponse(
        universe_id=universe_id,
        content=doc.get("content", ""),
        updated_at=doc["updated_at"],
    )


def mongodb_upsert_gm_note(universe_id: UUID, params: GmNoteUpsert) -> GmNoteResponse:
    """Upsert the GM notebook for a universe. Overwrites prior content.

    Returns the canonical post-write state (with refreshed ``updated_at``).
    """
    client = get_mongodb_client()
    collection = client.get_collection("gm_notes")

    now = datetime.now(UTC)
    collection.update_one(
        {"universe_id": str(universe_id)},
        {
            "$set": {
                "universe_id": str(universe_id),
                "content": params.content,
                "updated_at": now,
            }
        },
        upsert=True,
    )

    return GmNoteResponse(
        universe_id=universe_id,
        content=params.content,
        updated_at=now,
    )
