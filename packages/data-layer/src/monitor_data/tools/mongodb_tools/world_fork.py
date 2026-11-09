"""World-fork data copy for MongoDB (multi-world support).

LAYER: 1 (data-layer). Called by the UI fork endpoint after the Neo4j graph
fork, to clone a base world's universe-scoped documents into the derived
world's prefixed collections.

Only collections that carry a ``universe_id`` field are copied; everything
else (knowledge packs, templates, global config) is intentionally shared.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from monitor_data.db._utils import run_sync
from monitor_data.db.mongodb import get_mongodb_client

# Collections with a universe_id field that belong to a single world.
FORK_UNIVERSE_COLLECTIONS: tuple[str, ...] = (
    "scenes",
    "documents",
    "snippets",
    "ingestion_jobs",
    "chat_sessions",
    "gm_notes",
)


def mongodb_fork_universe_data(
    src_universe_id: UUID | str,
    dst_universe_id: UUID | str,
    prefix: str,
) -> dict[str, Any]:
    """Copy a universe's Mongo documents into the derived world's prefixed collections.

    Documents keep their field values except ``universe_id`` (rewritten to the
    destination) and ``_id`` (regenerated). Afterwards the prefixed
    collections get the standard index set via ensure_indexes_for_prefix.

    Args:
        src_universe_id: Source (base) universe id.
        dst_universe_id: Destination (forked) universe id.
        prefix: Destination collection prefix (e.g. "w0a1b2c3d4e5f_").

    Returns:
        Dict with per-collection copy counts and the total.
    """
    prefix = (prefix or "").strip()
    if not prefix:
        raise ValueError("prefix is required for a forked world")
    src = str(UUID(str(src_universe_id)))
    dst = str(UUID(str(dst_universe_id)))
    client = get_mongodb_client()
    db = client.get_database()

    copied: dict[str, int] = {}
    for name in FORK_UNIVERSE_COLLECTIONS:
        src_coll = db[name]  # source docs live in the unprefixed collection
        docs = list(src_coll.find({"universe_id": src}))
        if docs:
            dst_coll = db[f"{prefix}{name}"]
            for doc in docs:
                new_doc = {k: v for k, v in doc.items() if k != "_id"}
                new_doc["universe_id"] = dst
                dst_coll.insert_one(new_doc)
        copied[name] = len(docs)

    run_sync(client.ensure_indexes_for_prefix(prefix))

    return {
        "src_universe_id": src,
        "dst_universe_id": dst,
        "prefix": prefix,
        "collections": copied,
        "total_copied": sum(copied.values()),
    }
