"""
Game-system-aware dice engines for MONITOR.

A "dice engine" is a pluggable component that knows how to roll dice
and resolve contested checks / spends / conditions for a specific
TTRPG. The protocol is intentionally small so any game system can
plug in.

Public surface:
    DiceEngine           — protocol every engine implements
    DiceEngineRegistry    — keyed by game system name
    PoolContestedCheck   — typed result for a generic pool dice roll
    PoolDiceEngine       — entry point for Pool dice checks
"""

from __future__ import annotations

from monitor_agents.dice.base import (
    DiceEngine,
    DiceEngineRegistry,
    default_dice_registry,
)
from monitor_agents.dice.generic import GenericDiceEngine
from monitor_agents.dice.pool import (
    PoolContestedCheck,
    PoolDiceEngine,
)

# Register the built-in engines on import so callers can immediately
# use ``default_dice_registry.get("pool")`` or ``...get("generic")``
# without a separate setup step.
default_dice_registry.register(GenericDiceEngine())  # type: ignore[abstract]
default_dice_registry.register(PoolDiceEngine())  # type: ignore[abstract]

__all__ = [
    "DiceEngine",
    "DiceEngineRegistry",
    "default_dice_registry",
    "GenericDiceEngine",
    "PoolContestedCheck",
    "PoolDiceEngine",
]
