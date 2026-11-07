"""
Tests for monitor_data.tools.rpg_tools — PostgreSQL-backed RPG CRUD tools.

All database access is mocked via asyncpg-compatible AsyncMock fixtures so no
real Postgres connection is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import Field

from monitor_data.schemas.rpg_ontology import (
    EquipmentItemCreate,
    ItemType,
    TypedCharacterSheetCreate,
    TypedCharacterSheetUpdate,
)
from monitor_data.schemas.rpg_ontology.base import (
    AttributeSpec,
    BaseCharacterSheet,
    BaseGameSystem,
    GameSystemRegistry,
    ResourceSpec,
)

from monitor_data.tools.rpg_tools import (
    rpg_character_create,
    rpg_character_delete,
    rpg_character_get,
    rpg_character_get_by_entity,
    rpg_character_list,
    rpg_character_update,
    rpg_equipment_add,
    rpg_equipment_get,
    rpg_equipment_list,
    rpg_schema_inspect,
    rpg_sheet_equip,
    rpg_sheet_unequip,
    rpg_system_get,
    rpg_system_list,
    rpg_system_register,
    rpg_validate_sheet,
)

# The legacy typed-sheet path (rpg_character_create/update) validates through
# the legacy GameSystemRegistry. The platform ships no typed systems anymore,
# so these tests register a minimal inline one.
LEGACY_SYSTEM_ID = "legacy_test"

# Tests exercise the seeded builtin systems (spec registry); "D&D 5e" slugs
# to "dandd_5e".
SYSTEM_ID = "dandd_5e"


class _LegacyTestSheet(BaseCharacterSheet):
    """Minimal typed sheet for the inline legacy test system."""

    system_id: ClassVar[str] = LEGACY_SYSTEM_ID
    body: int = Field(ge=-3, le=3)
    dex: int = Field(ge=-3, le=3)
    savvy: int = Field(ge=-3, le=3)
    tech: int = Field(ge=-3, le=3)
    hp: int = Field(ge=0)
    max_hp: int = Field(ge=1)
    cosmic_rot: int = Field(ge=0, le=10, default=0)


def _legacy_definition() -> BaseGameSystem:
    return BaseGameSystem(
        system_id=LEGACY_SYSTEM_ID,
        system_name="Legacy Test",
        core_mechanic_formula="1d20",
        attributes=[
            AttributeSpec(name="Body", abbreviation="BDY", min_value=-3, max_value=3, default_value=0),
            AttributeSpec(name="Dexterity", abbreviation="DEX", min_value=-3, max_value=3, default_value=0),
            AttributeSpec(name="Savvy", abbreviation="SAVVY", min_value=-3, max_value=3, default_value=0),
            AttributeSpec(name="Tech", abbreviation="TECH", min_value=-3, max_value=3, default_value=0),
        ],
        resources=[ResourceSpec(name="Hit Points", abbreviation="HP")],
        schema_class="tests.test_rpg_tools._LegacyTestSheet",
    )


@pytest.fixture(scope="module", autouse=True)
def _register_legacy_system():
    """Register an inline legacy system so typed CRUD tools stay exercised."""
    GameSystemRegistry().register(_legacy_definition(), _LegacyTestSheet)
    yield

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_WORLD_ID = "world-test-1"
_ENTITY_ID = uuid4()
_SHEET_ID = uuid4()
_ITEM_ID = uuid4()
_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

# A minimal valid character sheet dict (payload for DB CRUD tests)
_VALID_SHEET_DATA = {
    "entity_id": str(_ENTITY_ID),
    "character_name": "Alpha Tester",
    "body": 1,
    "dex": 0,
    "savvy": 0,
    "tech": 0,
    "hp": 7,
    "max_hp": 7,
    "cosmic_rot": 0,
}


# ---------------------------------------------------------------------------
# Helpers — build asyncpg-style mock row dicts
# ---------------------------------------------------------------------------


def _sheet_row(**overrides) -> dict:
    row = {
        "id": _SHEET_ID,
        "world_id": _WORLD_ID,
        "entity_id": str(_ENTITY_ID),
        "system_id": SYSTEM_ID,
        "character_name": "Alpha Tester",
        "sheet_data": _VALID_SHEET_DATA,
        "created_at": _NOW,
        "updated_at": None,
    }
    row.update(overrides)
    return row


def _item_row(**overrides) -> dict:
    row = {
        "id": _ITEM_ID,
        "world_id": _WORLD_ID,
        "system_id": SYSTEM_ID,
        "item_name": "Laser Pistol",
        "item_type": "weapon",
        "item_data": {"damage_formula": "d6"},
        "source_ref": "Core Rules p.45",
        "created_at": _NOW,
    }
    row.update(overrides)
    return row


def _make_client(fetchrow=None, fetch=None, execute=None) -> MagicMock:
    """Return a mock PostgresClient whose pool returns controllable responses."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch = AsyncMock(return_value=fetch or [])
    conn.execute = AsyncMock(return_value=execute or "DELETE 1")

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)

    client = MagicMock()
    client._get_pool = AsyncMock(return_value=pool)
    return client


