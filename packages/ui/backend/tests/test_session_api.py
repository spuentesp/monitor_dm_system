"""Tests for session CRUD via the chat router (GAP-Q: chat_mode persistence)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app


client = TestClient(app)

BASE = "/api/chat"


def _make_session(session_id: str | None = None, **overrides) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    sid = session_id or str(uuid4())
    session = {
        "id": sid,
        "title": "Test Session",
        "mode": "solo_play",
        "multiverse_id": None,
        "multiverse_label": None,
        "universe_id": str(uuid4()),
        "universe_label": None,
        "world_id": None,
        "character_id": None,
        "speaker_character_id": None,
        "speaker_label": None,
        "controlled_character_ids": [],
        "system_id": None,
        "pack_id": None,
        "system_source_type": None,
        "system_source_id": None,
        "system_label": None,
        "benchmark_id": None,
        "benchmark_label": None,
        "tone": "dramatic",
        "gm_profile_id": None,
        "play_mode": "narrative",
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "chat_mode": "ic",
        "created_at": now,
        "updated_at": now,
    }
    session.update(overrides)
    return session


class TestChatModePersistence:
    """GAP-Q: Verify chat_mode is stored on session and returned by API."""

    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_session_default_chat_mode_is_ic(self, _msgs, _sessions, _save):
        """New sessions should default to chat_mode='ic'."""
        resp = client.post(f"{BASE}/", json={"title": "GAP-Q Session"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["chat_mode"] == "ic"

    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_create_session_with_chat_mode_ooc(self, _msgs, _sessions, _save):
        """Creating a session with chat_mode='ooc' should persist it."""
        resp = client.post(
            f"{BASE}/", json={"title": "OOC Session", "chat_mode": "ooc"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["chat_mode"] == "ooc"

    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_patch_session_chat_mode(self, _msgs, _sessions, _save):
        """Patching chat_mode should update the session."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id, chat_mode="ic")
        _msgs[session_id] = []

        resp = client.patch(f"{BASE}/{session_id}", json={"chat_mode": "ooc"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["chat_mode"] == "ooc"
        # Also verify in-memory dict
        assert _sessions[session_id]["chat_mode"] == "ooc"

    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_patch_session_invalid_chat_mode_returns_422(self, _msgs, _sessions, _save):
        """Patching with an invalid chat_mode should return 422."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        _msgs[session_id] = []

        resp = client.patch(f"{BASE}/{session_id}", json={"chat_mode": "invalid"})
        assert resp.status_code == 422

    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_list_sessions_includes_chat_mode(self, _msgs, _sessions, _save):
        """Listed sessions should include chat_mode."""
        sid1 = str(uuid4())
        sid2 = str(uuid4())
        _sessions[sid1] = _make_session(sid1, chat_mode="ic")
        _sessions[sid2] = _make_session(sid2, chat_mode="ooc")
        _msgs[sid1] = []
        _msgs[sid2] = []

        resp = client.get(f"{BASE}/")
        assert resp.status_code == 200
        data = resp.json()
        by_id = {s["id"]: s for s in data}
        assert by_id[sid1]["chat_mode"] == "ic"
        assert by_id[sid2]["chat_mode"] == "ooc"


# ---------------------------------------------------------------------------
# GAP-K: Server-side first_message greeting
# ---------------------------------------------------------------------------


class TestGreetCharacter:
    """GAP-K: Server-side first_message endpoint."""

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    @patch("monitor_ui.routers.character_storage.get_character")
    def test_greet_creates_character_message(
        self, mock_get_char, _msgs, _sessions, _save_session, _save_msg
    ):
        """Greet endpoint creates a 'character' role message with first_message."""
        session_id = str(uuid4())
        char_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        _msgs[session_id] = []
        mock_get_char.return_value = {
            "id": char_id,
            "name": "Aria",
            "first_message": "Welcome, adventurer!",
        }

        resp = client.post(f"{BASE}/{session_id}/greet?character_id={char_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "character"
        assert body["content"] == "Welcome, adventurer!"
        assert body["metadata"]["character_id"] == char_id
        assert body["metadata"]["type"] == "first_message"
        assert body["metadata"]["character_name"] == "Aria"

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    @patch("monitor_ui.routers.character_storage.get_character")
    def test_greet_idempotent_no_duplicate(
        self, mock_get_char, _msgs, _sessions, _save_session, _save_msg
    ):
        """Calling greet twice for same character should not create duplicate."""
        session_id = str(uuid4())
        char_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        # Simulate existing greeting message
        existing_msg = {
            "id": str(uuid4()),
            "session_id": session_id,
            "role": "character",
            "content": "Hello!",
            "timestamp": "2025-01-01T00:00:00Z",
            "metadata": {"character_id": char_id, "type": "first_message"},
            "chat_mode": "ic",
        }
        _msgs[session_id] = [existing_msg]
        mock_get_char.return_value = {
            "id": char_id,
            "name": "Aria",
            "first_message": "Hello!",
        }

        resp = client.post(f"{BASE}/{session_id}/greet?character_id={char_id}")

        assert resp.status_code == 200
        # Should return existing message, not create a new one
        body = resp.json()
        assert body["content"] == "Hello!"
        _save_msg.assert_not_called()

    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_greet_session_not_found(self, _msgs, _sessions):
        """Greet with nonexistent session returns 404."""
        _sessions.clear()
        _msgs.clear()
        resp = client.post(f"{BASE}/nonexistent/greet?character_id=char-1")
        assert resp.status_code == 404

    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    @patch("monitor_ui.routers.character_storage.get_character")
    def test_greet_character_not_found(self, mock_get_char, _msgs, _sessions, _save):
        """Greet with nonexistent character returns 404."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        _msgs[session_id] = []
        mock_get_char.return_value = None

        resp = client.post(f"{BASE}/{session_id}/greet?character_id=nonexistent")

        assert resp.status_code == 404

    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    @patch("monitor_ui.routers.character_storage.get_character")
    def test_greet_retconned_character_returns_404(
        self, mock_get_char, _msgs, _sessions, _save
    ):
        """Greet for a retconned (soft-deleted) character returns 404."""
        session_id = str(uuid4())
        char_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        _msgs[session_id] = []
        mock_get_char.return_value = {
            "id": char_id,
            "name": "Gone",
            "first_message": "I'm gone",
            "status": "retconned",
        }

        resp = client.post(f"{BASE}/{session_id}/greet?character_id={char_id}")

        assert resp.status_code == 404
