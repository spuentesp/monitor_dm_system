"""
Contract tests for Phase 2-3 features: seeding, forking, snapshots.

Tests schema validation and result structures.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.base import (
    AltWorldType,
)
from monitor_data.schemas.universe import UniverseCreate
from monitor_data.schemas.world_snapshots import (
    WorldSnapshotCreate,
    WorldSnapshotFilter,
    WorldSnapshotResponse,
)
from pydantic import ValidationError


class TestUniverseCreateForPhase3:
    def test_minimal(self):
        u = UniverseCreate(
            multiverse_id=uuid4(), name="Test World", description="A test"
        )
        assert u.name == "Test World"
        assert u.alt_world_type == AltWorldType.MAIN
        assert u.is_template is False

    def test_as_fork(self):
        parent = uuid4()
        u = UniverseCreate(
            multiverse_id=uuid4(),
            name="Forked World",
            description="A fork",
            parent_universe_id=parent,
            alt_world_type=AltWorldType.FORK,
        )
        assert u.parent_universe_id == parent
        assert u.alt_world_type == AltWorldType.FORK

    def test_all_alt_world_types(self):
        for awt in AltWorldType:
            u = UniverseCreate(
                multiverse_id=uuid4(),
                name=f"World {awt.value}",
                description="test",
                alt_world_type=awt,
            )
            assert u.alt_world_type == awt

    def test_with_game_system(self):
        gsid = uuid4()
        u = UniverseCreate(
            multiverse_id=uuid4(),
            name="System World",
            description="test",
            default_game_system_id=gsid,
            default_system_source_type="generic_library",
            default_system_name="D&D 5e",
        )
        assert u.default_game_system_id == gsid

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            UniverseCreate(
                multiverse_id=uuid4(), name="Test", description="x", confidence=-0.1
            )
        with pytest.raises(ValidationError):
            UniverseCreate(
                multiverse_id=uuid4(), name="Test", description="x", confidence=1.1
            )


class TestWorldSnapshotForPhase3:
    def test_minimal(self):
        s = WorldSnapshotCreate(universe_id=uuid4(), name="Snapshot 1")
        assert s.name == "Snapshot 1"
        assert s.description == ""

    def test_with_description(self):
        s = WorldSnapshotCreate(
            universe_id=uuid4(), name="Pre-Battle", description="Before the fight"
        )
        assert s.description == "Before the fight"


class TestWorldSnapshotResponse:
    def test_structure(self):
        now = datetime.now(UTC)
        r = WorldSnapshotResponse(
            snapshot_id=uuid4(),
            universe_id=uuid4(),
            name="Test Snapshot",
            description="",
            entity_count=10,
            fact_count=5,
            relationship_count=3,
            axiom_count=7,
            created_at=now,
        )
        assert r.entity_count == 10
        assert r.fact_count == 5
        assert r.relationship_count == 3
        assert r.axiom_count == 7


class TestWorldSnapshotFilter:
    def test_defaults(self):
        f = WorldSnapshotFilter()
        assert f.limit == 20


class TestAltWorldTypeEnum:
    def test_values(self):
        assert AltWorldType.MAIN.value == "main"
        assert AltWorldType.FORK.value == "fork"
        assert AltWorldType.WHAT_IF.value == "what_if"
        assert AltWorldType.DREAM.value == "dream"
        assert AltWorldType.SIMULATION.value == "simulation"
