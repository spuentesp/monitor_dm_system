"""GAP-B: Character Sheet CRUD endpoint tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)
BASE = "/api/entities"


def _make_sheet(**overrides):
    """Return a minimal valid CharacterSheetResponse dict."""
    now = datetime.now(timezone.utc)
    sheet = {
        "sheet_id": str(uuid4()),
        "entity_id": str(uuid4()),
        "game_system_id": str(uuid4()),
        "system_source_type": None,
        "system_source_id": None,
        "system_name": "D&D 5e",
        "stats": {"hp": {"current": 30, "max": 30}},
        "resources": {},
        "skills": {},
        "class_levels": {"fighter": 3},
        "total_level": 3,
        "experience_points": 0,
        "background": None,
        "alignment": "neutral",
        "equipment": [],
        "special_abilities": [],
        "spells_known": [],
        "notes": None,
        "is_active": True,
        "history_log": [],
        "created_at": now,
        "updated_at": now,
    }
    sheet.update(overrides)
    return sheet


# ---------------------------------------------------------------------------
# GET /api/entities/character-sheets/{sheet_id}
# ---------------------------------------------------------------------------


class TestGetCharacterSheet:
    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_get_character_sheet"
    )
    def test_get_sheet_success(self, mock_get):
        sheet_id = uuid4()
        mock_get.return_value = _make_sheet(
            sheet_id=str(sheet_id), system_name="Aldric"
        )

        resp = client.get(f"{BASE}/character-sheets/{sheet_id}")

        assert resp.status_code == 200
        assert resp.json()["system_name"] == "Aldric"
        mock_get.assert_called_once_with(sheet_id)

    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_get_character_sheet"
    )
    def test_get_sheet_not_found(self, mock_get):
        mock_get.return_value = None
        sheet_id = uuid4()

        resp = client.get(f"{BASE}/character-sheets/{sheet_id}")

        assert resp.status_code == 404
        mock_get.assert_called_once_with(sheet_id)


# ---------------------------------------------------------------------------
# PATCH /api/entities/character-sheets/{sheet_id}
# ---------------------------------------------------------------------------


class TestUpdateCharacterSheet:
    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_update_character_sheet"
    )
    def test_update_sheet_success(self, mock_update):
        sheet_id = uuid4()
        mock_update.return_value = _make_sheet(
            sheet_id=str(sheet_id),
            name="Aldric",
            stats={"hp": {"current": 25, "max": 30}},
        )

        resp = client.patch(
            f"{BASE}/character-sheets/{sheet_id}",
            json={"stats": {"hp": {"current": 25, "max": 30}}},
        )

        assert resp.status_code == 200
        assert resp.json()["stats"]["hp"]["current"] == 25
        mock_update.assert_called_once()

    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_update_character_sheet"
    )
    def test_update_sheet_not_found(self, mock_update):
        sheet_id = uuid4()
        mock_update.side_effect = ValueError("Character sheet not found")

        resp = client.patch(
            f"{BASE}/character-sheets/{sheet_id}",
            json={"stats": {"hp": {"current": 10}}},
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/entities/character-sheets/{sheet_id}
# ---------------------------------------------------------------------------


class TestDeleteCharacterSheet:
    @patch("monitor_data.db.mongodb.get_mongodb_client")
    def test_delete_sheet_success(self, mock_get_client):
        sheet_id = uuid4()
        mock_coll = MagicMock()
        mock_coll.update_one.return_value.matched_count = 1
        mock_get_client.return_value.get_collection.return_value = mock_coll

        resp = client.delete(f"{BASE}/character-sheets/{sheet_id}")

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
# GET /api/entities/character-sheets  (LIST)
# Note: List tests may exhibit Starlette testclient behavior differences
# ---------------------------------------------------------------------------


class TestListCharacterSheets:
    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_list_character_sheets"
    )
    def test_list_sheets_empty(self, mock_list):
        mock_list.return_value = {
            "sheets": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
        }

        resp = client.get(f"{BASE}/character-sheets")

        assert resp.status_code == 200
        assert resp.json()["sheets"] == []
        mock_list.assert_called_once()

    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_list_character_sheets"
    )
    def test_list_sheets_with_entity_filter(self, mock_list):
        entity_id = uuid4()
        mock_list.return_value = {
            "sheets": [_make_sheet(system_name="Aldric")],
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
        assert str(call_params.entity_id) == str(entity_id)

    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_list_character_sheets"
    )
    def test_list_sheets_with_game_system_filter(self, mock_list):
        gs_id = uuid4()
        mock_list.return_value = {"sheets": [], "total": 0, "limit": 10, "offset": 5}

        resp = client.get(
            f"{BASE}/character-sheets?game_system_id={gs_id}&limit=10&offset=5"
        )

        assert resp.status_code == 200
        call_params = mock_list.call_args[0][0]
        assert str(call_params.game_system_id) == str(gs_id)
        assert call_params.limit == 10
        assert call_params.offset == 5

    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_list_character_sheets"
    )
    def test_list_sheets_is_active_filter(self, mock_list):
        mock_list.return_value = {"sheets": [], "total": 0, "limit": 20, "offset": 0}

        resp = client.get(f"{BASE}/character-sheets?is_active=false")

        assert resp.status_code == 200
        call_params = mock_list.call_args[0][0]
        assert call_params.is_active is False

    @patch(
        "monitor_data.tools.mongodb_tools.character_sheets.mongodb_list_character_sheets"
    )
    def test_list_sheets_default_pagination(self, mock_list):
        mock_list.return_value = {"sheets": [], "total": 0, "limit": 20, "offset": 0}

        resp = client.get(f"{BASE}/character-sheets")

        assert resp.status_code == 200
        call_params = mock_list.call_args[0][0]
        assert call_params.limit == 20
        assert call_params.offset == 0
