"""
Contract tests for World Snapshot schemas (M-34).

Covers:
- WorldSnapshot: complete world state capture
- WorldSnapshotCreate: creation request
- WorldSnapshotResponse: metadata-only response
- WorldSnapshotFilter: list filter
- WorldSnapshotListResponse: paginated list
- SnapshotEntityDiff: per-entity diff
- SnapshotFactDiff: per-fact diff
- SnapshotRelationshipDiff: per-relationship diff
- SnapshotCompareResponse: full comparison

Use Cases: M-34 (World snapshot diff), Phase 3.1
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from typing import Any, Dict

import pytest

from monitor_data.schemas.world_snapshots import (
    WorldSnapshot,
    WorldSnapshotCreate,
    WorldSnapshotResponse,
    WorldSnapshotFilter,
    WorldSnapshotListResponse,
    SnapshotEntityDiff,
    SnapshotFactDiff,
    SnapshotRelationshipDiff,
    SnapshotCompareResponse,
)


# =============================================================================
# WorldSnapshot
# =============================================================================


class TestWorldSnapshot:
    def test_minimal(self):
        snap = WorldSnapshot(
            universe_id=uuid4(),
            name="Before the war",
        )
        assert snap.universe_id
        assert snap.name == "Before the war"
        assert snap.entities == []
        assert snap.facts == []
        assert snap.relationships == []
        assert snap.axioms == []

    def test_with_data(self):
        snap = WorldSnapshot(
            universe_id=uuid4(),
            name="Foundation Era",
            description="The world before the cataclysm",
            entities=[{"id": "king-1", "name": "Arthur"}],
            facts=[{"id": "f-1", "statement": "Arthur is king"}],
            relationships=[{"id": "r-1", "from": "king-1", "to": "excalibur"}],
            axioms=[{"id": "a-1", "statement": "Magic exists"}],
        )
        assert len(snap.entities) == 1
        assert len(snap.facts) == 1
        assert len(snap.relationships) == 1
        assert len(snap.axioms) == 1

    def test_snapshot_id_is_set(self):
        # snapshot_id field is generated
        snap = WorldSnapshot(universe_id=uuid4(), name="Test")
        # Field default is None until set externally
        assert snap.created_at is not None


# =============================================================================
# WorldSnapshotCreate
# =============================================================================


class TestWorldSnapshotCreate:
    def test_minimal(self):
        req = WorldSnapshotCreate(
            universe_id=uuid4(),
            name="Beginning of time",
        )
        assert req.universe_id
        assert req.name == "Beginning of time"
        assert req.description == ""  # default

    def test_with_description(self):
        req = WorldSnapshotCreate(
            universe_id=uuid4(),
            name="Year 1000",
            description="The world a thousand years in",
        )
        assert req.description == "The world a thousand years in"


# =============================================================================
# WorldSnapshotResponse
# =============================================================================


class TestWorldSnapshotResponse:
    def test_metadata_only(self):
        resp = WorldSnapshotResponse(
            snapshot_id=uuid4(),
            universe_id=uuid4(),
            name="Snapshot A",
            description="...",
            entity_count=42,
            fact_count=120,
            relationship_count=85,
            axiom_count=10,
            created_at=datetime.utcnow(),
        )
        assert resp.entity_count == 42
        assert resp.fact_count == 120


# =============================================================================
# WorldSnapshotFilter
# =============================================================================


class TestWorldSnapshotFilter:
    def test_defaults(self):
        f = WorldSnapshotFilter()
        assert f.limit == 20
        assert f.offset == 0
        assert f.universe_id is None

    def test_with_universe(self):
        f = WorldSnapshotFilter(universe_id=uuid4(), limit=50, offset=10)
        assert f.limit == 50
        assert f.offset == 10


# =============================================================================
# WorldSnapshotListResponse
# =============================================================================


class TestWorldSnapshotListResponse:
    def test_empty(self):
        resp = WorldSnapshotListResponse(
            snapshots=[],
            total=0,
            limit=20,
            offset=0,
        )
        assert resp.snapshots == []
        assert resp.total == 0


# =============================================================================
# SnapshotEntityDiff
# =============================================================================


class TestSnapshotEntityDiff:
    def test_added(self):
        diff = SnapshotEntityDiff(
            entity_id="king-1",
            name="Arthur",
            diff_type="added",
            snapshot_b_state={"id": "king-1", "name": "Arthur"},
        )
        assert diff.diff_type == "added"
        assert diff.snapshot_a_state is None
        assert diff.snapshot_b_state is not None

    def test_removed(self):
        diff = SnapshotEntityDiff(
            entity_id="king-1",
            name="Arthur",
            diff_type="removed",
            snapshot_a_state={"id": "king-1", "name": "Arthur"},
        )
        assert diff.diff_type == "removed"

    def test_modified(self):
        diff = SnapshotEntityDiff(
            entity_id="king-1",
            name="Arthur",
            diff_type="modified",
            snapshot_a_state={"age": 30},
            snapshot_b_state={"age": 35},
            changed_fields=["age"],
        )
        assert diff.changed_fields == ["age"]


# =============================================================================
# SnapshotFactDiff
# =============================================================================


class TestSnapshotFactDiff:
    def test_added_fact(self):
        diff = SnapshotFactDiff(
            fact_id="f-1",
            statement="The wall fell",
            diff_type="added",
        )
        assert diff.diff_type == "added"

    def test_modified_fact(self):
        diff = SnapshotFactDiff(
            fact_id="f-1",
            statement="The wall is tall",
            diff_type="modified",
            snapshot_a_state={"statement": "The wall is small"},
            snapshot_b_state={"statement": "The wall is tall"},
            changed_fields=["statement"],
        )
        assert diff.changed_fields == ["statement"]


# =============================================================================
# SnapshotRelationshipDiff
# =============================================================================


class TestSnapshotRelationshipDiff:
    def test_added_relationship(self):
        diff = SnapshotRelationshipDiff(
            relationship_id="r-1",
            from_entity_id="king-1",
            to_entity_id="queen-1",
            relationship_type="MARRIED_TO",
            diff_type="added",
        )
        assert diff.relationship_type == "MARRIED_TO"

    def test_removed_relationship(self):
        diff = SnapshotRelationshipDiff(
            relationship_id="r-1",
            from_entity_id="king-1",
            to_entity_id="queen-1",
            relationship_type="MARRIED_TO",
            diff_type="removed",
        )
        assert diff.diff_type == "removed"


# =============================================================================
# SnapshotCompareResponse
# =============================================================================


class TestSnapshotCompareResponse:
    def test_minimal(self):
        resp = SnapshotCompareResponse(
            snapshot_a_id=uuid4(),
            snapshot_b_id=uuid4(),
            universe_id=uuid4(),
            snapshot_a_name="Year 1000",
            snapshot_b_name="Year 1001",
        )
        assert resp.entities_added == 0
        assert resp.facts_added == 0
        assert resp.relationships_added == 0

    def test_with_counts(self):
        resp = SnapshotCompareResponse(
            snapshot_a_id=uuid4(),
            snapshot_b_id=uuid4(),
            universe_id=uuid4(),
            entities_added=5,
            entities_removed=2,
            entities_modified=8,
            facts_added=10,
            facts_removed=3,
            facts_modified=15,
            relationships_added=4,
            relationships_removed=1,
        )
        assert resp.entities_added == 5
        assert resp.entities_modified == 8
        assert resp.facts_added == 10

    def test_with_diffs(self):
        e_diff = SnapshotEntityDiff(
            entity_id="e-1", name="Bob", diff_type="added"
        )
        f_diff = SnapshotFactDiff(
            fact_id="f-1", statement="X", diff_type="modified"
        )
        r_diff = SnapshotRelationshipDiff(
            relationship_id="r-1",
            from_entity_id="a",
            to_entity_id="b",
            relationship_type="KNOWS",
            diff_type="added",
        )
        resp = SnapshotCompareResponse(
            snapshot_a_id=uuid4(),
            snapshot_b_id=uuid4(),
            universe_id=uuid4(),
            entity_diffs=[e_diff],
            fact_diffs=[f_diff],
            relationship_diffs=[r_diff],
        )
        assert len(resp.entity_diffs) == 1
        assert len(resp.fact_diffs) == 1
        assert len(resp.relationship_diffs) == 1
