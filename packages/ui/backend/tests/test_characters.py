"""Tests for standalone Character CRUD endpoints (Roleplay UI)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)

BASE = "/api/entities"


def _make_char_doc(**overrides):
    """Create a sample character document with sensible defaults."""
    now = datetime.now(UTC)
    doc = {
        "id": str(uuid4()),
        "name": "Test Character",
        "description": "A brave hero",
        "avatar_url": None,
        "personality": "Bold and curious",
        "gm_notes": "Keep the story moving",
        "first_message": "Greetings, traveler!",
        "is_ooc_persona": False,
        "entity_id": None,
        "source_universe_id": None,
        "memory_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# POST /api/characters
# ---------------------------------------------------------------------------


class TestCreateCharacter:
    @patch("monitor_ui.routers.entities._create_character_doc")
    def test_create_character_success(self, mock_create):
        doc = _make_char_doc()
        mock_create.return_value = doc

        resp = client.post(f"{BASE}/characters", json={"name": "Test Character"})

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Test Character"
        assert body["id"] == doc["id"]

    @patch("monitor_ui.routers.entities._create_character_doc")
    def test_create_character_with_all_fields(self, mock_create):
        doc = _make_char_doc(
            name="Eldrin",
            description="An elven mage",
            personality="Calm and wise",
            gm_notes="Eldrin is hiding a secret",
            first_message="Well met, friend.",
            is_ooc_persona=True,
        )
        mock_create.return_value = doc

        resp = client.post(
            f"{BASE}/characters",
            json={
                "name": "Eldrin",
                "description": "An elven mage",
                "personality": "Calm and wise",
                "gm_notes": "Eldrin is hiding a secret",
                "first_message": "Well met, friend.",
                "is_ooc_persona": True,
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["is_ooc_persona"] is True


# ---------------------------------------------------------------------------
# GET /api/characters
# ---------------------------------------------------------------------------


class TestListCharacters:
    @patch("monitor_ui.routers.entities._list_characters_docs")
    def test_list_characters_empty(self, mock_list):
        mock_list.return_value = ([], 0)

        resp = client.get(f"{BASE}/characters")

        assert resp.status_code == 200
        assert resp.json() == []

    @patch("monitor_ui.routers.entities._list_characters_docs")
    def test_list_characters_returns_list(self, mock_list):
        doc = _make_char_doc()
        mock_list.return_value = ([doc], 1)

        resp = client.get(f"{BASE}/characters")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["name"] == "Test Character"


# ---------------------------------------------------------------------------
# GET /api/characters/{id}
# ---------------------------------------------------------------------------


class TestGetCharacter:
    @patch("monitor_ui.routers.entities._get_character_doc")
    def test_get_character_found(self, mock_get):
        doc = _make_char_doc()
        mock_get.return_value = doc

        resp = client.get(f"{BASE}/characters/{doc['id']}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Character"

    @patch("monitor_ui.routers.entities._get_character_doc")
    def test_get_character_not_found(self, mock_get):
        mock_get.return_value = None

        resp = client.get(f"{BASE}/characters/nonexistent")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/characters/{id}
# ---------------------------------------------------------------------------


class TestUpdateCharacter:
    @patch("monitor_ui.routers.entities._update_character_doc")
    @patch("monitor_ui.routers.entities._get_character_doc")
    def test_update_character_name(self, mock_get, mock_update):
        original = _make_char_doc()
        updated = _make_char_doc(name="Updated Name")
        mock_update.return_value = updated
        mock_get.return_value = updated

        resp = client.put(f"{BASE}/characters/{original['id']}", json={"name": "Updated Name"})

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    @patch("monitor_ui.routers.entities._update_character_doc")
    def test_update_character_not_found(self, mock_update):
        mock_update.return_value = None

        resp = client.put(f"{BASE}/characters/nonexistent", json={"name": "X"})

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/characters/{id}
# ---------------------------------------------------------------------------


class TestDeleteCharacter:
    @patch("monitor_ui.routers.entities._delete_character_doc")
    def test_delete_character_success(self, mock_delete):
        mock_delete.return_value = True

        resp = client.delete(f"{BASE}/characters/some-id")

        assert resp.status_code == 204

    @patch("monitor_ui.routers.entities._delete_character_doc")
    def test_delete_character_not_found(self, mock_delete):
        mock_delete.return_value = False

        resp = client.delete(f"{BASE}/characters/nonexistent")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/characters/{id}/memories
# ---------------------------------------------------------------------------


class TestGetCharacterMemories:
    @patch("monitor_ui.routers.entities._get_character_doc")
    def test_memories_empty_when_no_entity_id(self, mock_get):
        """Character without entity_id should return empty memories."""
        mock_get.return_value = _make_char_doc(entity_id=None)

        resp = client.get(f"{BASE}/characters/char-1/memories")

        assert resp.status_code == 200
        body = resp.json()
        assert body["memories"] == []
        assert body["total"] == 0

    @patch("monitor_ui.routers.entities._get_character_doc")
    def test_memories_character_not_found(self, mock_get):
        """Asking memories for nonexistent character returns 404."""
        mock_get.return_value = None

        resp = client.get(f"{BASE}/characters/nonexistent/memories")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/characters/{id}/memories
# ---------------------------------------------------------------------------


class TestClearCharacterMemories:
    @patch("monitor_ui.routers.entities._get_character_doc")
    def test_clear_memories_no_entity_id_is_noop(self, mock_get):
        """Clearing memories for character without entity_id should succeed (204)."""
        mock_get.return_value = _make_char_doc(entity_id=None)

        resp = client.delete(f"{BASE}/characters/char-1/memories")

        assert resp.status_code == 204

    @patch("monitor_ui.routers.entities._get_character_doc")
    def test_clear_memories_character_not_found(self, mock_get):
        """Clearing memories for nonexistent character returns 404."""
        mock_get.return_value = None

        resp = client.delete(f"{BASE}/characters/nonexistent/memories")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/characters/{id}/import-from-universe
# ---------------------------------------------------------------------------


class TestImportFromUniverse:
    @patch("monitor_data.db.neo4j.get_neo4j_client")
    @patch("monitor_ui.routers.entities._create_character_doc")
    @patch("monitor_ui.routers.entities._get_character_doc")
    def test_import_requires_neo4j_entity(self, mock_get, mock_create, mock_neo4j):
        """Import from universe should fail gracefully if Neo4j is unavailable."""
        mock_get.return_value = _make_char_doc()
        # Simulate Neo4j being unavailable
        mock_neo4j.side_effect = Exception("Neo4j connection failed")

        # The endpoint should return 502 when Neo4j fails
        resp = client.post(
            f"{BASE}/characters/char-1/import-from-universe",
            json={"source_entity_id": "neo4j-entity-1", "as_ooc_persona": False},
        )

        # Our endpoint catches Neo4j exceptions and returns 502
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Character sheet endpoints  (GAP-B)
# ---------------------------------------------------------------------------


def _make_sheet_payload(sheet_id=None, **overrides):
    """Full, schema-valid CharacterSheetResponse payload for endpoint mocks."""
    payload = {
        "sheet_id": str(sheet_id or uuid4()),
        "entity_id": str(uuid4()),
        "game_system_id": str(uuid4()),
        "system_source_type": None,
        "system_source_id": None,
        "system_name": "Aldric's System",
        "stats": {"hp": {"current": 30, "max": 30}},
        "resources": {},
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
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": None,
    }
    payload.update(overrides)
    return payload


class TestGetCharacterSheet:
    @patch("monitor_data.tools.mongodb_tools.character_sheets.mongodb_get_character_sheet")
    def test_get_sheet_success(self, mock_get):
        sheet_id = uuid4()
        mock_get.return_value = _make_sheet_payload(sheet_id)

        resp = client.get(f"{BASE}/character-sheets/{sheet_id}")

        assert resp.status_code == 200
        assert resp.json()["sheet_id"] == str(sheet_id)
        assert resp.json()["stats"]["hp"]["max"] == 30

    @patch("monitor_data.tools.mongodb_tools.character_sheets.mongodb_get_character_sheet")
    def test_get_sheet_not_found(self, mock_get):
        mock_get.return_value = None

        resp = client.get(f"{BASE}/character-sheets/{uuid4()}")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/entities/character-sheets/{sheet_id}  (GAP-B)
# ---------------------------------------------------------------------------


class TestUpdateCharacterSheet:
    @patch("monitor_data.tools.mongodb_tools.character_sheets.mongodb_update_character_sheet")
    def test_update_sheet_success(self, mock_update):
        sheet_id = uuid4()
        mock_update.return_value = _make_sheet_payload(sheet_id, stats={"hp": {"current": 25, "max": 30}})

        resp = client.patch(
            f"{BASE}/character-sheets/{sheet_id}",
            json={"stats": {"hp": {"current": 25, "max": 30}}},
        )

        assert resp.status_code == 200
        assert resp.json()["stats"]["hp"]["current"] == 25

    @patch("monitor_data.tools.mongodb_tools.character_sheets.mongodb_update_character_sheet")
    def test_update_sheet_not_found(self, mock_update):
        mock_update.side_effect = ValueError("not found")

        resp = client.patch(
            f"{BASE}/character-sheets/{uuid4()}",
            json={"stats": {"hp": {"current": 10}}},
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/entities/character-sheets/{sheet_id}  (GAP-B)
# ---------------------------------------------------------------------------


class TestDeleteCharacterSheet:
    @patch("monitor_data.db.mongodb.get_mongodb_client")
    def test_delete_sheet_success(self, mock_get_client):
        mock_coll = MagicMock()
        mock_coll.update_one.return_value.matched_count = 1
        mock_get_client.return_value.get_collection.return_value = mock_coll

        resp = client.delete(f"{BASE}/character-sheets/{uuid4()}")

        assert resp.status_code == 204
        mock_coll.update_one.assert_called_once()

    @patch("monitor_data.db.mongodb.get_mongodb_client")
    def test_delete_sheet_not_found(self, mock_get_client):
        mock_coll = MagicMock()
        mock_coll.update_one.return_value.matched_count = 0
        mock_get_client.return_value.get_collection.return_value = mock_coll

        resp = client.delete(f"{BASE}/character-sheets/{uuid4()}")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/entities/character-sheets  (GAP-B)
# ---------------------------------------------------------------------------


class TestListCharacterSheets:
    @patch("monitor_data.tools.mongodb_tools.character_sheets.mongodb_list_character_sheets")
    def test_list_sheets_empty(self, mock_list):
        mock_list.return_value = {"sheets": [], "total": 0, "limit": 20, "offset": 0}

        resp = client.get(f"{BASE}/character-sheets")

        assert resp.status_code == 200
        assert resp.json()["sheets"] == []

    @patch("monitor_data.tools.mongodb_tools.character_sheets.mongodb_list_character_sheets")
    def test_list_sheets_with_entity_filter(self, mock_list):
        entity_id = uuid4()
        mock_list.return_value = {
            "sheets": [_make_sheet_payload()],
            "total": 1,
            "limit": 20,
            "offset": 0,
        }

        resp = client.get(f"{BASE}/character-sheets?entity_id={entity_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["sheets"]) == 1
        mock_list.assert_called_once()
        call_params = mock_list.call_args[0][0]
        assert call_params.entity_id == entity_id

    @patch("monitor_data.tools.mongodb_tools.character_sheets.mongodb_list_character_sheets")
    def test_list_sheets_with_game_system_filter(self, mock_list):
        game_system_id = uuid4()
        mock_list.return_value = {"sheets": [], "total": 0, "limit": 10, "offset": 5}

        resp = client.get(f"{BASE}/character-sheets?game_system_id={game_system_id}&limit=10&offset=5")

        assert resp.status_code == 200
        call_params = mock_list.call_args[0][0]
        assert call_params.game_system_id == game_system_id
        assert call_params.limit == 10
        assert call_params.offset == 5
