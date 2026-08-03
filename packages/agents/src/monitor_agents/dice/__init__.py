"""
Game-system-aware dice engines for MONITOR.

A "dice engine" is a pluggable component that knows how to roll dice
and resolve contested checks / spends / conditions for a specific
TTRPG. The protocol is intentionally small so any game system can
plug in.

Sub-plan 4 of docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md.

Public surface:
    DiceEngine           — protocol every engine implements
    DiceEngineRegistry    — keyed by game system name
    VtMContestedCheck    — typed result for a VtM V20 dice roll
    vt_contested_pool     — entry point for VtM contested checks
    vt_rouse_check        — entry point for VtM rouse checks
    vt_willpower_reroll   — entry point for VtM willpower rerolls
"""
from __future__ import annotations

from monitor_agents.dice.base import (
    DiceEngine,
    DiceEngineRegistry,
    default_dice_registry,
)
from monitor_agents.dice.generic import GenericDiceEngine
from monitor_agents.dice.vtm_v20 import (
    VtMContestedCheck,
    VtMV20Engine,
    vt_contested_pool,
    vt_rouse_check,
    vt_willpower_reroll,
)

# Register the built-in engines on import so callers can immediately
# use ``default_dice_registry.get("vtm_v20")`` or ``...get("generic")``
# without a separate setup step.
default_dice_registry.register(GenericDiceEngine())  # type: ignore[abstract]
default_dice_registry.register(VtMV20Engine())  # type: ignore[abstract]


__all__ = [
    "DiceEngine",
    "DiceEngineRegistry",
    "default_dice_registry",
    "GenericDiceEngine",
    "VtMContestedCheck",
    "VtMV20Engine",
    "vt_contested_pool",
    "vt_rouse_check",
    "vt_willpower_reroll",
]
