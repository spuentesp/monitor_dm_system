"""Tests for the [G-1](c) skip-preplay endpoint.

Covers the three POSTs ``/{session_id}/skip-preplay`` accepts/rejects:
  * 404 for unknown session
  * 409 when session is already past pre-play
  * 200 when session is in a pre-play phase (returns the prologue GM
    message, ``phase`` field flips to ``active_play``)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)

BASE = "/api/chat"


def _make_session(session_id: str | None = None, *, phase: str = "session_zero", **overrides) -> dict:
    now = datetime.now(UTC).isoformat()
    sid = session_id or str(uuid4())
    session = {
        "id": sid,
        "title": "Skip Session",
        "mode": "solo_play",
        "multiverse_id": None,
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
        "scene_id": None,
        "story_id": None,
        "chat_mode": "ic",
        "phase": phase,
        "session_zero_summary": None,
        "created_at": now,
        "updated_at": now,
    }
    session.update(overrides)
    return session


def test_skip_preplay_returns_404_for_unknown_session() -> None:
    """Unknown session id → 404, no LLM/fanout side effects."""
    with patch("monitor_ui.routers.chat._db_save_session"), patch("monitor_ui.routers.chat._db_save_message"):
        with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
            resp = client.post(f"{BASE}/{uuid4()}/skip-preplay")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session not found"


def test_skip_preplay_returns_409_when_already_in_active_play() -> None:
    """Session already in active_play is past pre-play → 409 (no no-op silently)."""
    sid = str(uuid4())
    session = _make_session(session_id=sid, phase="active_play")

    with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
        with patch("monitor_ui.routers.chat._SESSIONS", new={sid: session}):
            with patch("monitor_ui.routers.chat._db_save_session") as mock_save:
                resp = client.post(f"{BASE}/{sid}/skip-preplay")

    assert resp.status_code == 409
    assert "already past pre-play" in resp.json()["detail"]
    mock_save.assert_not_called()


def test_skip_preplay_advances_session_phase_and_persists_message() -> None:
    """Pre-play phase → 200, phase flips to active_play, GM message saved."""
    sid = str(uuid4())
    session = _make_session(session_id=sid, phase="session_zero")

    with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
        with patch("monitor_ui.routers.chat._SESSIONS", new={sid: session}):
            with patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict) as msgs:
                with patch("monitor_ui.routers.chat._db_save_session") as mock_save_session:
                    with patch("monitor_ui.routers.chat._db_save_message") as mock_save_msg:
                        with patch("monitor_ui.routers.chat._pop_session_zero_loop") as mock_pop_sz:
                            with patch("monitor_ui.routers.chat._pop_char_creation_loop") as mock_pop_cc:
                                resp = client.post(f"{BASE}/{sid}/skip-preplay")

    # Endpoint succeeded
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "gm"
    assert body["session_id"] == sid
    # meta is on the message envelope — skip_preplay marker
    assert body.get("metadata", {}).get("skip_preplay") is True

    # Phase flipped and saved
    assert session["phase"] == "active_play"
    mock_save_session.assert_called_once()
    mock_save_msg.assert_called_once()

    # Loop caches popped (both pop calls fire even if the caches were empty)
    mock_pop_sz.assert_called_once_with(sid)
    mock_pop_cc.assert_called_once_with(sid)

    # Message saved under the right session
    assert sid in msgs
    assert len(msgs[sid]) == 1


@pytest.mark.parametrize(
    "start_phase",
    ["awaiting_character", "session_zero", "char_creation"],
)
def test_skip_preplay_accepts_each_preplay_phase(start_phase) -> None:
    """All three pre-play phases are accepted by the endpoint."""
    sid = str(uuid4())
    session = _make_session(session_id=sid, phase=start_phase)

    with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
        with patch("monitor_ui.routers.chat._SESSIONS", new={sid: session}):
            with patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict):
                with patch("monitor_ui.routers.chat._db_save_session"):
                    with patch("monitor_ui.routers.chat._db_save_message"):
                        with patch("monitor_ui.routers.chat._pop_session_zero_loop"):
                            with patch("monitor_ui.routers.chat._pop_char_creation_loop"):
                                resp = client.post(f"{BASE}/{sid}/skip-preplay")

    assert resp.status_code == 200, f"phase={start_phase} should be accepted"
    assert session["phase"] == "active_play"
