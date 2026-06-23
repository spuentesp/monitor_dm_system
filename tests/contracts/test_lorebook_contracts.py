"""
Contract tests for Lorebook schemas.

Covers:
- LorebookEntry: stored lorebook entry with keywords and priority
- LorebookEntryCreate: creation payload
- LorebookEntryUpdate: partial update
- LorebookEntryDraft: AI-proposed entry
- LorebookIngestRequest: bulk-ingest request
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from monitor_data.schemas.lorebook import (
    LorebookEntry,
    LorebookEntryCreate,
    LorebookEntryUpdate,
    LorebookEntryDraft,
    LorebookIngestRequest,
)


# =============================================================================
# LorebookEntry
# =============================================================================


class TestLorebookEntry:
    def test_minimal(self):
        e = LorebookEntry(
            id="lb-001",
            character_id="char-1",
            content="Dragons hoard gold and breathe fire.",
            created_at=datetime.utcnow().isoformat(),
        )
        assert e.id == "lb-001"
        assert e.character_id == "char-1"
        assert e.priority == 0  # default
        assert e.is_active is True
        assert e.trigger_count == 0

    def test_universe_wide(self):
        e = LorebookEntry(
            id="lb-002",
            character_id="universe:u-1",
            content="World lore applies everywhere",
            created_at="2024-01-01T00:00:00",
        )
        assert "universe:" in e.character_id

    def test_with_keywords_and_priority(self):
        e = LorebookEntry(
            id="lb-003",
            character_id="char-1",
            keywords=["dragon", "wyrm", "Smaug"],
            content="The dragon is ancient.",
            priority=90,
            tags=["boss", "mythic"],
            scene_filter="combat",
            created_at="2024-01-01",
        )
        assert "Smaug" in e.keywords
        assert e.priority == 90
        assert e.scene_filter == "combat"

    def test_priority_bounds(self):
        with pytest.raises(Exception):
            LorebookEntry(
                id="x",
                character_id="c",
                content="x",
                priority=200,  # > 100
                created_at="x",
            )
        with pytest.raises(Exception):
            LorebookEntry(
                id="x",
                character_id="c",
                content="x",
                priority=-1,  # < 0
                created_at="x",
            )

    def test_trigger_count_increments(self):
        e = LorebookEntry(
            id="lb-004",
            character_id="c",
            content="x",
            trigger_count=5,
            last_triggered="2024-01-01T00:00:00",
            created_at="2024-01-01",
        )
        assert e.trigger_count == 5
        assert e.last_triggered is not None


# =============================================================================
# LorebookEntryCreate
# =============================================================================


class TestLorebookEntryCreate:
    def test_minimal(self):
        req = LorebookEntryCreate(content="Some lore")
        assert req.content == "Some lore"
        assert req.priority == 0
        assert req.is_active is True
        assert req.auto_generate_keywords is False

    def test_with_keywords(self):
        req = LorebookEntryCreate(
            keywords=["magic", "spell"],
            content="Magic flows through the world.",
            priority=75,
            tags=["arcane"],
        )
        assert "magic" in req.keywords
        assert req.priority == 75

    def test_auto_generate_keywords(self):
        req = LorebookEntryCreate(
            content="A wizard with a staff.",
            auto_generate_keywords=True,
        )
        assert req.auto_generate_keywords is True
        assert req.keywords == []  # Will be filled by AI


# =============================================================================
# LorebookEntryUpdate
# =============================================================================


class TestLorebookEntryUpdate:
    def test_empty(self):
        upd = LorebookEntryUpdate()
        assert upd.keywords is None
        assert upd.content is None
        assert upd.priority is None
        assert upd.is_active is None

    def test_partial_update(self):
        upd = LorebookEntryUpdate(priority=80, is_active=False)
        assert upd.priority == 80
        assert upd.is_active is False
        assert upd.keywords is None

    def test_full_update(self):
        upd = LorebookEntryUpdate(
            keywords=["new"],
            content="Updated content",
            priority=50,
            is_active=True,
            tags=["updated"],
            scene_filter="social",
        )
        assert upd.scene_filter == "social"


# =============================================================================
# LorebookEntryDraft
# =============================================================================


class TestLorebookEntryDraft:
    def test_minimal(self):
        d = LorebookEntryDraft(
            keywords=["k1"],
            content="x",
        )
        assert d.priority == 50  # default
        assert d.confidence == 0.5  # default

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            LorebookEntryDraft(
                keywords=["k"],
                content="x",
                confidence=1.5,
            )
        with pytest.raises(Exception):
            LorebookEntryDraft(
                keywords=["k"],
                content="x",
                confidence=-0.1,
            )


# =============================================================================
# LorebookIngestRequest
# =============================================================================


class TestLorebookIngestRequest:
    def test_minimal(self):
        req = LorebookIngestRequest(
            source="doc.md",
            content="A"*20,
            character_id="char-1",
        )
        assert req.source == "doc.md"
        assert req.chunk_size == 2000  # default
        assert req.auto_keywords is True  # default

    def test_chunk_size_bounds(self):
        with pytest.raises(Exception):
            LorebookIngestRequest(
                source="x",
                content="A"*20,
                character_id="c",
                chunk_size=100,  # < 500
            )
        with pytest.raises(Exception):
            LorebookIngestRequest(
                source="x",
                content="A"*20,
                character_id="c",
                chunk_size=20000,  # > 10000
            )

    def test_min_content_length(self):
        with pytest.raises(Exception):
            LorebookIngestRequest(
                source="x",
                content="short",  # < 10
                character_id="c",
            )
