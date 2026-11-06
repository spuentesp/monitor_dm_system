"""Backtracking a turn removes what the scene wrote after the restore point (P-7)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_data.schemas.base import ProposalStatus
from monitor_data.tools.mongodb_tools import scene_rewind
from monitor_data.tools.mongodb_tools.scene_rewind import SceneRewindRefused, mongodb_rewind_scene

T = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
BEFORE, AFTER = T - timedelta(minutes=5), T + timedelta(minutes=5)


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, want in query.items():
        have = doc.get(key)
        if isinstance(want, dict):
            if "$gt" in want and not (have is not None and scene_rewind._aware(have) > want["$gt"]):
                return False
            if "$in" in want and have not in want["$in"]:
                return False
        elif have != want:
            return False
    return True


class _Collection:
    """Just the MongoDB operations the rewind uses, with Mongo's naive-UTC datetimes."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def insert(self, **doc: Any) -> None:
        self.docs.append({k: v.replace(tzinfo=None) if isinstance(v, datetime) else v for k, v in doc.items()})

    def find(self, query: dict[str, Any], _projection: Any = None) -> list[dict[str, Any]]:
        return [copy.deepcopy(d) for d in self.docs if _matches(d, query)]

    def find_one(self, query: dict[str, Any], _projection: Any = None) -> dict[str, Any] | None:
        return next(iter(self.find(query)), None)

    def delete_many(self, query: dict[str, Any]) -> Any:
        keep = [d for d in self.docs if not _matches(d, query)]
        removed, self.docs = len(self.docs) - len(keep), keep
        return SimpleNamespace(deleted_count=removed)

    def delete_one(self, query: dict[str, Any]) -> Any:
        return self.delete_many(query)

    def update_many(self, query: dict[str, Any], update: dict[str, Any]) -> Any:
        hits = [d for d in self.docs if _matches(d, query)]
        for doc in hits:
            doc.update(update.get("$set", {}))
            for field, cond in update.get("$pull", {}).items():
                if "$in" in cond:
                    doc[field] = [v for v in doc.get(field, []) if v not in cond["$in"]]
                else:
                    doc[field] = [v for v in doc.get(field, []) if not _matches(v, cond)]
        return SimpleNamespace(modified_count=len(hits))

    def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> Any:
        return self.update_many(query, update)


@pytest.fixture
def db():
    collections: dict[str, _Collection] = {}
    client = SimpleNamespace(get_collection=lambda name: collections.setdefault(name, _Collection()))
    with patch.object(scene_rewind, "get_mongodb_client", return_value=client):
        yield client.get_collection


@pytest.fixture
def scene(db):
    sid = uuid4()
    s = str(sid)
    db("scenes").insert(
        scene_id=s,
        turns=[
            {"turn_id": "t1", "timestamp": BEFORE.replace(tzinfo=None)},
            {"turn_id": "t2", "timestamp": AFTER.replace(tzinfo=None)},
        ],
        proposed_changes=["p1", "p2"],
    )
    for name, when, key in (("before", BEFORE, "1"), ("after", AFTER, "2")):
        db("proposed_changes").insert(
            proposal_id=f"p{key}", scene_id=s, status=ProposalStatus.PENDING.value, created_at=when
        )
        db("resolutions").insert(resolution_id=f"r{key}", scene_id=s, created_at=when)
        db("character_memories").insert(memory_id=f"m{key}", scene_id=s, created_at=when)
        db("scene_foreshadowing").insert(foreshadowing_id=f"f{key}", scene_id=s, created_at=when, status="open")
    db("scene_foreshadowing").insert(
        foreshadowing_id="paid", scene_id=s, created_at=BEFORE, status="paid", paid_at=AFTER, paid_at_turn=2
    )
    db("character_working_state").insert(
        state_id="ws1",
        scene_id=s,
        created_at=BEFORE,
        updated_at=AFTER,
        current_stats={"xp": 30},
        resources={"HP": 2},
        modifications=[
            {"stat_or_resource": "HP", "change": -1, "timestamp": BEFORE.isoformat()},
            {"stat_or_resource": "HP", "change": -4, "timestamp": AFTER.isoformat()},
        ],
    )
    # Another scene's writes are never touched.
    db("resolutions").insert(resolution_id="other", scene_id=str(uuid4()), created_at=AFTER)
    return sid


