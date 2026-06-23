"""Tests for CharacterSheet CRUD operations in MongoDB tools."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from monitor_data.schemas.character_sheets import (
    CharacterSheetCreate,
    CharacterSheetUpdate,
    CharacterSheetFilter,
)


# =============================================================================
# FAKE MONGODB IMPLEMENTATION
# =============================================================================


class _FakeSheetsCollection:
    """Fake MongoDB collection for character sheets."""

    def __init__(self):
        self.sheets = {}

    def find_one(self, query):
        # Handle $or queries
        if "$or" in query:
            for or_clause in query["$or"]:
                result = self.find_one(or_clause)
                if result:
                    return result
            return None

        if "sheet_id" in query:
            return self.sheets.get(query["sheet_id"])
        if "entity_id" in query:
            for sheet in self.sheets.values():
                if sheet["entity_id"] == query["entity_id"]:
                    if "game_system_id" in query:
                        if sheet.get("game_system_id") == query["game_system_id"]:
                            return sheet
                    elif "system_source_type" in query and "system_source_id" in query:
                        if sheet.get("system_source_type") == query["system_source_type"]:
                            if sheet.get("system_source_id") == query["system_source_id"]:
                                return sheet
                    else:
                        return sheet
        if "system_source_type" in query and "system_source_id" in query:
            for sheet in self.sheets.values():
                if sheet.get("system_source_type") == query["system_source_type"]:
                    if sheet.get("system_source_id") == query["system_source_id"]:
                        return sheet
        if "system_id" in query:
            for sheet in self.sheets.values():
                if sheet.get("system_id") == query["system_id"] or sheet.get("system_id") == str(
                    query.get("system_id")
                ):
                    return sheet
        return None

    def insert_one(self, doc):
        self.sheets[doc["sheet_id"]] = doc

    def update_one(self, query, update):
        if "sheet_id" in query and query["sheet_id"] in self.sheets:
            sheet_id = query["sheet_id"]
            for key, value in update.get("$set", {}).items():
                self.sheets[sheet_id][key] = value
            return type("UpdateResult", (), {"matched_count": 1})()
        return type("UpdateResult", (), {"matched_count": 0})()

    def count_documents(self, query):
        count = 0
        for sheet in self.sheets.values():
            match = True
            if "entity_id" in query and sheet.get("entity_id") != query["entity_id"]:
                match = False
            if "game_system_id" in query and sheet.get("game_system_id") != query.get(
                "game_system_id"
            ):
                match = False
            if "system_source_type" in query and sheet.get("system_source_type") != query.get(
                "system_source_type"
            ):
                match = False
            if "system_source_id" in query and sheet.get("system_source_id") != query.get(
                "system_source_id"
            ):
                match = False
            if "is_active" in query and sheet.get("is_active") != query["is_active"]:
                match = False
            if match:
                count += 1
        return count

    def find(self, query):
        results = []
        for sheet in self.sheets.values():
            match = True
            if "entity_id" in query and sheet.get("entity_id") != query["entity_id"]:
                match = False
            if "game_system_id" in query and sheet.get("game_system_id") != query.get(
                "game_system_id"
            ):
                match = False
            if "system_source_type" in query and sheet.get("system_source_type") != query.get(
                "system_source_type"
            ):
                match = False
            if "system_source_id" in query and sheet.get("system_source_id") != query.get(
                "system_source_id"
            ):
                match = False
            if "is_active" in query and sheet.get("is_active") != query["is_active"]:
                match = False
            if match:
                results.append(sheet)
        return _FakeCursor(results)


class _FakeCursor:
    """Fake MongoDB cursor with sort/skip/limit support."""

    def __init__(self, results):
        self.results = results

    def sort(self, key, direction):
        # MongoDB sort key is typically a list like [("updated_at", -1)]
        if isinstance(key, list) and len(key) > 0:
            sort_key, sort_dir = key[0]
        else:
            # Handle single key format
            sort_key, sort_dir = key, direction

        # Sort results by the specified key
        reverse = sort_dir == -1
        self.results = sorted(self.results, key=lambda x: x.get(sort_key, ""), reverse=reverse)
        return self

    def skip(self, offset):
        return _FakeCursor(self.results[offset:])

    def limit(self, limit):
        return _FakeCursor(self.results[:limit])

    def __iter__(self):
        return iter(self.results)


class _FakeNeo4jClient:
    """Fake Neo4j client for entity verification."""

    def __init__(self, entity_exists=True):
        self.entity_exists = entity_exists

    def execute_read(self, query, params):
        if self.entity_exists:
            return [{"id": params.get("entity_id", str(uuid4()))}]
        return []


class _FakeMongoClient:
    """Fake MongoDB client."""

    def __init__(self):
        self.sheets_db = _FakeSheetsCollection()
        self.game_systems_db = _FakeSheetsCollection()
        self.systems_by_id = {}

    def get_collection(self, name):
        if name == "character_sheets":
            return self.sheets_db
        return _FakeSheetsCollection()

    def __getitem__(self, name):
        if name == "character_sheets":
            return self.sheets_db
        if name == "game_systems":
            return self.game_systems_db
        return _FakeSheetsCollection()


# =============================================================================
# mongodb_create_character_sheet TESTS
# =============================================================================


def test_create_character_sheet_basic(monkeypatch):
    """Test creating a character sheet with basic fields."""
    entity_id = uuid4()
    system_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=True)
    fake_mongo = _FakeMongoClient()
    fake_mongo.game_systems_db.sheets[str(system_id)] = {
        "system_id": str(system_id),
        "name": "Test System",
    }

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_create_character_sheet

    result = mongodb_create_character_sheet(
        CharacterSheetCreate(
            entity_id=entity_id,
            game_system_id=system_id,
            system_source_type="generic_library",
            system_source_id=str(system_id),
            system_name="Test System",
            stats={"STR": 12, "DEX": 14},
            resources={"HP": 10, "max_HP": 10},
            skills={"Stealth": 2},
        )
    )

    assert result.entity_id == entity_id
    assert result.game_system_id == system_id
    assert result.stats["DEX"] == 14
    assert result.is_active is True


def test_create_character_sheet_with_detailed_fields(monkeypatch):
    """Test creating a character sheet with all detailed fields."""
    entity_id = uuid4()
    system_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=True)
    fake_mongo = _FakeMongoClient()
    fake_mongo.game_systems_db.sheets[str(system_id)] = {
        "system_id": str(system_id),
        "name": "Test System",
    }

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import (
        mongodb_create_character_sheet,
        mongodb_get_character_sheet,
    )

    result = mongodb_create_character_sheet(
        CharacterSheetCreate(
            entity_id=entity_id,
            game_system_id=system_id,
            system_source_type="generic_library",
            system_source_id=str(system_id),
            system_name="Test System",
            stats={"STR": 12, "DEX": 14, "CON": 10, "INT": 16, "WIS": 8, "CHA": 10},
            resources={"HP": 10, "max_HP": 10, "spell_slots": {"1": 2, "2": 1}},
            skills={"Stealth": 4, "Arcana": 6, "Perception": 2},
            class_levels={"Wizard": 2},
            total_level=2,
            experience_points=300,
            background="Scholar",
            alignment="Lawful Neutral",
            equipment=[{"name": "Staff", "damage": "1d6"}, {"name": "Spellbook", "type": "arcane"}],
            special_abilities=["Arcane Recovery", "Spell Mastery"],
            spells_known=["Magic Missile", "Shield", "Sleep", "Fireball"],
            notes="High-intelligence wizard focused on evocation magic",
        )
    )

    # Verify sheet was created and can be retrieved
    assert result.sheet_id is not None
    assert result.entity_id == entity_id
    assert result.stats["INT"] == 16
    assert result.skills["Arcana"] == 6
    assert result.class_levels["Wizard"] == 2
    assert len(result.spells_known) == 4
    assert result.notes == "High-intelligence wizard focused on evocation magic"

    # Verify the sheet can be retrieved
    retrieved = mongodb_get_character_sheet(result.sheet_id)
    assert retrieved is not None
    assert retrieved.sheet_id == result.sheet_id


def test_create_character_sheet_duplicate_returns_existing(monkeypatch):
    """Test creating a duplicate sheet returns existing sheet."""
    entity_id = uuid4()
    system_id = uuid4()
    sheet_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=True)
    fake_mongo = _FakeMongoClient()
    fake_mongo.game_systems_db.sheets[str(system_id)] = {
        "system_id": str(system_id),
        "name": "Test System",
    }

    now = datetime.now(timezone.utc)

    # Pre-populate with existing sheet
    fake_mongo.sheets_db.sheets[str(sheet_id)] = {
        "sheet_id": str(sheet_id),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 15},
        "resources": {"HP": 20},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_create_character_sheet

    result = mongodb_create_character_sheet(
        CharacterSheetCreate(
            entity_id=entity_id,
            game_system_id=system_id,
            system_source_type="generic_library",
            system_source_id=str(system_id),
            system_name="Test System",
            stats={"STR": 12, "DEX": 14},
        )
    )

    assert result.sheet_id == sheet_id
    assert result.stats["STR"] == 15  # Original stats, not new ones


def test_create_character_sheet_entity_not_found_raises_error(monkeypatch):
    """Test creating a sheet for non-existent entity raises error."""
    entity_id = uuid4()
    system_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=False)
    fake_mongo = _FakeMongoClient()
    fake_mongo.game_systems_db.sheets[str(system_id)] = {
        "system_id": str(system_id),
        "name": "Test System",
    }

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_create_character_sheet

    with pytest.raises(ValueError, match="Entity.*not found"):
        mongodb_create_character_sheet(
            CharacterSheetCreate(
                entity_id=entity_id,
                game_system_id=system_id,
                system_source_type="generic_library",
                system_source_id=str(system_id),
                system_name="Test System",
            )
        )


# =============================================================================
# mongodb_get_character_sheet TESTS
# =============================================================================


def test_get_character_sheet_found(monkeypatch):
    """Test getting an existing character sheet."""
    sheet_id = uuid4()
    entity_id = uuid4()
    system_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id)] = {
        "sheet_id": str(sheet_id),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 10},
        "resources": {"HP": 8},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": None,
    }

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_get_character_sheet

    result = mongodb_get_character_sheet(sheet_id)

    assert result is not None
    assert result.sheet_id == sheet_id
    assert result.entity_id == entity_id


def test_get_character_sheet_not_found_returns_none(monkeypatch):
    """Test getting a non-existent sheet returns None."""
    sheet_id = uuid4()

    # Mock MongoDB client with empty collection
    fake_mongo = _FakeMongoClient()

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_get_character_sheet

    result = mongodb_get_character_sheet(sheet_id)

    assert result is None


# =============================================================================
# mongodb_update_character_sheet TESTS
# =============================================================================


def test_update_character_sheet_basic(monkeypatch):
    """Test updating a character sheet with basic fields."""
    sheet_id = uuid4()
    entity_id = uuid4()
    system_id = uuid4()
    now = datetime.now(timezone.utc)

    # Create existing sheet
    existing_sheet = {
        "sheet_id": str(sheet_id),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 10, "DEX": 12},
        "resources": {"HP": 10, "max_HP": 10},
        "skills": {"Stealth": 2},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": None,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id)] = existing_sheet

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_update_character_sheet

    result = mongodb_update_character_sheet(
        sheet_id,
        CharacterSheetUpdate(
            stats={"STR": 13},
            resources={"HP": 9},
            change_description="Level-up adjustment",
        ),
    )

    assert result.stats["STR"] == 13
    assert result.history_log[-1].change == "Level-up adjustment"


def test_update_character_sheet_all_fields(monkeypatch):
    """Test updating all fields of a character sheet."""
    sheet_id = uuid4()
    entity_id = uuid4()
    system_id = uuid4()

    # Create existing sheet
    now = datetime.now(timezone.utc)
    existing_sheet = {
        "sheet_id": str(sheet_id),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 10, "DEX": 12},
        "resources": {"HP": 10, "max_HP": 10},
        "skills": {"Stealth": 2},
        "class_levels": {"Fighter": 1},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": None,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id)] = existing_sheet

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_update_character_sheet

    result = mongodb_update_character_sheet(
        sheet_id,
        CharacterSheetUpdate(
            stats={"STR": 12, "DEX": 14, "CON": 10},
            resources={"HP": 15, "max_HP": 15},
            skills={"Stealth": 4, "Arcana": 2},
            class_levels={"Fighter": 2, "Rogue": 1},
            total_level=3,
            experience_points=300,
            background="Soldier",
            alignment="Lawful Good",
            equipment=[{"name": "Sword", "damage": "1d8"}],
            special_abilities=["Sneak Attack", "Second Wind"],
            spells_known=["Fireball"],
            notes="Updated notes",
            change_description="Multi-class advancement",
        ),
    )

    assert result.stats["STR"] == 12
    assert result.stats["DEX"] == 14
    assert result.stats["CON"] == 10
    assert result.resources["HP"] == 15
    assert result.skills["Stealth"] == 4
    assert result.skills["Arcana"] == 2
    assert result.class_levels["Fighter"] == 2
    assert result.class_levels["Rogue"] == 1
    assert result.total_level == 3
    assert result.experience_points == 300
    assert result.background == "Soldier"
    assert result.alignment == "Lawful Good"
    assert len(result.equipment) == 1
    assert result.equipment[0]["name"] == "Sword"
    assert result.special_abilities[0] == "Sneak Attack"
    assert result.spells_known[0] == "Fireball"
    assert result.notes == "Updated notes"
    assert result.history_log[-1].change == "Multi-class advancement"


def test_update_character_sheet_not_found_raises_error(monkeypatch):
    """Test updating a non-existent sheet raises error."""
    sheet_id = uuid4()

    # Mock MongoDB client with empty collection
    fake_mongo = _FakeMongoClient()

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_update_character_sheet

    with pytest.raises(ValueError, match="Character sheet.*not found"):
        mongodb_update_character_sheet(
            sheet_id,
            CharacterSheetUpdate(
                stats={"STR": 13},
            ),
        )


# =============================================================================
# mongodb_list_character_sheets TESTS
# =============================================================================


def test_list_character_sheets_all(monkeypatch):
    """Test listing all character sheets."""
    entity_id_1 = uuid4()
    entity_id_2 = uuid4()
    system_id = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()

    # Create sheets
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id_1),
        "game_system_id": str(system_id),
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id_2),
        "game_system_id": str(system_id),
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    result = mongodb_list_character_sheets(CharacterSheetFilter())

    assert result.total == 2
    assert len(result.sheets) == 2
    assert any(s.sheet_id == sheet_id_1 for s in result.sheets)
    assert any(s.sheet_id == sheet_id_2 for s in result.sheets)


def test_list_character_sheets_by_entity_id(monkeypatch):
    """Test listing character sheets filtered by entity_id."""
    entity_id_1 = uuid4()
    entity_id_2 = uuid4()
    system_id = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()

    # Create sheets for different entities
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id_1),
        "game_system_id": str(system_id),
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id_2),
        "game_system_id": str(system_id),
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    result = mongodb_list_character_sheets(CharacterSheetFilter(entity_id=entity_id_1))

    assert result.total == 1
    assert len(result.sheets) == 1
    assert result.sheets[0].sheet_id == sheet_id_1
    assert result.sheets[0].entity_id == entity_id_1


def test_list_character_sheets_by_game_system_id(monkeypatch):
    """Test listing character sheets filtered by game_system_id."""
    entity_id = uuid4()
    system_id_1 = uuid4()
    system_id_2 = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()

    # Create sheets for different systems
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id_1),
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id_2),
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    result = mongodb_list_character_sheets(CharacterSheetFilter(game_system_id=system_id_1))

    assert result.total == 1
    assert len(result.sheets) == 1
    assert result.sheets[0].sheet_id == sheet_id_1
    assert result.sheets[0].game_system_id == system_id_1


def test_list_character_sheets_by_is_active(monkeypatch):
    """Test listing character sheets filtered by is_active status."""
    entity_id = uuid4()
    system_id = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()

    # Create active and inactive sheets
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": False,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    result = mongodb_list_character_sheets(CharacterSheetFilter(is_active=True))

    assert result.total == 1
    assert len(result.sheets) == 1
    assert result.sheets[0].sheet_id == sheet_id_1
    assert result.sheets[0].is_active is True


def test_list_character_sheets_pagination(monkeypatch):
    """Test listing character sheets with offset and limit."""
    entity_id = uuid4()
    system_id = uuid4()
    sheet_ids = [uuid4() for _ in range(5)]

    # Create 5 sheets
    now = datetime.now(timezone.utc)
    fake_mongo = _FakeMongoClient()
    for i, sheet_id in enumerate(sheet_ids):
        sheet = {
            "sheet_id": str(sheet_id),
            "entity_id": str(entity_id),
            "game_system_id": str(system_id),
            "stats": {"STR": 10 + i},
            "resources": {"HP": 10 + i},
            "skills": {},
            "class_levels": {},
            "total_level": 1,
            "experience_points": 0,
            "background": None,
            "alignment": None,
            "equipment": [],
            "special_abilities": [],
            "spells_known": [],
            "notes": None,
            "is_active": True,
            "history_log": [],
            "created_at": now,
            "updated_at": now,
        }
        fake_mongo.sheets_db.sheets[str(sheet_id)] = sheet

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    # Test offset
    result = mongodb_list_character_sheets(CharacterSheetFilter(offset=2, limit=3))
    assert result.total == 5
    assert len(result.sheets) == 3

    # Test limit
    result = mongodb_list_character_sheets(CharacterSheetFilter(offset=0, limit=2))
    assert result.total == 5
    assert len(result.sheets) == 2


def test_list_character_sheets_by_system_source_type(monkeypatch):
    """Test listing character sheets filtered by system_source_type."""
    entity_id = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()

    # Create sheets with different system_source_type
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": "generic_library",
        "system_source_id": "dnd5e",
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": "homebrew",
        "system_source_id": "custom_v2",
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    result = mongodb_list_character_sheets(
        CharacterSheetFilter(system_source_type="generic_library")
    )

    assert result.total == 1
    assert len(result.sheets) == 1
    assert result.sheets[0].sheet_id == sheet_id_1
    assert result.sheets[0].system_source_type == "generic_library"


def test_list_character_sheets_by_system_source_id(monkeypatch):
    """Test listing character sheets filtered by system_source_id."""
    entity_id = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()

    # Create sheets with different system_source_id
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": "generic_library",
        "system_source_id": "dnd5e",
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": "generic_library",
        "system_source_id": "dnd5e_shaper",
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    result = mongodb_list_character_sheets(CharacterSheetFilter(system_source_id="dnd5e"))

    assert result.total == 1
    assert len(result.sheets) == 1
    assert result.sheets[0].sheet_id == sheet_id_1
    assert result.sheets[0].system_source_id == "dnd5e"


def test_create_character_sheet_without_game_system_id(monkeypatch):
    """Test creating a character sheet with only system_source_type and system_source_id."""
    entity_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=True)
    fake_mongo = _FakeMongoClient()

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_create_character_sheet

    result = mongodb_create_character_sheet(
        CharacterSheetCreate(
            entity_id=entity_id,
            game_system_id=None,
            system_source_type="homebrew",
            system_source_id="custom_system_v1",
            system_name="Custom Homebrew",
            stats={"STR": 14, "DEX": 12},
            resources={"HP": 12},
            skills={"Athletics": 3},
        )
    )

    assert result.entity_id == entity_id
    assert result.game_system_id is None
    assert result.system_source_type == "homebrew"
    assert result.system_source_id == "custom_system_v1"
    assert result.system_name == "Custom Homebrew"
    assert result.stats["STR"] == 14


def test_update_character_sheet_with_change_description(monkeypatch):
    """Test that change_description adds entry to history_log."""
    sheet_id = uuid4()
    entity_id = uuid4()
    system_id = uuid4()

    # Create existing sheet
    now = datetime.now(timezone.utc)
    existing_sheet = {
        "sheet_id": str(sheet_id),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id)] = existing_sheet

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_update_character_sheet

    result = mongodb_update_character_sheet(
        sheet_id,
        CharacterSheetUpdate(
            stats={"STR": 12},
            change_description="Strength increased after training",
        ),
    )

    # Verify history_log has one entry with the change_description
    assert len(result.history_log) == 1
    assert result.history_log[0].change == "Strength increased after training"
    assert result.history_log[0].timestamp is not None
    assert result.history_log[0].scene_id is None


def test_list_character_sheets_sort_by_updated_at(monkeypatch):
    """Test that listing character sheets is sorted by updated_at descending."""
    entity_id = uuid4()
    system_id = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()
    sheet_id_3 = uuid4()

    # Create sheets with different updated_at times
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc),
    }
    sheet_3 = {
        "sheet_id": str(sheet_id_3),
        "entity_id": str(entity_id),
        "game_system_id": str(system_id),
        "stats": {"STR": 14},
        "resources": {"HP": 20},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2
    fake_mongo.sheets_db.sheets[str(sheet_id_3)] = sheet_3

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    result = mongodb_list_character_sheets(CharacterSheetFilter())

    # Results should be sorted by updated_at descending (sheet_2, sheet_3, sheet_1)
    assert len(result.sheets) == 3
    assert result.sheets[0].sheet_id == sheet_id_2  # Most recent
    assert result.sheets[1].sheet_id == sheet_id_3  # Middle
    assert result.sheets[2].sheet_id == sheet_id_1  # Oldest


def test_list_character_sheets_with_multiple_filters(monkeypatch):
    """Test that listing character sheets with multiple filters applies all criteria."""
    entity_id_1 = uuid4()
    entity_id_2 = uuid4()
    system_id = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()
    sheet_id_3 = uuid4()
    sheet_id_4 = uuid4()

    # Create sheets for different entities and systems
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id_1),
        "game_system_id": str(system_id),
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id_1),
        "game_system_id": str(system_id),
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": False,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_3 = {
        "sheet_id": str(sheet_id_3),
        "entity_id": str(entity_id_2),
        "game_system_id": str(system_id),
        "stats": {"STR": 14},
        "resources": {"HP": 20},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_4 = {
        "sheet_id": str(sheet_id_4),
        "entity_id": str(entity_id_1),
        "game_system_id": str(uuid4()),  # Different system
        "stats": {"STR": 16},
        "resources": {"HP": 25},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2
    fake_mongo.sheets_db.sheets[str(sheet_id_3)] = sheet_3
    fake_mongo.sheets_db.sheets[str(sheet_id_4)] = sheet_4

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets

    # Filter by entity_id_1, game_system_id, and is_active=True
    result = mongodb_list_character_sheets(
        CharacterSheetFilter(entity_id=entity_id_1, game_system_id=system_id, is_active=True)
    )

    # Should return only sheet_1 (matches entity_id_1, system_id, and is_active=True)
    assert len(result.sheets) == 1
    assert result.sheets[0].sheet_id == sheet_id_1
    assert result.total == 1


def test_list_character_sheets_by_entity_id_and_system_source_type(
    monkeypatch,
):
    """Test that listing character sheets by entity_id and system_source_type filters correctly."""
    entity_id = uuid4()
    sheet_id_1 = uuid4()
    sheet_id_2 = uuid4()
    sheet_id_3 = uuid4()

    # Create sheets with different system_source_type
    now = datetime.now(timezone.utc)
    sheet_1 = {
        "sheet_id": str(sheet_id_1),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": "pack_embedded",
        "system_source_id": "pack_123",
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_2 = {
        "sheet_id": str(sheet_id_2),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": "generic_library",
        "system_source_id": "system_456",
        "stats": {"STR": 12},
        "resources": {"HP": 15},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet_3 = {
        "sheet_id": str(sheet_id_3),
        "entity_id": str(uuid4()),  # Different entity
        "game_system_id": None,
        "system_source_type": "pack_embedded",
        "system_source_id": "pack_123",
        "stats": {"STR": 14},
        "resources": {"HP": 20},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id_1)] = sheet_1
    fake_mongo.sheets_db.sheets[str(sheet_id_2)] = sheet_2
    fake_mongo.sheets_db.sheets[str(sheet_id_3)] = sheet_3

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import (
        mongodb_list_character_sheets,
    )

    # Filter by entity_id and system_source_type
    result = mongodb_list_character_sheets(
        CharacterSheetFilter(entity_id=entity_id, system_source_type="pack_embedded")
    )

    # Should return only sheet_1 (matches both filters)
    assert len(result.sheets) == 1
    assert result.sheets[0].sheet_id == sheet_id_1
    assert result.total == 1


def test_update_character_sheet_with_history_log_preserved(monkeypatch):
    """Test that updating a character sheet preserves existing history_log and appends new entry."""
    sheet_id = uuid4()
    entity_id = uuid4()
    now = datetime.now(timezone.utc)

    # Create sheet with existing history log
    existing_sheet = {
        "sheet_id": str(sheet_id),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": None,
        "system_source_id": None,
        "system_name": None,
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [
            {
                "timestamp": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                "change": "Initial creation",
                "scene_id": None,
                "old_value": None,
                "new_value": None,
                "field": None,
            }
        ],
        "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id)] = existing_sheet

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import (
        mongodb_update_character_sheet,
    )

    result = mongodb_update_character_sheet(
        sheet_id,
        CharacterSheetUpdate(stats={"STR": 12, "DEX": 14}, change_description="Increased stats"),
    )

    # Check that stats were updated
    assert result.stats == {"STR": 12, "DEX": 14}

    # Check that history_log was preserved and new entry was appended
    assert len(result.history_log) == 2
    assert result.history_log[0].change == "Initial creation"
    assert result.history_log[1].change == "Increased stats"
    assert result.history_log[1].timestamp >= now


def test_update_character_sheet_total_level_only(monkeypatch):
    """Test updating character sheet with only total_level field."""
    sheet_id = uuid4()
    entity_id = uuid4()

    # Create existing sheet
    existing_sheet = {
        "sheet_id": str(sheet_id),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": None,
        "system_source_id": None,
        "system_name": None,
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 1,
        "experience_points": 0,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id)] = existing_sheet

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import (
        mongodb_update_character_sheet,
    )

    result = mongodb_update_character_sheet(sheet_id, CharacterSheetUpdate(total_level=5))

    # Only total_level should change
    assert result.total_level == 5
    assert result.stats == {"STR": 10}  # Unchanged
    assert result.experience_points == 0  # Unchanged


def test_update_character_sheet_experience_points_only(monkeypatch):
    """Test updating character sheet with only experience_points field."""
    sheet_id = uuid4()
    entity_id = uuid4()

    # Create existing sheet
    datetime.now(timezone.utc)
    existing_sheet = {
        "sheet_id": str(sheet_id),
        "entity_id": str(entity_id),
        "game_system_id": None,
        "system_source_type": None,
        "system_source_id": None,
        "system_name": None,
        "stats": {"STR": 10},
        "resources": {"HP": 10},
        "skills": {},
        "class_levels": {},
        "total_level": 3,
        "experience_points": 1000,
        "background": None,
        "alignment": None,
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.sheets_db.sheets[str(sheet_id)] = existing_sheet

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.character_sheets.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.character_sheets import (
        mongodb_update_character_sheet,
    )

    result = mongodb_update_character_sheet(sheet_id, CharacterSheetUpdate(experience_points=2500))

    # Only experience_points should change
    assert result.experience_points == 2500
    assert result.stats == {"STR": 10}  # Unchanged
    assert result.total_level == 3  # Unchanged
