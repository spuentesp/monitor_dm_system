from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_agents.loops.progression_loop import ProgressionLoop, ProgressionState


class TestProgressionState:
    def test_progression_state_creation(self):
        """Test ProgressionState can be created with required fields."""
        e_id = uuid4()
        u_id = uuid4()
        state = ProgressionState(
            entity_id=e_id,
            universe_id=u_id,
        )
        assert state.entity_id == e_id
        assert state.universe_id == u_id
        assert state.available_xp == 0
        assert state.selected_upgrades == []

    def test_progression_state_with_upgrades(self):
        """Test ProgressionState with selected upgrades."""
        e_id = uuid4()
        u_id = uuid4()
        state = ProgressionState(
            entity_id=e_id,
            universe_id=u_id,
            available_xp=100,
            selected_upgrades=[{"id": "str_up", "stat": "STR", "cost": 10}],
        )
        assert state.available_xp == 100
        assert len(state.selected_upgrades) == 1
        assert state.selected_upgrades[0]["stat"] == "STR"


class TestProgressionLoop:
    def test_progression_loop_initialization(self):
        """Test ProgressionLoop initializes with entity and universe IDs."""
        e_id = uuid4()
        u_id = uuid4()
        loop = ProgressionLoop(e_id, u_id)
        assert loop.entity_id == e_id
        assert loop.universe_id == u_id


@pytest.mark.asyncio
async def test_progression_loop_start():
    e_id = uuid4()
    u_id = uuid4()
    loop = ProgressionLoop(e_id, u_id)

    res = await loop.start(available_xp=10)

    assert "available_upgrades" in res
    assert len(res["available_upgrades"]) > 0
    assert res["available_xp"] == 10


@pytest.mark.asyncio
async def test_progression_loop_finalize():
    e_id = uuid4()
    u_id = uuid4()

    with patch("monitor_agents.canonkeeper.agent.CanonKeeper.create_fact") as mock_create_fact:
        mock_create_fact.return_value = None

        # Manually run the finalize node for testing
        from monitor_agents.loops.progression_loop import finalize_progression

        state = ProgressionState(entity_id=e_id, universe_id=u_id, selected_upgrades=[{"id": "str_up", "stat": "STR"}])

        res = await finalize_progression(state)

        assert res["progression_complete"] is True
        mock_create_fact.assert_called_once()


@pytest.mark.asyncio
async def test_progression_loop_start_with_zero_xp():
    """Test that start works with zero XP."""
    e_id = uuid4()
    u_id = uuid4()
    loop = ProgressionLoop(e_id, u_id)

    res = await loop.start(available_xp=0)

    assert "available_upgrades" in res
    assert res["available_xp"] == 0


@pytest.mark.asyncio
async def test_progression_loop_finalize_with_no_upgrades():
    """Test finalize with no selected upgrades."""
    e_id = uuid4()
    u_id = uuid4()

    with patch("monitor_agents.canonkeeper.agent.CanonKeeper.create_fact") as mock_create_fact:
        mock_create_fact.return_value = None

        from monitor_agents.loops.progression_loop import finalize_progression

        state = ProgressionState(entity_id=e_id, universe_id=u_id, selected_upgrades=[])

        res = await finalize_progression(state)

        assert res["progression_complete"] is True


class TestProgressionLoopHelpers:
    """Tests for progression loop helper functions."""

    def test_build_progression_graph_returns_state_graph(self):
        """build_progression_graph should return a StateGraph."""
        from monitor_agents.loops.progression_loop import build_progression_graph

        graph = build_progression_graph()
        assert graph is not None
        assert "compile" in dir(graph)

    @pytest.mark.asyncio
    async def test_load_progression_options_with_xp(self):
        """load_progression_options should return upgrade options."""
        from monitor_agents.loops.progression_loop import load_progression_options

        state = ProgressionState(entity_id=uuid4(), universe_id=uuid4(), available_xp=50, selected_upgrades=[])
        result = await load_progression_options(state)
        assert "available_upgrades" in result
        assert isinstance(result["available_upgrades"], list)

    @pytest.mark.asyncio
    async def test_load_progression_options_returns_upgrades(self):
        """load_progression_options should return upgrade options."""
        from monitor_agents.loops.progression_loop import load_progression_options

        state = ProgressionState(entity_id=uuid4(), universe_id=uuid4(), available_xp=100, selected_upgrades=[])
        result = await load_progression_options(state)
        assert "available_upgrades" in result

    @pytest.mark.asyncio
    async def test_finalize_progression_with_multiple_upgrades(self):
        """finalize_progression should handle multiple upgrades."""
        from monitor_agents.loops.progression_loop import finalize_progression

        state = ProgressionState(
            entity_id=uuid4(),
            universe_id=uuid4(),
            available_xp=50,
            selected_upgrades=[
                {"id": "str_up", "stat": "STR", "cost": 10},
                {"id": "dex_up", "stat": "DEX", "cost": 15},
            ],
        )
        result = await finalize_progression(state)
        assert result["progression_complete"] is True
