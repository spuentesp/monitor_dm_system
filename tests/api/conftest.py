"""
API test fixtures for MONITOR UI backend.

Provides a TestClient with mocked dependencies so API tests can run
as fast unit tests without real databases or agent loops.

Use Cases: P-3, SYS-1, SYS-2
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _add_backend_to_path() -> None:
    """Ensure the monitor_ui package is importable."""
    backend_src = (
        Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
    )
    sys.path.insert(0, str(backend_src))


@pytest.fixture(autouse=True)
def _mock_db_clients(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Replace all DB client factories with MagicMock stubs.

    This prevents any real database connections during API tests.
    """
    _add_backend_to_path()
    from monitor_ui.routers import chat as chat_router
    from monitor_ui.routers import chat_persistence

    # Reset in-memory state before each test
    chat_router._SESSIONS.clear()
    chat_router._MESSAGES.clear()
    chat_router._WS_SUBSCRIBERS.clear()
    for task in list(chat_router._WS_FANOUT_TASKS.values()):
        if not task.done():
            task.cancel()
    chat_router._WS_FANOUT_TASKS.clear()
    chat_router._SESSIONS_LOADED_FROM_DB = False

    # Stub the MongoDB persistence functions with a store that is SEPARATE
    # from the router's in-memory caches — mirroring real DB semantics.
    # (Appending to chat_router._MESSAGES here would mutate the very list
    # create_session iterates while saving → infinite loop.)
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

    # Also patch the underlying chat_persistence functions (called by ensure_sessions_loaded
    # and other helpers that bypass the chat_router wrappers)
    monkeypatch.setattr(chat_persistence, "db_load_sessions", fake_db_load_sessions)
    monkeypatch.setattr(chat_persistence, "db_save_session", fake_db_save_session)
    monkeypatch.setattr(chat_persistence, "db_load_messages", fake_db_load_messages)
    monkeypatch.setattr(chat_persistence, "db_save_message", fake_db_save_message)

    # Stub agent turn runners — same (narrative, metadata) tuple contract and
    # keyword-only plumbing args as the real chat_loops runners.
    async def fake_run_scene_turn(
        session_id: str, user_content: str, **kwargs
    ) -> tuple[str, dict]:
        return (
            "The scene continues...",
            {"phase": "active_play", "action_taken": True, "scene_checkpoint": {}},
        )

    async def fake_run_world_architect_turn(
        session_id: str, user_content: str, **kwargs
    ) -> tuple[str, dict]:
        return (
            "World building response...",
            {"phase": "active_play", "action_taken": True},
        )

    async def fake_run_preplay_turn(
        session_id: str, user_content: str, **kwargs
    ) -> tuple[str, dict]:
        return (
            "Character creation response...",
            {"phase": "active_play", "action_taken": True},
        )

    monkeypatch.setattr(
        chat_router, "_run_scene_turn", fake_run_scene_turn
    )
    monkeypatch.setattr(
        chat_router, "_run_world_architect_turn", fake_run_world_architect_turn
    )
    monkeypatch.setattr(
        chat_router, "_run_preplay_turn", fake_run_preplay_turn
    )

    # Stub the GM opening builder — it walks the lore/LLM path (covered by its
    # own tests); session CRUD tests only need a deterministic opening message.
    async def fake_build_gm_opening(
        session_id: str, session: dict, *, session_game_system_doc
    ) -> tuple[str, dict]:
        return (
            "The mists part before you. Who are you, traveler?",
            {"type": "gm_opening", "lore_used": False},
        )

    monkeypatch.setattr(chat_router, "_build_gm_opening", fake_build_gm_opening)

    # Also stub the character creation and conversation loops
    monkeypatch.setattr(chat_router, "_CHAR_CREATION_LOOPS", {})
    monkeypatch.setattr(chat_router, "_pop_char_creation_loop", lambda sid: None)
    monkeypatch.setattr(chat_router, "_pop_conversation_loop", lambda sid: None)
    monkeypatch.setattr(chat_router, "_pop_scene_loop", lambda sid: None)

    yield


@pytest.fixture
def ui_client() -> Generator[TestClient, None, None]:
    """Fresh FastAPI TestClient with mocked DB dependencies."""
    _add_backend_to_path()
    from fastapi import FastAPI
    from monitor_ui.routers import chat as chat_router
    from monitor_ui.routers import modes as modes_router

    # Reset modes in-memory state
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

    # Create a fresh app without the real lifespan (bypasses MongoDB calls in _startup_runtime)
    app = FastAPI(title="MONITOR UI API (test)")
    app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
    app.include_router(modes_router.router, prefix="/api/modes", tags=["modes"])

    with TestClient(app) as client:
        yield client
