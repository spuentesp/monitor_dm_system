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


@pytest.fixture(autouse=True)
def _hermetic_db_singletons(monkeypatch: pytest.MonkeyPatch):
    import pkgutil

    """tests/api builds full apps whose lifespan and routes resolve the real
    DB singletons. Swap every singleton for the in-memory fakes and force
    local auth mode so no test ever opens a real socket."""
    from monitor_data.db import mongodb as _mongo_mod
    from monitor_data.db import neo4j as _neo4j_mod
    from monitor_data.db import postgres as _pg_mod
    from monitor_data.db import qdrant as _qdrant_mod
    from monitor_data.db import redis as _redis_mod
    from tests.mocks.db.mongo import FakeMongoClient
    from tests.mocks.db.neo4j import FakeNeo4jClient  # type: ignore[attr-defined]
    from tests.mocks.db.qdrant import FakeQdrantClient  # type: ignore[attr-defined]
    from tests.mocks.db.redis import FakeRedisClient  # type: ignore[attr-defined]

    import monitor_ui.auth as _auth_mod

    _backend_tests = Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "tests"
    sys.path.insert(0, str(_backend_tests))
    from fake_postgres import FakePostgres

    _fake_mongo = FakeMongoClient()
    _fake_mongo.get_collection = _fake_mongo.get_database().get_collection  # type: ignore[method-assign]
    _fake_pg = FakePostgres()
    monkeypatch.setattr(_mongo_mod, "get_mongodb_client", lambda: _fake_mongo)
    monkeypatch.setattr(_pg_mod, "get_postgres_client", lambda: _fake_pg)
    monkeypatch.setattr(_auth_mod, "get_postgres_client", lambda: _fake_pg)
    monkeypatch.setattr(_neo4j_mod, "get_neo4j_client", lambda: FakeNeo4jClient())
    monkeypatch.setattr(_qdrant_mod, "get_qdrant_client", lambda: FakeQdrantClient())
    monkeypatch.setattr(_redis_mod, "get_redis_client", lambda: FakeRedisClient())

    # Tool modules bind the client getters at import time; re-point those too.
    import monitor_data.tools as _tools_pkg

    _all_mods = list(pkgutil.iter_modules(_tools_pkg.__path__, prefix="monitor_data.tools."))
    for _mod_info in _all_mods:
        try:  # noqa: S112
            _mod = __import__(_mod_info.name, fromlist=["*"])
        except Exception:
            continue
        if hasattr(_mod, "get_mongodb_client"):
            monkeypatch.setattr(_mod, "get_mongodb_client", lambda: _fake_mongo)
        if hasattr(_mod, "get_neo4j_client"):
            monkeypatch.setattr(_mod, "get_neo4j_client", lambda: FakeNeo4jClient())
        if hasattr(_mod, "get_qdrant_client"):
            monkeypatch.setattr(_mod, "get_qdrant_client", lambda: FakeQdrantClient())
        if hasattr(_mod, "get_redis_client"):
            monkeypatch.setattr(_mod, "get_redis_client", lambda: FakeRedisClient())
    for _sub in (
        "mongodb_tools",
        "neo4j_tools",
        "ingest_tools",
        "plot_thread_tools",
        "temporal_tools",
    ):
        try:  # noqa: S112
            _submod = __import__(f"monitor_data.tools.{_sub}", fromlist=["*"])
        except Exception:
            continue
        for _mi in pkgutil.iter_modules(_submod.__path__, prefix=f"monitor_data.tools.{_sub}."):
            try:  # noqa: S112
                _m = __import__(_mi.name, fromlist=["*"])
            except Exception:
                continue
            if hasattr(_m, "get_mongodb_client"):
                monkeypatch.setattr(_m, "get_mongodb_client", lambda: _fake_mongo)
            if hasattr(_m, "get_neo4j_client"):
                monkeypatch.setattr(_m, "get_neo4j_client", lambda: FakeNeo4jClient())
            if hasattr(_m, "get_qdrant_client"):
                monkeypatch.setattr(_m, "get_qdrant_client", lambda: FakeQdrantClient())
            if hasattr(_m, "get_redis_client"):
                monkeypatch.setattr(_m, "get_redis_client", lambda: FakeRedisClient())
    monkeypatch.setenv("MONITOR_AUTH_DISABLED", "true")
    from monitor_ui.config import get_settings

    get_settings.cache_clear()

    # Ownership checks: tests/api covers behavior, not authz (that lives in
    # packages/ui/backend/tests). In local mode every require_* passes, so
    # override them on the singleton app and patch direct-call references.
    import monitor_ui.ownership as _own
    from monitor_ui.main import app as _ui_app
    from monitor_ui.routers import chat as _chat_mod

    async def _allow(*args, **kwargs):  # type: ignore[no-untyped-def]
        from uuid import uuid4 as _u4

        return {"id": str(_u4()), "owner_id": str(_u4())}

    _override_fns = [getattr(_own, n) for n in dir(_own) if n.startswith("require_")]
    for _fn in _override_fns:
        _ui_app.dependency_overrides[_fn] = _allow
    # Direct (non-Depends) call sites: re-point every router module's bound
    # require_* references at the passthrough.
    import monitor_ui.routers as _routers_pkg
    import pkgutil

    for _mod_info in pkgutil.iter_modules(_routers_pkg.__path__):
        _mod = __import__(f"monitor_ui.routers.{_mod_info.name}", fromlist=["*"])
        for _n in dir(_mod):
            if _n.startswith("require_"):
                monkeypatch.setattr(_mod, _n, _allow)

    yield

    for _fn in _override_fns:
        _ui_app.dependency_overrides.pop(_fn, None)
    get_settings.cache_clear()


