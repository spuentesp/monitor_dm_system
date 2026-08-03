"""
Generic dice engine — a thin wrapper over ``monitor_data.utils.dice``
that handles plain ``1d20 + mod`` checks. Used as the fallback when
no game-system-specific engine is registered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from monitor_data.utils.dice import roll_dice


@dataclass
class GenericRoll:
    """Result of a generic 1d20 + mod roll."""

    total: int
    natural: int
    modifier: int
    raw_rolls: list[int] = field(default_factory=list)
    formula: str = "1d20"
    engine: str = "generic"
    successes: int = 0  # 0 or 1 — beats DC or not

    def __post_init__(self) -> None:
        # For the generic engine, "successes" is 1 if the total meets
        # or beats the difficulty. The resolver uses ``successes`` to
        # decide success/failure, so we set it here for consistency.
        # (The actual difficulty is passed in by the resolver; the
        # generic engine doesn't know it. The resolver updates
        # ``successes`` post-hoc from the caller.)
        pass


class GenericDiceEngine:
    """Plain ``1d20 + mod`` roll. Used when no game-system engine is
    registered for the active game system."""

    name = "generic"

    def resolve_check(
        self,
        *,
        pool_size: int = 0,
        difficulty: int = 0,
        context: dict | None = None,
    ) -> GenericRoll:
        ctx = context or {}
        modifier = int(ctx.get("modifier", 0))
        # If the caller passed a formula, honour it; otherwise default
        # to 1d20 + mod.
        formula = str(ctx.get("formula") or "1d20")
        roll = roll_dice(formula)
        raw: list[int] = list(getattr(roll, "rolls", []) or [])
        natural = raw[0] if raw else 0
        total = natural + modifier
        return GenericRoll(
            total=total,
            natural=natural,
            modifier=modifier,
            raw_rolls=raw,
            formula=formula,
            successes=1 if total >= difficulty and difficulty > 0 else 0,
        )
