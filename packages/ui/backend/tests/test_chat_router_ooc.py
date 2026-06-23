"""Tests for OOC/IC chat mode routing (Roleplay UI)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app


client = TestClient(app)

BASE = "/api/chat"


def _make_session(session_id: str | None = None, **overrides) -> dict:
    """Create a minimal session dict."""
    now = datetime.now(timezone.utc).isoformat()
    sid = session_id or str(uuid4())
    session = {
        "id": sid,
        "title": "Test Session",
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


class TestOOCRouting:
    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_send_message_ooc_mode_routes_to_ooc_turn(
        self, _msgs, _sessions, mock_save_session, mock_save_msg
    ):
        """Sending chat_mode='ooc' with character_id should use run_ooc_turn."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        _msgs[session_id] = []

        with patch(
            "monitor_ui.routers.chat_loops.run_ooc_turn", new=AsyncMock()
        ) as mock_ooc:
            mock_ooc.return_value = (
                "The dragon nods slowly.",
                {
                    "type": "character_response",
                    "chat_mode": "ooc",
                    "character_id": "char-1",
                },
            )
            resp = client.post(
                f"{BASE}/{session_id}/send",
                json={
                    "content": "Hello dragon",
                    "chat_mode": "ooc",
                    "character_id": "char-1",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["chat_mode"] == "ooc"
        assert body["character_id"] == "char-1"
        mock_ooc.assert_called_once()

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_send_message_ooc_no_scene_created(
        self, _msgs, _sessions, mock_save_session, mock_save_msg
    ):
        """OOC messages should not trigger the SceneLoop."""
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
            mock_ooc.return_value = (
                "Hi there!",
                {"type": "character_response", "chat_mode": "ooc"},
            )
            resp = client.post(
                f"{BASE}/{session_id}/send",
                json={
                    "content": "Hello",
                    "chat_mode": "ooc",
                    "character_id": "char-1",
                },
            )

        assert resp.status_code == 200
        mock_scene.assert_not_called()

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_send_message_is_ooc_persona_skips_scene_loop(
        self, _msgs, _sessions, mock_save_session, mock_save_msg
    ):
        """is_ooc_persona=True with character_id should route to OOC turn."""
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
            mock_ooc.return_value = (
                "I'm here for you.",
                {"type": "character_response", "chat_mode": "ooc"},
            )
            resp = client.post(
                f"{BASE}/{session_id}/send",
                json={
                    "content": "Talk to me",
                    "is_ooc_persona": True,
                    "character_id": "char-ooc-1",
                },
            )

        assert resp.status_code == 200
        mock_scene.assert_not_called()
        mock_ooc.assert_called_once()

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_send_message_ic_without_character_goes_to_scene_loop(
        self, _msgs, _sessions, mock_save_session, mock_save_msg
    ):
        """IC message without character_id should use the normal scene loop."""
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
                "The goblin attacks!",
                {"type": "scene_turn", "phase": "active_play"},
            )
            resp = client.post(
                f"{BASE}/{session_id}/send",
                json={"content": "I attack the goblin"},
            )

        assert resp.status_code == 200
        mock_ooc.assert_not_called()
        mock_scene.assert_called_once()


class TestICCharacterIdPropagation:
    """GAP-9: When character_id is sent with IC mode, it must propagate to the session."""

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_ic_with_character_id_updates_speaker_character_id(
        self, _msgs, _sessions, mock_save_session, mock_save_msg
    ):
        """IC message with character_id should update session speaker_character_id."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id, speaker_character_id=None)
        _msgs[session_id] = []

        with (
            patch(
                "monitor_ui.routers.chat_loops.run_ooc_turn", new=AsyncMock()
            ) as mock_ooc,
            patch(
                "monitor_ui.routers.chat._run_scene_turn", new=AsyncMock()
            ) as mock_scene,
            patch("monitor_ui.routers.chat._pop_scene_loop") as mock_pop,
        ):
            mock_scene.return_value = (
                "The knight salutes.",
                {"type": "scene_turn", "phase": "active_play"},
            )
            resp = client.post(
                f"{BASE}/{session_id}/send",
                json={
                    "content": "I greet the knight",
                    "chat_mode": "ic",
                    "character_id": "char-aldrick",
                },
            )

        assert resp.status_code == 200
        # Speaker should be updated on the session
        assert _sessions[session_id].get("speaker_character_id") == "char-aldrick"
        # Scene loop cache should be invalidated (new actor)
        mock_pop.assert_called_once_with(session_id)
        mock_ooc.assert_not_called()

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_ic_without_character_id_does_not_change_speaker(
        self, _msgs, _sessions, mock_save_session, mock_save_msg
    ):
        """IC message without character_id should not alter the session speaker."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(
            session_id, speaker_character_id="existing-char"
        )
        _msgs[session_id] = []

        with (
            patch("monitor_ui.routers.chat_loops.run_ooc_turn", new=AsyncMock()),
            patch(
                "monitor_ui.routers.chat._run_scene_turn", new=AsyncMock()
            ) as mock_scene,
            patch("monitor_ui.routers.chat._pop_scene_loop"),
        ):
            mock_scene.return_value = (
                "The world continues.",
                {"type": "scene_turn", "phase": "active_play"},
            )
            resp = client.post(
                f"{BASE}/{session_id}/send",
                json={"content": "I look around"},
            )

        assert resp.status_code == 200
        # Speaker should remain unchanged
        assert _sessions[session_id].get("speaker_character_id") == "existing-char"


class TestPlayerMessageMetadata:
    """GAP-6: Player messages must carry character_id and chat_mode metadata."""

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_player_msg_includes_character_id_in_metadata(
        self, _msgs, _sessions, mock_save_session, mock_save_msg
    ):
        """Player message metadata should contain character_id when provided."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id, speaker_character_id=None)
        _msgs[session_id] = []

        with (
            patch("monitor_ui.routers.chat_loops.run_ooc_turn", new=AsyncMock()),
            patch(
                "monitor_ui.routers.chat._run_scene_turn", new=AsyncMock()
            ) as mock_scene,
            patch("monitor_ui.routers.chat._pop_scene_loop"),
        ):
            mock_scene.return_value = (
                "The dragon nods.",
                {"type": "scene_turn", "phase": "active_play"},
            )
            client.post(
                f"{BASE}/{session_id}/send",
                json={
                    "content": "I draw my sword",
                    "chat_mode": "ic",
                    "character_id": "char-aldrick",
                },
            )

        # The first message stored should be the player message
        player_msg = _msgs[session_id][0]
        assert player_msg["role"] == "player"
        assert player_msg["metadata"].get("character_id") == "char-aldrick"
        assert player_msg["metadata"].get("chat_mode") == "ic"

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_player_msg_without_character_id_has_empty_metadata(
        self, _msgs, _sessions, mock_save_session, mock_save_msg
    ):
        """Player message without character_id should have empty metadata."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        _msgs[session_id] = []

        with (
            patch("monitor_ui.routers.chat_loops.run_ooc_turn", new=AsyncMock()),
            patch(
                "monitor_ui.routers.chat._run_scene_turn", new=AsyncMock()
            ) as mock_scene,
        ):
            mock_scene.return_value = (
                "The goblin flees.",
                {"type": "scene_turn", "phase": "active_play"},
            )
            client.post(
                f"{BASE}/{session_id}/send",
                json={"content": "I attack the goblin"},
            )

        player_msg = _msgs[session_id][0]
        assert player_msg["role"] == "player"
        assert player_msg["metadata"] == {"chat_mode": "ic"}
