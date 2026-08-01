"""Tests for typed Begin Story commands during Session Zero confirmation.

While story agreements await confirmation, the story-agreements loop treats
any chat input as a revision request and re-presents the summary — so typing
"begin story" used to loop forever. The router now recognises confirmation
phrases and routes them through the same finalize path as the Begin Story
button (``POST /{id}/begin``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)

BASE = "/api/chat"


def _make_session(session_id: str | None = None, *, phase: str = "session_zero", **overrides) -> dict:
    now = datetime.now(UTC).isoformat()
    sid = session_id or str(uuid4())
    session = {
        "id": sid,
        "title": "Begin Session",
        "mode": "autonomous_gm",
        "multiverse_id": None,
        "universe_id": str(uuid4()),
        "universe_label": None,
        "world_id": None,
        "character_id": str(uuid4()),
        "speaker_character_id": None,
        "speaker_label": "John",
        "controlled_character_ids": [],
        "system_id": None,
        "pack_id": None,
        "system_source_type": None,
        "system_source_id": None,
        "system_label": None,
        "benchmark_id": None,
        "benchmark_label": None,
        "tone": "mystery",
        "gm_profile_id": None,
        "play_mode": "narrative",
        "scene_id": None,
        "story_id": None,
        "chat_mode": "ic",
        "phase": phase,
        "session_intro": {
            "universe_name": "Valparaíso",
            "intro_text": "This story takes place in **Valparaíso**.",
        },
        "character_summary": {
            "character_name": "John",
            "concept": "Neurologist turned undead.",
            "backstory": "John was embraced and abandoned.",
        },
        "story_agreements": {
            "story_premise": "A mystery with vampiric overtones.",
            "themes": ["humor", "vampirism"],
            "tone": "mystery",
            "lines": [],
            "veils": [],
            "confirmed": False,
        },
        "created_at": now,
        "updated_at": now,
    }
    session.update(overrides)
    return session


async def _finalize_stub(session, *, system_doc=None):
    session["phase"] = "active_play"
    session["preplay_finalized_at"] = datetime.now(UTC).isoformat()
    session["story_id"] = "story-1"
    session["scene_id"] = "scene-1"
    return "The fluorescents hum.", {
        "type": "gm_opening",
        "preplay_finalized": True,
        "phase": "active_play",
        "story_id": "story-1",
        "scene_id": "scene-1",
    }


def _send(sid: str, session: dict, content: str, finalize=_finalize_stub):
    patches = [
        patch("monitor_ui.routers.chat._ensure_sessions_loaded"),
        patch("monitor_ui.routers.chat._SESSIONS", new={sid: session}),
        patch("monitor_ui.routers.chat._MESSAGES", new={sid: []}),
        patch("monitor_ui.routers.chat._db_save_session"),
        patch("monitor_ui.routers.chat._db_save_message"),
    ]
    if finalize is not None:
        patches.append(patch("monitor_ui.routers.chat.finalize_preplay", finalize))
    for ctx in patches:
        ctx.start()
    try:
        return client.post(f"{BASE}/{sid}/send", json={"content": content})
    finally:
        for ctx in reversed(patches):
            ctx.stop()


def test_typed_begin_story_triggers_finalize() -> None:
    sid = str(uuid4())
    session = _make_session(session_id=sid)

    resp = _send(sid, session, "begin story")

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "gm"
    assert body["metadata"]["type"] == "gm_opening"
    assert body["metadata"]["preplay_finalized"] is True
    assert session["phase"] == "active_play"
    assert session.get("preplay_finalized_at")


def test_typed_confirm_variants_trigger_finalize() -> None:
    for phrase in ("Begin Story", "looks good!", "confirm", "let's begin"):
        sid = str(uuid4())
        session = _make_session(session_id=sid)
        resp = _send(sid, session, phrase)
        assert resp.status_code == 200, phrase
        assert resp.json()["metadata"]["type"] == "gm_opening", phrase


def test_revision_text_does_not_trigger_begin() -> None:
    """Ordinary input while awaiting confirmation still goes to pre-play."""
    sid = str(uuid4())
    session = _make_session(session_id=sid)

    async def _preplay_stub(*args, **kwargs):
        return "Here is the revised summary.", {
            "type": "story_agreements_summary",
            "phase": "session_zero",
        }

    with patch("monitor_ui.routers.chat._run_preplay_turn", _preplay_stub):
        resp = _send(sid, session, "actually, make the tone more comedic")

    assert resp.status_code == 200
    assert resp.json()["metadata"]["type"] == "story_agreements_summary"
    assert session["phase"] == "session_zero"
    assert not session.get("preplay_finalized_at")


def test_begin_phrase_before_agreements_does_not_trigger_begin() -> None:
    """During the question stage (no agreements yet) 'begin' is not a command."""
    sid = str(uuid4())
    session = _make_session(session_id=sid, story_agreements=None)

    async def _preplay_stub(*args, **kwargs):
        return "Next question.", {
            "type": "story_agreements_question",
            "phase": "session_zero",
        }

    with patch("monitor_ui.routers.chat._run_preplay_turn", _preplay_stub):
        resp = _send(sid, session, "begin")

    assert resp.status_code == 200
    assert resp.json()["metadata"]["type"] == "story_agreements_question"
    assert session["phase"] == "session_zero"


def test_begin_phrase_in_active_play_does_not_retrigger_begin() -> None:
    sid = str(uuid4())
    session = _make_session(session_id=sid, phase="active_play")

    async def _scene_stub(*args, **kwargs):
        return "The scene continues.", {"type": "scene_turn", "phase": "active_play"}

    with patch("monitor_ui.routers.chat._run_scene_turn", _scene_stub):
        resp = _send(sid, session, "begin")

    assert resp.status_code == 200
    assert resp.json()["metadata"]["type"] == "scene_turn"
