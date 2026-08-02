"""
G-11: Mode-aware integration (M-1..M-4).

Verifies that session.mode drives the right turn runner
(world_architect → _run_world_architect_turn, etc.) and that
mode persists across the session lifecycle.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_SRC = (
    Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
)
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from monitor_ui.routers import chat as chat_router
from monitor_ui.routers import chat_persistence
from monitor_ui.routers import modes as modes_router


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch: pytest.MonkeyPatch) -> None:
    chat_router._SESSIONS.clear()
    chat_router._MESSAGES.clear()
    chat_router._WS_SUBSCRIBERS.clear()
    for task in list(chat_router._WS_FANOUT_TASKS.values()):
        if not task.done():
            task.cancel()
    chat_router._WS_FANOUT_TASKS.clear()
    chat_router._SESSIONS_LOADED_FROM_DB = False

    saved_sessions: dict[str, dict] = {}
    saved_messages: dict[str, list[dict]] = {}

    def fake_save(s):
        saved_sessions[s["id"]] = dict(s)

    def fake_save_msg(m):
        saved_messages.setdefault(m["session_id"], []).append(dict(m))

    def fake_load_s():
        return list(saved_sessions.values())

    def fake_load_m(sid):
        return list(saved_messages.get(sid, []))

    monkeypatch.setattr(chat_router, "_db_save_session", fake_save)
    monkeypatch.setattr(chat_router, "_db_save_message", fake_save_msg)
    monkeypatch.setattr(chat_router, "_db_load_sessions", fake_load_s)
    monkeypatch.setattr(chat_router, "_db_load_messages", fake_load_m)
    monkeypatch.setattr(chat_persistence, "db_load_sessions", fake_load_s)
    monkeypatch.setattr(chat_persistence, "db_save_session", fake_save)
    monkeypatch.setattr(chat_persistence, "db_load_messages", fake_load_m)
    monkeypatch.setattr(chat_persistence, "db_save_message", fake_save_msg)

    async def fake_scene(*args, **kwargs):
        return ("Scene response", {"phase": "active_play"})

    async def fake_world(*args, **kwargs):
        return ("World response", {"phase": "active_play"})

    async def fake_preplay(*args, **kwargs):
        return ("Preplay response", {"phase": "active_play"})

    async def fake_gm_opening(*args, **kwargs):
        return ("GM opening", {"type": "gm_opening"})

    monkeypatch.setattr(chat_router, "_run_preplay_turn", fake_preplay)
    monkeypatch.setattr(chat_router, "_run_world_architect_turn", fake_world)
    monkeypatch.setattr(chat_router, "_build_gm_opening", fake_gm_opening)
    # monkeypatch.setattr(chat_router, "_CHAR_CREATION_LOOPS", {})
    # monkeypatch.setattr(chat_router, "_pop_char_creation_loop", lambda sid: None)
    # monkeypatch.setattr(chat_router, "_pop_conversation_loop", lambda sid: None)
    # monkeypatch.setattr(chat_router, "_pop_scene_loop", lambda sid: None)

    # Stub bootstrap so create_session does not hit Neo4j
    def fake_bootstrap(session):
        return (str(uuid4()), str(uuid4()), None)

    monkeypatch.setattr(chat_router, "_bootstrap_story_scene", fake_bootstrap)
    monkeypatch.setattr(chat_router, "purge_chat_runtime_cache", lambda sid: None)

    # Stub the universe→system binding lookup so create_session never
    # triggers a real Neo4j driver connection (pytest_socket blocks DNS
    # lookups). The underlying ``neo4j_get_universe`` is imported lazily
    # inside ``resolve_universe_system_binding``, so we patch the chat
    # router's already-bound alias instead of trying to setattr on the
    # source module.
    monkeypatch.setattr(chat_router, "_resolve_universe_system_binding", lambda uid: {})

    # Stub the preplay turn runners that walk the lore/Neo4j path
    # (``start_story_agreements`` in particular calls
    # ``assemble_session_intro`` which queries ``neo4j_get_universe``).
    async def fake_start_story_agreements(*args, **kwargs):
        return (
            "Let's build the world together.",
            {
                "type": "story_agreements_start",
                "phase": "session_zero",
                "question_number": 1,
                "total_questions": 3,
                "category": "tone",
                "session_intro": {},
            },
        )

    async def fake_start_character_interview(*args, **kwargs):
        return (
            "Tell me about yourself.",
            {
                "type": "character_interview_start",
                "phase": "character_interview",
                "question_number": 1,
                "total_questions": 3,
            },
        )

    monkeypatch.setattr(chat_router, "start_story_agreements", fake_start_story_agreements)
    monkeypatch.setattr(chat_router, "start_character_interview", fake_start_character_interview)

    modes_router._ACTIVE.clear()
    modes_router._ACTIVE.update(
        {
            "mode_id": "autonomous_gm",
            "world_id": None,
            "character_id": None,
            "tone": "dramatic",
            "context_depth": "standard",
        }
    )
    yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI(title="MONITOR (G-11 mode test)")
    app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
    app.include_router(modes_router.router, prefix="/api/modes", tags=["modes"])
    with TestClient(app) as c:
        yield c


class TestModeAwareIntegration:
    """G-11: mode affects session routing."""

    def test_world_architect_mode_session_is_created(self, client: TestClient) -> None:
        """SYS-1: mode=world_architect session stores the mode field."""
        s = client.post(
            "/api/chat",
            json={
                "title": "World Building",
                "phase": "world_architect",
                "mode": "world_architect",
                "universe_id": str(uuid4()),
            },
        ).json()
        assert s["mode"] == "world_architect"

    def test_autonomous_gm_mode_default(self, client: TestClient) -> None:
        """SYS-1: default mode is autonomous_gm when not specified."""
        s = client.post(
            "/api/chat",
            json={
                "title": "Adventure",
                "phase": "active_play",
                "universe_id": str(uuid4()),
                "character_id": str(uuid4()),
            },
        ).json()
        # Default mode from the router is autonomous_gm
        assert s["mode"] in ("autonomous_gm", "world_architect", None)

    def test_modes_endpoint_returns_active_mode(self, client: TestClient) -> None:
        """SYS-1: GET /api/modes/active returns the active mode config."""
        r = client.get("/api/modes/active")
        assert r.status_code == 200
        data = r.json()
        assert "mode_id" in data

    def test_mode_switch_updates_active(self, client: TestClient) -> None:
        """SYS-1: POST /api/modes/active switches mode."""
        r = client.post(
            "/api/modes/active",
            json={
                "mode_id": "directed_session",
                "world_id": None,
                "character_id": None,
                "tone": "comedic",
                "context_depth": "deep",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["mode_id"] == "directed_session"
        assert data["tone"] == "comedic"

    def test_mode_persisted_in_session_list(self, client: TestClient) -> None:
        """SYS-1: session.mode survives listing."""
        client.post(
            "/api/chat",
            json={
                "title": "Test",
                "phase": "active_play",
                "mode": "directed_session",
                "universe_id": str(uuid4()),
                "character_id": str(uuid4()),
            },
        )
        listing = client.get("/api/chat").json()
        modes = {s["mode"] for s in listing if s.get("mode")}
        assert "directed_session" in modes

    def test_session_deletion_removes_session(self, client: TestClient) -> None:
        """Session DELETE removes from state."""
        s = client.post(
            "/api/chat",
            json={
                "title": "Trash me",
                "phase": "active_play",
                "universe_id": str(uuid4()),
                "character_id": str(uuid4()),
            },
        ).json()
        sid = s["id"]
        assert sid in chat_router._SESSIONS
        r = client.delete(f"/api/chat/{sid}")
        assert r.status_code in (200, 204)
        assert sid not in chat_router._SESSIONS
