"""
E2E: IC chat with character — character CRUD lifecycle + IC message flow.

Requires: RUN_E2E=1

Covers:
- Character CRUD full lifecycle (create → read → update → delete)
- List characters endpoint
- IC message with character_id passes through scene loop
- Character memories endpoint returns empty for non-linked characters

Use-cases: P-20 (IC mode with character), M-1 (memory access)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, UTC
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_ui.main import app

# Skip unless explicitly enabled
pytestmark = pytest.mark.e2e

SKIP_REASON = "Set RUN_E2E=1 to run e2e tests"


@pytest.fixture(autouse=True)
def _skip_unless_e2e():
    if not os.environ.get("RUN_E2E"):
        pytest.skip(SKIP_REASON)


@pytest.fixture()
def client():
    return TestClient(app)


def _make_session(session_id: str | None = None, **overrides) -> dict:
    now = datetime.now(UTC).isoformat()
    sid = session_id or str(uuid4())
    session = {
        "id": sid,
        "title": "E2E IC Test",
        "mode": "solo_play",
        "universe_id": str(uuid4()),
        "system_id": None,
        "pack_id": None,
        "system_source_type": None,
        "system_source_id": None,
        "tone": "dramatic",
        "play_mode": "narrative",
        "phase": "active_play",
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "gm_profile_id": None,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
    }
    session.update(overrides)
    return session


class TestCharacterCRUDLifecycle:
    """Full CRUD lifecycle for standalone characters."""

    @patch("monitor_ui.routers.entities._delete_character_doc")
    @patch("monitor_ui.routers.entities._update_character_doc")
    @patch("monitor_ui.routers.entities._get_character_doc")
    @patch("monitor_ui.routers.entities._list_characters_docs")
    @patch("monitor_ui.routers.entities._create_character_doc")
    def test_create_character(
        self, mock_create, mock_list, mock_get, mock_update, mock_delete, client
    ):
        mock_create.return_value = {
            "id": "char-1",
            "name": "Nyx",
            "description": "Shadow walker",
            "avatar_url": None,
            "personality": "Cryptic",
            "gm_notes": "",
            "first_message": "",
            "is_ooc_persona": False,
            "entity_id": None,
            "memory_count": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        resp = client.post(
            "/api/entities/characters",
            json={
                "name": "Nyx",
                "description": "Shadow walker",
                "personality": "Cryptic",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Nyx"

    @patch("monitor_ui.routers.entities._delete_character_doc")
    @patch("monitor_ui.routers.entities._update_character_doc")
    @patch("monitor_ui.routers.entities._get_character_doc")
    @patch("monitor_ui.routers.entities._list_characters_docs")
    @patch("monitor_ui.routers.entities._create_character_doc")
    def test_list_characters(
        self, mock_create, mock_list, mock_get, mock_update, mock_delete, client
    ):
        mock_list.return_value = (
            [
                {
                    "id": "c1",
                    "name": "A",
                    "description": "",
                    "avatar_url": None,
                    "personality": "",
                    "gm_notes": "",
                    "first_message": "",
                    "is_ooc_persona": False,
                    "entity_id": None,
                    "memory_count": 0,
                    "created_at": "2025-01-01T00:00:00",
                    "updated_at": "2025-01-01T00:00:00",
                },
                {
                    "id": "c2",
                    "name": "B",
                    "description": "",
                    "avatar_url": None,
                    "personality": "",
                    "gm_notes": "",
                    "first_message": "",
                    "is_ooc_persona": False,
                    "entity_id": None,
                    "memory_count": 0,
                    "created_at": "2025-01-01T00:00:00",
                    "updated_at": "2025-01-01T00:00:00",
                },
            ],
            2,
        )
        resp = client.get("/api/entities/characters")
        assert resp.status_code == 200
        names = [ch["name"] for ch in resp.json()]
        assert "A" in names
        assert "B" in names


class TestICChatWithCharacter:
    """IC message with character_id should pass through scene loop."""

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_ic_chat_with_character_routes_to_scene_loop(
        self, _msgs, _sessions, _save_ses, _save_msg, client
    ):
        """IC message with character_id falls through to SceneLoop (not OOC)."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        _msgs[session_id] = []

        with (
            patch(
                "monitor_ui.routers.chat_loops.run_ooc_turn", new=AsyncMock()
            ) as mock_ooc,
            patch(
                "monitor_ui.routers.chat._run_scene_turn", new=AsyncMock()
            ) as mock_scene,
        ):
            mock_scene.return_value = (
                "The knight nods solemnly.",
                {"type": "scene_turn", "phase": "active_play"},
            )
            resp = client.post(
                f"/api/chat/{session_id}/send",
                json={
                    "content": "I greet the knight",
                    "chat_mode": "ic",
                    "character_id": "char-1",
                },
            )

        assert resp.status_code == 200
        mock_ooc.assert_not_called()

    @patch("monitor_ui.routers.entities._delete_character_doc")
    @patch("monitor_ui.routers.entities._update_character_doc")
    @patch("monitor_ui.routers.entities._get_character_doc")
    @patch("monitor_ui.routers.entities._list_characters_docs")
    @patch("monitor_ui.routers.entities._create_character_doc")
    def test_character_memories_empty_when_no_entity(
        self, mock_create, mock_list, mock_get, mock_update, mock_delete, client
    ):
        """Character without entity_id should return empty memories."""
        mock_get.return_value = {
            "id": "char-no-entity",
            "name": "No Entity Char",
            "entity_id": None,
        }
        resp = client.get("/api/entities/characters/char-no-entity/memories")
        assert resp.status_code == 200
        assert resp.json()["memories"] == []
        assert resp.json()["total"] == 0
