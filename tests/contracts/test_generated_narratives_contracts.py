"""Contract tests for the GeneratedNarrative schemas.

Verifies that generated_narratives Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce length constraints,
- reject invalid enum values where applicable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from monitor_data.schemas.base import NarrativeSourceType, NarrativeStyle
from monitor_data.schemas.generated_narratives import (
    GeneratedNarrativeCreate,
    GeneratedNarrativeFilter,
    GeneratedNarrativeListResponse,
    GeneratedNarrativeResponse,
    GeneratedNarrativeUpdate,
)
from pydantic import ValidationError


pytestmark = pytest.mark.unit


# =============================================================================
# GeneratedNarrativeCreate
# =============================================================================


class TestGeneratedNarrativeCreate:
    def test_minimal(self):
        n = GeneratedNarrativeCreate(
            source_type=NarrativeSourceType.SCENE,
            source_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            text="Once upon a time...",
        )
        assert n.style == NarrativeStyle.LITERARY  # default
        assert n.perspective is None
        assert n.model_used is None
        assert n.scene_ids_covered == []

    def test_with_all_fields(self):
        n = GeneratedNarrativeCreate(
            source_type=NarrativeSourceType.STORY,
            source_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            style=NarrativeStyle.DRAMATIC,
            text="INT. TAVERN — NIGHT",
            perspective="third_person",
            model_used="claude-3-opus",
            scene_ids_covered=[uuid4(), uuid4()],
        )
        assert n.style == NarrativeStyle.DRAMATIC
        assert n.perspective == "third_person"
        assert n.model_used == "claude-3-opus"
        assert len(n.scene_ids_covered) == 2

    def test_text_empty_rejected(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeCreate(
                source_type=NarrativeSourceType.SCENE,
                source_id=uuid4(),
                universe_id=uuid4(),
                story_id=uuid4(),
                text="",
            )

    def test_perspective_too_long(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeCreate(
                source_type=NarrativeSourceType.SCENE,
                source_id=uuid4(),
                universe_id=uuid4(),
                story_id=uuid4(),
                text="x",
                perspective="x" * 51,
            )

    def test_model_used_too_long(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeCreate(
                source_type=NarrativeSourceType.SCENE,
                source_id=uuid4(),
                universe_id=uuid4(),
                story_id=uuid4(),
                text="x",
                model_used="x" * 201,
            )

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeCreate(
                source_type="bogus",  # type: ignore[arg-type]
                source_id=uuid4(),
                universe_id=uuid4(),
                story_id=uuid4(),
                text="x",
            )

    def test_invalid_style(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeCreate(
                source_type=NarrativeSourceType.SCENE,
                source_id=uuid4(),
                universe_id=uuid4(),
                story_id=uuid4(),
                text="x",
                style="bogus",  # type: ignore[arg-type]
            )

    def test_required_text(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeCreate(
                source_type=NarrativeSourceType.SCENE,
                source_id=uuid4(),
                universe_id=uuid4(),
                story_id=uuid4(),
            )

    def test_required_universe_id(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeCreate(
                source_type=NarrativeSourceType.SCENE,
                source_id=uuid4(),
                story_id=uuid4(),
                text="x",
            )

    def test_required_story_id(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeCreate(
                source_type=NarrativeSourceType.SCENE,
                source_id=uuid4(),
                universe_id=uuid4(),
                text="x",
            )


# =============================================================================
# GeneratedNarrativeUpdate
# =============================================================================


class TestGeneratedNarrativeUpdate:
    def test_empty(self):
        u = GeneratedNarrativeUpdate()
        assert u.text is None
        assert u.is_edited_by_user is None

    def test_with_text(self):
        u = GeneratedNarrativeUpdate(text="Edited text here")
        assert u.text == "Edited text here"

    def test_with_flag(self):
        u = GeneratedNarrativeUpdate(is_edited_by_user=True)
        assert u.is_edited_by_user is True

    def test_text_empty_rejected(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeUpdate(text="")


# =============================================================================
# GeneratedNarrativeResponse
# =============================================================================


class TestGeneratedNarrativeResponse:
    def _kwargs(self, **overrides):
        base = {
            "narrative_id": uuid4(),
            "source_type": NarrativeSourceType.SCENE,
            "source_id": uuid4(),
            "universe_id": uuid4(),
            "story_id": uuid4(),
            "style": NarrativeStyle.LITERARY,
            "text": "Once upon a time...",
            "scene_ids_covered": [],
            "word_count": 4,
            "created_at": datetime.now(timezone.utc),
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        r = GeneratedNarrativeResponse(**self._kwargs())
        assert r.perspective is None
        assert r.model_used is None
        assert r.is_edited_by_user is False
        assert r.updated_at is None

    def test_with_full(self):
        ts = datetime.now(timezone.utc)
        r = GeneratedNarrativeResponse(
            **self._kwargs(
                text="Long text...",
                word_count=2,
                perspective="first_person",
                model_used="claude-3-opus",
                is_edited_by_user=True,
                updated_at=ts,
            )
        )
        assert r.is_edited_by_user is True
        assert r.updated_at == ts

    def test_required_narrative_id(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeResponse(
                source_type=NarrativeSourceType.SCENE,
                source_id=uuid4(),
                universe_id=uuid4(),
                story_id=uuid4(),
                style=NarrativeStyle.LITERARY,
                text="x",
                scene_ids_covered=[],
                word_count=1,
                created_at=datetime.now(timezone.utc),
            )


# =============================================================================
# GeneratedNarrativeFilter
# =============================================================================


class TestGeneratedNarrativeFilter:
    def test_defaults(self):
        f = GeneratedNarrativeFilter()
        assert f.source_type is None
        assert f.source_id is None
        assert f.story_id is None
        assert f.universe_id is None
        assert f.style is None
        assert f.limit == 50
        assert f.offset == 0

    def test_with_filters(self):
        f = GeneratedNarrativeFilter(
            source_type=NarrativeSourceType.SESSION,
            story_id=uuid4(),
            style=NarrativeStyle.SUMMARY,
            limit=100,
        )
        assert f.source_type == NarrativeSourceType.SESSION
        assert f.style == NarrativeStyle.SUMMARY
        assert f.limit == 100

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeFilter(limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeFilter(limit=201)

    def test_offset_min(self):
        with pytest.raises(ValidationError):
            GeneratedNarrativeFilter(offset=-1)


# =============================================================================
# GeneratedNarrativeListResponse
# =============================================================================


class TestGeneratedNarrativeListResponse:
    def test_empty(self):
        r = GeneratedNarrativeListResponse(narratives=[], total=0, limit=50, offset=0)
        assert r.narratives == []
        assert r.total == 0

    def test_with_narrative(self):
        n = GeneratedNarrativeResponse(
            narrative_id=uuid4(),
            source_type=NarrativeSourceType.SCENE,
            source_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            style=NarrativeStyle.LITERARY,
            text="x",
            scene_ids_covered=[],
            word_count=1,
            created_at=datetime.now(timezone.utc),
        )
        r = GeneratedNarrativeListResponse(narratives=[n], total=1, limit=50, offset=0)
        assert len(r.narratives) == 1
        assert r.total == 1
