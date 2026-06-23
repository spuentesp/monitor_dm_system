"""
Contract tests for the ToneProfile schema (Phase 5 polish — narrator voice).

Tests:
- ToneProfileCreate: input schema for creating a new tone profile
- ToneProfileUpdate: schema for partial updates
- ToneProfileResponse: response shape
- ToneProfileListResponse: paginated list shape

Use Cases: P-5 (Narrator tone management)
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from monitor_data.schemas.tone_profiles import (
    ToneProfileCreate,
    ToneProfileUpdate,
    ToneProfileResponse,
    ToneProfileListResponse,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# ToneProfileCreate
# =============================================================================


class TestToneProfileCreate:
    def test_minimal(self):
        profile = ToneProfileCreate(
            name="Dramatic",
            description="Tense, emotional, high-stakes narration",
            instruction="Write in a dramatic style with heightened tension.",
        )
        assert profile.name == "Dramatic"
        assert profile.description is not None
        assert profile.is_builtin is False  # default

    def test_with_trigger_tags(self):
        profile = ToneProfileCreate(
            name="Grim Noir",
            description="Dark, moody narration",
            instruction="Write in dark noir style with cynical characters.",
            trigger_tags=["grim", "noir"],
        )
        assert "grim" in profile.trigger_tags

    def test_built_in_flag(self):
        profile = ToneProfileCreate(
            name="Builtin",
            description="Built-in tone",
            instruction="...",
            is_builtin=True,
        )
        assert profile.is_builtin is True

    def test_with_example_output(self):
        profile = ToneProfileCreate(
            name="Test",
            description="Test",
            instruction="...",
            example_output="The rain fell. The rain always fell.",
        )
        assert profile.example_output is not None


# =============================================================================
# ToneProfileUpdate
# =============================================================================


class TestToneProfileUpdate:
    def test_empty_update(self):
        update = ToneProfileUpdate()
        assert update.name is None
        assert update.description is None
        assert update.instruction is None

    def test_partial_update(self):
        update = ToneProfileUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.description is None  # other fields still None


# =============================================================================
# ToneProfileResponse
# =============================================================================


class TestToneProfileResponse:
    def _make(self, **overrides) -> ToneProfileResponse:
        defaults = {
            "profile_id": uuid4(),
            "name": "Dramatic",
            "description": "Intense narration",
            "instruction": "Write dramatically.",
            "trigger_tags": [],
            "category": "narrative",
            "language": "en",
            "pack_id": None,
            "is_builtin": True,
            "example_output": None,
            "created_at": _ts(),
        }
        defaults.update(overrides)
        return ToneProfileResponse(**defaults)

    def test_minimal(self):
        resp = self._make()
        assert resp.profile_id
        assert resp.name == "Dramatic"
        assert resp.is_builtin is True

    def test_with_trigger_tags(self):
        resp = self._make(trigger_tags=["tag1", "tag2"])
        assert len(resp.trigger_tags) == 2

    def test_custom_not_builtin(self):
        resp = self._make(is_builtin=False)
        assert resp.is_builtin is False


# =============================================================================
# ToneProfileListResponse
# =============================================================================


class TestToneProfileListResponse:
    def test_empty_list(self):
        resp = ToneProfileListResponse(profiles=[], total=0, page=1, page_size=20)
        assert resp.total == 0
        assert resp.profiles == []
        assert resp.page == 1
        assert resp.page_size == 20

    def test_with_profiles(self):
        profiles = [
            ToneProfileResponse(
                profile_id=uuid4(),
                name="Dramatic",
                description="Intense",
                instruction="...",
                trigger_tags=[],
                category="narrative",
                language="en",
                pack_id=None,
                is_builtin=True,
                example_output=None,
                created_at=_ts(),
            ),
            ToneProfileResponse(
                profile_id=uuid4(),
                name="Witty",
                description="Clever",
                instruction="...",
                trigger_tags=[],
                category="narrative",
                language="en",
                pack_id=None,
                is_builtin=True,
                example_output=None,
                created_at=_ts(),
            ),
        ]
        resp = ToneProfileListResponse(profiles=profiles, total=2, page=1, page_size=20)
        assert resp.total == 2
        assert len(resp.profiles) == 2
