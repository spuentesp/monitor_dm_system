"""
Contract tests for GMProfile schemas.

Covers:
- GMProfileCreate: create with all tag dimensions
- GMProfileUpdate: partial update
- GMProfileResponse: full response
- GMProfileFilter: list filter
- GMProfileListResponse: paginated

Use Cases: Phase 4 GM Assistant
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import uuid4

import pytest

from monitor_data.schemas.gm_profiles import (
    GMProfileCreate,
    GMProfileUpdate,
    GMProfileResponse,
    GMProfileFilter,
    GMProfileListResponse,
)


# =============================================================================
# GMProfileCreate
# =============================================================================


class TestGMProfileCreate:
    def test_minimal(self):
        p = GMProfileCreate(name="Grim Noir Detective")
        assert p.description == ""  # default
        assert p.tone_tags == []  # default
        assert p.theme_tags == []  # default
        assert p.style_tags == []  # default
        assert p.concept_tags == []  # default
        assert p.tone_instructions is None
        assert p.merge_with_default_library is True  # default
        assert p.is_builtin is False  # default

    def test_with_all_tags(self):
        p = GMProfileCreate(
            name="Cosmic Horror GM",
            description="A GM who emphasizes the unknown",
            tone_tags=["ominous", "clinical"],
            theme_tags=["cosmic_indifference", "madness"],
            style_tags=["long_sentences", "present_tense"],
            concept_tags=["knowledge_costs", "humans_are_insignificant"],
        )
        assert "clinical" in p.tone_tags
        assert "madness" in p.theme_tags

    def test_with_tone_library(self):
        p = GMProfileCreate(
            name="Cyberpunk",
            tone_library_id=uuid4(),
            merge_with_default_library=True,
        )
        assert p.tone_library_id is not None

    def test_with_overrides(self):
        p = GMProfileCreate(
            name="Family-Friendly",
            tone_instructions="Use only G-rated language",
            narrator_constraints="No violence, no romance",
        )
        assert "G-rated" in p.tone_instructions
        assert "violence" in p.narrator_constraints

    def test_builtin(self):
        p = GMProfileCreate(name="Default", is_builtin=True)
        assert p.is_builtin is True

    def test_with_scope(self):
        p = GMProfileCreate(
            name="Custom",
            universe_id=uuid4(),
            game_system_id=uuid4(),
        )
        assert p.universe_id is not None
        assert p.game_system_id is not None

    def test_empty_name_fails(self):
        with pytest.raises(Exception):
            GMProfileCreate(name="")  # min_length=1


# =============================================================================
# GMProfileUpdate
# =============================================================================


class TestGMProfileUpdate:
    def test_empty(self):
        u = GMProfileUpdate()
        assert u.name is None
        assert u.tone_tags is None

    def test_partial(self):
        u = GMProfileUpdate(
            name="Updated",
            tone_tags=["dramatic"],
        )
        assert u.name == "Updated"
        assert u.tone_tags == ["dramatic"]


# =============================================================================
# GMProfileResponse
# =============================================================================


class TestGMProfileResponse:
    def test_minimal(self):
        r = GMProfileResponse(
            profile_id=uuid4(),
            name="Test",
            description="",
            tone_tags=[],
            theme_tags=[],
            style_tags=[],
            concept_tags=[],
            created_at=datetime.utcnow(),
        )
        assert r.is_builtin is False  # default
        assert r.updated_at is None  # default

    def test_with_overrides(self):
        r = GMProfileResponse(
            profile_id=uuid4(),
            name="x",
            description="",
            tone_tags=[],
            theme_tags=[],
            style_tags=[],
            concept_tags=[],
            tone_instructions="Custom",
            narrator_constraints="No violence",
            tone_library_id=uuid4(),
            universe_id=uuid4(),
            game_system_id=uuid4(),
            is_builtin=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert r.tone_instructions == "Custom"
        assert r.is_builtin is True


# =============================================================================
# GMProfileFilter
# =============================================================================


class TestGMProfileFilter:
    def test_defaults(self):
        f = GMProfileFilter()
        assert f.limit == 50
        assert f.offset == 0

    def test_with_filters(self):
        f = GMProfileFilter(
            universe_id=uuid4(),
            game_system_id=uuid4(),
            tone_tag="grim",
            is_builtin=True,
        )
        assert f.tone_tag == "grim"
        assert f.is_builtin is True

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            GMProfileFilter(limit=0)
        with pytest.raises(Exception):
            GMProfileFilter(limit=300)


# =============================================================================
# GMProfileListResponse
# =============================================================================


class TestGMProfileListResponse:
    def test_empty(self):
        r = GMProfileListResponse(
            profiles=[],
            total=0,
            limit=50,
            offset=0,
        )
        assert r.profiles == []
