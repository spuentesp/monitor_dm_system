"""
Contract tests for ToneLibrary schemas.

Covers:
- ToneLibraryCreate: create library
- ToneLibraryUpdate: partial update
- ToneLibraryResponse: full response
- ToneLibraryListResponse: paginated

Use Cases: Phase 4 Tone system
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import uuid4

import pytest

from monitor_data.schemas.tone_libraries import (
    ToneLibraryCreate,
    ToneLibraryUpdate,
    ToneLibraryResponse,
    ToneLibraryListResponse,
)


# =============================================================================
# ToneLibraryCreate
# =============================================================================


class TestToneLibraryCreate:
    def test_minimal(self):
        lib = ToneLibraryCreate(name="Cyberpunk 2020")
        assert lib.name == "Cyberpunk 2020"
        assert lib.description == ""  # default
        assert lib.tone_profile_ids == []  # default
        assert lib.priority == 100  # default
        assert lib.is_default is False  # default
        assert lib.pack_id is None  # default
        assert lib.universe_id is None  # default

    def test_with_profiles(self):
        lib = ToneLibraryCreate(
            name="My Library",
            description="A custom tone library",
            tone_profile_ids=[uuid4(), uuid4()],
        )
        assert len(lib.tone_profile_ids) == 2

    def test_priority_bounds(self):
        with pytest.raises(Exception):
            ToneLibraryCreate(name="x", priority=-1)  # < 0
        with pytest.raises(Exception):
            ToneLibraryCreate(name="x", priority=2000)  # > 1000

    def test_with_scope(self):
        lib = ToneLibraryCreate(
            name="Pack Lib",
            pack_id=uuid4(),
            universe_id=uuid4(),
        )
        assert lib.pack_id is not None
        assert lib.universe_id is not None

    def test_default_library(self):
        lib = ToneLibraryCreate(
            name="Default",
            is_default=True,
            priority=100,
        )
        assert lib.is_default is True


# =============================================================================
# ToneLibraryUpdate
# =============================================================================


class TestToneLibraryUpdate:
    def test_empty(self):
        u = ToneLibraryUpdate()
        assert u.name is None
        assert u.tone_profile_ids is None

    def test_partial(self):
        u = ToneLibraryUpdate(
            name="Updated name",
            priority=200,
            is_default=True,
        )
        assert u.name == "Updated name"
        assert u.priority == 200

    def test_priority_bounds(self):
        with pytest.raises(Exception):
            ToneLibraryUpdate(priority=-1)


# =============================================================================
# ToneLibraryResponse
# =============================================================================


class TestToneLibraryResponse:
    def test_minimal(self):
        lib = ToneLibraryResponse(
            library_id=uuid4(),
            name="x",
            description="",
            tone_profile_ids=[],
            pack_id=None,
            universe_id=None,
            priority=100,
            is_default=False,
            created_at=datetime.now(),
        )
        assert lib.updated_at is None  # default

    def test_with_profiles(self):
        lib = ToneLibraryResponse(
            library_id=uuid4(),
            name="x",
            description="",
            tone_profile_ids=[uuid4(), uuid4(), uuid4()],
            pack_id=None,
            universe_id=None,
            priority=150,
            is_default=False,
            created_at=datetime.now(),
        )
        assert len(lib.tone_profile_ids) == 3


# =============================================================================
# ToneLibraryListResponse
# =============================================================================


class TestToneLibraryListResponse:
    def test_empty(self):
        r = ToneLibraryListResponse(
            libraries=[],
            total=0,
            page=1,
            page_size=50,
        )
        assert r.libraries == []

    def test_with_libraries(self):
        libs = [
            ToneLibraryResponse(
                library_id=uuid4(),
                name="L1",
                description="",
                tone_profile_ids=[],
                pack_id=None,
                universe_id=None,
                priority=100,
                is_default=False,
                created_at=datetime.now(),
            )
        ]
        r = ToneLibraryListResponse(libraries=libs, total=1, page=1, page_size=50)
        assert len(r.libraries) == 1
