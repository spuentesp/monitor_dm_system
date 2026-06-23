"""
E2E: OOC chat flow — OOC message routing with character.

Requires: RUN_E2E=1

Covers:
- Create session in active_play phase
- Send OOC message with chat_mode="ooc" + character_id
- Verify: run_ooc_turn is invoked, _run_scene_turn is NOT

Use-cases: P-20 (OOC/AI Persona mode)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
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
def api_client():
    return TestClient(app)


def _make_session(session_id: str | None = None, **overrides) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    sid = session_id or str(uuid4())
    session = {
        "id": sid,
        "title": "E2E OOC Test",
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


class TestOOCChatRouting:
    """OOC chat routing — verifies correct handler dispatch."""

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_ooc_message_routes_to_ooc_turn(self, _msgs, _sessions, _save_ses, _save_msg):
        """OOC message with character_id should route to run_ooc_turn."""
        session_id = str(uuid4())
        _sessions[session_id] = _make_session(session_id)
        _msgs[session_id] = []

        with patch(
            "monitor_ui.routers.chat_loops.run_ooc_turn", new=AsyncMock()
        ) as mock_ooc:
            mock_ooc.return_value = (
                "The shadows welcome you… I am Nyx.",
                {
                    "type": "character_response",
                    "chat_mode": "ooc",
                    "character_id": "char-1",
                },
            )
            client = TestClient(app)
            resp = client.post(
                f"/api/chat/{session_id}/send",
                json={
                    "content": "Hello, Nyx",
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
    def test_ooc_message_does_not_trigger_scene_loop(
        self, _msgs, _sessions, _save_ses, _save_msg
    ):
        """OOC messages should NOT trigger the SceneLoop."""
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
            client = TestClient(app)
            resp = client.post(
                f"/api/chat/{session_id}/send",
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
    def test_is_ooc_persona_routes_to_ooc(self, _msgs, _sessions, _save_ses, _save_msg):
        """is_ooc_persona=True with character_id should route to OOC, not SceneLoop."""
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
                "I am Echo.",
                {"type": "character_response", "chat_mode": "ooc"},
            )
            client = TestClient(app)
            resp = client.post(
                f"/api/chat/{session_id}/send",
                json={
                    "content": "Hello",
                    "is_ooc_persona": True,
                    "character_id": "char-2",
                },
            )

        assert resp.status_code == 200
        mock_scene.assert_not_called()
        mock_ooc.assert_called_once()

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_ic_message_without_character_uses_scene_loop(
        self, _msgs, _sessions, _save_ses, _save_msg
    ):
        """IC message without character_id should route to SceneLoop, not OOC."""
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
                "The goblin growls.",
                {"type": "scene_turn", "phase": "active_play"},
            )
            client = TestClient(app)
            resp = client.post(
                f"/api/chat/{session_id}/send",
                json={"content": "I attack the goblin"},
            )

        assert resp.status_code == 200
        mock_ooc.assert_not_called()
        mock_scene.assert_called_once()