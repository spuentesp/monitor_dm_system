"""
Dice tool — promote ``monitor_data.utils.dice.roll_dice`` to a dspy.Tool.

The dice tool is mechanical ground truth: when the GM asks for a roll,
this tool runs the actual RNG and returns the result. The LLM never invents
dice outcomes.

NOTE: This is a synchronous tool by necessity (DSPy Tool wraps sync callables).
The dice rolling itself is a CPU-only operation (random.randint under the
hood) so threading concerns are minimal.
"""

from __future__ import annotations

import json
from typing import Any

import dspy
from monitor_data.utils.dice import roll_dice


def _roll_dice_sync(formula: str, modifier: int = 0) -> dict[str, Any]:
    """Synchronous wrapper around ``monitor_data.utils.dice.roll_dice``."""
    try:
        result = roll_dice(formula)
        # Apply the optional flat modifier after the engine computed the total.
        total = result.total + modifier
        return {
            "formula": formula,
            "modifier": modifier,
            "rolls": list(result.rolls),
            "kept_rolls": list(result.kept_rolls),
            "total": total,
            "method": "random",
        }
    except Exception as exc:
        return {"formula": formula, "modifier": modifier, "error": str(exc), "method": "fail"}


def gm_tool_roll_dice() -> Any:
    """Return a ``dspy.Tool`` for rolling dice."""

    def roll(formula: str, modifier: int = 0) -> str:
        """Roll dice and return the result as JSON.

        ``formula`` is a dice formula like ``"1d20"`` or ``"3d6+2"`` — the
        embedded modifier is parsed by the dice engine. ``modifier`` is an
        additional flat bonus applied separately. The result includes
        per-die rolls, kept rolls (for kh/kl), total, and outcome.
        """
        return json.dumps(_roll_dice_sync(formula, modifier))

    return dspy.Tool(
        roll,
        name="roll_dice",
        desc=(
            "Roll dice and return the outcome. Use ``formula`` like '1d20' or "
            "'3d6+2'; the dice engine parses embedded modifiers. The flat "
            "``modifier`` argument adds to the total. The result includes "
            "per-die rolls, kept rolls, total, and outcome. ALWAYS call this "
            "when committing a contested or contested-against roll — never "
            "fabricate dice results."
        ),
        args={
            "formula": {"type": "string", "description": "Dice formula (e.g. '1d20', '3d6+2')."},
            "modifier": {
                "type": "integer",
                "description": "Flat bonus added to the roll total.",
                "default": 0,
            },
        },
    )


def gm_tool_contested_check() -> Any:
    """Return a ``dspy.Tool`` for resolving a contested check using the pool engine."""

    def resolve_check(pool_size: int, difficulty: int) -> str:
        from monitor_agents.dice import default_dice_registry

        engine = default_dice_registry.get("pool")
        res = engine.resolve_check(pool_size=pool_size, difficulty=difficulty)
        return json.dumps(
            {
                "successes": res.successes,
                "raw_rolls": res.raw_rolls,
                "botches": res.botches,
                "passed": res.passed,
                "pool_size": res.pool_size,
                "difficulty": res.difficulty,
                "engine": res.engine,
            }
        )

    return dspy.Tool(
        resolve_check,
        name="contested_check",
        desc=(
            "Resolve a contested check using a dice pool. Used for game systems "
            "where you roll a pool of dice against a difficulty (threshold). "
            "Returns the number of successes, raw rolls, and whether the check passed."
        ),
        args={
            "pool_size": {"type": "integer", "description": "Number of dice in the pool (e.g. Attribute + Ability)."},
            "difficulty": {"type": "integer", "description": "Target number each die must meet to be a success."},
        },
    )
