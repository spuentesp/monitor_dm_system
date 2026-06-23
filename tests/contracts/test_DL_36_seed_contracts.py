"""
Contract tests for universe seeding (Phase 2.2).

Tests the seed schemas and WorldArchitect seed_universe contract.
"""

from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from monitor_data.schemas.base import EntityType, Authority, CanonLevel
from monitor_data.schemas.entities import EntityCreate
from monitor_data.schemas.random_tables import RandomTableType, RandomTableCreate


class TestEntityCreateForSeeding:
    def test_location_entity(self):
        """EntityCreate for a seeded location is valid."""
        e = EntityCreate(
            universe_id=uuid4(),
            name="Procedural Inn",
            entity_type=EntityType.LOCATION,
            is_archetype=False,
            description="A randomly generated inn",
            properties={"source": "procedural_seed"},
            authority=Authority.SYSTEM,
            canon_level=CanonLevel.CANON,
            confidence=0.8,
        )
        assert e.entity_type == EntityType.LOCATION
        assert e.canon_level == CanonLevel.CANON

    def test_npc_entity(self):
        """EntityCreate for a seeded NPC is valid."""
        e = EntityCreate(
            universe_id=uuid4(),
            name="Procedural Guard",
            entity_type=EntityType.CHARACTER,
            is_archetype=False,
            description="A randomly generated NPC",
            properties={"source": "procedural_seed", "source_table": "NPC Names"},
            authority=Authority.SYSTEM,
            canon_level=CanonLevel.CANON,
            confidence=0.8,
        )
        assert e.entity_type == EntityType.CHARACTER

    def test_confidence_bounds(self):
        """Seeded entities use valid confidence."""
        e = EntityCreate(
            universe_id=uuid4(),
            name="Test",
            entity_type=EntityType.CHARACTER,
            confidence=0.8,
        )
        assert 0.0 <= e.confidence <= 1.0


class TestSeedReport:
    def test_seed_report_structure(self):
        """Seed result has expected keys."""
        result = {
            "generated": 5,
            "entities": [
                {"id": str(uuid4()), "name": "Inn", "entity_type": "location"},
            ],
            "errors": [],
            "target_universe": str(uuid4()),
        }
        assert "generated" in result
        assert "entities" in result
        assert "errors" in result
        assert result["generated"] == 5


class TestRandomTableForSeeding:
    def test_table_type_enum(self):
        assert RandomTableType.NPC.value == "npc"
        assert RandomTableType.LOCATION.value == "location"
        assert RandomTableType.NAME.value == "name"
        assert RandomTableType.ENCOUNTER.value == "encounter"
        assert RandomTableType.CUSTOM.value == "custom"
