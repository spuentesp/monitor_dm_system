"""
Tests for Resolution Contracts.

These tests verify preconditions, postconditions, and invariants
for dice resolution operations.

Use Cases: P-3, P-4, P-8, DL-24
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from monitor_data.contracts.resolution_contracts import (
    ResolutionPreConditions,
    ResolutionPostConditions,
    ResolutionInvariants,
)
from monitor_data.schemas.resolutions import (
    ResolutionCreate,
    ResolutionResponse,
    Mechanics,
    RollResult,
    Modifier,
    ActionType,
    SuccessLevel,
    Effect,
    EffectType,
    ResolutionType,
)


class TestResolutionPreConditions:
    """Tests for ResolutionPreConditions."""

    def test_create_resolution_valid(self):
        """Valid resolution creation passes preconditions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack the goblin",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.SUCCESS,
        )
        
        result = ResolutionPreConditions.create_resolution(
            params,
            scene_is_active=True,
            caller_is_resolver_or_canon_keeper=True,
        )
        assert result is True

    def test_create_resolution_inactive_scene_raises(self):
        """Resolution for inactive scene fails preconditions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.SUCCESS,
        )
        
        with pytest.raises(ValueError, match="inactive scene"):
            ResolutionPreConditions.create_resolution(
                params,
                scene_is_active=False,
                caller_is_resolver_or_canon_keeper=True,
            )

    def test_create_resolution_unauthorized_raises(self):
        """Unauthorized caller fails preconditions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.SUCCESS,
        )
        
        with pytest.raises(PermissionError):
            ResolutionPreConditions.create_resolution(
                params,
                scene_is_active=True,
                caller_is_resolver_or_canon_keeper=False,
            )

    def test_create_resolution_empty_action_raises(self):
        """Empty action string fails preconditions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="   ",  # whitespace only
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.SUCCESS,
        )
        
        with pytest.raises(ValueError, match="empty"):
            ResolutionPreConditions.create_resolution(
                params,
                scene_is_active=True,
                caller_is_resolver_or_canon_keeper=True,
            )

    def test_create_resolution_critical_success_requires_dice(self):
        """CRITICAL_SUCCESS only valid for dice/card resolutions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.NARRATIVE,  # Not dice/card - should fail!
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.CRITICAL_SUCCESS,  # Invalid!
        )
        
        with pytest.raises(ValueError, match="Critical success only valid"):
            ResolutionPreConditions.create_resolution(
                params,
                scene_is_active=True,
                caller_is_resolver_or_canon_keeper=True,
            )

    def test_create_resolution_critical_failure_requires_dice(self):
        """CRITICAL_FAILURE only valid for dice resolutions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.NARRATIVE,  # Not dice - should fail!
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.CRITICAL_FAILURE,  # Invalid!
        )
        
        with pytest.raises(ValueError, match="Critical failure only valid"):
            ResolutionPreConditions.create_resolution(
                params,
                scene_is_active=True,
                caller_is_resolver_or_canon_keeper=True,
            )

    def test_roll_dice_valid(self):
        """Valid dice roll parameters pass preconditions."""
        result = ResolutionPreConditions.roll_dice(
            num_dice=2,
            dice_sides=6,
            modifier=5,
        )
        assert result is True

    def test_roll_dice_invalid_num_dice(self):
        """Invalid num_dice fails preconditions."""
        with pytest.raises(ValueError, match="num_dice must be 1-20"):
            ResolutionPreConditions.roll_dice(num_dice=0, dice_sides=6)
        
        with pytest.raises(ValueError, match="num_dice must be 1-20"):
            ResolutionPreConditions.roll_dice(num_dice=21, dice_sides=6)

    def test_roll_dice_invalid_dice_sides(self):
        """Invalid dice_sides fails preconditions."""
        with pytest.raises(ValueError, match="dice_sides must be 2-100"):
            ResolutionPreConditions.roll_dice(num_dice=1, dice_sides=1)
        
        with pytest.raises(ValueError, match="dice_sides must be 2-100"):
            ResolutionPreConditions.roll_dice(num_dice=1, dice_sides=101)


class TestResolutionPostConditions:
    """Tests for ResolutionPostConditions."""

    def test_create_resolution_valid_response(self):
        """Valid resolution response passes postconditions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.SUCCESS,
        )
        
        result = ResolutionResponse(
            id=uuid4(),
            turn_id=params.turn_id,
            scene_id=params.scene_id,
            story_id=params.story_id,
            actor_id=params.actor_id,
            action=params.action,
            action_type=params.action_type,
            resolution_type=params.resolution_type,
            mechanics=params.mechanics,
            success_level=params.success_level,
            roll_result=RollResult(
                raw_rolls=[15, 6],
                kept_rolls=[15, 6],
                modifier=5,
                total=26,
                natural=21,
            ),
            margin=5,
            effects=[],
            description="Successful attack",
            gm_notes=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        assert ResolutionPostConditions.create_resolution(result, params) is True

    def test_create_resolution_id_must_be_set(self):
        """Response with null id fails postconditions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.SUCCESS,
        )
        
        result = MagicMock()
        result.id = None
        
        with pytest.raises(ValueError, match="id must be set"):
            ResolutionPostConditions.create_resolution(result, params)

    def test_create_resolution_turn_id_mismatch(self):
        """Response with mismatched turn_id fails postconditions."""
        params = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="d20+5", target=15),
            success_level=SuccessLevel.SUCCESS,
        )
        
        result = MagicMock()
        result.id = uuid4()
        result.turn_id = uuid4()  # Different!
        result.scene_id = params.scene_id
        result.created_at = datetime.now(timezone.utc)
        
        with pytest.raises(ValueError, match="turn_id mismatch"):
            ResolutionPostConditions.create_resolution(result, params)

    def test_roll_result_invariant_valid(self):
        """Valid roll result passes invariant."""
        roll_result = RollResult(
            raw_rolls=[15, 6],
            kept_rolls=[15, 6],
            modifier=5,
            total=26,
            natural=21,
        )
        
        assert ResolutionPostConditions.roll_result_invariant(roll_result) is True

    def test_roll_result_invariant_empty_raw_rolls(self):
        """Empty raw_rolls fails invariant."""
        roll_result = MagicMock()
        roll_result.raw_rolls = []
        
        with pytest.raises(ValueError, match="raw_rolls cannot be empty"):
            ResolutionPostConditions.roll_result_invariant(roll_result)

    def test_roll_result_invariant_invalid_roll_value(self):
        """Roll value less than 1 fails invariant."""
        roll_result = MagicMock()
        roll_result.raw_rolls = [0, 6]  # 0 is invalid
        
        with pytest.raises(ValueError, match="must be >= 1"):
            ResolutionPostConditions.roll_result_invariant(roll_result)

    def test_roll_result_invariant_kept_not_subset(self):
        """kept_rolls not a subset of raw_rolls fails invariant."""
        roll_result = MagicMock()
        roll_result.raw_rolls = [15, 6]
        roll_result.kept_rolls = [15, 20]  # 20 not in raw_rolls
        
        with pytest.raises(ValueError, match="kept_rolls must be a subset"):
            ResolutionPostConditions.roll_result_invariant(roll_result)


class TestResolutionInvariants:
    """Tests for ResolutionInvariants."""

    def test_mechanics_invariant_valid(self):
        """Valid mechanics passes invariant."""
        mechanics = Mechanics(formula="d20+5", target=15)
        assert ResolutionInvariants.mechanics_invariant(mechanics) is True

    def test_mechanics_invariant_empty_formula(self):
        """Empty formula fails invariant."""
        mechanics = MagicMock()
        mechanics.formula = "   "
        mechanics.target = 15
        
        with pytest.raises(ValueError, match="formula cannot be empty"):
            ResolutionInvariants.mechanics_invariant(mechanics)

    def test_mechanics_invariant_non_positive_target(self):
        """Non-positive target fails invariant."""
        mechanics = MagicMock()
        mechanics.formula = "d20+5"
        mechanics.target = 0
        
        with pytest.raises(ValueError, match="target must be positive"):
            ResolutionInvariants.mechanics_invariant(mechanics)

    def test_effect_invariant_damage_valid(self):
        """Valid DAMAGE effect passes invariant."""
        effect = Effect(
            effect_type=EffectType.DAMAGE,
            target_id=uuid4(),
            magnitude=10,
            damage_type="fire",
            description="Fire damage",
        )
        assert ResolutionInvariants.effect_invariant(effect) is True

    def test_effect_invariant_damage_no_magnitude(self):
        """DAMAGE effect with zero magnitude fails invariant."""
        effect = Effect(
            effect_type=EffectType.DAMAGE,
            target_id=uuid4(),
            magnitude=0,  # Invalid!
            damage_type="fire",
            description="Fire damage",
        )
        
        with pytest.raises(ValueError, match="positive magnitude"):
            ResolutionInvariants.effect_invariant(effect)

    def test_effect_invariant_damage_no_damage_type(self):
        """DAMAGE effect without damage_type fails invariant."""
        effect = Effect(
            effect_type=EffectType.DAMAGE,
            target_id=uuid4(),
            magnitude=10,
            damage_type=None,  # Invalid!
            description="Damage",
        )
        
        with pytest.raises(ValueError, match="must specify damage_type"):
            ResolutionInvariants.effect_invariant(effect)

    def test_effect_invariant_condition_valid(self):
        """Valid CONDITION effect passes invariant."""
        effect = Effect(
            effect_type=EffectType.CONDITION,
            target_id=uuid4(),
            magnitude=1,
            condition="stunned",
            description="Stunned condition",
        )
        assert ResolutionInvariants.effect_invariant(effect) is True

    def test_effect_invariant_condition_no_condition(self):
        """CONDITION effect without condition fails invariant."""
        effect = Effect(
            effect_type=EffectType.CONDITION,
            target_id=uuid4(),
            magnitude=1,
            condition=None,  # Invalid!
            description="Condition",
        )
        
        with pytest.raises(ValueError, match="must specify condition"):
            ResolutionInvariants.effect_invariant(effect)

    def test_effect_invariant_buff_valid(self):
        """Valid BUFF effect passes invariant."""
        effect = Effect(
            effect_type=EffectType.BUFF,
            target_id=uuid4(),
            magnitude=5,
            duration=3,
            description="Buff",
        )
        assert ResolutionInvariants.effect_invariant(effect) is True

    def test_effect_invariant_buff_no_duration(self):
        """BUFF effect without positive duration fails invariant."""
        effect = Effect(
            effect_type=EffectType.BUFF,
            target_id=uuid4(),
            magnitude=5,
            duration=0,  # Invalid!
            description="Buff",
        )
        
        with pytest.raises(ValueError, match="positive duration"):
            ResolutionInvariants.effect_invariant(effect)

    def test_success_level_invariant_critical_success_requires_20(self):
        """CRITICAL_SUCCESS requires a natural 20 in raw_rolls."""
        roll_result = RollResult(
            raw_rolls=[15, 6],
            kept_rolls=[15, 6],
            modifier=5,
            total=26,
            natural=21,
        )
        
        with pytest.raises(ValueError, match="natural 20"):
            ResolutionInvariants.success_level_invariant(
                SuccessLevel.CRITICAL_SUCCESS,
                margin=10,
                roll_result=roll_result,
            )

    def test_success_level_invariant_critical_failure_requires_1(self):
        """CRITICAL_FAILURE requires a natural 1 in raw_rolls."""
        roll_result = RollResult(
            raw_rolls=[15, 6],
            kept_rolls=[15, 6],
            modifier=5,
            total=26,
            natural=21,
        )
        
        with pytest.raises(ValueError, match="natural 1"):
            ResolutionInvariants.success_level_invariant(
                SuccessLevel.CRITICAL_FAILURE,
                margin=-10,
                roll_result=roll_result,
            )


class TestResolutionPropertyBased:
    """Property-based tests for resolution contracts."""

    @given(
        num_dice=st.integers(min_value=1, max_value=20),
        dice_sides=st.integers(min_value=2, max_value=100),
        modifier=st.integers(min_value=-50, max_value=50),
    )
    @settings(max_examples=100)
    def test_roll_dice_preconditions_always_pass(self, num_dice, dice_sides, modifier):
        """Valid dice parameters always pass preconditions."""
        result = ResolutionPreConditions.roll_dice(num_dice, dice_sides, modifier)
        assert result is True

    @given(
        num_dice=st.integers(min_value=-10, max_value=0).filter(lambda x: x < 1),
        dice_sides=st.integers(min_value=2, max_value=100),
    )
    @settings(max_examples=50)
    def test_roll_dice_rejects_invalid_num_dice(self, num_dice, dice_sides):
        """Invalid num_dice is rejected."""
        with pytest.raises(ValueError, match="num_dice must be 1-20"):
            ResolutionPreConditions.roll_dice(num_dice, dice_sides)

    @given(
        mechanics_formula=st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
        mechanics_target=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=50)
    def test_mechanics_invariant_valid_inputs(self, mechanics_formula, mechanics_target):
        """Valid mechanics inputs pass invariant."""
        mechanics = Mechanics(formula=mechanics_formula, target=mechanics_target)
        assert ResolutionInvariants.mechanics_invariant(mechanics) is True
