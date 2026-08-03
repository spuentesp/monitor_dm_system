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


# === Sub-plan 4 Task 4: VtM-specific dice tools ==========================
# These tools wrap the VtM V20 dice engine so the GMAgent can drive
# VtM contested checks, rouse checks, and willpower rerolls without
# hand-rolling the mechanic in the prompt. The system underneath
# (VtMV20Engine in monitor_agents.dice) handles hunger dice,
# willpower reroll, and bestial-failure detection — the GM only
# needs to supply the pool size, difficulty, and (optionally)
# hunger / use_willpower flags.


def _vtm_contested_sync(
    pool_size: int,
    difficulty: int,
    hunger: int = 0,
    use_willpower: bool = False,
    willpower_available: bool = True,
) -> dict[str, Any]:
    """Synchronous wrapper around ``vt_contested_pool``.

    Returns a dict with ``successes``, ``raw_rolls``, ``botches``,
    ``hunger_dice``, ``willpower_spent``, ``messy_critical``,
    ``bestial_failure``, and ``passed``. The GMAgent can narrate
    from these flags.
    """
    from monitor_agents.dice import vt_contested_pool

    res = vt_contested_pool(
        pool_size=pool_size,
        difficulty=difficulty,
        hunger=hunger,
        use_willpower=use_willpower,
        willpower_available=willpower_available,
    )
    return {
        "engine": res.engine,
        "pool_size": res.pool_size,
        "difficulty": res.difficulty,
        "raw_rolls": list(res.raw_rolls),
        "successes": res.successes,
        "botches": res.botches,
        "hunger_dice": res.hunger_dice,
        "willpower_spent": res.willpower_spent,
        "willpower_rerolled": list(res.willpower_rerolled),
        "messy_critical": res.messy_critical,
        "bestial_failure": res.bestial_failure,
        "passed": res.passed,
    }


def _vtm_rouse_sync() -> dict[str, Any]:
    """Synchronous wrapper around ``vt_rouse_check`` (1d10 rouse)."""
    from monitor_agents.dice import vt_rouse_check

    return vt_rouse_check()


def _vtm_willpower_reroll_sync(rolls_json: str, difficulty: int) -> dict[str, Any]:
    """Synchronous wrapper around ``vt_willpower_reroll`` — the GM
    passes the current rolls as a JSON array and the difficulty, and
    the engine returns the new rolls (failed dice rerolled)."""
    import json as _json
    from monitor_agents.dice import vt_willpower_reroll

    rolls = _json.loads(rolls_json)
    if not isinstance(rolls, list):
        return {"error": "rolls_json must be a JSON array of integers"}
    new = vt_willpower_reroll(rolls, difficulty)
    return {"rolls": list(new), "difficulty": difficulty}


def gm_tool_vtm_contested_pool() -> Any:
    """Return a ``dspy.Tool`` for VtM contested checks."""
    def vt_contested_pool(
        pool_size: int,
        difficulty: int,
        hunger: int = 0,
        use_willpower: bool = False,
        willpower_available: bool = True,
    ) -> str:
        """Resolve a Vampire: the Masquerade contested check.

        Rolls a pool of d10s (count = pool_size) and counts how many
        meet or exceed ``difficulty``. ``hunger`` dice (V5 only) replace
        normal dice in the pool; a 1 on a hunger die triggers messy
        critical (if there are other successes) or bestial failure
        (if there are no successes). ``use_willpower`` will spend 1
        Willpower to reroll all failed dice — only if the roll would
        otherwise have 0 successes.
        """
        return json.dumps(_vtm_contested_sync(
            pool_size=pool_size,
            difficulty=difficulty,
            hunger=hunger,
            use_willpower=use_willpower,
            willpower_available=willpower_available,
        ))

    return dspy.Tool(
        vt_contested_pool,
        name="vtm_contested_pool",
        desc=(
            "Resolve a Vampire: the Masquerade contested check. Rolls a "
            "pool of d10s and counts how many meet or exceed difficulty. "
            "Supports hunger dice, willpower reroll, and bestial-failure "
            "detection. Use this for V5 / V20 / Dark Ages dice."
        ),
        args={
            "pool_size": {
                "type": "integer",
                "description": "Number of d10s in the pool (Attribute + Ability).",
            },
            "difficulty": {
                "type": "integer",
                "description": "Target number to beat. 1=trivial, 6=standard, 10=extreme.",
            },
            "hunger": {
                "type": "integer",
                "description": "Number of red hunger dice in the pool (V5 only).",
                "default": 0,
            },
            "use_willpower": {
                "type": "boolean",
                "description": "Spend 1 Willpower to reroll all failed dice. Only fires if 0 successes.",
                "default": False,
            },
            "willpower_available": {
                "type": "boolean",
                "description": "Whether the character has 1+ Willpower to spend.",
                "default": True,
            },
        },
    )


def gm_tool_vtm_rouse_check() -> Any:
    """Return a ``dspy.Tool`` for VtM rouse checks (1d10)."""
    def vt_rouse_check() -> str:
        """Roll a VtM rouse check (1d10). Success on 1+ (always for 1d10).
        A failed rouse (Hunger +1) only happens when the player refuses
        to spend Willpower to reroll; if the player has 1+ WP, the
        rouse succeeds automatically.
        """
        return json.dumps(_vtm_rouse_sync())

    return dspy.Tool(
        vt_rouse_check,
        name="vtm_rouse_check",
        desc=(
            "Roll a Vampire: the Masquerade rouse check (1d10). The rouse "
            "is for spending blood: each rouse costs 1 blood, and on a "
            "failure (1) the vampire gains 1 Hunger. In practice the rouse "
            "auto-succeeds unless the character has 0 Willpower."
        ),
        args={},
    )


def gm_tool_vtm_willpower_reroll() -> Any:
    """Return a ``dspy.Tool`` for the manual willpower-reroll helper."""
    def vt_willpower_reroll(rolls_json: str, difficulty: int) -> str:
        """Spend 1 Willpower to reroll all dice that failed to meet the
        difficulty. ``rolls_json`` is a JSON array of the current dice
        rolls (e.g. ``"[3, 1, 8, 4]"``). Returns the new rolls.
        """
        return json.dumps(_vtm_willpower_reroll_sync(rolls_json, difficulty))

    return dspy.Tool(
        vt_willpower_reroll,
        name="vtm_willpower_reroll",
        desc=(
            "Manual willpower-reroll helper. Pass the current rolls as a "
            "JSON array and the difficulty; failed dice are rerolled, "
            "successful dice are preserved."
        ),
        args={
            "rolls_json": {
                "type": "string",
                "description": "JSON array of current rolls, e.g. '[3, 1, 8, 4]'.",
            },
            "difficulty": {
                "type": "integer",
                "description": "Target number the failed dice are rerolled against.",
            },
        },
    )
