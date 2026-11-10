"""Shared fixtures for UI backend tests."""

from __future__ import annotations

import pytest
from fake_postgres import FakePostgres


@pytest.fixture
def local_auth_mode(monkeypatch: pytest.MonkeyPatch):
    """Run a test in MONITOR_AUTH_DISABLED local mode with a fake registry.

    For characterization tests of non-auth behavior: requests resolve to the
    fixed local admin, ownership checks pass, and the Postgres dependency is
    an in-memory FakePostgres so no real database is needed. Two-user
    isolation tests live in test_auth.py / test_universes_ownership.py and
    do NOT use this fixture.
    """
    from monitor_ui.auth import get_postgres
    from monitor_ui.config import get_settings
    from monitor_ui.main import app

    monkeypatch.setenv("MONITOR_AUTH_DISABLED", "true")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    fake = FakePostgres()

    async def _fake_get_postgres() -> FakePostgres:
        return fake

    app.dependency_overrides[get_postgres] = _fake_get_postgres
    # Also patch at the source so tests that build a fresh app via
    # create_app() (and thus bypass the singleton's dependency_overrides)
    # still get the fake: the real get_postgres dependency calls
    # get_postgres_client().connect(), and the fake's connect() is a no-op.
    import monitor_ui.auth as auth_mod

    monkeypatch.setattr(auth_mod, "get_postgres_client", lambda: fake)

    # Chat router: the WebSocket handler builds its own client via
    # get_postgres_client(), and require_chat_session_owner reads Mongo.
    # In local mode the local account owns everything, so stand both in for
    # the in-memory session cache (tests patch chat._SESSIONS directly).
    from fastapi import HTTPException

    import monitor_ui.routers.chat as chat_mod

    monkeypatch.setattr(chat_mod, "get_postgres_client", lambda: fake)

    async def _fake_require_chat_session_owner(principal, session_id: str):  # type: ignore[no-untyped-def]
        chat_mod._ensure_sessions_loaded()
        session = chat_mod._SESSIONS.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Not found")
        return session

    monkeypatch.setattr(chat_mod, "require_chat_session_owner", _fake_require_chat_session_owner)

    # Entities router: character/universe owner checks read Mongo/Postgres.
    # In local mode the local account owns everything — allow all.
    import monitor_ui.routers.entities as entities_mod

    async def _allow(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {"id": args[-1] if args else None}

    monkeypatch.setattr(entities_mod, "require_character_owner", _allow)
    monkeypatch.setattr(entities_mod, "require_universe_owner", _allow)

    # Stories / play-sessions routers: owner checks chain through universe
    # ownership; local mode allows all.
    import monitor_ui.routers.play_sessions as ps_mod
    import monitor_ui.routers.stories as stories_mod

    for mod in (ps_mod, stories_mod):
        for name in (
            "require_universe_owner",
            "require_story_owner",
            "require_scene_owner",
            "require_play_session_owner",
        ):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, _allow)

    # OpenAI-compat router: character/conversation owner checks.
    import monitor_ui.routers.openai_compat as oa_mod

    monkeypatch.setattr(oa_mod, "require_character_owner", _allow)
    monkeypatch.setattr(oa_mod, "_require_conversation_owner", _allow)

    # Universes router: the pre-existing fork path clones Mongo/Qdrant/MinIO
    # data; stub those in local mode (no real data to clone in tests).
    import monitor_ui.routers.universes as universes_mod

    monkeypatch.setattr(universes_mod, "mongodb_fork_universe_data", lambda *a, **k: {"copied": 0})
    monkeypatch.setattr(universes_mod, "qdrant_clone_collection", lambda *a, **k: {"points_copied": 0})

    class _FakeMinio:
        async def copy_prefix(self, *a, **k):  # type: ignore[no-untyped-def]
            return {"copied": 0}

    monkeypatch.setattr(universes_mod, "get_minio_client", lambda: _FakeMinio())
    yield fake
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_chat_loops_globals():
    """Clear chat-loop module-level caches around every test.

    Without this, mutations made by tests in `test_chat_loops.py` (which
    already has its own autouse fixture) leak across files and break
    tests in `test_scene_loop_story_state_wiring.py` and others.
    """
    from monitor_ui.routers import chat_loops

    chat_loops._SCENE_LOOPS.clear()
    chat_loops._CONVERSATION_LOOPS.clear()
    yield
    chat_loops._SCENE_LOOPS.clear()
    chat_loops._CONVERSATION_LOOPS.clear()
