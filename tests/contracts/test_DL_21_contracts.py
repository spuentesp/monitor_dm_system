"""
DL-21: Random Tables — Contract Tests

Tests the input/output contracts for random table schemas.
These tests validate schema constraints, not database interactions.

Use Cases: DL-21 (Random Tables), M-33
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from monitor_data.schemas.random_tables import (
    RandomTableType,
    RandomTableEntry,
    RandomTableCreate,
    RandomTableUpdate,
    RandomTableResponse,
    RandomTableFilter,
    RandomTableListResponse,
)


# =============================================================================
# RandomTableType enum contract tests
# =============================================================================


@pytest.mark.unit
class TestRandomTableTypeContract:
    """Contract tests for RandomTableType enum."""

    def test_table_type_values(self):
        """RandomTableType has expected values."""
        assert RandomTableType.ENCOUNTER == "encounter"
        assert RandomTableType.LOOT == "loot"
        assert RandomTableType.NAME == "name"
        assert RandomTableType.TRAIT == "trait"
        assert RandomTableType.WEATHER == "weather"
        assert RandomTableType.RUMOR == "rumor"
        assert RandomTableType.NPC == "npc"
        assert RandomTableType.EVENT == "event"
        assert RandomTableType.LOCATION == "location"
        assert RandomTableType.COMPLICATION == "complication"
        assert RandomTableType.CUSTOM == "custom"

    def test_table_type_count(self):
        """RandomTableType has 11 values."""
        assert len(RandomTableType) == 11


# =============================================================================
# RandomTableEntry contract tests
# =============================================================================


@pytest.mark.unit
class TestRandomTableEntryContract:
    """Contract tests for RandomTableEntry schema."""

    def test_entry_minimal(self):
        """RandomTableEntry with required fields is valid."""
        entry = RandomTableEntry(
            min_roll=1,
            max_roll=10,
            value="A goblin appears!",
        )
        assert entry.min_roll == 1
        assert entry.max_roll == 10
        assert entry.value == "A goblin appears!"
        assert entry.weight is None
        assert entry.subtable_id is None
        assert entry.conditions is None

    def test_entry_with_weight(self):
        """RandomTableEntry can specify weight for weighted tables."""
        entry = RandomTableEntry(
            min_roll=1,
            max_roll=1,
            value="Rare treasure",
            weight=0.05,
        )
        assert entry.weight == 0.05

    def test_entry_with_subtable(self):
        """RandomTableEntry can reference a subtable."""
        sid = uuid4()
        entry = RandomTableEntry(
            min_roll=1,
            max_roll=5,
            value="Roll on treasure table",
            subtable_id=sid,
        )
        assert entry.subtable_id == sid

    def test_entry_with_conditions(self):
        """RandomTableEntry can specify conditions."""
        entry = RandomTableEntry(
            min_roll=1,
            max_roll=10,
            value="Dragon encounter",
            conditions={"level_min": 5, "terrain": "mountains"},
        )
        assert entry.conditions["level_min"] == 5

    def test_entry_empty_value_fails(self):
        """RandomTableEntry with empty value raises ValidationError."""
        with pytest.raises(Exception):
            RandomTableEntry(
                min_roll=1,
                max_roll=10,
                value="",
            )

    def test_entry_zero_weight_fails(self):
        """RandomTableEntry with weight <= 0 raises ValidationError."""
        with pytest.raises(Exception):
            RandomTableEntry(
                min_roll=1,
                max_roll=1,
                value="test",
                weight=0.0,
            )

    def test_entry_negative_weight_fails(self):
        """RandomTableEntry with negative weight raises ValidationError."""
        with pytest.raises(Exception):
            RandomTableEntry(
                min_roll=1,
                max_roll=1,
                value="test",
                weight=-0.5,
            )


# =============================================================================
# RandomTableCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestRandomTableCreateContract:
    """Contract tests for RandomTableCreate schema."""

    def test_create_minimal(self):
        """RandomTableCreate with required fields is valid."""
        params = RandomTableCreate(
            name="Encounter Table",
            dice_formula="1d20",
            entries=[
                RandomTableEntry(min_roll=1, max_roll=20, value="A goblin appears!"),
            ],
        )
        assert params.name == "Encounter Table"
        assert params.dice_formula == "1d20"
        assert params.table_type == RandomTableType.CUSTOM
        assert params.weighted is False
        assert params.universe_id is None
        assert params.description == ""
        assert len(params.entries) == 1

    def test_create_with_all_fields(self):
        """RandomTableCreate with all optional fields populated."""
        uid = uuid4()
        sid = uuid4()
        gsid = uuid4()
        params = RandomTableCreate(
            universe_id=uid,
            name="Weather Table",
            description="Random weather events.",
            table_type=RandomTableType.WEATHER,
            dice_formula="2d6",
            weighted=True,
            entries=[
                RandomTableEntry(min_roll=2, max_roll=4, value="Clear skies", weight=0.3),
                RandomTableEntry(min_roll=5, max_roll=9, value="Cloudy", weight=0.4),
                RandomTableEntry(min_roll=10, max_roll=12, value="Storm", weight=0.3),
            ],
            source_id=sid,
            game_system_id=gsid,
        )
        assert params.universe_id == uid
        assert params.table_type == RandomTableType.WEATHER
        assert params.weighted is True
        assert params.source_id == sid
        assert params.game_system_id == gsid

    def test_create_empty_name_fails(self):
        """RandomTableCreate with empty name raises ValidationError."""
        with pytest.raises(Exception):
            RandomTableCreate(
                name="",
                dice_formula="1d20",
                entries=[
                    RandomTableEntry(min_roll=1, max_roll=20, value="test"),
                ],
            )

    def test_create_empty_entries_fails(self):
        """RandomTableCreate with empty entries list raises ValidationError."""
        with pytest.raises(Exception):
            RandomTableCreate(
                name="Empty Table",
                dice_formula="1d20",
                entries=[],
            )

    def test_create_all_table_types(self):
        """All RandomTableType values are valid for table_type."""
        for tt in RandomTableType:
            params = RandomTableCreate(
                name=f"Test {tt.value}",
                dice_formula="1d20",
                entries=[
                    RandomTableEntry(min_roll=1, max_roll=20, value="test"),
                ],
                table_type=tt,
            )
            assert params.table_type == tt


# =============================================================================
# RandomTableUpdate contract tests
# =============================================================================


@pytest.mark.unit
class TestRandomTableUpdateContract:
    """Contract tests for RandomTableUpdate schema."""

    def test_update_all_none(self):
        """RandomTableUpdate with all fields None is valid (no-op update)."""
        update = RandomTableUpdate()
        assert update.name is None
        assert update.description is None
        assert update.table_type is None
        assert update.dice_formula is None
        assert update.weighted is None
        assert update.entries is None

    def test_update_name_only(self):
        """RandomTableUpdate can update just the name."""
        update = RandomTableUpdate(name="Updated Table")
        assert update.name == "Updated Table"

    def test_update_entries(self):
        """RandomTableUpdate can replace entries."""
        update = RandomTableUpdate(
            entries=[
                RandomTableEntry(min_roll=1, max_roll=10, value="New entry"),
            ],
        )
        assert len(update.entries) == 1

    def test_update_empty_name_fails(self):
        """RandomTableUpdate with empty name raises ValidationError."""
        with pytest.raises(Exception):
            RandomTableUpdate(name="")


# =============================================================================
# RandomTableResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestRandomTableResponseContract:
    """Contract tests for RandomTableResponse schema."""

    def test_response_minimal(self):
        """RandomTableResponse with required fields is valid."""
        resp = RandomTableResponse(
            table_id=uuid4(),
            name="Encounter Table",
            description="",
            table_type=RandomTableType.ENCOUNTER,
            dice_formula="1d20",
            weighted=False,
            entries=[
                RandomTableEntry(min_roll=1, max_roll=20, value="A goblin!"),
            ],
            created_at=datetime.now(timezone.utc),
        )
        assert resp.name == "Encounter Table"
        assert resp.universe_id is None
        assert resp.source_id is None
        assert resp.game_system_id is None
        assert resp.updated_at is None

    def test_response_with_universe(self):
        """RandomTableResponse can include universe_id."""
        uid = uuid4()
        resp = RandomTableResponse(
            table_id=uuid4(),
            universe_id=uid,
            name="Weather Table",
            description="Random weather",
            table_type=RandomTableType.WEATHER,
            dice_formula="2d6",
            weighted=True,
            entries=[
                RandomTableEntry(min_roll=2, max_roll=12, value="Rain"),
            ],
            created_at=datetime.now(timezone.utc),
        )
        assert resp.universe_id == uid


# =============================================================================
# RandomTableFilter contract tests
# =============================================================================


@pytest.mark.unit
class TestRandomTableFilterContract:
    """Contract tests for RandomTableFilter schema."""

    def test_filter_defaults(self):
        """RandomTableFilter has sensible defaults."""
        f = RandomTableFilter()
        assert f.universe_id is None
        assert f.table_type is None
        assert f.game_system_id is None
        assert f.limit == 50
        assert f.offset == 0

    def test_filter_by_universe(self):
        """RandomTableFilter can filter by universe_id."""
        uid = uuid4()
        f = RandomTableFilter(universe_id=uid)
        assert f.universe_id == uid

    def test_filter_by_table_type(self):
        """RandomTableFilter can filter by table_type."""
        f = RandomTableFilter(table_type=RandomTableType.ENCOUNTER)
        assert f.table_type == RandomTableType.ENCOUNTER

    def test_filter_limit_range(self):
        """RandomTableFilter limit must be between 1 and 200."""
        with pytest.raises(Exception):
            RandomTableFilter(limit=0)
        with pytest.raises(Exception):
            RandomTableFilter(limit=201)

    def test_filter_offset_range(self):
        """RandomTableFilter offset must be >= 0."""
        with pytest.raises(Exception):
            RandomTableFilter(offset=-1)


# =============================================================================
# RandomTableListResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestRandomTableListResponseContract:
    """Contract tests for RandomTableListResponse schema."""

    def test_list_response_empty(self):
        """RandomTableListResponse with empty list is valid."""
        resp = RandomTableListResponse(
            tables=[],
            total=0,
            limit=50,
            offset=0,
        )
        assert resp.tables == []
        assert resp.total == 0

    def test_list_response_with_tables(self):
        """RandomTableListResponse can include tables."""
        table = RandomTableResponse(
            table_id=uuid4(),
            name="Encounter Table",
            description="",
            table_type=RandomTableType.ENCOUNTER,
            dice_formula="1d20",
            weighted=False,
            entries=[
                RandomTableEntry(min_roll=1, max_roll=20, value="A goblin!"),
            ],
            created_at=datetime.now(timezone.utc),
        )
        resp = RandomTableListResponse(
            tables=[table],
            total=1,
            limit=50,
            offset=0,
        )
        assert resp.total == 1
        assert resp.tables[0].name == "Encounter Table"