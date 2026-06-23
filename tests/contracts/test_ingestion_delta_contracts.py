"""Contract tests for the IngestionDelta schemas (P2-6 re-ingestion delta).

Verifies that ingestion_delta Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce numeric / length / pattern constraints,
- compute has_changes and apply_decision properties correctly.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from monitor_data.schemas.ingestion_delta import (
    DeltaCategory,
    DeltaItem,
    IngestionDelta,
    IngestionDeltaApplyRequest,
)
from pydantic import ValidationError


pytestmark = pytest.mark.unit


# =============================================================================
# DeltaCategory
# =============================================================================


class TestDeltaCategory:
    def test_values(self):
        assert DeltaCategory.ADDED.value == "added"
        assert DeltaCategory.MODIFIED.value == "modified"
        assert DeltaCategory.UNCHANGED.value == "unchanged"
        assert DeltaCategory.REMOVED.value == "removed"

    def test_iteration(self):
        categories = list(DeltaCategory)
        assert len(categories) == 4


# =============================================================================
# DeltaItem
# =============================================================================


class TestDeltaItem:
    def test_minimal(self):
        item = DeltaItem(
            item_index=0,
            delta_category=DeltaCategory.ADDED,
            field_name="axioms",
            summary="new axiom about magic",
        )
        assert item.item_index == 0
        assert item.delta_category == DeltaCategory.ADDED
        assert item.field_name == "axioms"
        assert item.summary == "new axiom about magic"
        assert item.changed_fields == []
        assert item.item_snapshot == {}
        assert item.confidence_delta is None
        assert item.source_ref is None

    def test_with_changed_fields(self):
        item = DeltaItem(
            item_index=3,
            delta_category=DeltaCategory.MODIFIED,
            field_name="entities",
            summary="armor class changed",
            changed_fields=["properties.armor_class", "name"],
            item_snapshot={"id": "x", "name": "Ogre"},
        )
        assert "properties.armor_class" in item.changed_fields
        assert item.item_snapshot["name"] == "Ogre"

    def test_with_confidence_delta(self):
        item = DeltaItem(
            item_index=0,
            delta_category=DeltaCategory.MODIFIED,
            field_name="axioms",
            summary="x",
            confidence_delta=0.15,
        )
        assert item.confidence_delta == 0.15

    def test_with_source_ref(self):
        item = DeltaItem(
            item_index=0,
            delta_category=DeltaCategory.UNCHANGED,
            field_name="lore_facts",
            summary="unchanged",
            source_ref="page 42 ¶3",
        )
        assert item.source_ref == "page 42 ¶3"

    def test_field_name_too_long(self):
        with pytest.raises(ValidationError):
            DeltaItem(
                item_index=0,
                delta_category=DeltaCategory.ADDED,
                field_name="x" * 51,
                summary="x",
            )

    def test_summary_too_long(self):
        with pytest.raises(ValidationError):
            DeltaItem(
                item_index=0,
                delta_category=DeltaCategory.ADDED,
                field_name="x",
                summary="x" * 301,
            )

    def test_source_ref_too_long(self):
        with pytest.raises(ValidationError):
            DeltaItem(
                item_index=0,
                delta_category=DeltaCategory.ADDED,
                field_name="x",
                summary="x",
                source_ref="x" * 201,
            )

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            DeltaItem(
                item_index=0,
                delta_category="bogus",  # type: ignore[arg-type]
                field_name="x",
                summary="x",
            )

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            DeltaItem()  # type: ignore[call-arg]


# =============================================================================
# IngestionDelta
# =============================================================================


class TestIngestionDelta:
    def test_minimal(self):
        sid = uuid4()
        d = IngestionDelta(source_id=sid, change_significance="minimal")
        assert d.source_id == sid
        assert d.pack_id_current is None
        assert d.pack_id_new is None
        assert d.total_axioms == 0
        assert d.total_entities == 0
        assert d.total_lore_facts == 0
        assert d.total_relationships == 0
        assert d.total_random_tables == 0
        assert d.total_agendas == 0
        assert d.total_topologies == 0
        assert d.total_plot_threads == 0
        assert d.axioms_delta == []
        assert d.net_new_items == 0
        assert d.modified_items == 0
        assert d.removed_items == 0
        assert d.unchanged_items == 0
        assert d.recommendations == []

    def test_full(self):
        sid = uuid4()
        d = IngestionDelta(
            source_id=sid,
            pack_id_current=uuid4(),
            pack_id_new=uuid4(),
            total_axioms=10,
            total_entities=5,
            total_lore_facts=20,
            total_relationships=8,
            total_random_tables=2,
            total_agendas=1,
            total_topologies=3,
            total_plot_threads=4,
            net_new_items=2,
            modified_items=1,
            removed_items=0,
            unchanged_items=53,
            change_significance="moderate",
            recommendations=["Review modified items manually"],
        )
        assert d.net_new_items == 2
        assert d.modified_items == 1
        assert d.unchanged_items == 53

    def test_required_source_id(self):
        with pytest.raises(ValidationError):
            IngestionDelta(change_significance="minimal")  # type: ignore[call-arg]

    def test_change_significance_too_long(self):
        with pytest.raises(ValidationError):
            IngestionDelta(source_id=uuid4(), change_significance="x" * 51)

    def test_has_changes_true_when_added(self):
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="minimal",
            net_new_items=1,
        )
        assert d.has_changes is True

    def test_has_changes_true_when_modified(self):
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="minimal",
            modified_items=1,
        )
        assert d.has_changes is True

    def test_has_changes_true_when_removed(self):
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="minimal",
            removed_items=1,
        )
        assert d.has_changes is True

    def test_has_changes_false(self):
        d = IngestionDelta(source_id=uuid4(), change_significance="minimal")
        assert d.has_changes is False

    def test_apply_decision_skip(self):
        d = IngestionDelta(source_id=uuid4(), change_significance="minimal")
        assert d.apply_decision == "skip"

    def test_apply_decision_auto_apply_minimal(self):
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="minimal",
            net_new_items=1,
        )
        assert d.apply_decision == "auto_apply"

    def test_apply_decision_auto_apply_minor(self):
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="minor",
            net_new_items=1,
        )
        assert d.apply_decision == "auto_apply"

    def test_apply_decision_approve_review_moderate(self):
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="moderate",
            net_new_items=1,
        )
        assert d.apply_decision == "approve_review"

    def test_apply_decision_approve_review_significant(self):
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="significant",
            modified_items=1,
        )
        assert d.apply_decision == "approve_review"

    def test_apply_decision_approve_review_major(self):
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="major",
            removed_items=1,
        )
        assert d.apply_decision == "approve_review"

    def test_with_delta_items(self):
        item = DeltaItem(
            item_index=0,
            delta_category=DeltaCategory.ADDED,
            field_name="axioms",
            summary="new axiom",
        )
        d = IngestionDelta(
            source_id=uuid4(),
            change_significance="moderate",
            axioms_delta=[item],
        )
        assert len(d.axioms_delta) == 1
        assert d.axioms_delta[0].delta_category == DeltaCategory.ADDED


# =============================================================================
# IngestionDeltaApplyRequest
# =============================================================================


class TestIngestionDeltaApplyRequest:
    def test_minimal(self):
        delta = IngestionDelta(source_id=uuid4(), change_significance="minimal")
        req = IngestionDeltaApplyRequest(
            source_id=uuid4(),
            delta=delta,
            multiverse_id=uuid4(),
        )
        assert req.universe_id is None
        assert req.include_added is True
        assert req.include_modified is True
        assert req.proposer == "IngestionPipeline"
        assert req.conflict_resolution == "merge"

    def test_full(self):
        delta = IngestionDelta(source_id=uuid4(), change_significance="moderate")
        req = IngestionDeltaApplyRequest(
            source_id=uuid4(),
            delta=delta,
            multiverse_id=uuid4(),
            universe_id=uuid4(),
            include_added=False,
            include_modified=False,
            proposer="GM",
            conflict_resolution="force",
        )
        assert req.include_added is False
        assert req.proposer == "GM"
        assert req.conflict_resolution == "force"

    def test_required_source_id(self):
        delta = IngestionDelta(source_id=uuid4(), change_significance="minimal")
        with pytest.raises(ValidationError):
            IngestionDeltaApplyRequest(
                delta=delta, multiverse_id=uuid4()  # type: ignore[call-arg]
            )

    def test_required_delta(self):
        with pytest.raises(ValidationError):
            IngestionDeltaApplyRequest(
                source_id=uuid4(), multiverse_id=uuid4()  # type: ignore[call-arg]
            )

    def test_required_multiverse_id(self):
        delta = IngestionDelta(source_id=uuid4(), change_significance="minimal")
        with pytest.raises(ValidationError):
            IngestionDeltaApplyRequest(
                source_id=uuid4(), delta=delta  # type: ignore[call-arg]
            )
