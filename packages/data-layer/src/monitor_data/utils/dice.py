"""
Dice rolling utility for MONITOR.

LAYER: 1 (data-layer)
"""

import math
import random
import re
from typing import Any

# ---------------------------------------------------------------------------
# Regex for full dice expression: [N]d[S][k[h/l]N][+/-M] or [N]d[S][+/-M][k[h/l]N]
# Examples: 1d20, 2d6+3, 3d4-1, d20, 2d20kh1, 2d20kl1, 2d20kh1+3, 2d20kl1-2
# ---------------------------------------------------------------------------
_DICE_RE = re.compile(
    r"^(?P<amount>\d*)d(?P<sides>\d+)"
    r"(?:"
    r"(?:k(?P<keep_dir>[hl])(?P<keep_n>\d+))?(?:(?P<sign>[+-])(?P<mod>\d+))?"
    r"|"
    r"(?:(?P<sign_pre>[+-])(?P<mod_pre>\d+))(?:k(?P<keep_dir_post>[hl])(?P<keep_n_post>\d+))"
    r")$",
    re.IGNORECASE,
)

# Blocked patterns for formula sandbox
_SANDBOX_BLOCKED = ("import", "__", "exec", "eval(", "open", "os.", "sys.")

# Safe builtins allowed in formula evaluation
_SANDBOX_GLOBALS: dict[str, Any] = {
    "__builtins__": {},
    "abs": abs,
    "max": max,
    "min": min,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "int": int,
    "float": float,
    "bool": bool,
}


class DiceResult:
    def __init__(
        self,
        total: int,
        rolls: list[int],
        expression: str,
        kept_rolls: list[int] | None = None,
    ):
        self.total = total
        self.rolls = rolls
        self.expression = expression
        self.kept_rolls = kept_rolls or rolls

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "rolls": self.rolls,
            "expression": self.expression,
            "kept_rolls": self.kept_rolls,
        }


def roll_dice(expression: str) -> DiceResult:
    """
    Roll dice from a standard notation string.

    Supports:
    - ``NdS``       — N dice with S sides (e.g. ``2d6``)
    - ``NdS+M``     — with positive modifier (e.g. ``1d20+5``)
    - ``NdS-M``     — with negative modifier (e.g. ``2d8-2``)
    - ``dS``        — shorthand for 1dS (e.g. ``d20``)
    - ``NdSkhN``    — keep highest N (e.g. ``2d20kh1``)
    - ``NdSklN``    — keep lowest N (e.g. ``2d20kl1``)

    Returns a :class:`DiceResult` with total, individual rolls, expression,
    and kept_rolls (for kh/kl notation).
    Raises ``ValueError`` for unrecognised expressions.
    """
    cleaned = expression.strip().replace(" ", "")
    m = _DICE_RE.match(cleaned)
    if not m:
        raise ValueError(f"Unrecognised dice expression: {expression!r}")

    amount = int(m.group("amount") or 1)
    sides = int(m.group("sides"))
    if amount < 1 or sides < 2:
        raise ValueError(f"Invalid dice parameters: {amount}d{sides} (amount ≥ 1, sides ≥ 2)")

    rolls = [random.randint(1, sides) for _ in range(amount)]

    # Handle keep-highest / keep-lowest
    raw_keep_dir = m.group("keep_dir") or m.group("keep_dir_post")
    keep_dir = raw_keep_dir.lower() if raw_keep_dir else None
    keep_n_str = m.group("keep_n") or m.group("keep_n_post")
    kept_rolls: list[int] | None = None

    if keep_dir and keep_n_str:
        keep_n = int(keep_n_str)
        if keep_n < 1 or keep_n > amount:
            raise ValueError(f"Invalid keep count: {keep_n} (must be 1..{amount})")
        if keep_dir == "h":
            kept_rolls = sorted(rolls, reverse=True)[:keep_n]
        else:
            kept_rolls = sorted(rolls)[:keep_n]
        total = sum(kept_rolls)
    else:
        total = sum(rolls)
        kept_rolls = list(rolls)

    sign = m.group("sign") or m.group("sign_pre")
    mod_str = m.group("mod") or m.group("mod_pre")
    if sign and mod_str:
        mod = int(mod_str)
        total = total + mod if sign == "+" else total - mod

    return DiceResult(total, rolls, cleaned, kept_rolls=kept_rolls)


def calculate_modifier(value: int, formula: str) -> int:
    """
    Evaluate a formula string with ``VALUE`` bound to *value*.

    Example: ``calculate_modifier(16, "(VALUE - 10) // 2")`` → ``3``

    The formula is executed in a restricted sandbox that permits only:
    ``abs``, ``max``, ``min``, ``round``, ``floor``, ``ceil``,
    ``int``, ``float``, ``bool``, and the ``VALUE`` variable.

    Formulas must originate from trusted admin-defined game-system JSON;
    they are never accepted from end-user input.

    Returns ``0`` on any evaluation error.
    """
    for blocked in _SANDBOX_BLOCKED:
        if blocked in formula:
            return 0

    local_env = {"VALUE": value}
    try:
        result = eval(formula, _SANDBOX_GLOBALS, local_env)
        return math.floor(result) if isinstance(result, float) else int(result)
    except Exception:  # noqa: BLE001  # reason: falls back to `0` on failure (in calculate_modifier)
        return 0
