"""
Contract tests for GMProfile schemas.

LAYER: 1 (data-layer)
TESTS: Schema validation (unit)
"""

import pytest
from pydantic import ValidationError
from monitor_data.schemas.gm_profiles import (
    GMProfileCreate, GMProfileUpdate, GMProfileResponse, GMProfileFilter, GMProfileListResponse,
)


class TestGMProfileCreate:
    def test_minimal(self):
        p = GMProfileCreate(name="Grim Noir")
        assert p.name == "Grim Noir"
        assert p.description == ""
        assert p.tone_tags == []

    def test_full(self):
        p = GMProfileCreate(
            name="Dark Fantasy",
            description="A grim dark fantasy GM",
            tone_tags=["grim", "dramatic"],
            theme_tags=["corruption", "redemption"],
            style_tags=["terse"],
            concept_tags=["hope is earned"],
        )
        assert p.tone_tags == ["grim", "dramatic"]

    def test_name_required(self):
        with pytest.raises(ValidationError):
            GMProfileCreate(name="")  # type: ignore[arg-type]


class TestGMProfileUpdate:
    def test_empty(self):
        u = GMProfileUpdate()
        assert u.name is None


class TestGMProfileResponse:
    def test_valid(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        from uuid import uuid4
        r = GMProfileResponse(
            profile_id=uuid4(), name="Grim", description="",
            tone_tags=[], theme_tags=[], style_tags=[], concept_tags=[],
            created_at=now,
        )
        assert r.name == "Grim"


class TestGMProfileFilter:
    def test_defaults(self):
        f = GMProfileFilter()
        assert f.limit == 50
        assert f.offset == 0


class TestGMProfileListResponse:
    def test_valid(self):
        r = GMProfileListResponse(profiles=[], total=0, limit=20, offset=0)
        assert r.total == 0
