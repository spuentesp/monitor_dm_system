from unittest.mock import MagicMock, patch
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


class TestApplyUpgrade:
    """The entry point that applies the player's chosen upgrade (join task 8).

    ``start`` only offers and waits; this is the deliberate player choice
    that commits the selection.
    """

    @pytest.mark.asyncio
    async def test_applies_the_selection_through_finalize(self):
        e_id = uuid4()
        u_id = uuid4()
        loop = ProgressionLoop(e_id, u_id)

        with patch("monitor_agents.canonkeeper.agent.CanonKeeper.create_fact") as mock_create_fact:
            result = await loop.apply_upgrade(["str_up"], available_xp=10)

        assert result["progression_complete"] is True
        assert result["xp_spent"] == 5
        assert result["xp_remaining"] == 5
        assert [u["id"] for u in result["selected_upgrades"]] == ["str_up"]
        # The real callee committed the chosen upgrade.
        assert mock_create_fact.await_count == 1
        fact = mock_create_fact.await_args.args[0]
        assert "STR" in fact["statement"]
        assert fact["properties"]["upgrade_id"] == "str_up"

    @pytest.mark.asyncio
    async def test_an_unoffered_upgrade_is_refused(self):
        loop = ProgressionLoop(uuid4(), uuid4())
        with pytest.raises(ValueError, match="not offered"):
            await loop.apply_upgrade(["con_up"], available_xp=10)

    @pytest.mark.asyncio
    async def test_a_selection_beyond_the_award_is_refused(self):
        loop = ProgressionLoop(uuid4(), uuid4())
        with pytest.raises(ValueError, match="costs"):
            await loop.apply_upgrade(["str_up", "dex_up"], available_xp=5)

    @pytest.mark.asyncio
    async def test_an_empty_selection_is_refused(self):
        """No choice, no application — the offer-and-wait contract."""
        loop = ProgressionLoop(uuid4(), uuid4())
        with pytest.raises(ValueError, match="no upgrades"):
            await loop.apply_upgrade([], available_xp=10)


class TestLevelUpServiceWiring:
    """The level-up endpoint route reaches ProgressionLoop.apply_upgrade."""

    @pytest.mark.asyncio
    async def test_the_level_up_service_applies_the_players_chosen_upgrades(self):
        from types import SimpleNamespace

        from monitor_agents.services.entity_service import EntityProgressionService
        from monitor_data.schemas.entities import LevelUpRequest

        captured: dict = {}

        class _StubLoop:
            def __init__(self, entity_id, universe_id):
                captured["entity_id"] = entity_id
                captured["universe_id"] = universe_id

            async def apply_upgrade(self, upgrade_ids, *, available_xp=0):
                captured["upgrade_ids"] = list(upgrade_ids)
                captured["available_xp"] = available_xp
                return {"selected_upgrades": [{"id": "str_up"}]}

        universe_id = uuid4()
        request = LevelUpRequest(upgrade_ids=["str_up"], available_xp=10, universe_id=str(universe_id))
        with (
            patch("monitor_agents.loops.progression_loop.ProgressionLoop", _StubLoop),
            patch(
                "monitor_agents.services.entity_service.mongodb_list_character_sheets",
                MagicMock(return_value=SimpleNamespace(sheets=[])),
            ),
        ):
            # The level-up mechanics run after the selection; with no game
            # system on the sheet they stop there — the wiring is what pins.
            with pytest.raises(ValueError, match="game system"):
                await EntityProgressionService.process_level_up(uuid4(), request)

        assert captured["upgrade_ids"] == ["str_up"]
        assert captured["available_xp"] == 10
        assert captured["universe_id"] == universe_id

    @pytest.mark.asyncio
    async def test_chosen_upgrades_without_a_universe_are_refused(self):
        from monitor_agents.services.entity_service import EntityProgressionService
        from monitor_data.schemas.entities import LevelUpRequest

        request = LevelUpRequest(upgrade_ids=["str_up"])
        with pytest.raises(ValueError, match="universe_id"):
            await EntityProgressionService.process_level_up(uuid4(), request)
