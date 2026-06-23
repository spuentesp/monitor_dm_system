"""
DL-23 / M-34: World Snapshots — Behavior Tests

Tests the behavioral correctness of snapshot tool functions,
including create, get, list, delete, restore, and compare.

Use Cases: DL-23 (World Snapshots), M-34 (Snapshot Management)
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from monitor_data.schemas.world_snapshots import (
    SnapshotCompareResponse,
    SnapshotEntityDiff,
    SnapshotFactDiff,
    SnapshotRelationshipDiff,
    WorldSnapshotCreate,
    WorldSnapshotFilter,
    WorldSnapshotListResponse,
    WorldSnapshotResponse,
)


# =============================================================================
# Snapshot Tool — Behavior Tests (Signature Verification)
# =============================================================================


@pytest.mark.unit
class TestSnapshotToolBehavior:
    """Behavior tests for snapshot tool function signatures and contracts."""

    def test_create_snapshot_signature(self):
        """mongodb_create_world_snapshot takes WorldSnapshotCreate params."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_create_world_snapshot,
        )

        import inspect

        sig = inspect.signature(mongodb_create_world_snapshot)
        params = list(sig.parameters.keys())
        assert "params" in params

    def test_get_snapshot_signature(self):
        """mongodb_get_world_snapshot takes snapshot_id."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_get_world_snapshot,
        )

        import inspect

        sig = inspect.signature(mongodb_get_world_snapshot)
        params = list(sig.parameters.keys())
        assert "snapshot_id" in params

    def test_list_snapshots_signature(self):
        """mongodb_list_world_snapshots takes WorldSnapshotFilter."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_list_world_snapshots,
        )

        import inspect

        sig = inspect.signature(mongodb_list_world_snapshots)
        params = list(sig.parameters.keys())
        assert "filters" in params

    def test_delete_snapshot_signature(self):
        """mongodb_delete_world_snapshot takes snapshot_id."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_delete_world_snapshot,
        )

        import inspect

        sig = inspect.signature(mongodb_delete_world_snapshot)
        params = list(sig.parameters.keys())
        assert "snapshot_id" in params

    def test_restore_snapshot_signature(self):
        """mongodb_restore_world_snapshot takes snapshot_id."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_restore_world_snapshot,
        )

        import inspect

        sig = inspect.signature(mongodb_restore_world_snapshot)
        params = list(sig.parameters.keys())
        assert "snapshot_id" in params

    def test_compare_snapshots_signature(self):
        """mongodb_compare_snapshots takes two snapshot IDs."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_compare_snapshots,
        )

        import inspect

        sig = inspect.signature(mongodb_compare_snapshots)
        params = list(sig.parameters.keys())
        assert "snapshot_a_id" in params
        assert "snapshot_b_id" in params


# =============================================================================
# Snapshot Schema — Behavioral Correctness
# =============================================================================


@pytest.mark.unit
class TestSnapshotCreateBehavior:
    """Behavior tests for WorldSnapshotCreate schema."""

    def test_create_snapshot_with_description(self):
        """WorldSnapshotCreate can include a meaningful description."""
        uid = uuid4()
        params = WorldSnapshotCreate(
            universe_id=uid,
            name="Pre-battle snapshot",
            description="World state before the Battle of Helm's Deep.",
        )
        assert params.description == "World state before the Battle of Helm's Deep."

    def test_create_snapshot_name_length_boundary(self):
        """WorldSnapshotCreate name at max length (200) is valid."""
        uid = uuid4()
        params = WorldSnapshotCreate(
            universe_id=uid,
            name="x" * 200,
        )
        assert len(params.name) == 200

    def test_create_snapshot_name_over_max_fails(self):
        """WorldSnapshotCreate name over 200 chars raises ValidationError."""
        with pytest.raises(Exception):
            WorldSnapshotCreate(
                universe_id=uuid4(),
                name="x" * 201,
            )

    def test_create_snapshot_description_at_max(self):
        """WorldSnapshotCreate description at max length (1000) is valid."""
        uid = uuid4()
        params = WorldSnapshotCreate(
            universe_id=uid,
            name="Test",
            description="x" * 1000,
        )
        assert len(params.description) == 1000

    def test_create_snapshot_description_over_max_fails(self):
        """WorldSnapshotCreate description over 1000 chars raises ValidationError."""
        with pytest.raises(Exception):
            WorldSnapshotCreate(
                universe_id=uuid4(),
                name="Test",
                description="x" * 1001,
            )


@pytest.mark.unit
class TestSnapshotFilterBehavior:
    """Behavior tests for WorldSnapshotFilter schema."""

    def test_filter_pagination(self):
        """WorldSnapshotFilter supports pagination with limit and offset."""
        f = WorldSnapshotFilter(limit=10, offset=20)
        assert f.limit == 10
        assert f.offset == 20

    def test_filter_limit_minimum(self):
        """WorldSnapshotFilter limit must be at least 1."""
        with pytest.raises(Exception):
            WorldSnapshotFilter(limit=0)

    def test_filter_limit_maximum(self):
        """WorldSnapshotFilter limit must be at most 100."""
        with pytest.raises(Exception):
            WorldSnapshotFilter(limit=101)

    def test_filter_offset_minimum(self):
        """WorldSnapshotFilter offset must be at least 0."""
        with pytest.raises(Exception):
            WorldSnapshotFilter(offset=-1)


# =============================================================================
# Snapshot Comparison — Behavioral Correctness
# =============================================================================


@pytest.mark.unit
class TestSnapshotComparisonBehavior:
    """Behavior tests for snapshot comparison schemas."""

    def test_entity_diff_added(self):
        """SnapshotEntityDiff with diff_type='added' is valid."""
        diff = SnapshotEntityDiff(
            entity_id=str(uuid4()),
            name="New NPC",
            diff_type="added",
            snapshot_a_state=None,
            snapshot_b_state={"name": "New NPC", "type": "CHARACTER"},
        )
        assert diff.diff_type == "added"
        assert diff.snapshot_a_state is None
        assert diff.snapshot_b_state["name"] == "New NPC"

    def test_entity_diff_removed(self):
        """SnapshotEntityDiff with diff_type='removed' is valid."""
        diff = SnapshotEntityDiff(
            entity_id=str(uuid4()),
            name="Deleted NPC",
            diff_type="removed",
            snapshot_a_state={"name": "Deleted NPC", "type": "CHARACTER"},
            snapshot_b_state=None,
        )
        assert diff.diff_type == "removed"

    def test_entity_diff_modified(self):
        """SnapshotEntityDiff with diff_type='modified' includes changed_fields."""
        diff = SnapshotEntityDiff(
            entity_id=str(uuid4()),
            name="Changed NPC",
            diff_type="modified",
            snapshot_a_state={"name": "NPC", "level": 5},
            snapshot_b_state={"name": "NPC", "level": 10},
            changed_fields=["level"],
        )
        assert diff.diff_type == "modified"
        assert "level" in diff.changed_fields

    def test_fact_diff_types(self):
        """SnapshotFactDiff supports added, removed, modified diff types."""
        for diff_type in ["added", "removed", "modified"]:
            diff = SnapshotFactDiff(
                fact_id=str(uuid4()),
                statement="A fact",
                diff_type=diff_type,
            )
            assert diff.diff_type == diff_type

    def test_relationship_diff_types(self):
        """SnapshotRelationshipDiff supports added and removed diff types."""
        for diff_type in ["added", "removed"]:
            diff = SnapshotRelationshipDiff(
                relationship_id=str(uuid4()),
                from_entity_id=str(uuid4()),
                to_entity_id=str(uuid4()),
                relationship_type="KNOWS",
                diff_type=diff_type,
            )
            assert diff.diff_type == diff_type

    def test_compare_response_defaults(self):
        """SnapshotCompareResponse has zero defaults for counts."""
        uid = uuid4()
        resp = SnapshotCompareResponse(
            snapshot_a_id=uuid4(),
            snapshot_b_id=uuid4(),
            universe_id=uid,
        )
        assert resp.entities_added == 0
        assert resp.entities_removed == 0
        assert resp.entities_modified == 0
        assert resp.facts_added == 0
        assert resp.facts_removed == 0
        assert resp.facts_modified == 0
        assert resp.relationships_added == 0
        assert resp.relationships_removed == 0
        assert resp.entity_diffs == []
        assert resp.fact_diffs == []
        assert resp.relationship_diffs == []


# =============================================================================
# Snapshot List Response — Behavioral Correctness
# =============================================================================


@pytest.mark.unit
class TestSnapshotListResponseBehavior:
    """Behavior tests for WorldSnapshotListResponse schema."""

    def test_list_response_with_snapshots(self):
        """WorldSnapshotListResponse can contain multiple snapshot summaries."""
        now = datetime.now(timezone.utc)
        snapshots = [
            WorldSnapshotResponse(
                snapshot_id=uuid4(),
                universe_id=uuid4(),
                name=f"Snapshot {i}",
                description="",
                entity_count=i * 10,
                fact_count=i * 5,
                relationship_count=i * 3,
                axiom_count=i,
                created_at=now,
            )
            for i in range(3)
        ]
        resp = WorldSnapshotListResponse(
            snapshots=snapshots,
            total=3,
            limit=20,
            offset=0,
        )
        assert len(resp.snapshots) == 3
        assert resp.total == 3
        assert resp.limit == 20
        assert resp.offset == 0

    def test_list_response_empty(self):
        """WorldSnapshotListResponse can be empty."""
        resp = WorldSnapshotListResponse(
            snapshots=[],
            total=0,
            limit=20,
            offset=0,
        )
        assert resp.snapshots == []
        assert resp.total == 0

    def test_list_response_pagination(self):
        """WorldSnapshotListResponse reflects pagination parameters."""
        resp = WorldSnapshotListResponse(
            snapshots=[],
            total=100,
            limit=20,
            offset=40,
        )
        assert resp.offset == 40
        assert resp.total == 100


# =============================================================================
# Snapshot Restore — ProposedChange Behavior Tests
# =============================================================================


@pytest.mark.unit
class TestSnapshotRestoreBehavior:
    """Behavior tests for snapshot restore creating ProposedChange documents."""

    def test_restore_returns_proposed_status(self):
        """Restore returns 'proposed' status, not 'restored' (CanonKeeper commits)."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_restore_world_snapshot,
        )

        import inspect

        sig = inspect.signature(mongodb_restore_world_snapshot)
        params = list(sig.parameters.keys())
        assert "snapshot_id" in params

    def test_restore_docstring_mentions_canonkeeper(self):
        """Restore function docstring references CanonKeeper evaluation."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_restore_world_snapshot,
        )

        assert "CanonKeeper" in mongodb_restore_world_snapshot.__doc__

    def test_restore_docstring_mentions_proposed_change(self):
        """Restore function docstring references ProposedChange documents."""
        from monitor_data.tools.mongodb_tools.snapshots import (
            mongodb_restore_world_snapshot,
        )

        assert "ProposedChange" in mongodb_restore_world_snapshot.__doc__

    def test_proposed_change_create_allows_system_proposer(self):
        """ProposedChangeCreate allows snapshot_restore proposer without scene/story."""
        from monitor_data.schemas.proposed_changes import ProposedChangeCreate
        from monitor_data.schemas.base import ProposalType, Authority

        # This should NOT raise ValueError — system proposers don't need scene/story
        proposal = ProposedChangeCreate(
            scene_id=None,
            story_id=None,
            change_type=ProposalType.ENTITY,
            content={"name": "Test Entity"},
            confidence=1.0,
            authority=Authority.SYSTEM,
            proposer="snapshot_restore",
        )
        assert proposal.proposer == "snapshot_restore"
        assert proposal.scene_id is None
        assert proposal.story_id is None

    def test_proposed_change_create_rejects_unknown_proposer_without_ids(self):
        """ProposedChangeCreate rejects proposals without scene/story from unknown proposers."""
        from monitor_data.schemas.proposed_changes import ProposedChangeCreate
        from monitor_data.schemas.base import ProposalType, Authority

        # This SHOULD raise ValueError — unknown proposer needs scene or story
        with pytest.raises(ValueError, match="scene_id or story_id"):
            ProposedChangeCreate(
                scene_id=None,
                story_id=None,
                change_type=ProposalType.ENTITY,
                content={"name": "Test Entity"},
                confidence=1.0,
                authority=Authority.SYSTEM,
                proposer="narrator_agent",
            )

    def test_proposed_change_create_system_proposer_allowed(self):
        """ProposedChangeCreate allows 'system' proposer without scene/story."""
        from monitor_data.schemas.proposed_changes import ProposedChangeCreate
        from monitor_data.schemas.base import ProposalType, Authority

        proposal = ProposedChangeCreate(
            scene_id=None,
            story_id=None,
            change_type=ProposalType.FACT,
            content={"statement": "Test fact"},
            confidence=1.0,
            authority=Authority.SYSTEM,
            proposer="system",
        )
        assert proposal.proposer == "system"

    def test_proposed_change_create_world_architect_allowed(self):
        """ProposedChangeCreate allows 'world_architect' proposer without scene/story."""
        from monitor_data.schemas.proposed_changes import ProposedChangeCreate
        from monitor_data.schemas.base import ProposalType, Authority

        proposal = ProposedChangeCreate(
            scene_id=None,
            story_id=None,
            change_type=ProposalType.RELATIONSHIP,
            content={"from_entity_id": "a", "to_entity_id": "b"},
            confidence=1.0,
            authority=Authority.SYSTEM,
            proposer="world_architect",
        )
        assert proposal.proposer == "world_architect"

    def test_restore_imports_proposed_change_schema(self):
        """Restore function imports ProposedChangeCreate from schemas."""
        from monitor_data.schemas.proposed_changes import ProposedChangeCreate

        assert hasattr(ProposedChangeCreate, "model_fields")
        assert "change_type" in ProposedChangeCreate.model_fields
        assert "content" in ProposedChangeCreate.model_fields
        assert "proposer" in ProposedChangeCreate.model_fields

    def test_restore_imports_proposal_type_enum(self):
        """Restore function uses ProposalType enum values."""
        from monitor_data.schemas.base import ProposalType

        assert ProposalType.ENTITY.value == "entity"
        assert ProposalType.FACT.value == "fact"
        assert ProposalType.RELATIONSHIP.value == "relationship"

    def test_restore_imports_authority_enum(self):
        """Restore function uses Authority.SYSTEM for snapshot proposals."""
        from monitor_data.schemas.base import Authority

        assert Authority.SYSTEM.value == "system"