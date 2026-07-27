"""
Contract tests for ChangeLog schemas.

Covers:
- ChangeSubjectType enum: 10 subject types (entity, fact, event, etc.)
- ChangeType enum: 9 change operations (created, updated, deleted, etc.)
- ChangeLogEntry: append-only change record
- ChangeLogFilter: query filter
- ChangeLogListResponse: paginated

Use Cases: SYS-3 (CanonKeeper audit trail)
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from monitor_data.schemas.base import Authority
from monitor_data.schemas.change_log import (
    ChangeLogEntry,
    ChangeLogFilter,
    ChangeLogListResponse,
    ChangeSubjectType,
    ChangeType,
)

# =============================================================================
# Enums
# =============================================================================


class TestChangeSubjectTypeEnum:
    def test_all_values(self):
        assert ChangeSubjectType.ENTITY.value == "entity"
        assert ChangeSubjectType.FACT.value == "fact"
        assert ChangeSubjectType.EVENT.value == "event"
        assert ChangeSubjectType.LORE_EVENT.value == "lore_event"
        assert ChangeSubjectType.STORY.value == "story"
        assert ChangeSubjectType.SCENE.value == "scene"
        assert ChangeSubjectType.RELATIONSHIP.value == "relationship"
        assert ChangeSubjectType.AXIOM.value == "axiom"
        assert ChangeSubjectType.PARTY.value == "party"
        assert ChangeSubjectType.SOURCE.value == "source"


class TestChangeTypeEnum:
    def test_all_values(self):
        assert ChangeType.CREATED.value == "created"
        assert ChangeType.UPDATED.value == "updated"
        assert ChangeType.DELETED.value == "deleted"
        assert ChangeType.STATE_TAG_ADDED.value == "state_tag_added"
        assert ChangeType.STATE_TAG_REMOVED.value == "state_tag_removed"
        assert ChangeType.RELATIONSHIP_ADDED.value == "relationship_added"
        assert ChangeType.RELATIONSHIP_REMOVED.value == "relationship_removed"
        assert ChangeType.CANON_LEVEL_CHANGED.value == "canon_level_changed"
        assert ChangeType.RETCONNED.value == "retconned"


# =============================================================================
# ChangeLogEntry
# =============================================================================


class TestChangeLogEntry:
    def test_minimal(self):
        e = ChangeLogEntry(
            change_id=uuid4(),
            subject_type=ChangeSubjectType.ENTITY,
            subject_id=uuid4(),
            change_type=ChangeType.CREATED,
            timestamp=datetime.utcnow(),
            author="CanonKeeper",
            authority=Authority.SYSTEM,
        )
        assert e.field_path is None  # default
        assert e.old_value is None  # default
        assert e.new_value is None  # default
        assert e.evidence_type is None  # default
        assert e.reason is None  # default

    def test_with_field_change(self):
        e = ChangeLogEntry(
            change_id=uuid4(),
            subject_type=ChangeSubjectType.ENTITY,
            subject_id=uuid4(),
            change_type=ChangeType.UPDATED,
            timestamp=datetime.utcnow(),
            field_path="state_tags",
            old_value=["alive"],
            new_value=["dead"],
            author="CanonKeeper",
            authority=Authority.GM,
        )
        assert e.field_path == "state_tags"
        assert e.new_value == ["dead"]

    def test_with_evidence(self):
        e = ChangeLogEntry(
            change_id=uuid4(),
            subject_type=ChangeSubjectType.FACT,
            subject_id=uuid4(),
            change_type=ChangeType.RETCONNED,
            timestamp=datetime.utcnow(),
            author="CanonKeeper",
            authority=Authority.SYSTEM,
            evidence_type="scene",
            evidence_id=uuid4(),
            reason="New canon",
        )
        assert e.evidence_type == "scene"

    def test_with_transaction(self):
        e = ChangeLogEntry(
            change_id=uuid4(),
            subject_type=ChangeSubjectType.ENTITY,
            subject_id=uuid4(),
            change_type=ChangeType.CREATED,
            timestamp=datetime.utcnow(),
            author="CanonKeeper",
            authority=Authority.SYSTEM,
            transaction_id=uuid4(),
        )
        assert e.transaction_id is not None


# =============================================================================
# ChangeLogFilter
# =============================================================================


class TestChangeLogFilter:
    def test_defaults(self):
        f = ChangeLogFilter()
        assert f.limit == 100
        assert f.offset == 0
        assert f.sort_order == "desc"

    def test_with_filters(self):
        f = ChangeLogFilter(
            subject_type=ChangeSubjectType.FACT,
            subject_id=uuid4(),
            change_type=ChangeType.RETCONNED,
            author="CanonKeeper",
            transaction_id=uuid4(),
        )
        assert f.change_type == ChangeType.RETCONNED

    def test_with_date_range(self):
        f = ChangeLogFilter(
            since=datetime(2024, 1, 1),
            until=datetime(2024, 12, 31),
        )
        assert f.since < f.until

    def test_invalid_sort_order_fails(self):
        with pytest.raises(Exception):
            ChangeLogFilter(sort_order="invalid")

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            ChangeLogFilter(limit=0)
        with pytest.raises(Exception):
            ChangeLogFilter(limit=2000)


# =============================================================================
# ChangeLogListResponse
# =============================================================================


class TestChangeLogListResponse:
    def test_empty(self):
        r = ChangeLogListResponse(
            entries=[],
            total=0,
            limit=100,
            offset=0,
        )
        assert r.entries == []
