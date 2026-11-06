"""Undo what a scene wrote after a point in time, for backtracking a turn (P-7).

Turns write outside the scene loop's checkpoints: the scene's turn entries, a resolution,
proposals, memories, foreshadowing, and the actor's working state. Rewinding the
checkpoint alone left all of that in place, so an undone turn came back on the next
load and its proposals could still be accepted into canon.

Records a turn inserts are removed. The working state is written in place, so it is put
back from a copy the caller supplies. Nothing here touches Neo4j: a proposal that was
already accepted makes the whole rewind refuse, since only CanonKeeper may change canon.
Pending and rejected ones never reached canon, so they are removed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, Field

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.base import ProposalStatus

log = structlog.get_logger()


class SceneRewindRefused(Exception):
    """A record written since the rewind point can't be undone here."""


class SceneRewindResult(BaseModel):
    """What a rewind removed or restored, so the caller can report it truthfully."""

    turns_removed: int = 0
    resolutions_removed: int = 0
    proposals_removed: int = 0
    memory_ids_removed: list[str] = Field(default_factory=list)
    foreshadowing_removed: int = 0
    foreshadowing_reopened: int = 0
    modifications_removed: int = 0
    working_states_removed: int = 0
    working_states_restored: int = 0
    not_undone: list[str] = Field(default_factory=list, description="What couldn't be put back, in words")


def _aware(value: Any) -> datetime | None:
    """Mongo returns naive UTC datetimes, and modifications hold ISO strings."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def mongodb_rewind_scene(
    scene_id: UUID,
    since: datetime,
    *,
    working_states: dict[str, dict[str, Any]] | None = None,
) -> SceneRewindResult:
    """Remove what scene ``scene_id`` wrote after ``since``.

    ``working_states`` maps a working state's ``state_id`` to its earlier
    ``current_stats`` and ``resources``. A working state changed after ``since``
    with no earlier copy is left alone and named in ``not_undone``.

    Authority: SceneLoop (backtrack)
    Use Case: P-7

    Raises:
        SceneRewindRefused: If a proposal written since then was accepted into canon.
    """
    since = _aware(since) or since
    scene = str(scene_id)
    db = get_mongodb_client()
    after = {"scene_id": scene, "created_at": {"$gt": since}}
    result = SceneRewindResult()

    proposals = db.get_collection("proposed_changes")
    written = list(proposals.find(after, {"proposal_id": 1, "status": 1}))
    accepted = [doc["proposal_id"] for doc in written if doc.get("status") == ProposalStatus.ACCEPTED.value]
    if accepted:
        raise SceneRewindRefused(
            f"{len(accepted)} change(s) from this turn were already accepted into canon, so the turn can't be undone."
        )

    proposal_ids = [doc["proposal_id"] for doc in written]
    if proposal_ids:
        result.proposals_removed = proposals.delete_many({"proposal_id": {"$in": proposal_ids}}).deleted_count

    scenes = db.get_collection("scenes")
    doc = scenes.find_one({"scene_id": scene}, {"turns": 1}) or {}
    later = [turn for turn in doc.get("turns") or [] if (_aware(turn.get("timestamp")) or since) > since]
    if later or proposal_ids:
        scenes.update_one(
            {"scene_id": scene},
            {
                "$pull": {
                    "turns": {"turn_id": {"$in": [turn["turn_id"] for turn in later]}},
                    "proposed_changes": {"$in": proposal_ids},
                },
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
    result.turns_removed = len(later)

    result.resolutions_removed = db.get_collection("resolutions").delete_many(after).deleted_count

    memories = db.get_collection("character_memories")
    result.memory_ids_removed = [doc["memory_id"] for doc in memories.find(after, {"memory_id": 1})]
    if result.memory_ids_removed:
        memories.delete_many({"memory_id": {"$in": result.memory_ids_removed}})

    foreshadowing = db.get_collection("scene_foreshadowing")
    result.foreshadowing_removed = foreshadowing.delete_many(after).deleted_count
    result.foreshadowing_reopened = foreshadowing.update_many(
        {"scene_id": scene, "paid_at": {"$gt": since}},
        {"$set": {"status": "open", "paid_at": None, "paid_at_turn": None}},
    ).modified_count

    _rewind_working_states(db.get_collection("character_working_state"), scene, since, working_states or {}, result)
    log.info("scene_rewound", scene_id=scene, since=since.isoformat(), **result.model_dump(exclude={"not_undone"}))
    return result


def _rewind_working_states(
    states: Any,
    scene: str,
    since: datetime,
    earlier: dict[str, dict[str, Any]],
    result: SceneRewindResult,
) -> None:
    for doc in states.find({"scene_id": scene}):
        state_id = doc["state_id"]
        created = _aware(doc.get("created_at"))
        if created is not None and created > since:
            states.delete_one({"state_id": state_id})
            result.working_states_removed += 1
            continue
        mods = doc.get("modifications") or []
        kept = [mod for mod in mods if (_aware(mod.get("timestamp")) or since) <= since]
        updated = doc.get("updated_at")
        # A rewind's own write isn't a change made by a turn.
        changed = (_aware(updated) or since) > since and updated != doc.get("rewound_at")
        if not changed and len(kept) == len(mods):
            continue
        now = datetime.now(UTC)
        update: dict[str, Any] = {"modifications": kept, "updated_at": now, "rewound_at": now}
        if state_id in earlier:
            snapshot = earlier[state_id]
            update["current_stats"] = snapshot.get("current_stats") or {}
            update["resources"] = snapshot.get("resources") or {}
            result.working_states_restored += 1
        elif changed:
            result.not_undone.append(f"working state {state_id}: no earlier copy, so its stats were kept")
        states.update_one({"state_id": state_id}, {"$set": update})
        result.modifications_removed += len(mods) - len(kept)