# ---------------------------------------------------------------------------
# rpg_system_register
# ---------------------------------------------------------------------------


class TestRpgSystemRegister:
    @pytest.mark.asyncio
    async def test_returns_dict_of_row(self):
        system = _legacy_definition()
        expected = {
            "system_id": system.system_id,
            "system_name": system.system_name,
        }
        client = _make_client(fetchrow=expected)
        result = await rpg_system_register(client, system)
        assert result == expected


# ---------------------------------------------------------------------------
# rpg_system_get
# ---------------------------------------------------------------------------


class TestRpgSystemGet:
    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        row = {"system_id": SYSTEM_ID, "system_name": "D&D 5e"}
        client = _make_client(fetchrow=row)
        result = await rpg_system_get(client, SYSTEM_ID)
        assert result == row

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        client = _make_client(fetchrow=None)
        result = await rpg_system_get(client, "nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# rpg_system_list
# ---------------------------------------------------------------------------


class TestRpgSystemList:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        rows = [
            {"system_id": "fate_core", "system_name": "Fate Core"},
            {"system_id": "dnd_5e", "system_name": "D&D 5e"},
        ]
        client = _make_client(fetch=rows)
        result = await rpg_system_list(client)
        assert len(result) == 2
        assert result[0] == rows[0]

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self):
        client = _make_client(fetch=[])
        result = await rpg_system_list(client)
        assert result == []


# ---------------------------------------------------------------------------
# rpg_character_create
# ---------------------------------------------------------------------------


class TestRpgCharacterCreate:
    @pytest.mark.asyncio
    async def test_creates_and_returns_response(self):
        row = _sheet_row(system_id=LEGACY_SYSTEM_ID)
        client = _make_client(fetchrow=row)
        request = TypedCharacterSheetCreate(
            world_id=_WORLD_ID,
            entity_id=_ENTITY_ID,
            system_id=LEGACY_SYSTEM_ID,
            sheet_data=_VALID_SHEET_DATA,
        )
        result = await rpg_character_create(client, request)
        assert result.id == _SHEET_ID
        assert result.system_id == LEGACY_SYSTEM_ID
        assert result.character_name == "Alpha Tester"

    @pytest.mark.asyncio
    async def test_invalid_sheet_raises_validation_error(self):
        from pydantic import ValidationError

        client = _make_client()
        request = TypedCharacterSheetCreate(
            world_id=_WORLD_ID,
            entity_id=_ENTITY_ID,
            system_id=LEGACY_SYSTEM_ID,
            sheet_data={
                "body": 99,
                "character_name": "X",
                "dex": 0,
                "savvy": 0,
                "tech": 0,
                "hp": 1,
                "max_hp": 1,
                "cosmic_rot": 0,
            },
        )
        with pytest.raises(ValidationError):
            await rpg_character_create(client, request)


# ---------------------------------------------------------------------------
# rpg_character_get
# ---------------------------------------------------------------------------


