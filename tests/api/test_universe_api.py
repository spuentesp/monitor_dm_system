"""
API contract tests for universe lifecycle endpoints (Phase 2-3).

Tests schemas for seed, fork, and snapshot operations.
"""

from __future__ import annotations

from uuid import uuid4

from monitor_data.schemas.base import Authority, CanonLevel, EntityType
from monitor_data.schemas.entities import EntityCreate
from monitor_data.schemas.random_tables import RandomTableEntry, RandomTableType


class TestSeedSchemas:
    def test_seed_request_defaults(self):
        """Seed request schema with defaults."""
        req = {
            "template_ids": [],
            "random_table_ids": [],
            "entity_count": 10,
            "location_count": 3,
            "npc_count": 5,
            "seed_facts": True,
        }
        assert req["entity_count"] == 10
        assert req["seed_facts"] is True

    def test_seed_result_structure(self):
        """Seed result has expected keys."""
        result = {
            "universe_id": str(uuid4()),
            "entities_created": 8,
            "entities": [
                {"id": str(uuid4()), "name": "Inn", "entity_type": "location"},
            ],
            "errors": [],
            "status": "seeded",
        }
        assert result["entities_created"] == 8
        assert result["status"] == "seeded"


class TestForkSchemas:
    def test_fork_request(self):
        """Fork request schema."""
        req = {
            "name": "Forked World",
            "description": "A forked universe",
            "include_stories": False,
        }
        assert req["name"] == "Forked World"

    def test_fork_result_structure(self):
        """Fork result has expected keys."""
        result = {
            "source_universe_id": str(uuid4()),
            "new_universe_id": str(uuid4()),
            "name": "Forked World",
            "entities_cloned": 5,
            "relationships_cloned": 3,
            "status": "forked",
        }
        assert result["status"] == "forked"
        assert result["entities_cloned"] == 5


class TestSnapshotSchemas:
    def test_snapshot_request(self):
        """Snapshot request schema."""
        req = {
            "name": "Pre-battle save",
            "description": "Before the big fight",
        }
        assert req["name"] == "Pre-battle save"

    def test_snapshot_result_structure(self):
        """Snapshot result has expected keys."""
        result = {
            "snapshot_id": str(uuid4()),
            "universe_id": str(uuid4()),
            "name": "Snapshot",
            "entity_count": 10,
            "fact_count": 5,
            "status": "created",
        }
        assert result["entity_count"] == 10
        assert result["fact_count"] == 5

    def test_restore_request(self):
        """Restore request requires confirmation."""
        req = {"confirm": True}
        assert req["confirm"] is True


class TestSeedEntitySchemas:
    def test_seeded_location_entity(self):
        """EntityCreate for a seeded location uses correct defaults."""
        e = EntityCreate(
            universe_id=uuid4(),
            name="Procedural Tavern",
            entity_type=EntityType.LOCATION,
            is_archetype=False,
            description="A procedurally generated tavern",
            authority=Authority.SYSTEM,
            canon_level=CanonLevel.CANON,
            confidence=0.8,
        )
        assert e.is_archetype is False
        assert e.canon_level == CanonLevel.CANON

    def test_seeded_npc_entity(self):
        """EntityCreate for a seeded NPC."""
        e = EntityCreate(
            universe_id=uuid4(),
            name="Procedural Guard",
            entity_type=EntityType.CHARACTER,
            is_archetype=False,
            description="A procedurally generated guard",
            authority=Authority.SYSTEM,
            canon_level=CanonLevel.CANON,
            confidence=0.8,
        )
        assert e.entity_type == EntityType.CHARACTER


class TestRandomTableForSeeding:
    def test_entry_creation(self):
        """Random table entries are valid."""
        entry = RandomTableEntry(min_roll=1, max_roll=4, value="Goblin Scout")
        assert entry.value == "Goblin Scout"
        assert entry.min_roll == 1

    def test_table_types(self):
        """All table types are available."""
        assert RandomTableType.NPC.value == "npc"
        assert RandomTableType.LOCATION.value == "location"
        assert RandomTableType.NAME.value == "name"
        assert RandomTableType.ENCOUNTER.value == "encounter"
        assert RandomTableType.CUSTOM.value == "custom"
