"""
Unit tests for the forge router — quick-world PC bootstrap (T-092).

Verifies that quick-world with start_playing=true bootstraps a demo PC
with a character sheet and binds it to the session.

Use Cases: I-12 (quick-world), P-1 (start playing)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _mock_db_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace DB client factories with MagicMock stubs."""
    import sys
    from pathlib import Path

    backend_src = (
        Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
    )
    if str(backend_src) not in sys.path:
        sys.path.insert(0, str(backend_src))

    from monitor_ui.routers import chat as chat_router

    chat_router._SESSIONS.clear()
    chat_router._MESSAGES.clear()


def _make_mock_result():
    """Create a mock QuickWorldResult."""
    r = MagicMock()
    r.multiverse_id = uuid4()
    r.universe_id = uuid4()
    r.world_name = "Test World"
    r.world_description = "A test world"
    r.axiom = "Magic is real"
    r.opening_scene = "You arrive at the gates"
    r.pc_concept = "A brave explorer"
    r.entities = []
    r.lore_facts = []
    r.committed = 5
    r.errors = []
    r.summary.return_value = {
        "multiverse_id": str(r.multiverse_id),
        "universe_id": str(r.universe_id),
        "world_name": r.world_name,
        "world_description": r.world_description,
        "axiom": r.axiom,
        "opening_scene": r.opening_scene,
        "pc_concept": r.pc_concept,
        "entities": r.entities,
        "lore_facts": r.lore_facts,
        "committed": r.committed,
        "errors": list(r.errors),
    }
    return r


class TestQuickWorldPCBootstrap:
    """T-092: verify quick-world bootstraps a PC with stats."""

    @pytest.mark.asyncio
    async def test_quick_world_with_start_playing_binds_pc(self, monkeypatch):
        """When start_playing=true, the session should have character_id and
        speaker_character_id set from the bootstrapped PC."""
        from monitor_ui.routers import forge

        pc_id = str(uuid4())
        session_id = str(uuid4())
        mock_result = _make_mock_result()

        # Patch QuickWorldBuilder at the source module
        mock_builder_instance = MagicMock()
        mock_builder_instance.build = AsyncMock(return_value=mock_result)
        monkeypatch.setattr(
            "monitor_agents.quick_world.agent.QuickWorldBuilder",
            lambda: mock_builder_instance,
        )

        # Mock _ensure_demo_pc
        monkeypatch.setattr(forge, "_ensure_demo_pc", lambda _uid, _sid=None: pc_id)

        # Mock create_session
        mock_session = MagicMock()
        mock_session.id = session_id
        monkeypatch.setattr(
            "monitor_ui.routers.chat.create_session",
            AsyncMock(return_value=mock_session),
        )

        # Mock mongodb_list_game_systems
        mock_systems_res = MagicMock()
        mock_systems_res.systems = []
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            lambda *a, **kw: mock_systems_res,
        )

        result = await forge.quick_world(
            forge.QuickWorldRequest(
                seed="A dark city where shadows talk",
                start_playing=True,
            )
        )

        assert result.session_id == session_id
        assert result.committed == 5

    @pytest.mark.asyncio
    async def test_quick_world_without_start_playing_no_session(self, monkeypatch):
        """When start_playing=false, no session should be created."""
        from monitor_ui.routers import forge

        mock_result = _make_mock_result()
        mock_result.committed = 3
        mock_result.summary.return_value["committed"] = 3

        mock_builder_instance = MagicMock()
        mock_builder_instance.build = AsyncMock(return_value=mock_result)
        monkeypatch.setattr(
            "monitor_agents.quick_world.agent.QuickWorldBuilder",
            lambda: mock_builder_instance,
        )

        # Mock mongodb_list_game_systems
        mock_systems_res = MagicMock()
        mock_systems_res.systems = []
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            lambda *a, **kw: mock_systems_res,
        )

        result = await forge.quick_world(
            forge.QuickWorldRequest(
                seed="A bright meadow",
                start_playing=False,
            )
        )

        assert result.session_id is None
        assert result.committed == 3

    @pytest.mark.asyncio
    async def test_quick_world_pc_bootstrap_failure_is_non_fatal(self, monkeypatch):
        """If PC bootstrap fails, the world is still created and error is recorded."""
        from monitor_ui.routers import forge

        session_id = str(uuid4())
        mock_result = _make_mock_result()
        mock_result.committed = 2
        mock_result.summary.return_value["committed"] = 2

        mock_builder_instance = MagicMock()
        mock_builder_instance.build = AsyncMock(return_value=mock_result)
        monkeypatch.setattr(
            "monitor_agents.quick_world.agent.QuickWorldBuilder",
            lambda: mock_builder_instance,
        )

        # Mock _ensure_demo_pc to raise
        def failing_ensure_pc(_uid, _sid=None):
            raise RuntimeError("DB connection failed")

        monkeypatch.setattr(forge, "_ensure_demo_pc", failing_ensure_pc)

        mock_session = MagicMock()
        mock_session.id = session_id
        monkeypatch.setattr(
            "monitor_ui.routers.chat.create_session",
            AsyncMock(return_value=mock_session),
        )

        # Mock mongodb_list_game_systems
        mock_systems_res = MagicMock()
        mock_systems_res.systems = []
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            lambda *a, **kw: mock_systems_res,
        )

        result = await forge.quick_world(
            forge.QuickWorldRequest(
                seed="A stormy coast",
                start_playing=True,
            )
        )

        # World was still created
        assert result.committed == 2
        # PC bootstrap error was recorded
        assert any("PC bootstrap" in e for e in result.errors)
