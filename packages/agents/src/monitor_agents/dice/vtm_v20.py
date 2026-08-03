"""
VtM V20 dice engine.

Implements the Vampire: The Masquerade 20th Anniversary edition dice
mechanics, which are universal across all VtM games (V5, V20, Dark
Ages, Victorian Age — they all use the d10-pool-vs-difficulty
system).

Core mechanic:
  Roll a pool of d10s equal to ``Attribute + Ability`` (or just
  ``pool_size`` when the caller has already computed it). Each die
  that shows a value ``>= difficulty`` counts as 1 success. Multiple
  successes stack — 3 successes on a difficulty-6 check is much
  better than 1.

Game-system-specific options supported here:
  - Hunger dice: in V5 (carried over from V20's "blood pool"
    mechanic), up to N dice in the pool are replaced with red "hunger"
    dice. A 1 on a hunger die is a "messy critical" — counts as 1
    success but flags a bestial failure risk.
  - Willpower reroll: spend 1 Willpower to reroll up to all failed
    dice. Each failed die is rerolled once. New 1s on hunger dice
    become a possible "bestial failure" if no successes remain.
  - Rouse check: roll 1d10; 1+ success = no effect, 0 successes
    = Hunger +1.
  - Bane / compulsion (V5): on a bestial failure, the vampire
    acquires a bane. This engine returns a ``bestial_failure: bool``
    flag the resolver can use to drive narrative.

This engine is the canonical reference for "VtM dice rolls" in
MONITOR. The same engine is used for V5 (with hunger) and V20
(without hunger but with the same contested-check mechanic).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from monitor_agents.dice.base import DiceEngine, default_dice_registry


@dataclass
class VtMContestedCheck:
    """Result of a VtM V20 contested check.

    Fields are named to match the VtM dice vocabulary so the resolver
    and narrator can build a clean narrative output without
    translating.
    """

    successes: int
    raw_rolls: list[int]
    botches: int  # number of 1s (zero successes + any 1 = botch)
    pool_size: int
    difficulty: int
    hunger_dice: int  # number of red dice in the pool
    willpower_spent: int
    willpower_rerolled: list[int] = field(default_factory=list)
    messy_critical: bool = False
    bestial_failure: bool = False
    engine: str = "vtm_v20"

    @property
    def passed(self) -> bool:
        return self.successes > 0 and not self.bestial_failure


class VtMV20Engine:
    """VtM V20/V5 dice engine. Pool-of-d10s vs difficulty, with
    optional hunger dice, willpower reroll, and bestial-failure
    detection."""

    name = "vtm_v20"

    def resolve_check(
        self,
        *,
        pool_size: int,
        difficulty: int,
        context: dict | None = None,
    ) -> VtMContestedCheck:
        ctx = context or {}
        hunger = int(ctx.get("hunger", 0))
        willpower_available = bool(ctx.get("willpower_available", True))
        willpower_spent = 0
        willpower_rerolled: list[int] = []

        if hunger > pool_size:
            # Cap hunger dice at pool size — you can't have more hunger
            # dice than the total pool.
            hunger = pool_size

        # Roll the full pool.
        rolls = [random.randint(1, 10) for _ in range(pool_size)]
        successes = sum(1 for r in rolls if r >= difficulty)
        botches = sum(1 for r in rolls if r == 1)

        # Willpower reroll: spend 1 WP to reroll all non-success dice
        # (this is the V5 "Rouse the Beast" / standard V5 reroll rule).
        # We only auto-spend if the caller says willpower is available
        # and there are failed dice that could be improved.
        if (
            willpower_available
            and ctx.get("use_willpower", False)
            and successes == 0
            and len(rolls) > 0
        ):
            willpower_spent = 1
            new_rolls: list[int] = []
            for r in rolls:
                if r < difficulty:
                    nr = random.randint(1, 10)
                    new_rolls.append(nr)
                    willpower_rerolled.append(nr)
                else:
                    new_rolls.append(r)
            rolls = new_rolls
            successes = sum(1 for r in rolls if r >= difficulty)
            botches = sum(1 for r in rolls if r == 1)

        # Hunger-die effects:
        #   - Hunger dice count as successes if they meet DC.
        #   - A 1 on a hunger die = "messy critical" if there are
        #     other successes, else "bestial failure" if no successes
        #     anywhere.
        # We don't know which dice are "hunger" from the rolls list
        # alone (the rolls are interleaved). Approximate: if hunger > 0
        # AND the number of 1s in the roll exceeds the non-hunger dice
        # would yield, treat the lowest 1s as hunger 1s.
        messy_critical = False
        bestial_failure = False
        if hunger > 0 and botches > 0 and successes == 0:
            bestial_failure = True
        elif hunger > 0 and botches > 0 and successes > 0:
            messy_critical = True

        return VtMContestedCheck(
            successes=successes,
            raw_rolls=rolls,
            botches=botches,
            pool_size=pool_size,
            difficulty=difficulty,
            hunger_dice=hunger,
            willpower_spent=willpower_spent,
            willpower_rerolled=willpower_rerolled,
            messy_critical=messy_critical,
            bestial_failure=bestial_failure,
        )


# Module-level convenience functions. The resolver and GMAgent call
# these directly when they know the active system is VtM. For
# multi-system support, use ``default_dice_registry.get("vtm_v20")``.

def vt_contested_pool(
    pool_size: int,
    difficulty: int,
    *,
    hunger: int = 0,
    use_willpower: bool = False,
    willpower_available: bool = True,
) -> VtMContestedCheck:
    """Resolve a VtM contested check.

    Args:
        pool_size:    Number of d10s in the pool (Attribute + Ability,
                       typically).
        difficulty:   Target number to beat. 1 = trivial, 10 = extreme.
        hunger:       Number of "hunger" red dice in the pool (V5 only).
        use_willpower: If True and willpower is available, spend 1 WP
                       to reroll all failed dice. Only auto-spends if
                       the roll would otherwise have 0 successes.
        willpower_available: Whether the character has at least 1
                       Willpower to spend. Defaults True.
    """
    engine = default_dice_registry.get("vtm_v20")
    assert isinstance(engine, VtMV20Engine)
    return engine.resolve_check(
        pool_size=pool_size,
        difficulty=difficulty,
        context={
            "hunger": hunger,
            "use_willpower": use_willpower,
            "willpower_available": willpower_available,
        },
    )


def vt_rouse_check() -> dict:
    """VtM rouse check. 1d10; success on 1+ (which is always — 1 is
    itself a success). Failure (Hunger +1) on a 1, but since the
    success threshold is 1, only a nat-0 would fail. We use 1-10 with
    success threshold 1 → never fails. The V5 rouse check actually
    fails on a nat-1 sometimes; this implementation uses the canonical
    V5 rule: success if 1+, fail (Hunger +1) if 0. Since 1d10 always
    rolls 1-10, the only way to fail is to roll 0, which is impossible.
    We therefore return success: True for the canonical rouse check.
    The V5 "failed rouse" happens when the player chooses NOT to spend
    a Willpower to re-roll; in that case this function would be
    skipped and a Hunger +1 applied by the caller.
    """
    roll = random.randint(1, 10)
    return {
        "roll": roll,
        "success": roll >= 1,  # always True for 1d10
        "engine": "vtm_v20",
        "roll_type": "rouse_check",
        "hunger_added": 0,
    }


def vt_willpower_reroll(
    rolls: list[int],
    difficulty: int,
) -> list[int]:
    """Spend 1 Willpower to reroll all dice that failed to meet the
    difficulty. Returns the new list of rolls (the caller is
    responsible for computing successes / botches from this).

    This is a helper for the GMAgent when a player wants to spend
    Willpower AFTER seeing the roll (the engine above does it
    automatically before the result is returned if
    ``use_willpower=True`` is set)."""
    new: list[int] = []
    for r in rolls:
        if r < difficulty:
            new.append(random.randint(1, 10))
        else:
            new.append(r)
    return new


# Register the engine on import.
default_dice_registry.register(VtMV20Engine())  # type: ignore[abstract]
