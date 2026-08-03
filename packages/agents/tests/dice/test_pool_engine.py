import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.dice.base import default_dice_registry
from monitor_agents.resolver import Resolver


def _make_context() -> dict[str, Any]:
    return {
        "entities": [{"properties": {"attributes": {"Strength": 4, "Dexterity": 3}}}],
        "turns": [],
    }


@pytest.mark.asyncio
async def test_pool_engine_uses_seed_mechanics():
    """
    Proves that the dice system works from the PDF-ingested rules:
    load seed JSON -> engine applies the core_mechanic from the seed.
    """
    # The test file is at
    #   packages/agents/tests/dice/test_pool_engine.py
    # The repo root is the parent of the ``packages/`` directory.
    # That is 4 levels up: dice → tests → agents → packages → repo_root.
    repo_root = Path(__file__).resolve().parents[4]
    seed_path = (
        repo_root / "packages" / "data-layer" / "src"
        / "monitor_data" / "defaults" / "systems" / "vampire.json"
    )
    with open(seed_path) as f:
        seed_data = json.load(f)

    assert seed_data["core_mechanic"]["type"] == "dice_pool"
    assert seed_data["core_mechanic"]["success_threshold"] == "6"

    resolver = Resolver()

    from monitor_agents.gm_awareness import (
        ActionType,
        CausalityAction,
        GMAwareness,
        IntentType,
        RollNecessity,
        Severity,
    )

    verdict = GMAwareness(
        intent_type=IntentType.ACTION,
        action_type=ActionType.COMBAT,
        roll_necessity=RollNecessity.CONTESTED,
        declares_outcome=False,
        violates_causality=False,
        severity=Severity.NONE,
        action=CausalityAction.ACCEPT,
        reasoning="Punching is combat.",
    )

    pool_engine = default_dice_registry.get("pool")
    original_resolve_check = pool_engine.resolve_check

    spied_kwargs: dict[str, Any] = {}

    def spy_resolve_check(*args, **kwargs):
        spied_kwargs.update(kwargs)
        return original_resolve_check(*args, **kwargs)

    pool_engine.resolve_check = spy_resolve_check

    try:
        with patch("monitor_agents.resolver.check_gm_awareness", new_callable=AsyncMock, return_value=verdict):
            result, _ = await resolver.resolve_turn(
                "s1",
                "I punch him",
                context=_make_context(),
                game_context=seed_data,
                play_mode="dice_game_system",
                roll_mode="auto",
            )

        print("RESULT:", result)
        print("SPIED_KWARGS:", spied_kwargs)
        assert result["resolution_type"] == "dice"
        assert "difficulty" in spied_kwargs, f"spied_kwargs was {spied_kwargs}"
        assert spied_kwargs["difficulty"] == 6
    finally:
        pool_engine.resolve_check = original_resolve_check