def _ids(db, name: str, key: str) -> list[str]:
    return [d[key] for d in db(name).docs]


def test_everything_written_after_the_point_is_removed(db, scene):
    earlier = {"ws1": {"current_stats": {"xp": 10}, "resources": {"HP": 6}}}
    result = mongodb_rewind_scene(scene, T, working_states=earlier)

    (doc,) = db("scenes").docs
    assert [t["turn_id"] for t in doc["turns"]] == ["t1"] and doc["proposed_changes"] == ["p1"]
    assert _ids(db, "proposed_changes", "proposal_id") == ["p1"]
    assert _ids(db, "resolutions", "resolution_id") == ["r1", "other"]
    assert _ids(db, "character_memories", "memory_id") == ["m1"]
    assert result.memory_ids_removed == ["m2"]
    assert _ids(db, "scene_foreshadowing", "foreshadowing_id") == ["f1", "paid"]
    paid = db("scene_foreshadowing").docs[1]
    assert paid["status"] == "open" and paid["paid_at"] is None and paid["paid_at_turn"] is None
    (state,) = db("character_working_state").docs
    assert state["resources"] == {"HP": 6} and state["current_stats"] == {"xp": 10}
    assert [m["change"] for m in state["modifications"]] == [-1]
    assert result.not_undone == []
    assert (result.turns_removed, result.proposals_removed, result.resolutions_removed) == (1, 1, 1)


def test_an_accepted_proposal_refuses_and_changes_nothing(db, scene):
    db("proposed_changes").docs[1]["status"] = ProposalStatus.ACCEPTED.value
    before = {name: copy.deepcopy(c.docs) for name, c in [(n, db(n)) for n in ("scenes", "resolutions")]}
    with pytest.raises(SceneRewindRefused, match="already accepted"):
        mongodb_rewind_scene(scene, T)
    assert db("scenes").docs == before["scenes"] and db("resolutions").docs == before["resolutions"]
    assert len(db("proposed_changes").docs) == 2


def test_a_rejected_proposal_never_reached_canon_so_it_is_removed(db, scene):
    db("proposed_changes").docs[1]["status"] = ProposalStatus.REJECTED.value
    assert mongodb_rewind_scene(scene, T).proposals_removed == 1
    assert _ids(db, "proposed_changes", "proposal_id") == ["p1"]


def test_a_working_state_created_after_the_point_is_removed(db, scene):
    db("character_working_state").insert(state_id="ws2", scene_id=str(scene), created_at=AFTER, modifications=[])
    result = mongodb_rewind_scene(scene, T, working_states={"ws1": {"current_stats": {}, "resources": {}}})
    assert _ids(db, "character_working_state", "state_id") == ["ws1"]
    assert result.working_states_removed == 1


def test_a_changed_working_state_without_an_earlier_copy_is_reported(db, scene):
    result = mongodb_rewind_scene(scene, T)
    (state,) = db("character_working_state").docs
    assert state["resources"] == {"HP": 2}  # Kept, since nothing says what it was.
    assert [m["change"] for m in state["modifications"]] == [-1]
    assert result.not_undone and "ws1" in result.not_undone[0]


def test_rewinding_again_to_the_same_point_finds_nothing_more(db, scene):
    mongodb_rewind_scene(scene, T, working_states={"ws1": {"current_stats": {}, "resources": {}}})
    again = mongodb_rewind_scene(scene, T)
    assert (again.turns_removed, again.proposals_removed, again.memory_ids_removed) == (0, 0, [])
    assert again.not_undone == [] and again.working_states_restored == 0


def test_a_turn_after_a_rewind_counts_as_a_change_again(db, scene):
    mongodb_rewind_scene(scene, T, working_states={"ws1": {"current_stats": {}, "resources": {}}})
    db("character_working_state").docs[0]["updated_at"] = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=1)
    assert mongodb_rewind_scene(scene, T).not_undone
