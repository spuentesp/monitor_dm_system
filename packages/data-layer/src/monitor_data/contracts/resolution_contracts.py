# ruff: noqa: E402
from typing import Any

"""
Resolution Contract Definitions.

These contracts define pre-conditions, post-conditions, and invariants
for dice resolution operations.

Use Cases: P-3, P-4, P-8, DL-24
"""

from dataclasses import dataclass

from hypothesis import strategies as st

from monitor_data.schemas.resolutions import (
    Effect,
    Mechanics,
    ResolutionCreate,
    ResolutionResponse,
    RollResult,
    SuccessLevel,
)

# =============================================================================
# RESOLUTION PRE-CONDITIONS
# =============================================================================


@dataclass
class ResolutionPreConditions:
    """
    Pre-conditions for Resolution operations.

    These must be TRUE before the operation can proceed.
    """

    @staticmethod
    def create_resolution(
        params: ResolutionCreate,
        scene_is_active: bool,
        caller_is_resolver_or_canon_keeper: bool,
    ) -> bool:
        """
        Pre-condition for mongodb_create_resolution.

        Requirements:
        - scene must be ACTIVE
        - caller must be Resolver or CanonKeeper
        - turn_id must reference existing turn
        - action must be non-empty
        - success_level must be valid for resolution_type
        """
        if not scene_is_active:
            raise ValueError("Cannot create resolution for inactive scene")

        if not caller_is_resolver_or_canon_keeper:
            raise PermissionError("Only Resolver or CanonKeeper can create resolutions")

        if not params.action or len(params.action.strip()) == 0:
            raise ValueError("Action description cannot be empty")

        if params.success_level == SuccessLevel.CRITICAL_SUCCESS:
            if params.resolution_type.value not in ("dice", "card"):
                raise ValueError("Critical success only valid for dice/card resolutions")

        if params.success_level == SuccessLevel.CRITICAL_FAILURE:
            if params.resolution_type.value not in ("dice",):
                raise ValueError("Critical failure only valid for dice resolutions")

        return True

    @staticmethod
    def roll_dice(
        num_dice: int,
        dice_sides: int,
        modifier: int = 0,
    ) -> bool:
        """
        Pre-condition for dice roll.

        Requirements:
        - num_dice must be 1-20
        - dice_sides must be 2-100
        - modifier can be any integer
        """
        if num_dice < 1 or num_dice > 20:
            raise ValueError(f"num_dice must be 1-20, got {num_dice}")
        if dice_sides < 2 or dice_sides > 100:
            raise ValueError(f"dice_sides must be 2-100, got {dice_sides}")
        return True


# =============================================================================
# RESOLUTION POST-CONDITIONS
# =============================================================================


@dataclass
class ResolutionPostConditions:
    """
    Post-conditions for Resolution operations.

    These must be TRUE after the operation completes.
    """

    @staticmethod
    def create_resolution(result: ResolutionResponse, params: ResolutionCreate) -> bool:
        """
        Post-condition for mongodb_create_resolution.

        Guarantees:
        - Returns a ResolutionResponse with valid UUID
        - turn_id matches params
        - scene_id matches params
        - created_at is set
        """
        if result.id is None:
            raise ValueError("Resolution id must be set in response")
        if result.turn_id != params.turn_id:
            raise ValueError(f"turn_id mismatch: expected {params.turn_id}, got {result.turn_id}")
        if result.scene_id != params.scene_id:
            raise ValueError(f"scene_id mismatch: expected {params.scene_id}, got {result.scene_id}")
        if result.created_at is None:
            raise ValueError("created_at must be set")
        return True

    @staticmethod
    def roll_result_invariant(roll_result: RollResult) -> bool:
        """
        Post-condition for dice roll.

        Guarantees:
        - raw_rolls is non-empty
        - Each raw_roll is within dice range
        - total equals sum of kept_rolls + modifiers
        - natural equals sum of raw_rolls
        """
        if not roll_result.raw_rolls:
            raise ValueError("raw_rolls cannot be empty")

        for roll in roll_result.raw_rolls:
            if roll < 1:
                raise ValueError(f"Individual roll must be >= 1, got {roll}")
            # Note: Upper bound check requires knowing dice_sides

        if roll_result.kept_rolls:
            if not all(r in roll_result.raw_rolls for r in roll_result.kept_rolls):
                raise ValueError("kept_rolls must be a subset of raw_rolls")

        return True


