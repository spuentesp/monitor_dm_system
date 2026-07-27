"""
Direct behavior tests for mongodb_tools.snapshots and merge_candidates
(FINAL_FABLE T-042 — the two coverage cold spots).

Unlike the contract suites (which exercise re-exported signatures with
package-level fakes), these import the modules directly and drive the real
function bodies against an in-memory Mongo fake.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from monitor_data.schemas.merge_candidates import EntityMergeCandidate
from monitor_data.schemas.world_snapshots import WorldSnapshotCreate, WorldSnapshotFilter
from monitor_data.tools.mongodb_tools import merge_candidates as mc
from monitor_data.tools.mongodb_tools import snapshots as snap

# ─── In-memory Mongo fake ───────────────────────────────────────────────────


class _Result:
    def __init__(self, matched=0, modified=0, deleted=0):
        self.matched_count = matched
        self.modified_count = modified
        self.deleted_count = deleted


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]):
        self._docs = list(docs)

    def sort(self, key, direction=-1):
        if isinstance(key, list):
            key, direction = key[0]
        self._docs.sort(key=lambda d: d.get(key) or 0, reverse=direction == -1)
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    for k, v in query.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$gte" in v:
            if (doc.get(k) or 0) < v["$gte"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Collection:
    def __init__(self):
        self.docs: list[dict[str, Any]] = []

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        return _Result()

    def find_one(self, query):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        docs = [dict(d) for d in self.docs if _matches(d, query)]
        if projection:
            excluded = {k for k, v in projection.items() if v == 0}
            docs = [{k: v for k, v in d.items() if k not in excluded} for d in docs]
        return _Cursor(docs)

    def count_documents(self, query=None):
        query = query or {}
        return sum(1 for d in self.docs if _matches(d, query))

    def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return _Result(matched=1, modified=1)
        if upsert:
            new = dict(query)
            new.update(update.get("$set", {}))
            self.docs.append(new)
            return _Result(matched=0, modified=0)
        return _Result()

    def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _matches(d, query):
                del self.docs[i]
                return _Result(deleted=1)
        return _Result()


class _Client:
    def __init__(self):
        self.collections: dict[str, _Collection] = {}

    def get_collection(self, name):
        return self.collections.setdefault(name, _Collection())


@pytest.fixture()
def mongo(monkeypatch) -> _Client:
    client = _Client()
    monkeypatch.setattr(snap, "get_mongodb_client", lambda: client)
    monkeypatch.setattr(mc, "get_mongodb_client", lambda: client)
    return client


@pytest.fixture()
def world_state(monkeypatch) -> dict[str, Any]:
    eid = str(uuid4())
    state = {
        "entities": [{"id": eid, "name": "Barnaby", "entity_type": "character"}],
        "facts": [{"id": str(uuid4()), "statement": "Mist rises at dusk"}],
        "axioms": [],
        "relationships": [],
    }
    monkeypatch.setattr(snap, "neo4j_get_universe_state", lambda _uid: state)
    return state


# ─── Snapshots ──────────────────────────────────────────────────────────────


class TestSnapshotsDirect:
    def test_create_captures_counts(self, mongo, world_state):
        universe_id = uuid4()
        resp = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=universe_id, name="before-raid"))
        assert resp.entity_count == 1
        assert resp.fact_count == 1
        assert resp.relationship_count == 0
        stored = mongo.get_collection("world_snapshots").docs
        assert len(stored) == 1
        assert stored[0]["universe_id"] == str(universe_id)

    def test_get_round_trip_and_missing(self, mongo, world_state):
        resp = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=uuid4(), name="s1"))
        loaded = snap.mongodb_get_world_snapshot(resp.snapshot_id)
        assert loaded is not None
        assert loaded.name == "s1"
        assert snap.mongodb_get_world_snapshot(uuid4()) is None

    def test_list_filters_by_universe(self, mongo, world_state):
        u1, u2 = uuid4(), uuid4()
        snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=u1, name="a"))
        snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=u1, name="b"))
        snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=u2, name="c"))
        res = snap.mongodb_list_world_snapshots(WorldSnapshotFilter(universe_id=u1))
        assert res.total == 2
        assert {s.name for s in res.snapshots} == {"a", "b"}

    def test_delete(self, mongo, world_state):
        resp = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=uuid4(), name="gone"))
        assert snap.mongodb_delete_world_snapshot(resp.snapshot_id) is True
        assert snap.mongodb_delete_world_snapshot(resp.snapshot_id) is False

    def test_restore_missing_raises(self, mongo, world_state):
        with pytest.raises(ValueError, match="not found"):
            snap.mongodb_restore_world_snapshot(uuid4())

    def test_restore_creates_proposals(self, mongo, world_state, monkeypatch):
        created: list[Any] = []
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.proposals.mongodb_create_proposed_change",
            lambda params: created.append(params) or params,
        )
        resp = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=uuid4(), name="restore-me"))
        result = snap.mongodb_restore_world_snapshot(resp.snapshot_id)
        assert isinstance(result, dict)
        # one proposal per entity + per fact in the captured state
        assert len(created) >= 2

    def test_compare_diffs_added_removed_modified(self, mongo, monkeypatch):
        universe_id = uuid4()
        kept = {"id": "kept", "name": "Kept", "entity_type": "character"}
        removed = {"id": "removed", "name": "Removed", "entity_type": "character"}
        modified_a = {"id": "mod", "name": "Old Name", "entity_type": "character"}
        modified_b = {"id": "mod", "name": "New Name", "entity_type": "character"}
        added = {"id": "added", "name": "Added", "entity_type": "character"}

        states = iter(
            [
                {
                    "entities": [kept, removed, modified_a],
                    "facts": [],
                    "axioms": [],
                    "relationships": [],
                },
                {
                    "entities": [kept, modified_b, added],
                    "facts": [],
                    "axioms": [],
                    "relationships": [],
                },
            ]
        )
        monkeypatch.setattr(snap, "neo4j_get_universe_state", lambda _uid: next(states))

        a = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=universe_id, name="a"))
        b = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=universe_id, name="b"))
        cmp_resp = snap.mongodb_compare_snapshots(a.snapshot_id, b.snapshot_id)
        assert cmp_resp.entities_added == 1
        assert cmp_resp.entities_removed == 1
        assert cmp_resp.entities_modified >= 1

    def test_compare_rejects_cross_universe(self, mongo, world_state):
        a = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=uuid4(), name="a"))
        b = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=uuid4(), name="b"))
        with pytest.raises(ValueError, match="different universes"):
            snap.mongodb_compare_snapshots(a.snapshot_id, b.snapshot_id)

    def test_compare_missing_raises(self, mongo, world_state):
        a = snap.mongodb_create_world_snapshot(WorldSnapshotCreate(universe_id=uuid4(), name="a"))
        with pytest.raises(ValueError, match="not found"):
            snap.mongodb_compare_snapshots(a.snapshot_id, uuid4())


# ─── Merge candidates ───────────────────────────────────────────────────────


def _candidate(universe_id=None, confidence=0.9) -> EntityMergeCandidate:
    return EntityMergeCandidate(
        candidate_id=uuid4(),
        universe_id=universe_id or uuid4(),
        entity_ids=[uuid4(), uuid4()],
        merge_confidence=confidence,
        confidence_level="high" if confidence > 0.85 else "medium",
        similarity_metrics={"name": confidence},
        conflicting_fields=[],
        agreed_fields=["name"],
        source_pack_ids=[],
        created_at=datetime.now(UTC),
        reviewed_at=None,
    )


class TestMergeCandidatesDirect:
    def test_save_get_round_trip(self, mongo):
        cand = _candidate()
        mc.mongodb_save_merge_candidate(cand)
        loaded = mc.mongodb_get_merge_candidate(cand.candidate_id)
        assert loaded is not None
        assert loaded.candidate_id == cand.candidate_id
        assert mc.mongodb_get_merge_candidate(uuid4()) is None

    def test_save_is_upsert(self, mongo):
        cand = _candidate()
        mc.mongodb_save_merge_candidate(cand)
        mc.mongodb_save_merge_candidate(cand)
        assert mongo.get_collection("entity_merge_candidates").count_documents({}) == 1

    def test_list_scopes_to_universe(self, mongo):
        u = uuid4()
        mc.mongodb_save_merge_candidate(_candidate(universe_id=u))
        mc.mongodb_save_merge_candidate(_candidate(universe_id=u))
        mc.mongodb_save_merge_candidate(_candidate())
        listed = mc.mongodb_list_merge_candidates(universe_id=u)
        assert len(listed) == 2

    def test_mark_reviewed(self, mongo):
        cand = _candidate()
        mc.mongodb_save_merge_candidate(cand)
        assert mc.mongodb_mark_candidate_reviewed(cand.candidate_id) is True
        doc = mongo.get_collection("entity_merge_candidates").find_one({"candidate_id": str(cand.candidate_id)})
        assert doc["status"] == "reviewed"
        assert mc.mongodb_mark_candidate_reviewed(uuid4()) is False

    def test_delete(self, mongo):
        cand = _candidate()
        mc.mongodb_save_merge_candidate(cand)
        assert mc.mongodb_delete_merge_candidate(cand.candidate_id) is True
        assert mc.mongodb_delete_merge_candidate(cand.candidate_id) is False

    def test_detect_finds_similar_names(self, mongo):
        u = uuid4()
        entities = [
            {"id": str(uuid4()), "name": "Barnaby the Innkeeper", "entity_type": "character"},
            {"id": str(uuid4()), "name": "Barnaby the Inkeeper", "entity_type": "character"},
            {"id": str(uuid4()), "name": "Completely Different", "entity_type": "location"},
        ]
        # Weighted similarity for name-only entities tops out ~0.7; use 0.6
        candidates = mc.mongodb_detect_merge_candidates(entities, u, min_confidence=0.6)
        assert len(candidates) >= 1
        assert all(c.universe_id == u for c in candidates)

    def test_detect_ignores_dissimilar(self, mongo):
        u = uuid4()
        entities = [
            {"id": str(uuid4()), "name": "Alpha", "entity_type": "character"},
            {"id": str(uuid4()), "name": "Omega Station", "entity_type": "location"},
        ]
        assert mc.mongodb_detect_merge_candidates(entities, u, min_confidence=0.7) == []