class TestRpgCharacterGet:
    @pytest.mark.asyncio
    async def test_returns_response_when_found(self):
        row = _sheet_row()
        client = _make_client(fetchrow=row)
        result = await rpg_character_get(client, _SHEET_ID)
        assert result is not None
        assert result.id == _SHEET_ID

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        client = _make_client(fetchrow=None)
        result = await rpg_character_get(client, uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# rpg_character_get_by_entity
# ---------------------------------------------------------------------------


class TestRpgCharacterGetByEntity:
    @pytest.mark.asyncio
    async def test_returns_response_when_found(self):
        row = _sheet_row()
        client = _make_client(fetchrow=row)
        result = await rpg_character_get_by_entity(client, _ENTITY_ID, _WORLD_ID)
        assert result is not None
        assert result.entity_id == _ENTITY_ID

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        client = _make_client(fetchrow=None)
        result = await rpg_character_get_by_entity(client, uuid4(), _WORLD_ID)
        assert result is None


# ---------------------------------------------------------------------------
# rpg_character_update
# ---------------------------------------------------------------------------


class TestRpgCharacterUpdate:
    @pytest.mark.asyncio
    async def test_updates_and_returns_response(self):
        updated_row = _sheet_row(
            system_id=LEGACY_SYSTEM_ID,
            character_name="Alpha Tester",
            sheet_data={**_VALID_SHEET_DATA, "hp": 5},
        )
        # First fetchrow = get current, second fetchrow = update result
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[_sheet_row(system_id=LEGACY_SYSTEM_ID), updated_row])
        conn.execute = AsyncMock(return_value="UPDATE 1")

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=None)

        pool = MagicMock()
        pool.acquire = MagicMock(return_value=cm)

        client = MagicMock()
        client._get_pool = AsyncMock(return_value=pool)

        update = TypedCharacterSheetUpdate(sheet_data={"hp": 5})
        result = await rpg_character_update(client, _SHEET_ID, update)
        assert result is not None
        assert result.sheet_data["hp"] == 5

    @pytest.mark.asyncio
    async def test_returns_none_when_sheet_not_found(self):
        client = _make_client(fetchrow=None)
        update = TypedCharacterSheetUpdate(sheet_data={"hp": 3})
        result = await rpg_character_update(client, uuid4(), update)
        assert result is None


# ---------------------------------------------------------------------------
# rpg_character_delete
# ---------------------------------------------------------------------------


class TestRpgCharacterDelete:
    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self):
        client = _make_client(execute="DELETE 1")
        result = await rpg_character_delete(client, _SHEET_ID)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        client = _make_client(execute="DELETE 0")
        result = await rpg_character_delete(client, uuid4())
        assert result is False


# ---------------------------------------------------------------------------
# rpg_character_list
# ---------------------------------------------------------------------------


class TestRpgCharacterList:
    @pytest.mark.asyncio
    async def test_returns_all_characters(self):
        rows = [_sheet_row(), _sheet_row(id=uuid4(), character_name="Beta")]
        client = _make_client(fetch=rows)
        result = await rpg_character_list(client)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_by_world_id(self):
        client = _make_client(fetch=[_sheet_row()])
        result = await rpg_character_list(client, world_id=_WORLD_ID)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filter_by_system_and_pc(self):
        client = _make_client(fetch=[_sheet_row()])
        result = await rpg_character_list(client, system_id=SYSTEM_ID, is_player_character=True)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self):
        client = _make_client(fetch=[])
        result = await rpg_character_list(client)
        assert result == []


# ---------------------------------------------------------------------------
# rpg_equipment_add
# ---------------------------------------------------------------------------


class TestRpgEquipmentAdd:
    @pytest.mark.asyncio
    async def test_adds_and_returns_response(self):
        row = _item_row()
        client = _make_client(fetchrow=row)
        request = EquipmentItemCreate(
            world_id=_WORLD_ID,
            system_id=SYSTEM_ID,
            item_name="Laser Pistol",
            item_type=ItemType.WEAPON,
            item_data={"damage_formula": "d6"},
            source_ref="Core Rules p.45",
        )
        result = await rpg_equipment_add(client, request)
        assert result.id == _ITEM_ID
        assert result.item_name == "Laser Pistol"
        assert result.item_type == ItemType.WEAPON


