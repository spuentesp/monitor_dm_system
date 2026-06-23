"""
DL-23: World Snapshots — Contract Tests

Tests the input/output contracts for MongoDB world snapshot tools.
These tests validate schema constraints, not database interactions.

Use Cases: DL-23 (World Snapshots), M-34
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from monitor_data.schemas.world_snapshots import (
    SnapshotCompareResponse,
    SnapshotEntityDiff,
    SnapshotFactDiff,
    SnapshotRelationshipDiff,
    WorldSnapshot,
    WorldSnapshotCreate,
    WorldSnapshotResponse,
    WorldSnapshotFilter,
    WorldSnapshotListResponse,
)


# =============================================================================
# WorldSnapshotCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestWorldSnapshotCreateContract:
    """Contract tests for WorldSnapshotCreate schema."""

    def test_snapshot_create_minimal(self):
        """WorldSnapshotCreate with only required fields is valid."""
        uid = uuid4()
        params = WorldSnapshotCreate(
            universe_id=uid,
            name="Before the battle",
        )
        assert params.universe_id == uid
        assert params.name == "Before the battle"
        assert params.description == ""

    def test_snapshot_create_with_description(self):
        """WorldSnapshotCreate can include a description."""
        params = WorldSnapshotCreate(
            universe_id=uuid4(),
            name="Pre-war snapshot",
            description="State before the war arc begins.",
        )
        assert params.description == "State before the war arc begins."

    def test_snapshot_create_empty_name_fails(self):
        """WorldSnapshotCreate with empty name raises ValidationError."""
        with pytest.raises(Exception):
            WorldSnapshotCreate(
                universe_id=uuid4(),
                name="",
            )

    def test_snapshot_create_too_long_name_fails(self):
        """WorldSnapshotCreate with name > 200 chars raises ValidationError."""
        with pytest.raises(Exception):
            WorldSnapshotCreate(
                universe_id=uuid4(),
                name="x" * 201,
            )

    def test_snapshot_create_too_long_description_fails(self):
        """WorldSnapshotCreate with description > 1000 chars raises ValidationError."""
        with pytest.raises(Exception):
            WorldSnapshotCreate(
                universe_id=uuid4(),
                name="test",
                description="x" * 1001,
            )


# =============================================================================
# WorldSnapshot contract tests
# =============================================================================


@pytest.mark.unit
class TestWorldSnapshotContract:
    """Contract tests for WorldSnapshot schema."""

    def test_snapshot_minimal(self):
        """WorldSnapshot with required fields is valid."""
        uid = uuid4()
        snapshot = WorldSnapshot(
            universe_id=uid,
            name="Test snapshot",
        )
        assert snapshot.universe_id == uid
        assert snapshot.name == "Test snapshot"
        assert snapshot.entities == []
        assert snapshot.facts == []
        assert snapshot.relationships == []
        assert snapshot.axioms == []

    def test_snapshot_with_content(self):
        """WorldSnapshot can include entities, facts, relationships, axioms."""
        snapshot = WorldSnapshot(
            universe_id=uuid4(),
            name="Full snapshot",
            description="Complete world state",
            entities=[{"id": str(uuid4()), "name": "Gandalf"}],
            facts=[{"id": str(uuid4()), "statement": "Magic exists"}],
            relationships=[{"id": str(uuid4()), "type": "KNOWS"}],
            axioms=[{"id": str(uuid4()), "statement": "Gods are real"}],
        )
        assert len(snapshot.entities) == 1
        assert len(snapshot.facts) == 1
        assert len(snapshot.relationships) == 1
        assert len(snapshot.axioms) == 1

    def test_snapshot_empty_name_fails(self):
        """WorldSnapshot with empty name raises ValidationError."""
        with pytest.raises(Exception):
            WorldSnapshot(
                universe_id=uuid4(),
                name="",
            )


# =============================================================================
# WorldSnapshotResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestWorldSnapshotResponseContract:
    """Contract tests for WorldSnapshotResponse schema."""

    def test_snapshot_response(self):
        """WorldSnapshotResponse with all fields is valid."""
        now = datetime.now(timezone.utc)
        resp = WorldSnapshotResponse(
            snapshot_id=uuid4(),
            universe_id=uuid4(),
            name="Test snapshot",
            description="A test",
            entity_count=10,
            fact_count=5,
            relationship_count=3,
            axiom_count=2,
            created_at=now,
        )
        assert resp.name == "Test snapshot"
        assert resp.entity_count == 10
        assert resp.fact_count == 5
        assert resp.relationship_count == 3
        assert resp.axiom_count == 2

    def test_snapshot_response_zero_counts(self):
        """WorldSnapshotResponse with zero counts is valid (empty snapshot)."""
        resp = WorldSnapshotResponse(
            snapshot_id=uuid4(),
            universe_id=uuid4(),
            name="Empty snapshot",
            description="",
            entity_count=0,
            fact_count=0,
            relationship_count=0,
            axiom_count=0,
            created_at=datetime.now(timezone.utc),
        )
        assert resp.entity_count == 0
        assert resp.fact_count == 0


# =============================================================================
# WorldSnapshotFilter contract tests
# =============================================================================


@pytest.mark.unit
class TestWorldSnapshotFilterContract:
    """Contract tests for WorldSnapshotFilter schema."""

    def test_filter_defaults(self):
        """WorldSnapshotFilter has sensible defaults."""
        f = WorldSnapshotFilter()
        assert f.universe_id is None
        assert f.limit == 20
        assert f.offset == 0

    def test_filter_with_universe(self):
        """WorldSnapshotFilter can filter by universe_id."""
        uid = uuid4()
        f = WorldSnapshotFilter(universe_id=uid)
        assert f.universe_id == uid

    def test_filter_limit_range(self):
        """WorldSnapshotFilter limit must be between 1 and 100."""
        with pytest.raises(Exception):
            WorldSnapshotFilter(limit=0)
        with pytest.raises(Exception):
            WorldSnapshotFilter(limit=101)

    def test_filter_offset_range(self):
        """WorldSnapshotFilter offset must be >= 0."""
        with pytest.raises(Exception):
            WorldSnapshotFilter(offset=-1)


# =============================================================================
# WorldSnapshotListResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestWorldSnapshotListResponseContract:
    """Contract tests for WorldSnapshotListResponse schema."""

    def test_list_response_empty(self):
        """WorldSnapshotListResponse with empty list is valid."""
        resp = WorldSnapshotListResponse(
            snapshots=[],
            total=0,
            limit=20,
            offset=0,
        )
        assert resp.snapshots == []
        assert resp.total == 0

    def test_list_response_with_snapshots(self):
        """WorldSnapshotListResponse can include snapshots."""
        snapshot = WorldSnapshotResponse(
            snapshot_id=uuid4(),
            universe_id=uuid4(),
            name="Test snapshot",
            description="",
            entity_count=5,
            fact_count=3,
            relationship_count=2,
            axiom_count=1,
            created_at=datetime.now(timezone.utc),
        )
        resp = WorldSnapshotListResponse(
            snapshots=[snapshot],
            total=1,
            limit=20,
            offset=0,
        )
        assert resp.total == 1
        assert resp.snapshots[0].name == "Test snapshot"


# =============================================================================
# SnapshotCompareResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestSnapshotCompareResponseContract:
    """Contract tests for SnapshotCompareResponse schema."""

    def test_compare_response_minimal(self):
        """SnapshotCompareResponse with minimal fields is valid."""
        uid = uuid4()
        sid_a = uuid4()
        sid_b = uuid4()
        resp = SnapshotCompareResponse(
            snapshot_a_id=sid_a,
            snapshot_b_id=sid_b,
            universe_id=uid,
        )
        assert resp.entities_added == 0
        assert resp.entities_removed == 0
        assert resp.entities_modified == 0
        assert resp.entity_diffs == []
        assert resp.fact_diffs == []
        assert resp.relationship_diffs == []

    def test_compare_response_with_counts(self):
        """SnapshotCompareResponse tracks diff counts."""
        uid = uuid4()
        sid_a = uuid4()
        sid_b = uuid4()
        resp = SnapshotCompareResponse(
            snapshot_a_id=sid_a,
            snapshot_b_id=sid_b,
            universe_id=uid,
            entities_added=3,
            entities_removed=1,
            entities_modified=2,
            facts_added=5,
            facts_removed=0,
            facts_modified=1,
            relationships_added=4,
            relationships_removed=2,
        )
        assert resp.entities_added == 3
        assert resp.entities_removed == 1
        assert resp.entities_modified == 2
        assert resp.facts_added == 5
        assert resp.facts_modified == 1

    def test_compare_response_with_diff_lists(self):
        """SnapshotCompareResponse accepts diff lists."""
        uid = uuid4()
        sid_a = uuid4()
        sid_b = uuid4()

        entity_diff = SnapshotEntityDiff(
            entity_id="e1",
            name="Theron",
            diff_type="added",
            snapshot_b_state={"id": "e1", "name": "Theron", "entity_type": "npc"},
        )
        fact_diff = SnapshotFactDiff(
            fact_id="f1",
            statement="Theron is a guard",
            diff_type="added",
            snapshot_b_state={"id": "f1", "statement": "Theron is a guard"},
        )
        rel_diff = SnapshotRelationshipDiff(
            relationship_id="r1",
            from_entity_id="e1",
            to_entity_id="e2",
            relationship_type="knows",
            diff_type="added",
        )

        resp = SnapshotCompareResponse(
            snapshot_a_id=sid_a,
            snapshot_b_id=sid_b,
            universe_id=uid,
            entity_diffs=[entity_diff],
            fact_diffs=[fact_diff],
            relationship_diffs=[rel_diff],
        )
        assert len(resp.entity_diffs) == 1
        assert len(resp.fact_diffs) == 1
        assert len(resp.relationship_diffs) == 1

    def test_compare_response_modified_entity(self):
        """SnapshotCompareResponse tracks changed fields."""
        diff = SnapshotEntityDiff(
            entity_id="e1",
            name="Theron",
            diff_type="modified",
            snapshot_a_state={"id": "e1", "name": "Theron", "level": 1},
            snapshot_b_state={"id": "e1", "name": "Theron", "level": 2},
            changed_fields=["level"],
        )
        resp = SnapshotCompareResponse(
            snapshot_a_id=uuid4(),
            snapshot_b_id=uuid4(),
            universe_id=uuid4(),
            entities_modified=1,
            entity_diffs=[diff],
        )
        assert resp.entities_modified == 1
        assert resp.entity_diffs[0].changed_fields == ["level"]

    def test_compare_response_metadata(self):
        """SnapshotCompareResponse includes snapshot metadata."""
        now = datetime.now(timezone.utc)
        resp = SnapshotCompareResponse(
            snapshot_a_id=uuid4(),
            snapshot_b_id=uuid4(),
            universe_id=uuid4(),
            snapshot_a_name="Before",
            snapshot_b_name="After",
            snapshot_a_created_at=now,
            snapshot_b_created_at=now,
        )
        assert resp.snapshot_a_name == "Before"
        assert resp.snapshot_b_name == "After"


@pytest.mark.unit
class TestSnapshotEntityDiffContract:
    """Contract tests for SnapshotEntityDiff schema."""

    def test_entity_diff_added(self):
        """SnapshotEntityDiff for added entity."""
        diff = SnapshotEntityDiff(
            entity_id="e1",
            name="New NPC",
            diff_type="added",
            snapshot_b_state={"id": "e1", "name": "New NPC"},
        )
        assert diff.diff_type == "added"
        assert diff.snapshot_a_state is None
        assert diff.snapshot_b_state is not None

    def test_entity_diff_removed(self):
        """SnapshotEntityDiff for removed entity."""
        diff = SnapshotEntityDiff(
            entity_id="e1",
            name="Old NPC",
            diff_type="removed",
            snapshot_a_state={"id": "e1", "name": "Old NPC"},
        )
        assert diff.diff_type == "removed"
        assert diff.snapshot_a_state is not None
        assert diff.snapshot_b_state is None

    def test_entity_diff_modified(self):
        """SnapshotEntityDiff for modified entity."""
        diff = SnapshotEntityDiff(
            entity_id="e1",
            name="Changed NPC",
            diff_type="modified",
            snapshot_a_state={"id": "e1", "level": 1},
            snapshot_b_state={"id": "e1", "level": 2},
            changed_fields=["level"],
        )
        assert diff.diff_type == "modified"
        assert diff.changed_fields == ["level"]


@pytest.mark.unit
class TestSnapshotFactDiffContract:
    """Contract tests for SnapshotFactDiff schema."""

    def test_fact_diff_added(self):
        """SnapshotFactDiff for added fact."""
        diff = SnapshotFactDiff(
            fact_id="f1",
            statement="The sky is blue",
            diff_type="added",
            snapshot_b_state={"id": "f1", "statement": "The sky is blue"},
        )
        assert diff.diff_type == "added"

    def test_fact_diff_modified(self):
        """SnapshotFactDiff for modified fact."""
        diff = SnapshotFactDiff(
            fact_id="f1",
            statement="Updated statement",
            diff_type="modified",
            snapshot_a_state={"id": "f1", "statement": "Old statement"},
            snapshot_b_state={"id": "f1", "statement": "Updated statement"},
            changed_fields=["statement"],
        )
        assert diff.diff_type == "modified"
        assert diff.changed_fields == ["statement"]


@pytest.mark.unit
class TestSnapshotRelationshipDiffContract:
    """Contract tests for SnapshotRelationshipDiff schema."""

    def test_rel_diff_added(self):
        """SnapshotRelationshipDiff for added relationship."""
        diff = SnapshotRelationshipDiff(
            relationship_id="r1",
            from_entity_id="e1",
            to_entity_id="e2",
            relationship_type="knows",
            diff_type="added",
        )
        assert diff.diff_type == "added"
        assert diff.relationship_type == "knows"

    def test_rel_diff_removed(self):
        """SnapshotRelationshipDiff for removed relationship."""
        diff = SnapshotRelationshipDiff(
            relationship_id="r1",
            from_entity_id="e1",
            to_entity_id="e2",
            relationship_type="loves",
            diff_type="removed",
            snapshot_a_state={"from_entity_id": "e1", "to_entity_id": "e2", "relationship_type": "loves"},
        )
        assert diff.diff_type == "removed"
        assert diff.relationship_type == "loves"


@pytest.mark.unit
class TestSnapshotToolSignatures:
    """Contract tests for snapshot MCP tool function signatures."""

    def test_mongodb_compare_snapshots_accepts_two_uuids(self):
        """mongodb_compare_snapshots takes two UUID parameters."""
        from monitor_data.tools.mongodb_tools.snapshots import mongodb_compare_snapshots
        import inspect

        sig = inspect.signature(mongodb_compare_snapshots)
        params = list(sig.parameters.keys())
        assert "snapshot_a_id" in params
        assert "snapshot_b_id" in params

    def test_mongodb_create_world_snapshot_accepts_params(self):
        """mongodb_create_world_snapshot accepts WorldSnapshotCreate."""
        from monitor_data.tools.mongodb_tools.snapshots import mongodb_create_world_snapshot
        import inspect

        sig = inspect.signature(mongodb_create_world_snapshot)
        assert "params" in sig.parameters

    def test_mongodb_get_world_snapshot_returns_optional(self):
        """mongodb_get_world_snapshot returns Optional[WorldSnapshot]."""
        from monitor_data.tools.mongodb_tools.snapshots import mongodb_get_world_snapshot
        import inspect

        sig = inspect.signature(mongodb_get_world_snapshot)
        assert "snapshot_id" in sig.parameters
        assert sig.return_annotation != inspect.Signature.empty

    def test_mongodb_list_world_snapshots_accepts_filter(self):
        """mongodb_list_world_snapshots accepts WorldSnapshotFilter."""
        from monitor_data.tools.mongodb_tools.snapshots import mongodb_list_world_snapshots
        import inspect

        sig = inspect.signature(mongodb_list_world_snapshots)
        assert "filters" in sig.parameters

    def test_mongodb_delete_world_snapshot_accepts_uuid(self):
        """mongodb_delete_world_snapshot accepts UUID parameter."""
        from monitor_data.tools.mongodb_tools.snapshots import mongodb_delete_world_snapshot
        import inspect

        sig = inspect.signature(mongodb_delete_world_snapshot)
        assert "snapshot_id" in sig.parameters

    def test_mongodb_restore_world_snapshot_accepts_uuid(self):
        """mongodb_restore_world_snapshot accepts UUID parameter."""
        from monitor_data.tools.mongodb_tools.snapshots import mongodb_restore_world_snapshot
        import inspect

        sig = inspect.signature(mongodb_restore_world_snapshot)
        assert "snapshot_id" in sig.parameters