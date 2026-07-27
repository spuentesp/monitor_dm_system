"""
Contract tests for Tag Registry schemas.

Covers:
- TagCategory enum
- TagDefinitionCreate: create tag
- TagDefinitionUpdate: partial update
- TagDefinitionResponse: tag with metadata
- TagDefinitionListResponse: paginated
- TagSuggestionRequest: autocomplete

Use Cases: Phase 4 Tone system support
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from monitor_data.schemas.tag_registry import (
    TagCategory,
    TagDefinitionCreate,
    TagDefinitionListResponse,
    TagDefinitionResponse,
    TagDefinitionUpdate,
    TagSuggestionRequest,
)

# =============================================================================
# Enum
# =============================================================================


class TestTagCategoryEnum:
    def test_all_values(self):
        assert TagCategory.TONE.value == "tone"
        assert TagCategory.THEME.value == "theme"
        assert TagCategory.STYLE.value == "style"
        assert TagCategory.CONCEPT.value == "concept"


# =============================================================================
# TagDefinitionCreate
# =============================================================================


class TestTagDefinitionCreate:
    def test_minimal(self):
        t = TagDefinitionCreate(tag="grim_noir", category=TagCategory.TONE)
        assert t.tag == "grim_noir"
        assert t.category == TagCategory.TONE
        assert t.synonyms == []
        assert t.is_builtin is False  # default
        assert t.pack_id is None  # default

    def test_with_synonyms(self):
        t = TagDefinitionCreate(
            tag="grim",
            category=TagCategory.TONE,
            synonyms=["dark", "bleak", "gritty"],
            description="Dark, pessimistic tone",
        )
        assert "bleak" in t.synonyms
        assert t.description == "Dark, pessimistic tone"

    def test_builtin_tag(self):
        t = TagDefinitionCreate(
            tag="dramatic",
            category=TagCategory.TONE,
            is_builtin=True,
        )
        assert t.is_builtin is True

    def test_with_pack(self):
        t = TagDefinitionCreate(
            tag="x",
            category=TagCategory.THEME,
            pack_id=uuid4(),
        )
        assert t.pack_id is not None

    def test_with_example_tones(self):
        t = TagDefinitionCreate(
            tag="lyrical",
            category=TagCategory.STYLE,
            example_tones=[uuid4(), uuid4()],
        )
        assert len(t.example_tones) == 2

    def test_tag_length_bounds(self):
        with pytest.raises(Exception):
            TagDefinitionCreate(tag="", category=TagCategory.TONE)


# =============================================================================
# TagDefinitionUpdate
# =============================================================================


class TestTagDefinitionUpdate:
    def test_empty(self):
        u = TagDefinitionUpdate()
        assert u.synonyms is None
        assert u.description is None

    def test_partial(self):
        u = TagDefinitionUpdate(
            synonyms=["new1", "new2"],
            description="Updated description",
        )
        assert len(u.synonyms) == 2


# =============================================================================
# TagDefinitionResponse
# =============================================================================


class TestTagDefinitionResponse:
    def test_minimal(self):
        t = TagDefinitionResponse(
            tag="noir",
            category=TagCategory.TONE,
            synonyms=[],
            description="",
            example_tones=[],
            pack_id=None,
            is_builtin=False,
            created_at=datetime.now(),
        )
        assert t.updated_at is None  # default


# =============================================================================
# TagDefinitionListResponse
# =============================================================================


class TestTagDefinitionListResponse:
    def test_empty(self):
        r = TagDefinitionListResponse(
            tags=[],
            total=0,
            page=1,
            page_size=50,
        )
        assert r.tags == []


# =============================================================================
# TagSuggestionRequest
# =============================================================================


class TestTagSuggestionRequest:
    def test_minimal(self):
        r = TagSuggestionRequest(partial="grim")
        assert r.partial == "grim"
        assert r.category is None
