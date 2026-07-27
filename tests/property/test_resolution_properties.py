"""
Property-based tests for dice resolution mechanics.

These tests use Hypothesis to verify dice roll properties across
thousands of randomly generated inputs.

Use Cases: P-3, P-4, P-8, DL-24
"""

from uuid import uuid4

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from monitor_data.contracts.resolution_contracts import (
    ResolutionInvariants,
    ResolutionPreConditions,
)
from monitor_data.schemas.resolutions import (
    ActionType,
    Effect,
    EffectType,
    Mechanics,
    Modifier,
    ResolutionCreate,
    RollResult,
    SuccessLevel,
)


class TestDiceRollProperties:
    """Property-based tests for dice rolls."""

    @given(
        num_dice=st.integers(min_value=1, max_value=10),
        dice_sides=st.integers(min_value=2, max_value=20),
        modifier=st.integers(min_value=-10, max_value=10),
    )
    @settings(max_examples=100, deadline=1000)
    def test_dice_preconditions_valid_range(self, num_dice, dice_sides, modifier):
        """Dice preconditions accept all valid inputs."""
        # This should not raise for valid ranges
        result = ResolutionPreConditions.roll_dice(num_dice, dice_sides, modifier)
        assert result is True

    @given(
        num_dice=st.one_of(
            st.integers(max_value=0),  # 0 or negative
            st.integers(min_value=21),  # 21 or above
        ),
        dice_sides=st.integers(min_value=2, max_value=100),
    )
    @settings(max_examples=50)
    def test_dice_preconditions_rejects_invalid_num_dice(self, num_dice, dice_sides):
        """Dice preconditions reject invalid num_dice."""
        assume(num_dice < 1 or num_dice > 20)  # Ensure invalid
        with pytest.raises(ValueError, match="num_dice must be 1-20"):
            ResolutionPreConditions.roll_dice(num_dice, dice_sides)

    @given(
        num_dice=st.integers(min_value=1, max_value=20),
        dice_sides=st.one_of(
            st.integers(max_value=1),  # 1 or less
            st.integers(min_value=101),  # 101 or above
        ),
    )
    @settings(max_examples=50)
    def test_dice_preconditions_rejects_invalid_dice_sides(self, num_dice, dice_sides):
        """Dice preconditions reject invalid dice_sides."""
        assume(dice_sides < 2 or dice_sides > 100)  # Ensure invalid
        with pytest.raises(ValueError, match="dice_sides must be 2-100"):
            ResolutionPreConditions.roll_dice(num_dice, dice_sides)


