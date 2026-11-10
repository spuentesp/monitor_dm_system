"""
MongoDB tools for GM prep bundle (prep-to-table, CF-7) operations.

LAYER: 1 (data-layer)
Authority: MongoDB
Use Case: CF-7 (Session Prep Assistant)

One document per (universe, story), keyed on ``universe_id`` + ``story_id``
(empty string for a story-less bundle). The bundle is user-owned scratch
state for "tonight's" session — no canon, no Neo4j, no CanonKeeper gate.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.gm_prep import (
    GmPrepBundleResponse,
    GmPrepBundleUpsert,
    GmPrepLocation,
    GmPrepNpc,
    GmPrepThread,
)

logger = logging.getLogger(__name__)

GM_PREP_COLLECTION = "gm_prep_bundles"


def _story_key(story_id: UUID | None) -> str:
    return str(story_id) if story_id else ""


def _bundle_doc_to_response(doc: dict) -> GmPrepBundleResponse:
    """Convert a bundle document from MongoDB to a GmPrepBundleResponse."""
    return GmPrepBundleResponse(
        universe_id=UUID(doc["universe_id"]),
        story_id=UUID(doc["story_id"]) if doc.get("story_id") else None,
        npcs=[GmPrepNpc(**npc) for npc in doc.get("npcs", []) or []],
        locations=[GmPrepLocation(**loc) for loc in doc.get("locations", []) or []],
        threads=[GmPrepThread(**thread) for thread in doc.get("threads", []) or []],
        source=doc.get("source", "prep_flow"),
        updated_at=doc["updated_at"],
    )


def mongodb_get_gm_prep_bundle(
    universe_id: UUID,
    story_id: UUID | None = None,
) -> GmPrepBundleResponse | None:
    """Retrieve the prep bundle for a (universe, story), or ``None`` if absent."""
    client = get_mongodb_client()
    collection = client.get_collection(GM_PREP_COLLECTION)

    doc = collection.find_one({"universe_id": str(universe_id), "story_id": _story_key(story_id)})
    if not doc:
        return None

    return _bundle_doc_to_response(doc)


def mongodb_upsert_gm_prep_bundle(params: GmPrepBundleUpsert) -> GmPrepBundleResponse:
    """Upsert the prep bundle for a (universe, story). Overwrites prior content.

    Returns the canonical post-write state (with refreshed ``updated_at``).
    """
    client = get_mongodb_client()
    collection = client.get_collection(GM_PREP_COLLECTION)

    now = datetime.now(UTC)
    doc = {
        "universe_id": str(params.universe_id),
        "story_id": _story_key(params.story_id),
        "npcs": [npc.model_dump(mode="json") for npc in params.npcs],
        "locations": [loc.model_dump(mode="json") for loc in params.locations],
        "threads": [thread.model_dump(mode="json") for thread in params.threads],
        "source": params.source,
        "updated_at": now,
    }
    collection.update_one(
        {"universe_id": doc["universe_id"], "story_id": doc["story_id"]},
        {"$set": doc},
        upsert=True,
    )

    return GmPrepBundleResponse(
        universe_id=params.universe_id,
        story_id=params.story_id,
        npcs=list(params.npcs),
        locations=list(params.locations),
        threads=list(params.threads),
        source=params.source,
        updated_at=now,
    )