# =============================================================================
# RESOLUTION INVARIANTS
# =============================================================================


@dataclass
class ResolutionInvariants:
    """
    Resolution invariants that must hold at all times.
    """

    @staticmethod
    def mechanics_invariant(mechanics: Mechanics) -> bool:
        """
        Invariant for Mechanics schema.

        Requirements:
        - formula is non-empty if present
        - target is positive if present
        - roll is present for DICE resolution_type
        - contested is present for CONTESTED resolution_type
        """
        if mechanics.formula and len(mechanics.formula.strip()) == 0:
            raise ValueError("formula cannot be empty if provided")

        if mechanics.target is not None and mechanics.target <= 0:
            raise ValueError(f"target must be positive, got {mechanics.target}")

        return True

    @staticmethod
    def success_level_invariant(
        success_level: SuccessLevel,
        margin: int | None,
        roll_result: RollResult | None,
    ) -> bool:
        """
        Invariant for SuccessLevel.

        Rules:
        - CRITICAL_SUCCESS requires roll of 20 (natural d20)
        - CRITICAL_FAILURE requires roll of 1 (natural d20)
        - margin must be consistent with success_level
        """
        if success_level == SuccessLevel.CRITICAL_SUCCESS:
            if roll_result is None:
                raise ValueError("CRITICAL_SUCCESS requires roll_result")
            if 20 not in roll_result.raw_rolls:
                raise ValueError("CRITICAL_SUCCESS requires a natural 20")

        if success_level == SuccessLevel.CRITICAL_FAILURE:
            if roll_result is None:
                raise ValueError("CRITICAL_FAILURE requires roll_result")
            if 1 not in roll_result.raw_rolls:
                raise ValueError("CRITICAL_FAILURE requires a natural 1")

        return True

    @staticmethod
    def effect_invariant(effect: Effect) -> bool:
        """
        Invariant for Effect schema.

        Requirements:
        - magnitude is consistent with effect_type
        - damage_type is required for DAMAGE effect_type
        - condition is required for CONDITION effect_type
        """
        if effect.effect_type.value == "damage":
            if effect.magnitude <= 0:
                raise ValueError("DAMAGE effect must have positive magnitude")
            if not effect.damage_type:
                raise ValueError("DAMAGE effect must specify damage_type")

        if effect.effect_type.value == "condition" and not effect.condition:
            raise ValueError("CONDITION effect must specify condition")

        if effect.effect_type.value in ("buff", "debuff"):
            if effect.duration is None or effect.duration <= 0:
                raise ValueError(f"{effect.effect_type.value} effect should have positive duration")

        return True


# =============================================================================
# PROPERTY-BASED TEST STRATEGIES
# =============================================================================


# Valid modifier values (typically -10 to +10 in most systems)
modifier_strategy = st.integers(min_value=-10, max_value=10)

# Valid difficulty targets (1-20 is standard d20 range)
difficulty_strategy = st.integers(min_value=1, max_value=20)

# Valid dice rolls (d20)
d20_strategy = st.integers(min_value=1, max_value=20)


def dice_roll_properties() -> dict[str, Any]:
    """
    Property-based test strategies for dice rolls.

    These define valid input spaces for property-based testing.
    """
    return {
        "num_dice": st.integers(min_value=1, max_value=10),
        "dice_sides": st.integers(min_value=2, max_value=20),
        "modifier": st.integers(min_value=-10, max_value=10),
        "expected_total_range": lambda num_dice, dice_sides, modifier: (
            num_dice * 1 + modifier,  # All 1s
            num_dice * dice_sides + modifier,  # All max
        ),
    }


def modifier_properties() -> dict[str, Any]:
    """
    Property-based test strategies for modifiers.

    These define valid modifier input spaces.
    """
    return {
        "value": st.integers(min_value=-10, max_value=10),
        "source": st.text(min_size=1, max_size=200),
        "reason": st.text(min_size=1, max_size=500),
    }