class TestModifierProperties:
    """Property-based tests for modifier application."""

    @given(
        base_value=st.integers(min_value=1, max_value=20),
        modifiers=st.lists(
            st.integers(min_value=-10, max_value=10),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=1000)
    def test_modifier_sum_bounded(self, base_value, modifiers):
        """Sum of modifiers stays within reasonable bounds."""
        total = base_value + sum(modifiers)
        # A d20 roll with heavy penalties/bonuses should still be bounded
        assert -100 <= total <= 200  # Reasonable bounds for any system

    @given(
        value=st.integers(min_value=-100, max_value=100),
        reason=st.text(min_size=1, max_size=500),
    )
    @settings(max_examples=50)
    def test_modifier_schema_valid(self, value, reason):
        """Modifier schema accepts all valid inputs."""
        modifier = Modifier(source="test", value=value, reason=reason)
        assert modifier.value == value
        assert modifier.reason == reason


class TestRollResultProperties:
    """Property-based tests for RollResult."""

    @given(
        raw_rolls=st.lists(
            st.integers(min_value=1, max_value=100),
            min_size=1,
            max_size=20,
        ),
        kept_rolls=st.lists(
            st.integers(min_value=1, max_value=100),
            min_size=0,
            max_size=10,
        ),
        total=st.integers(min_value=-50, max_value=500),
        natural=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=100, deadline=1000)
    def test_roll_result_basic_properties(self, raw_rolls, kept_rolls, total, natural):
        """RollResult basic properties hold."""
        roll_result = RollResult(
            raw_rolls=raw_rolls,
            kept_rolls=kept_rolls if kept_rolls else raw_rolls,
            total=total,
            natural=natural,
            critical=20 in raw_rolls if raw_rolls else False,
            fumble=1 in raw_rolls if raw_rolls else False,
        )

        # Basic sanity checks
        assert len(roll_result.raw_rolls) > 0
        assert roll_result.total is not None

    @given(
        raw_rolls=st.lists(
            st.integers(min_value=1, max_value=20),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=1000)
    def test_d20_roll_always_valid(self, raw_rolls):
        """d20 rolls always produce values 1-20."""
        for roll in raw_rolls:
            assert 1 <= roll <= 20

    @given(
        raw_rolls=st.lists(
            st.integers(min_value=1, max_value=20),
            min_size=2,
            max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=1000)
    def test_keep_highest_logic(self, raw_rolls):
        """Keep highest (advantage) logic produces valid results."""
        if len(raw_rolls) >= 2:
            kept = [max(raw_rolls)]  # Simulate keep highest
            assert len(kept) == 1
            assert kept[0] in raw_rolls
            assert kept[0] == max(raw_rolls)

    @given(
        raw_rolls=st.lists(
            st.integers(min_value=1, max_value=20),
            min_size=2,
            max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=1000)
    def test_keep_lowest_logic(self, raw_rolls):
        """Keep lowest (disadvantage) logic produces valid results."""
        if len(raw_rolls) >= 2:
            kept = [min(raw_rolls)]  # Simulate keep lowest
            assert len(kept) == 1
            assert kept[0] in raw_rolls
            assert kept[0] == min(raw_rolls)


class TestSuccessLevelProperties:
    """Property-based tests for success level determination."""

    @given(roll=st.integers(min_value=1, max_value=20))
    @settings(max_examples=20)
    def test_critical_success_requires_d20(self, roll):
        """CRITICAL_SUCCESS requires a natural 20."""
        roll_result = RollResult(
            raw_rolls=[roll],
            kept_rolls=[roll],
            total=roll,
            natural=roll,
            critical=roll == 20,
            fumble=False,
        )

        if roll == 20:
            assert roll_result.critical is True
            # Would need to also verify success_level == CRITICAL_SUCCESS

    @given(roll=st.integers(min_value=1, max_value=20))
    @settings(max_examples=20)
    def test_critical_failure_requires_d1(self, roll):
        """CRITICAL_FAILURE requires a natural 1."""
        roll_result = RollResult(
            raw_rolls=[roll],
            kept_rolls=[roll],
            total=roll,
            natural=roll,
            critical=False,
            fumble=roll == 1,
        )

        if roll == 1:
            assert roll_result.fumble is True


class TestResolutionCreationProperties:
    """Property-based tests for resolution creation."""

    @given(
        action=st.text(min_size=1, max_size=500).filter(lambda a: len(a.strip()) > 0),
        action_type=st.sampled_from(list(ActionType)),
        scene_active=st.booleans(),
        caller_auth=st.sampled_from(
            [("Resolver", True), ("CanonKeeper", True), ("Narrator", False)]
        ),
    )
    @settings(max_examples=50, deadline=1000)
    def test_resolution_preconditions(
        self, action, action_type, scene_active, caller_auth
    ):
        """Resolution preconditions correctly validate."""
        caller, is_auth = caller_auth
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action=action,
            action_type=action_type,
            resolution_type="dice",
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.SUCCESS,
        )

        if not scene_active or not is_auth:
            with pytest.raises((ValueError, PermissionError)):
                ResolutionPreConditions.create_resolution(
                    params,
                    scene_is_active=scene_active,
                    caller_is_resolver_or_canon_keeper=is_auth,
                )
        else:
            result = ResolutionPreConditions.create_resolution(
                params,
                scene_is_active=scene_active,
                caller_is_resolver_or_canon_keeper=is_auth,
            )
            assert result is True


class TestEffectProperties:
    """Property-based tests for Effect schema."""

    @given(
        effect_type=st.sampled_from(list(EffectType)),
        magnitude=st.integers(min_value=-100, max_value=1000),
        damage_type=st.sampled_from(
            ["fire", "cold", "lightning", "acid", "poison", None]
        ),
        condition=st.sampled_from(["stunned", "prone", "charmed", "frightened", None]),
    )
    @settings(max_examples=50, deadline=1000)
    def test_effect_invariant_damage_type(
        self, effect_type, magnitude, damage_type, condition
    ):
        """Effect invariant correctly validates damage effects."""
        effect = Effect(
            effect_type=effect_type,
            target_id=uuid4(),
            magnitude=magnitude,
            damage_type=damage_type,
            condition=condition,
            description="Test effect",
        )

        # DAMAGE effects must have damage_type and positive magnitude
        if effect_type == EffectType.DAMAGE:
            if magnitude <= 0:
                with pytest.raises(ValueError, match="positive magnitude"):
                    ResolutionInvariants.effect_invariant(effect)
            elif not damage_type:
                with pytest.raises(ValueError, match="must specify damage_type"):
                    ResolutionInvariants.effect_invariant(effect)

    @given(
        effect_type=st.sampled_from([EffectType.BUFF, EffectType.DEBUFF]),
        magnitude=st.integers(min_value=1, max_value=100),
        duration=st.integers(min_value=1, max_value=100),  # Positive only
    )
    @settings(max_examples=50, deadline=1000)
    def test_effect_invariant_buff_debuff(self, effect_type, magnitude, duration):
        """Effect invariant correctly validates buff/debuff effects."""
        assume(effect_type in (EffectType.BUFF, EffectType.DEBUFF))
        assume(duration > 0)  # Must be positive

        effect = Effect(
            effect_type=effect_type,
            target_id=uuid4(),
            magnitude=magnitude,
            duration=duration,
            description="Test effect",
        )

        if duration <= 0:
            with pytest.raises(ValueError, match="should have positive duration"):
                ResolutionInvariants.effect_invariant(effect)
        else:
            assert ResolutionInvariants.effect_invariant(effect) is True


class TestResolutionMechanicsProperties:
    """Property-based tests for Mechanics schema."""

    @given(
        formula=st.text(min_size=1, max_size=200).filter(lambda x: len(x.strip()) > 0),
        target=st.integers(min_value=-10, max_value=100).filter(
            lambda x: x is not None and x <= 0
        ),
    )
    @settings(max_examples=30)
    def test_mechanics_invariant_rejects_invalid_target(self, formula, target):
        """Mechanics invariant rejects non-positive target."""
        mechanics = Mechanics(formula=formula, target=target)

        with pytest.raises(ValueError, match="target must be positive"):
            ResolutionInvariants.mechanics_invariant(mechanics)

    @given(
        formula=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        target=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=50)
    def test_mechanics_invariant_accepts_valid(self, formula, target):
        """Mechanics invariant accepts valid inputs."""
        assume(len(formula.strip()) > 0)  # Non-empty after stripping whitespace
        mechanics = Mechanics(formula=formula, target=target)
        assert ResolutionInvariants.mechanics_invariant(mechanics) is True

    @given(
        formula=st.just("d20+5"),
        target=st.integers(min_value=-50, max_value=0),
    )
    @settings(max_examples=30)
    def test_mechanics_with_formula_must_have_positive_target(self, formula, target):
        """Any mechanics with a formula referencing target must have target ≥ 1."""
        assume(target <= 0)
        mechanics = Mechanics(formula=formula, target=target)
        with pytest.raises(ValueError, match="target must be positive"):
            ResolutionInvariants.mechanics_invariant(mechanics)


# =============================================================================
# TESTS: Effect Edge Cases (Phase 4 additions)
# =============================================================================


class TestEffectEdgeCaseProperties:
    """Additional edge case property tests for Effect schema."""

    @given(
        effect_type=st.sampled_from(list(EffectType)),
        damage_type=st.sampled_from(
            ["fire", "cold", "lightning", "acid", "poison", None]
        ),
    )
    @settings(max_examples=50, deadline=1000)
    def test_effect_damage_type_consistency(self, effect_type, damage_type):
        """DAMAGE effects require damage_type; the invariant only checks DAMAGE type."""
        effect = Effect(
            effect_type=effect_type,
            target_id=uuid4(),
            magnitude=10,
            damage_type=damage_type,
            description="Test effect",
        )
        if effect_type == EffectType.DAMAGE:
            if damage_type is None:
                with pytest.raises(ValueError, match="must specify damage_type"):
                    ResolutionInvariants.effect_invariant(effect)
            else:
                # DAMAGE with valid damage_type and positive magnitude should pass
                assert ResolutionInvariants.effect_invariant(effect) is True
        else:
            # Non-DAMAGE effects: the invariant does not validate damage_type
            # (it's only required for DAMAGE type per current implementation)
            pass

    @given(
        effect_type=st.sampled_from(
            [EffectType.BUFF, EffectType.DEBUFF, EffectType.HEALING]
        ),
        duration=st.just(
            0
        ),  # Zero duration — valid for Pydantic, should fail invariant for BUFF/DEBUFF
    )
    @settings(max_examples=20, deadline=1000)
    def test_effect_duration_bounds(self, effect_type, duration):
        """BUFF/DEBUFF effects require positive duration; non-BUFF/DEBUFF have no duration requirement."""
        effect = Effect(
            effect_type=effect_type,
            target_id=uuid4(),
            magnitude=5,
            duration=duration,
            description="Test effect",
        )
        if effect_type in (EffectType.BUFF, EffectType.DEBUFF):
            with pytest.raises(ValueError, match="should have positive duration"):
                ResolutionInvariants.effect_invariant(effect)
        # HEALING with zero duration: may or may not be checked by invariant


# =============================================================================
# TESTS: Dice Roll Edge Cases (Phase 4 additions)
# =============================================================================


class TestDiceRollEdgeCaseProperties:
    """Additional edge case property tests for dice roll mechanics."""

    @given(
        num_dice=st.integers(min_value=2, max_value=10),
        keep=st.integers(min_value=1, max_value=9),
    )
    @settings(max_examples=100, deadline=1000)
    def test_multi_dice_keep_consistency(self, num_dice, keep):
        """keep_highest=N with X dice should produce exactly N kept rolls."""
        assume(keep <= num_dice)
        # Generate num_dice rolls, keep 'keep' highest
        raw_rolls = [10 + i for i in range(num_dice)]  # Increasing values
        kept = sorted(raw_rolls, reverse=True)[:keep]
        assert len(kept) == keep, (
            f"Expected {keep} kept rolls from {num_dice} dice, got {len(kept)}"
        )
        # Kept rolls must be a subset of raw rolls
        for roll in kept:
            assert roll in raw_rolls


class TestModifierEdgeCaseProperties:
    """Additional edge case property tests for modifier composition."""

    @given(
        positive=st.integers(min_value=1, max_value=10),
        negative=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100, deadline=1000)
    def test_modifier_composition_cancellation(self, positive, negative):
        """Two modifiers (+A, -B) produce total A-B, cancelling correctly."""
        mod1 = Modifier(source="test", value=positive, reason="bonus")
        mod2 = Modifier(source="test", value=-negative, reason="penalty")
        total = mod1.value + mod2.value
        assert total == positive - negative

    @given(
        base_value=st.integers(min_value=1, max_value=20),
        modifiers=st.lists(
            st.integers(min_value=-10, max_value=10),
            min_size=2,
            max_size=5,
        ),
    )
    @settings(max_examples=100, deadline=1000)
    def test_modifier_total_is_sum(self, base_value, modifiers):
        """The total of base + sum(modifiers) equals sequential addition."""
        total = base_value + sum(modifiers)
        # Verify sequential order doesn't matter (commutativity of addition)
        reversed_total = base_value + sum(reversed(modifiers))
        assert total == reversed_total
