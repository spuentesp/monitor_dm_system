"""CRUD for the scene_foreshadowing collection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.foreshadowing import (
    ForeshadowingCreate,
    ForeshadowingResponse,
)


def _doc_to_response(doc: dict[str, Any]) -> ForeshadowingResponse:
    created_at = doc.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.fromisoformat(created_at) if created_at else datetime.now(UTC)
    return ForeshadowingResponse(
        foreshadowing_id=UUID(doc["foreshadowing_id"]),
        scene_id=UUID(doc["scene_id"]),
        story_id=UUID(doc["story_id"]),
        kind=doc["kind"],
        summary=doc["summary"],
        planted_by_turn=int(doc.get("planted_by_turn", 0)),
        target_turn=int(doc.get("target_turn", 0)),
        status=doc.get("status", "open"),
        created_at=created_at,
        paid_at=doc.get("paid_at"),
        paid_at_turn=doc.get("paid_at_turn"),
    )


def mongodb_create_foreshadowing(params: ForeshadowingCreate) -> ForeshadowingResponse:
    """Insert a new plant/payoff item; returns the typed response."""
    mongo_client = get_mongodb_client()
    coll = mongo_client["scene_foreshadowing"]
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "foreshadowing_id": str(uuid4()),
        "scene_id": str(params.scene_id),
        "story_id": str(params.story_id),
        "kind": params.kind,
        "summary": params.summary,
        "planted_by_turn": params.planted_by_turn,
        "target_turn": params.target_turn,
        "status": "open",
        "created_at": now,
        "paid_at": None,
        "paid_at_turn": None,
    }
    coll.insert_one(doc)
    return _doc_to_response(doc)


def mongodb_list_open_foreshadowing(
    scene_id: UUID, story_id: UUID, *, limit: int = 5
) -> list[ForeshadowingResponse]:
    """Return open plant/payoff items for the given scene+story, newest first."""
    mongo_client = get_mongodb_client()
    coll = mongo_client["scene_foreshadowing"]
    docs = list(
        coll.find(
            {
                "scene_id": str(scene_id),
                "story_id": str(story_id),
                "status": "open",
            }
        )
    )
    # Newest first; cap at limit.
    docs.sort(key=lambda d: d.get("created_at") or datetime.min, reverse=True)
    return [_doc_to_response(d) for d in docs[:limit]]


def mongodb_mark_foreshadowing_paid(
    foreshadowing_id: UUID, *, paid_at_turn: int
) -> ForeshadowingResponse | None:
    """Mark an open item as paid; returns the updated response (or None if missing)."""
    mongo_client = get_mongodb_client()
    coll = mongo_client["scene_foreshadowing"]
    coll.update_one(
        {"foreshadowing_id": str(foreshadowing_id)},
        {
            "$set": {
                "status": "paid",
                "paid_at": datetime.now(UTC),
                "paid_at_turn": int(paid_at_turn),
            }
        },
    )
    docs = list(coll.find({"foreshadowing_id": str(foreshadowing_id)}))
    if not docs:
        return None
    return _doc_to_response(docs[0])