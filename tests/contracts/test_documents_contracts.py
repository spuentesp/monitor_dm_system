"""
Contract tests for Document/Source schemas.

Covers:
- SourceCreate: create Source node
- SourceUpdate: partial update
- SourceResponse: response
- SourceFilter: list filter
- SourceListResponse: paginated
- SourceType enum
- SourcePriority enum
- KnowledgeTreeType enum
- SourceCanonLevel enum

Use Cases: DL-2 (Source provenance)
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from monitor_data.schemas.base import (
    KnowledgeTreeType,
    SourceCanonLevel,
    SourcePriority,
    SourceType,
)
from monitor_data.schemas.documents import (
    SourceCreate,
    SourceFilter,
    SourceListResponse,
    SourceResponse,
    SourceUpdate,
)

# =============================================================================
# Enums
# =============================================================================


class TestSourceTypeEnum:
    def test_all_values(self):
        assert SourceType.MANUAL.value == "manual"
        assert SourceType.RULEBOOK.value == "rulebook"
        assert SourceType.LORE.value == "lore"
        assert SourceType.SESSION.value == "session"


class TestSourcePriorityEnum:
    def test_all_values(self):
        assert SourcePriority.CORE.value == "core"
        assert SourcePriority.SUPPLEMENT.value == "supplement"
        assert SourcePriority.ADVENTURE.value == "adventure"
        assert SourcePriority.FAN.value == "fan"


class TestKnowledgeTreeTypeEnum:
    def test_all_values(self):
        assert KnowledgeTreeType.STATIC.value == "static"
        assert KnowledgeTreeType.DYNAMIC.value == "dynamic"
        assert KnowledgeTreeType.TEMPLATE.value == "template"


class TestSourceCanonLevelEnum:
    def test_inherits_canon_levels(self):
        # Should have values: proposed, canon, retconned, authoritative, etc.
        assert hasattr(SourceCanonLevel, "PROPOSED")
        assert hasattr(SourceCanonLevel, "CANON")


# =============================================================================
# SourceCreate
# =============================================================================


class TestSourceCreate:
    def test_minimal(self):
        s = SourceCreate(
            universe_id=uuid4(),
            title="Player's Handbook",
            source_type=SourceType.RULEBOOK,
        )
        assert s.title == "Player's Handbook"
        assert s.priority == SourcePriority.CUSTOM  # default
        assert s.knowledge_tree_type == KnowledgeTreeType.DYNAMIC  # default

    def test_with_full_metadata(self):
        s = SourceCreate(
            universe_id=uuid4(),
            title="Curse of Strahd",
            edition="5th Edition",
            provenance="ISBN 978-0-7869-6626-0",
            source_type=SourceType.LORE,
            priority=SourcePriority.ADVENTURE,
            knowledge_tree_type=KnowledgeTreeType.STATIC,
            canon_level=SourceCanonLevel.AUTHORITATIVE,
        )
        assert s.edition == "5th Edition"
        assert s.priority == SourcePriority.ADVENTURE

    def test_with_explicit_id(self):
        s = SourceCreate(
            universe_id=uuid4(),
            id=uuid4(),
            title="Manual",
            source_type=SourceType.MANUAL,
        )
        assert s.id is not None


# =============================================================================
# SourceUpdate
# =============================================================================


class TestSourceUpdate:
    def test_empty(self):
        u = SourceUpdate()
        assert u.title is None
        assert u.priority is None

    def test_partial(self):
        u = SourceUpdate(
            title="Updated title",
            priority=SourcePriority.CORE,
            doc_id="minio-doc-123",
        )
        assert u.doc_id == "minio-doc-123"


# =============================================================================
# SourceResponse
# =============================================================================


class TestSourceResponse:
    def test_minimal(self):
        s = SourceResponse(
            id=uuid4(),
            universe_id=uuid4(),
            title="PHB",
            source_type=SourceType.RULEBOOK,
            priority=SourcePriority.CORE,
            knowledge_tree_type=KnowledgeTreeType.STATIC,
            canon_level=SourceCanonLevel.AUTHORITATIVE,
            created_at=datetime.now(),
        )
        assert s.doc_id is None
        assert s.edition is None


# =============================================================================
# SourceFilter
# =============================================================================


class TestSourceFilter:
    def test_defaults(self):
        f = SourceFilter()
        assert f.limit == 50
        assert f.offset == 0

    def test_with_filters(self):
        f = SourceFilter(
            universe_id=uuid4(),
            source_type=SourceType.RULEBOOK,
            priority=SourcePriority.CORE,
        )
        assert f.source_type == SourceType.RULEBOOK

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            SourceFilter(limit=0)
        with pytest.raises(Exception):
            SourceFilter(limit=500)


# =============================================================================
# SourceListResponse
# =============================================================================


class TestSourceListResponse:
    def test_empty(self):
        r = SourceListResponse(sources=[], total=0, limit=50, offset=0)
        assert r.sources == []