def _add_backend_to_path() -> None:
    """Ensure the monitor_ui package is importable."""
    backend_src = Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
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
    async def fake_run_scene_turn(session_id: str, user_content: str, **kwargs) -> tuple[str, dict]:
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

    monkeypatch.setattr(chat_router, "_run_scene_turn", fake_run_scene_turn)
    monkeypatch.setattr(chat_router, "_run_world_architect_turn", fake_run_world_architect_turn)
    monkeypatch.setattr(chat_router, "_run_preplay_turn", fake_run_preplay_turn)

    # Stub the GM opening builder — it walks the lore/LLM path (covered by its
    # own tests); session CRUD tests only need a deterministic opening message.
    async def fake_build_gm_opening(
        session_id: str, session: dict, *, session_game_system_doc, **_kwargs
    ) -> tuple[str, dict]:
        return (
            "The mists part before you. Who are you, traveler?",
            {"type": "gm_opening", "lore_used": False},
        )

    monkeypatch.setattr(chat_router, "_build_gm_opening", fake_build_gm_opening)

    # Also stub the character creation and conversation loops
    # monkeypatch.setattr(chat_router, "_CHAR_CREATION_LOOPS", {})
    # monkeypatch.setattr(chat_router, "_pop_char_creation_loop", lambda sid: None)
    # monkeypatch.setattr(chat_router, "_pop_conversation_loop", lambda sid: None)
    # monkeypatch.setattr(chat_router, "_pop_scene_loop", lambda sid: None)

    yield


@pytest.fixture
def ui_client() -> Generator[TestClient, None, None]:
    """Fresh FastAPI TestClient with mocked DB dependencies."""
    _add_backend_to_path()
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

    # Hermetic: auth resolves to a fixed local principal and Postgres/Mongo
    # are the in-memory fakes, so no request ever opens a real socket.
    from unittest.mock import patch as _mock_patch
    from uuid import uuid4

    from fastapi import HTTPException

    from monitor_ui.auth import Principal, get_current_user, get_postgres
    from tests.mocks.db.mongo import FakeMongoClient

    backend_tests = Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "tests"
    sys.path.insert(0, str(backend_tests))
    from fake_postgres import FakePostgres

    _fake_pg = FakePostgres()
    _fake_mongo = FakeMongoClient()
    _fake_mongo.get_collection = _fake_mongo.get_database().get_collection  # type: ignore[method-assign]
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id=uuid4(), is_admin=True, via="local"
    )
    app.dependency_overrides[get_postgres] = lambda: _fake_pg

    async def _passthrough_session_owner(principal, session_id: str):  # type: ignore[no-untyped-def]
        chat_router._ensure_sessions_loaded()
        session = chat_router._SESSIONS.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Not found")
        return session

    import monitor_ui.auth as _auth_mod

    with (
        _mock_patch("monitor_data.db.mongodb.get_mongodb_client", lambda: _fake_mongo),
        _mock_patch.object(chat_router, "require_chat_session_owner", _passthrough_session_owner),
        _mock_patch.object(_auth_mod, "get_postgres_client", lambda: _fake_pg),
    ):
        with TestClient(app) as client:
            yield client
    app.dependency_overrides.clear()
