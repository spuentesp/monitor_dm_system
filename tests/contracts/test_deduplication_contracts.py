"""
Contract tests for Deduplication schemas.

Covers:
- DeduplicationStrategy enum (4 strategies)
- DuplicateCategory enum (4 categories)
- DuplicateItemRef: ref to a single item
- DuplicateGroup: group of duplicates with strategy
- DeduplicationResult: full result
- DeduplicationApplyRequest: apply request

Use Cases: DL-5 (Deduplication before commit)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

import pytest

from monitor_data.schemas.deduplication import (
    DeduplicationStrategy,
    DuplicateCategory,
    DuplicateItemRef,
    DuplicateGroup,
    DeduplicationResult,
    DeduplicationApplyRequest,
)


# =============================================================================
# Enums
# =============================================================================


class TestDeduplicationStrategyEnum:
    def test_all_values(self):
        assert DeduplicationStrategy.KEEP_NEW.value == "keep_new"
        assert DeduplicationStrategy.KEEP_EXISTING.value == "keep_existing"
        assert DeduplicationStrategy.MERGE.value == "merge"
        assert DeduplicationStrategy.REVIEW.value == "review"


class TestDuplicateCategoryEnum:
    def test_all_values(self):
        assert DuplicateCategory.EXACT.value == "exact"
        assert DuplicateCategory.SEMANTIC.value == "semantic"
        assert DuplicateCategory.SUBSUMED.value == "subsumed"
        assert DuplicateCategory.CONFLICTING.value == "conflicting"


# =============================================================================
# DuplicateItemRef
# =============================================================================


class TestDuplicateItemRef:
    def test_minimal(self):
        ref = DuplicateItemRef(
            item_index=0,
            identity_value="Gandalf the Grey",
            confidence=1.0,
        )
        assert ref.item_index == 0
        assert ref.identity_value == "Gandalf the Grey"
        assert ref.content_hash is None
        assert ref.item_snapshot == {}

    def test_with_snapshot(self):
        ref = DuplicateItemRef(
            item_index=5,
            pack_id=uuid4(),
            identity_value="Mithrandir",
            confidence=0.9,
            content_hash="abc123def456",
            item_snapshot={"name": "Gandalf", "title": "Mithrandir"},
            source_ref="p. 142",
        )
        assert ref.content_hash == "abc123def456"
        assert ref.source_ref == "p. 142"

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            DuplicateItemRef(
                item_index=0,
                identity_value="x",
                confidence=1.5,
            )

    def test_item_index_bounds(self):
        with pytest.raises(Exception):
            DuplicateItemRef(
                item_index=-1,
                identity_value="x",
                confidence=0.5,
            )


# =============================================================================
# DuplicateGroup
# =============================================================================


class TestDuplicateGroup:
    def _make_item(self, idx, identity):
        return DuplicateItemRef(
            item_index=idx,
            identity_value=identity,
            confidence=1.0,
        )

    def test_minimal(self):
        items = [
            self._make_item(0, "Gandalf"),  # new
            self._make_item(1, "Gandalf the Grey"),  # existing
        ]
        g = DuplicateGroup(
            duplicate_id="dup-001",
            category=DuplicateCategory.SEMANTIC,
            field_name="entity_archetypes",
            identity_field="name",
            strategy=DeduplicationStrategy.KEEP_EXISTING,
            strategy_reason="Existing is more specific",
            similarity_score=0.95,
            items=items,
        )
        assert g.duplicate_id == "dup-001"
        assert g.items[0].identity_value == "Gandalf"  # new first

    def test_with_merge(self):
        items = [
            self._make_item(0, "Gandalf"),
            self._make_item(1, "Mithrandir"),
        ]
        g = DuplicateGroup(
            duplicate_id="dup-002",
            category=DuplicateCategory.SUBSUMED,
            field_name="lore_facts",
            identity_field="statement",
            strategy=DeduplicationStrategy.MERGE,
            strategy_reason="Both contain useful info",
            similarity_score=0.8,
            items=items,
            merged_content={"name": "Gandalf", "aliases": ["Mithrandir"]},
        )
        assert g.merged_content is not None
        assert "Mithrandir" in g.merged_content["aliases"]

    def test_similarity_bounds(self):
        items = [self._make_item(0, "x")]
        with pytest.raises(Exception):
            DuplicateGroup(
                duplicate_id="x",
                category=DuplicateCategory.EXACT,
                field_name="x",
                identity_field="x",
                strategy=DeduplicationStrategy.KEEP_NEW,
                strategy_reason="x",
                similarity_score=1.5,  # > 1.0
                items=items,
            )


# =============================================================================
# DeduplicationResult
# =============================================================================


class TestDeduplicationResult:
    def test_minimal(self):
        r = DeduplicationResult(
            new_pack_id=uuid4(),
            multiverse_id=uuid4(),
            auto_resolvable_count=0,
            review_required_count=0,
            total_items_checked=50,
        )
        assert r.duplicate_groups == []
        assert r.has_duplicates is False
        assert r.all_auto_resolvable is True

    def test_with_duplicates(self):
        items = [
            DuplicateItemRef(
                item_index=0,
                identity_value="x",
                confidence=0.9,
            ),
        ]
        g = DuplicateGroup(
            duplicate_id="x",
            category=DuplicateCategory.EXACT,
            field_name="axioms",
            identity_field="statement",
            strategy=DeduplicationStrategy.KEEP_NEW,
            strategy_reason="Identical",
            similarity_score=1.0,
            items=items,
        )
        r = DeduplicationResult(
            new_pack_id=uuid4(),
            multiverse_id=uuid4(),
            duplicate_groups=[g],
            auto_resolvable_count=1,
            review_required_count=0,
            total_items_checked=10,
        )
        assert r.has_duplicates is True
        assert r.all_auto_resolvable is True

    def test_review_required(self):
        items = [DuplicateItemRef(item_index=0, identity_value="x", confidence=0.7)]
        g = DuplicateGroup(
            duplicate_id="x",
            category=DuplicateCategory.CONFLICTING,
            field_name="x",
            identity_field="x",
            strategy=DeduplicationStrategy.REVIEW,
            strategy_reason="Same identity, different content",
            similarity_score=0.85,
            items=items,
        )
        r = DeduplicationResult(
            new_pack_id=uuid4(),
            multiverse_id=uuid4(),
            duplicate_groups=[g],
            auto_resolvable_count=0,
            review_required_count=1,
            total_items_checked=5,
        )
        assert r.all_auto_resolvable is False


# =============================================================================
# DeduplicationApplyRequest
# =============================================================================


class TestDeduplicationApplyRequest:
    def test_minimal(self):
        req = DeduplicationApplyRequest(
            new_pack_id=uuid4(),
            multiverse_id=uuid4(),
            decisions={"dup-001": DeduplicationStrategy.KEEP_NEW},
        )
        assert req.author == "IngestionPipeline"  # default
        assert "dup-001" in req.decisions

    def test_with_multiple_decisions(self):
        req = DeduplicationApplyRequest(
            new_pack_id=uuid4(),
            multiverse_id=uuid4(),
            universe_id=uuid4(),
            decisions={
                "dup-001": DeduplicationStrategy.KEEP_NEW,
                "dup-002": DeduplicationStrategy.KEEP_EXISTING,
                "dup-003": DeduplicationStrategy.MERGE,
            },
            author="GM",
        )
        assert len(req.decisions) == 3
        assert req.author == "GM"
