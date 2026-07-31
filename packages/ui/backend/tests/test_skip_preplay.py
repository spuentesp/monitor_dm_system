"""Tests for the /api/chat/{id}/skip-preplay endpoint.

After the P-19 redesign a player cannot begin narration without a bound
character; ``skip-preplay`` honours that invariant, persists default
agreements, and delegates to the real ``begin_story`` finalizer.
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


def _make_session(
    session_id: str | None = None,
    *,
    phase: str = "session_zero",
    **overrides,
) -> dict:
    now = datetime.now(UTC).isoformat()
    sid = session_id or str(uuid4())
    session = {
        "id": sid,
        "title": "Skip Session",
        "mode": "autonomous_gm",
        "multiverse_id": None,
        "universe_id": str(uuid4()),
        "universe_label": None,
        "world_id": None,
        "character_id": str(uuid4()),
        "speaker_character_id": None,
        "speaker_label": "Mara",
        "controlled_character_ids": [],
        "system_id": None,
        "pack_id": None,
        "system_source_type": None,
        "system_source_id": None,
        "system_label": None,
        "benchmark_id": None,
        "benchmark_label": None,
        "tone": "grim",
        "gm_profile_id": None,
        "play_mode": "narrative",
        "scene_id": None,
        "story_id": None,
        "chat_mode": "ic",
        "phase": phase,
        "session_intro": {
            "universe_name": "Tenebris",
            "intro_text": "This story takes place in **Tenebris**.",
        },
        "character_summary": {
            "character_name": "Mara",
            "concept": "Salvage investigator on a derelict station.",
            "backstory": "Mara has worked salvage across three systems.",
        },
        "story_agreements": {
            "story_premise": "A salvage mystery.",
            "themes": ["isolation"],
            "tone": "grim",
            "lines": [],
            "veils": [],
        },
        "created_at": now,
        "updated_at": now,
    }
    session.update(overrides)
    return session


def test_skip_preplay_returns_404_for_unknown_session() -> None:
    with patch("monitor_ui.routers.chat._db_save_session"), patch("monitor_ui.routers.chat._db_save_message"):
        with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
            resp = client.post(f"{BASE}/{uuid4()}/skip-preplay")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session not found"


def test_skip_preplay_returns_409_when_already_in_active_play() -> None:
    sid = str(uuid4())
    session = _make_session(session_id=sid, phase="active_play")

    with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
        with patch("monitor_ui.routers.chat._SESSIONS", new={sid: session}):
            with patch("monitor_ui.routers.chat._db_save_session") as mock_save:
                resp = client.post(f"{BASE}/{sid}/skip-preplay")

    assert resp.status_code == 409
    assert "Cannot skip-preplay" in resp.json()["detail"]
    mock_save.assert_not_called()


def test_skip_preplay_rejects_character_setup_without_bound_character() -> None:
    sid = str(uuid4())
    session = _make_session(session_id=sid, phase="character_interview", character_id=None)

    with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
        with patch("monitor_ui.routers.chat._SESSIONS", new={sid: session}):
            with patch("monitor_ui.routers.chat._db_save_session") as mock_save:
                resp = client.post(f"{BASE}/{sid}/skip-preplay")

    assert resp.status_code == 409
    assert "character" in resp.json()["detail"]
    mock_save.assert_not_called()


def _patched_story_bootstrap(character_id: str | None = None):
    """Return a ``finalize_preplay`` stub that mirrors the real side effects."""

    async def _finalize(session, *, system_doc=None):
        session["phase"] = "active_play"
        session["preplay_finalized_at"] = datetime.now(UTC).isoformat()
        session["story_id"] = "story-1"
        session["scene_id"] = "scene-1"
        return "The station hums.", {
            "type": "gm_opening",
            "preplay_finalized": True,
            "phase": "active_play",
            "story_id": "story-1",
            "scene_id": "scene-1",
        }

    return _finalize


def test_skip_preplay_uses_defaults_and_invokes_begin() -> None:
    """skip-preplay persists default agreements and runs the begin flow."""
    sid = str(uuid4())
    session = _make_session(session_id=sid, phase="session_zero")

    with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
        with patch("monitor_ui.routers.chat._SESSIONS", new={sid: session}):
            with patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict) as msgs:
                with patch("monitor_ui.routers.chat._db_save_session") as mock_save_session:
                    with patch("monitor_ui.routers.chat._db_save_message") as mock_save_msg:
                        with patch("monitor_ui.routers.chat._pop_session_zero_loop") as mock_pop_sz:
                            with patch("monitor_ui.routers.chat._pop_char_creation_loop") as mock_pop_cc:
                                with patch(
                                    "monitor_ui.routers.chat.finalize_preplay",
                                    _patched_story_bootstrap(),
                                ):
                                    resp = client.post(f"{BASE}/{sid}/skip-preplay")

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "gm"
    assert body["metadata"]["type"] == "gm_opening"
    assert body["metadata"]["preplay_finalized"] is True
    assert session["story_agreements"]["source"] == "skipped"
    assert session.get("preplay_finalized_at")
    assert session["phase"] == "active_play"
    mock_pop_sz.assert_called_once_with(sid)
    mock_pop_cc.assert_called_once_with(sid)
    mock_save_session.assert_called()
    mock_save_msg.assert_called()
    assert msgs[sid][-1]["content"] == "The station hums."


@pytest.mark.parametrize(
    "start_phase",
    ["character_interview", "session_zero", "char_creation"],
)
def test_skip_preplay_accepts_prepared_phases(start_phase: str) -> None:
    sid = str(uuid4())
    session = _make_session(session_id=sid, phase=start_phase)

    with patch("monitor_ui.routers.chat._ensure_sessions_loaded"):
        with patch("monitor_ui.routers.chat._SESSIONS", new={sid: session}):
            with patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict):
                with patch("monitor_ui.routers.chat._db_save_session"):
                    with patch("monitor_ui.routers.chat._db_save_message"):
                        with patch("monitor_ui.routers.chat._pop_session_zero_loop"):
                            with patch("monitor_ui.routers.chat._pop_char_creation_loop"):
                                with patch(
                                    "monitor_ui.routers.chat.finalize_preplay",
                                    _patched_story_bootstrap(),
                                ):
                                    resp = client.post(f"{BASE}/{sid}/skip-preplay")

    assert resp.status_code == 200, f"phase={start_phase} should be accepted"
    assert session.get("preplay_finalized_at")
    assert session["phase"] == "active_play"