# ---------------------------------------------------------------------------
# rpg_equipment_get
# ---------------------------------------------------------------------------


class TestRpgEquipmentGet:
    @pytest.mark.asyncio
    async def test_returns_response_when_found(self):
        row = _item_row()
        client = _make_client(fetchrow=row)
        result = await rpg_equipment_get(client, _ITEM_ID)
        assert result is not None
        assert result.id == _ITEM_ID

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        client = _make_client(fetchrow=None)
        result = await rpg_equipment_get(client, uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# rpg_equipment_list
# ---------------------------------------------------------------------------


class TestRpgEquipmentList:
    @pytest.mark.asyncio
    async def test_returns_items(self):
        rows = [_item_row(), _item_row(id=uuid4(), item_name="Radiation Suit")]
        client = _make_client(fetch=rows)
        result = await rpg_equipment_list(client)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_by_item_type(self):
        client = _make_client(fetch=[_item_row()])
        result = await rpg_equipment_list(client, item_type=ItemType.WEAPON)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_all_filters_combined(self):
        client = _make_client(fetch=[])
        result = await rpg_equipment_list(
            client,
            world_id=_WORLD_ID,
            system_id=SYSTEM_ID,
            item_type=ItemType.ARMOR,
        )
        assert result == []


# ---------------------------------------------------------------------------
# rpg_sheet_equip / rpg_sheet_unequip
# ---------------------------------------------------------------------------


class TestRpgSheetEquip:
    @pytest.mark.asyncio
    async def test_equip_returns_row_dict(self):
        row = {
            "character_sheet_id": _SHEET_ID,
            "item_id": _ITEM_ID,
            "quantity": 1,
            "is_equipped": True,
            "slot": "holster",
            "notes": None,
        }
        client = _make_client(fetchrow=row)
        result = await rpg_sheet_equip(client, _SHEET_ID, _ITEM_ID, quantity=1, is_equipped=True, slot="holster")
        assert result["character_sheet_id"] == _SHEET_ID

    @pytest.mark.asyncio
    async def test_unequip_returns_true_when_deleted(self):
        client = _make_client(execute="DELETE 1")
        result = await rpg_sheet_unequip(client, _SHEET_ID, _ITEM_ID)
        assert result is True

    @pytest.mark.asyncio
    async def test_unequip_returns_false_when_not_found(self):
        client = _make_client(execute="DELETE 0")
        result = await rpg_sheet_unequip(client, _SHEET_ID, uuid4())
        assert result is False


# ---------------------------------------------------------------------------
# rpg_validate_sheet (pure logic — no DB)
# ---------------------------------------------------------------------------


class TestRpgValidateSheet:
    def test_unknown_system_returns_error(self):
        result = rpg_validate_sheet("not_a_real_system", {})
        assert result["valid"] is False
        assert "Unknown game system" in result["errors"][0]


# ---------------------------------------------------------------------------
# rpg_schema_inspect
# ---------------------------------------------------------------------------


class TestRpgSchemaInspect:
    """Tests for the schema introspection tool.

    ``dandd_5e`` (D&D 5e, seeded from builtin_systems.json) is auto-registered
    in SystemRegistry at import time, so most tests use the in-memory path
    (no real DB needed).
    """

    @pytest.fixture(autouse=True)
    def _ensure_spec_registered(self):
        """Ensure the seeded dandd_5e spec is in the registry.

        Other test modules (e.g. test_rpg_ontology_converters) may replace
        the registry contents, so re-register the builtin-systems spec before
        each test.
        """
        from monitor_data.schemas.rpg_ontology import SystemRegistry
        from monitor_data.schemas.rpg_ontology.converters import get_spec_for_system

        spec = get_spec_for_system("D&D 5e")
        assert spec is not None
        SystemRegistry().register(spec)

    @pytest.mark.asyncio
    async def test_returns_dict_for_registered_system(self):
        client = _make_client()  # DB never touched for in-memory hit
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_system_id_and_name_present(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        assert result["system_id"] == SYSTEM_ID
        assert result["system_name"]  # non-empty string

    @pytest.mark.asyncio
    async def test_core_mechanic_has_required_keys(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        cm = result["core_mechanic"]
        assert "mechanic_type" in cm
        assert "success_condition" in cm

    @pytest.mark.asyncio
    async def test_dnd5e_core_mechanic_is_d20_over(self):
        """meet_or_beat must map to D20_OVER (not CUSTOM) via the converter."""
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        assert result["core_mechanic"]["mechanic_type"] == "d20_over"

    @pytest.mark.asyncio
    async def test_entity_types_key_present(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        assert "entity_types" in result
        assert isinstance(result["entity_types"], dict)

    @pytest.mark.asyncio
    async def test_character_entity_type_present(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        assert "character" in result["entity_types"]

    @pytest.mark.asyncio
    async def test_character_fields_non_empty(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        fields = result["entity_types"]["character"]["fields"]
        assert len(fields) > 0

    @pytest.mark.asyncio
    async def test_field_summary_has_required_keys(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        field = result["entity_types"]["character"]["fields"][0]
        for key in ("name", "display_name", "field_type", "required", "user_settable"):
            assert key in field, f"Missing key '{key}' in field summary"

    @pytest.mark.asyncio
    async def test_strength_field_has_dnd_range(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        fields = result["entity_types"]["character"]["fields"]
        strength = next(f for f in fields if f["name"] == "strength")
        assert strength["min_value"] == 1
        assert strength["max_value"] == 30

    @pytest.mark.asyncio
    async def test_attribute_modifier_is_derived(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        fields = result["entity_types"]["character"]["fields"]
        str_mod = next(f for f in fields if f["name"] == "strength_mod")
        assert str_mod["user_settable"] is False
        assert str_mod["derived_formula"] is not None

    @pytest.mark.asyncio
    async def test_relations_list_present(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        assert "relations" in result
        assert isinstance(result["relations"], list)

    @pytest.mark.asyncio
    async def test_data_edges_list_present(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        assert "data_edges" in result
        assert isinstance(result["data_edges"], list)

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_system_not_in_db(self):
        # DB fetchrow returns None → no spec JSONB
        client = _make_client(fetchrow=None)
        result = await rpg_schema_inspect(client, "totally_unknown_system")
        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_postgres_when_not_in_registry(self):
        from monitor_data.schemas.rpg_ontology import SystemRegistry
        from monitor_data.schemas.rpg_ontology.converters import get_spec_for_system
        from monitor_data.schemas.rpg_ontology.factory import clear_model_cache

        # Temporarily unregister the seeded spec, then restore after test
        reg = SystemRegistry()
        reg.unregister(SYSTEM_ID)
        clear_model_cache(SYSTEM_ID)
        try:
            # DB returns the full spec JSON
            spec_dict = get_spec_for_system("D&D 5e").model_dump(mode="json")

            # Build a mock row with spec column holding the spec dict
            mock_spec_row = MagicMock()
            mock_spec_row.__getitem__ = lambda self, key: spec_dict if key == "spec" else None

            conn = AsyncMock()
            conn.fetchrow = AsyncMock(return_value=mock_spec_row)
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=conn)
            cm.__aexit__ = AsyncMock(return_value=None)
            pool = MagicMock()
            pool.acquire = MagicMock(return_value=cm)
            client = MagicMock()
            client._get_pool = AsyncMock(return_value=pool)

            result = await rpg_schema_inspect(client, SYSTEM_ID)
            assert result is not None
            assert result["system_id"] == SYSTEM_ID
        finally:
            # Always restore the spec so other tests still work
            spec = get_spec_for_system("D&D 5e")
            assert spec is not None
            reg.register(spec)

    @pytest.mark.asyncio
    async def test_tags_is_list(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        assert isinstance(result["tags"], list)

    @pytest.mark.asyncio
    async def test_storage_backends_is_list_of_strings(self):
        client = _make_client()
        result = await rpg_schema_inspect(client, SYSTEM_ID)
        for et in result["entity_types"].values():
            assert isinstance(et["storage_backends"], list)
            for b in et["storage_backends"]:
                assert isinstance(b, str)
