"""Behavior tests for ProgressionLoop (Phase 2-3).

Exercises pure logic and node functions without LLM or DB.

Covers:
- load_progression_options
- ProgressionState defaults
- finalize_progression (with mocked CanonKeeper)
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_state(**overrides) -> Any:
    from monitor_agents.loops.progression_loop import ProgressionState

    base = {"entity_id": uuid4(), "universe_id": uuid4()}
    base.update(overrides)
    return ProgressionState(**base)


# =============================================================================
# ProgressionState defaults
# =============================================================================


class TestProgressionStateDefaults:
    def test_minimal_construct(self):
        from monitor_agents.loops.progression_loop import ProgressionState

        eid = uuid4()
        uid = uuid4()
        state = ProgressionState(entity_id=eid, universe_id=uid)

        assert state.entity_id == eid
        assert state.universe_id == uid
        assert state.available_xp == 0
        assert state.available_upgrades == []
        assert state.selected_upgrades == []
        assert state.progression_complete is False


# =============================================================================
# load_progression_options
# =============================================================================


class TestLoadProgressionOptions:
    def test_returns_placeholder_upgrades(self):
        from monitor_agents.loops.progression_loop import load_progression_options

        state = _make_state()
        result = asyncio.run(load_progression_options(state))
        assert "available_upgrades" in result
        assert len(result["available_upgrades"]) >= 2
        # First upgrade should be a strength bump
        ups = result["available_upgrades"]
        stats = [u["stat"] for u in ups]
        assert "STR" in stats
        assert "DEX" in stats

    def test_preserves_other_state(self):
        from monitor_agents.loops.progression_loop import load_progression_options

        state = _make_state(available_xp=10, selected_upgrades=[{"id": "test"}])
        result = asyncio.run(load_progression_options(state))
        # Should only return available_upgrades field
        assert set(result.keys()) == {"available_upgrades"}


# =============================================================================
# finalize_progression (mocked CanonKeeper)
# =============================================================================


class TestFinalizeProgression:
    def test_no_upgrades_still_completes(self, monkeypatch):
        from monitor_agents.loops import progression_loop

        class FakeKeeper:
            def __init__(self):
                self.created_facts = []

            async def create_fact(self, params):
                self.created_facts.append(params)

        keeper = FakeKeeper()

        # The finalize function does an in-function import of CanonKeeper
        # from monitor_agents.canonkeeper.agent. Replace that module attribute.
        import monitor_agents.canonkeeper.agent as ck_mod

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: keeper)

        state = _make_state(selected_upgrades=[])
        result = asyncio.run(progression_loop.finalize_progression(state))
        assert result["progression_complete"] is True
        assert keeper.created_facts == []

    def test_creates_fact_per_upgrade(self, monkeypatch):
        from monitor_agents.loops import progression_loop

        class FakeKeeper:
            def __init__(self):
                self.created_facts = []

            async def create_fact(self, params):
                self.created_facts.append(params)

        keeper = FakeKeeper()
        import monitor_agents.canonkeeper.agent as ck_mod

        monkeypatch.setattr(ck_mod, "CanonKeeper", lambda: keeper)

        upgrades = [
            {"id": "str_up", "stat": "STR", "value": 1},
            {"id": "dex_up", "stat": "DEX", "value": 1},
        ]
        state = _make_state(selected_upgrades=upgrades)
        result = asyncio.run(progression_loop.finalize_progression(state))
        assert result["progression_complete"] is True
        assert len(keeper.created_facts) == 2
        assert "STR" in keeper.created_facts[0]["statement"]
        assert "DEX" in keeper.created_facts[1]["statement"]
        assert keeper.created_facts[0]["fact_type"] == "state_change"
        assert keeper.created_facts[0]["entity_ids"] == [state.entity_id]
        assert keeper.created_facts[0]["properties"] == {"upgrade_id": "str_up"}


# =============================================================================
# build_progression_graph (sanity)
# =============================================================================


class TestBuildProgressionGraph:
    def test_graph_built(self):
        from monitor_agents.loops.progression_loop import build_progression_graph

        graph = build_progression_graph()
        assert graph is not None
