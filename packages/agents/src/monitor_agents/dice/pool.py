"""
Generic Pool Dice Engine.

Core mechanic:
  Roll a pool of dice (default d10s) equal to ``pool_size``. Each die
  that shows a value >= difficulty counts as 1 success.
  Resources and specific mechanical rules (like willpower or hunger)
  should be applied by the game system logic using the GameSystemRuntime,
  rather than being hardcoded in the engine.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from monitor_agents.dice.base import default_dice_registry


@dataclass
class PoolContestedCheck:
    """Result of a generic pool contested check."""

    successes: int
    raw_rolls: list[int]
    botches: int  # number of 1s (zero successes + any 1 = botch)
    pool_size: int
    difficulty: int
    engine: str = "pool"

    @property
    def passed(self) -> bool:
        return self.successes > 0


class PoolDiceEngine:
    """Generic Pool dice engine. Pool of dice vs difficulty."""

    name = "pool"

    def resolve_check(
        self,
        *,
        pool_size: int,
        difficulty: int,
        context: dict | None = None,
    ) -> PoolContestedCheck:
        # Default die size to d10 if not specified
        ctx = context or {}
        die_size = ctx.get("die_size", 10)

        # Roll the full pool.
        rolls = [random.randint(1, die_size) for _ in range(pool_size)]
        successes = sum(1 for r in rolls if r >= difficulty)
        botches = sum(1 for r in rolls if r == 1)

        return PoolContestedCheck(
            successes=successes,
            raw_rolls=rolls,
            botches=botches,
            pool_size=pool_size,
            difficulty=difficulty,
        )


# Register the engine on import.
default_dice_registry.register(PoolDiceEngine())  # type: ignore[abstract]
