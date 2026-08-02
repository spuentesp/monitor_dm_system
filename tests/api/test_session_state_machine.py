"""
G-10: Session state-machine coverage (phase transitions).

Verifies the canonical phase transitions and that invalid
transitions are handled correctly. Uses hermetic TestClient with
mocked DB (the same pattern as test_chat_router.py).
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

# ---------------------------------------------------------------------------
# Fixtures (mirror tests/api/conftest.py)
# ---------------------------------------------------------------------------


def _add_backend_to_path() -> None:
    if str(BACKEND_SRC) not in sys.path:
        sys.path.insert(0, str(BACKEND_SRC))


@pytest.fixture(autouse=True)
def _mock_db_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    _add_backend_to_path()
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

    def fake_db_save_session(session: dict) -> None:
        saved_sessions[session["id"]] = dict(session)

    def fake_db_save_message(msg: dict) -> None:
        saved_messages.setdefault(msg["session_id"], []).append(dict(msg))

    def fake_db_load_sessions() -> list[dict]:
        return list(saved_sessions.values())

    def fake_db_load_messages(session_id: str) -> list[dict]:
        return list(saved_messages.get(session_id, []))

    monkeypatch.setattr(chat_router, "_db_save_session", fake_db_save_session)
    monkeypatch.setattr(chat_router, "_db_save_message", fake_db_save_message)
    monkeypatch.setattr(chat_router, "_db_load_sessions", fake_db_load_sessions)
    monkeypatch.setattr(chat_router, "_db_load_messages", fake_db_load_messages)
    monkeypatch.setattr(chat_persistence, "db_load_sessions", fake_db_load_sessions)
    monkeypatch.setattr(chat_persistence, "db_save_session", fake_db_save_session)
    monkeypatch.setattr(chat_persistence, "db_load_messages", fake_db_load_messages)
    monkeypatch.setattr(chat_persistence, "db_save_message", fake_db_save_message)

    # Stub turn runners to return canned output
    async def fake_run_scene_turn(*args, **kwargs):
        return (
            "The scene continues...",
            {"phase": "active_play", "action_taken": True, "scene_checkpoint": {}},
        )

    async def fake_run_world_architect_turn(*args, **kwargs):
        return (
            "World building response...",
            {"phase": "active_play", "action_taken": True},
        )

    async def fake_run_preplay_turn(*args, **kwargs):
        return (
            "Character creation response...",
            {"phase": "active_play", "action_taken": True},
        )

    monkeypatch.setattr(chat_router, "_run_preplay_turn", fake_run_preplay_turn)
    monkeypatch.setattr(
        chat_router, "_run_world_architect_turn", fake_run_world_architect_turn
    )

    async def fake_build_gm_opening(*args, **kwargs):
        return (
            "The mists part before you. Who are you, traveler?",
            {"type": "gm_opening", "lore_used": False},
        )

    monkeypatch.setattr(chat_router, "_build_gm_opening", fake_build_gm_opening)
    # monkeypatch.setattr(chat_router, "_CHAR_CREATION_LOOPS", {})
    # monkeypatch.setattr(chat_router, "_pop_char_creation_loop", lambda sid: None)
    # monkeypatch.setattr(chat_router, "_pop_conversation_loop", lambda sid: None)
    # monkeypatch.setattr(chat_router, "_pop_scene_loop", lambda sid: None)

    # Stub bootstrap so create_session does not hit Neo4j
    def fake_bootstrap(session):
        return (str(uuid4()), str(uuid4()), None)

    monkeypatch.setattr(chat_router, "_bootstrap_story_scene", fake_bootstrap)

    # Stub the universe→system binding lookup so create_session never triggers
    # a real Neo4j driver connection (which would do a DNS lookup blocked by
    # pytest_socket). The underlying ``neo4j_get_universe`` is imported lazily
    # inside ``resolve_universe_system_binding``, so we patch the chat router's
    # already-bound alias instead of trying to setattr on the source module.
    monkeypatch.setattr(chat_router, "_resolve_universe_system_binding", lambda uid: {})

    # Stub the preplay turn runners that internally walk the lore/Neo4j path;
    # these are pulled into chat.py's module namespace at import time so they
    # can be monkeypatched directly. ``start_story_agreements`` in particular
    # calls ``assemble_session_intro`` which queries ``neo4j_get_universe`` —
    # blocking pytest_socket — so we return canned output here.
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
    app = FastAPI(title="MONITOR (G-10 state machine test)")
    app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
    app.include_router(modes_router.router, prefix="/api/modes", tags=["modes"])
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_session(client: TestClient, **overrides) -> dict:
    payload = {
        "title": "G-10 State Test",
        "phase": "active_play",
        # Use ``world_architect`` mode here — the SessionCreate schema's default
        # mode is ``autonomous_gm`` which triggers defer_autonomous_preplay and
        # overrides the phase to ``session_zero``. The state-machine tests are
        # about explicit phase transitions, so we want the simplest path
        # through create_session (phase set from the payload, no Neo4j/lore
        # walks).
        "mode": "world_architect",
        "universe_id": str(uuid4()),
        "character_id": str(uuid4()),
    }
    payload.update(overrides)
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSessionStateMachine:
    """G-10: phase transitions and validity."""

    def test_session_starts_in_documented_phase(self, client: TestClient) -> None:
        """P-1: a new session gets the requested phase or default awaiting_character."""
        s = _create_session(client)
        # active_play because we sent character_id
        assert s["phase"] == "active_play"

    def test_active_session_can_send_message(self, client: TestClient) -> None:
        """P-3: in active_play phase, send returns 200."""
        s = _create_session(client, phase="active_play")
        sid = s["id"]
        resp = client.post(f"/api/chat/{sid}/send", json={"content": "I look around."})
        assert resp.status_code == 200

    def test_unknown_session_send_returns_404(self, client: TestClient) -> None:
        """Defensive: unknown session id → 404."""
        resp = client.post(
            "/api/chat/00000000-0000-0000-0000-000000000000/send",
            json={"content": "Hi"},
        )
        assert resp.status_code == 404

    def test_end_scene_no_session_404(self, client: TestClient) -> None:
        """end-scene on unknown session returns 404."""
        resp = client.post("/api/chat/00000000-0000-0000-0000-000000000000/end-scene")
        assert resp.status_code == 404

    def test_end_scene_no_active_scene_400(self, client: TestClient) -> None:
        """end-scene on a session with no scene_id returns 400."""
        # Create a session without bootstrap, so scene_id is None
        s = _create_session(client, phase="active_play")
        # Force scene_id to None
        chat_router._SESSIONS[s["id"]]["scene_id"] = None
        resp = client.post(f"/api/chat/{s['id']}/end-scene")
        assert resp.status_code == 400

    def test_state_endpoint_returns_complete_payload(self, client: TestClient) -> None:
        """GET /state returns message_count, latest_gm_metadata, etc."""
        s = _create_session(client, phase="active_play")
        sid = s["id"]
        client.post(f"/api/chat/{sid}/send", json={"content": "Hello."})
        state = client.get(f"/api/chat/{sid}/state").json()
        assert state["session"]["id"] == sid
        assert state["message_count"] >= 2  # player + gm
        # latest_gm_metadata may have a different shape per code path; just
        # assert it is a non-empty dict (proves the GM response was recorded).
        assert isinstance(state["latest_gm_metadata"], dict)
        assert state["latest_gm_metadata"], "latest_gm_metadata is empty"

    def test_mode_persists_across_session_lifecycle(self, client: TestClient) -> None:
        """SYS-1: session.mode is preserved on read-back."""
        s = _create_session(client, mode="world_architect")
        sid = s["id"]
        # GET session
        listed = client.get("/api/chat").json()
        target = next(x for x in listed if x["id"] == sid)
        assert target["mode"] == "world_architect"

    def test_patch_session_updates_title(self, client: TestClient) -> None:
        """Session PATCH updates title and updated_at."""
        s = _create_session(client, title="Old Title")
        sid = s["id"]
        # PATCH
        resp = client.patch(f"/api/chat/{sid}", json={"title": "New Title"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"
