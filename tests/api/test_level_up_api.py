"""
Unit tests for the character level-up endpoint (P-21 progression).

Verifies that POST /api/entities/characters/{id}/level-up correctly:
- Reads XP/level from working state or character sheet
- Checks the advancement model's progression table
- Applies level-up when XP is sufficient
- Rejects when XP is insufficient or no advancement model

Use Cases: P-21 (Downtime & Character Progression)
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _setup_path() -> None:
    import sys
    from pathlib import Path

    backend_src = (
        Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
    )
    if str(backend_src) not in sys.path:
        sys.path.insert(0, str(backend_src))


class TestLevelUp:
    """Tests for POST /characters/{character_id}/level-up."""

    @pytest.mark.asyncio
    async def test_level_up_success_with_sufficient_xp(self, monkeypatch):
        """Level up succeeds when XP >= xp_required for next level."""
        from monitor_ui.routers import entities

        entity_id = uuid4()
        scene_id = uuid4()
        system_id = uuid4()
        state_id = uuid4()

        # Mock working state with enough XP
        mock_ws = MagicMock()
        mock_ws.state.xp = 200
        mock_ws.state.level = 1
        mock_ws.state.state_id = state_id
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.working_state.mongodb_get_working_state",
            lambda eid, sid: mock_ws,
        )

        # Mock game system with advancement model
        mock_system = MagicMock()
        mock_system.advancement = MagicMock()
        mock_system.advancement.max_level = 20
        mock_system.advancement.progression_table = [
            MagicMock(level=1, xp_required=0, features_gained=[], resource_increases={}),
            MagicMock(level=2, xp_required=100, features_gained=["Extra Attack"], resource_increases={"HP": 10}),
            MagicMock(level=3, xp_required=300, features_gained=[], resource_increases={}),
        ]
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_game_system",
            lambda sid: mock_system,
        )

        # Mock working state update
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.working_state.mongodb_update_working_state",
            lambda sid, upd: None,
        )

        result = await entities.level_up_character(
            str(entity_id),
            entities.LevelUpRequest(
                scene_id=str(scene_id),
                system_id=str(system_id),
            ),
        )

        assert result.old_level == 1
        assert result.new_level == 2
        assert "Extra Attack" in result.features_gained
        assert result.resource_increases.get("HP") == 10

    @pytest.mark.asyncio
    async def test_level_up_rejected_insufficient_xp(self, monkeypatch):
        """Level up fails with 422 when XP < xp_required."""
        from monitor_ui.routers import entities
        from fastapi import HTTPException

        entity_id = uuid4()
        scene_id = uuid4()
        system_id = uuid4()

        mock_ws = MagicMock()
        mock_ws.state.xp = 50  # Not enough for level 2 (needs 100)
        mock_ws.state.level = 1
        mock_ws.state.state_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.working_state.mongodb_get_working_state",
            lambda eid, sid: mock_ws,
        )

        mock_system = MagicMock()
        mock_system.advancement = MagicMock()
        mock_system.advancement.max_level = 20
        mock_system.advancement.progression_table = [
            MagicMock(level=1, xp_required=0),
            MagicMock(level=2, xp_required=100),
        ]
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_game_system",
            lambda sid: mock_system,
        )

        with pytest.raises(HTTPException) as exc_info:
            await entities.level_up_character(
                str(entity_id),
                entities.LevelUpRequest(
                    scene_id=str(scene_id),
                    system_id=str(system_id),
                ),
            )
        assert exc_info.value.status_code == 422
        assert "Insufficient XP" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_level_up_rejected_no_advancement_model(self, monkeypatch):
        """Level up fails with 422 when game system has no advancement model."""
        from monitor_ui.routers import entities
        from fastapi import HTTPException

        entity_id = uuid4()
        system_id = uuid4()

        # No working state, no character sheet → XP stays 0
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.working_state.mongodb_get_working_state",
            lambda eid, sid: None,
        )

        mock_system = MagicMock()
        mock_system.advancement = None  # No advancement model
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_game_system",
            lambda sid: mock_system,
        )

        with pytest.raises(HTTPException) as exc_info:
            await entities.level_up_character(
                str(entity_id),
                entities.LevelUpRequest(system_id=str(system_id)),
            )
        assert exc_info.value.status_code == 422
        assert "no advancement model" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_level_up_rejected_at_max_level(self, monkeypatch):
        """Level up fails with 422 when already at max level."""
        from monitor_ui.routers import entities
        from fastapi import HTTPException

        entity_id = uuid4()
        scene_id = uuid4()
        system_id = uuid4()

        mock_ws = MagicMock()
        mock_ws.state.xp = 9999
        mock_ws.state.level = 20  # At max
        mock_ws.state.state_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.working_state.mongodb_get_working_state",
            lambda eid, sid: mock_ws,
        )

        mock_system = MagicMock()
        mock_system.advancement = MagicMock()
        mock_system.advancement.max_level = 20
        mock_system.advancement.progression_table = []
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_game_system",
            lambda sid: mock_system,
        )

        with pytest.raises(HTTPException) as exc_info:
            await entities.level_up_character(
                str(entity_id),
                entities.LevelUpRequest(
                    scene_id=str(scene_id),
                    system_id=str(system_id),
                ),
            )
        assert exc_info.value.status_code == 422
        assert "max level" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_level_up_invalid_character_id(self, monkeypatch):
        """Level up fails with 422 for invalid UUID."""
        from monitor_ui.routers import entities
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await entities.level_up_character(
                "not-a-uuid",
                entities.LevelUpRequest(system_id=str(uuid4())),
            )
        assert exc_info.value.status_code == 422


class TestDowntimeOptions:
    """Tests for GET /characters/{character_id}/downtime (P-21)."""

    @pytest.mark.asyncio
    async def test_downtime_shows_available_level_up(self, monkeypatch):
        """Downtime returns can_level_up=True when XP is sufficient."""
        from monitor_ui.routers import entities

        entity_id = uuid4()
        scene_id = uuid4()
        system_id = uuid4()

        mock_ws = MagicMock()
        mock_ws.state.xp = 200
        mock_ws.state.level = 1
        mock_ws.state.state_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.working_state.mongodb_get_working_state",
            lambda eid, sid: mock_ws,
        )

        mock_system = MagicMock()
        mock_system.advancement = MagicMock()
        mock_system.advancement.max_level = 20
        mock_system.advancement.progression_table = [
            MagicMock(level=1, xp_required=0, features_gained=[], resource_increases={}),
            MagicMock(level=2, xp_required=100, features_gained=["Extra Attack"], resource_increases={"HP": 10}),
        ]
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_game_system",
            lambda sid: mock_system,
        )

        result = await entities.get_downtime_options(
            str(entity_id),
            scene_id=str(scene_id),
            system_id=str(system_id),
        )

        assert result.can_level_up is True
        assert result.current_xp == 200
        assert result.next_level_xp_required == 100
        assert "Extra Attack" in result.available_features

    @pytest.mark.asyncio
    async def test_downtime_shows_insufficient_xp(self, monkeypatch):
        """Downtime returns can_level_up=False when XP is insufficient."""
        from monitor_ui.routers import entities

        entity_id = uuid4()
        scene_id = uuid4()
        system_id = uuid4()

        mock_ws = MagicMock()
        mock_ws.state.xp = 50
        mock_ws.state.level = 1
        mock_ws.state.state_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.working_state.mongodb_get_working_state",
            lambda eid, sid: mock_ws,
        )

        mock_system = MagicMock()
        mock_system.advancement = MagicMock()
        mock_system.advancement.max_level = 20
        mock_system.advancement.progression_table = [
            MagicMock(level=1, xp_required=0),
            MagicMock(level=2, xp_required=100),
        ]
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_game_system",
            lambda sid: mock_system,
        )

        result = await entities.get_downtime_options(
            str(entity_id),
            scene_id=str(scene_id),
            system_id=str(system_id),
        )

        assert result.can_level_up is False
        assert result.current_xp == 50
        assert result.next_level_xp_required == 100

    @pytest.mark.asyncio
    async def test_downtime_no_system_returns_message(self, monkeypatch):
        """Downtime returns a message when no game system is found."""
        from monitor_ui.routers import entities

        entity_id = uuid4()

        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.working_state.mongodb_get_working_state",
            lambda eid, sid: None,
        )

        result = await entities.get_downtime_options(str(entity_id))

        assert result.can_level_up is False
        assert "No game system" in result.message