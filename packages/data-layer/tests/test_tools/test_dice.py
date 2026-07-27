"""
Tests for monitor_data.utils.dice — roll_dice() and calculate_modifier().

All tests are pure-unit (no DB, no LLM).
"""

from unittest.mock import patch

import pytest

from monitor_data.utils.dice import DiceResult, calculate_modifier, roll_dice

# ===========================================================================
# DiceResult
# ===========================================================================


class TestDiceResult:
    def test_to_dict(self):
        dr = DiceResult(total=7, rolls=[3, 4], expression="2d6")
        d = dr.to_dict()
        assert d["total"] == 7
        assert d["rolls"] == [3, 4]
        assert d["expression"] == "2d6"

    def test_to_dict_with_modifier(self):
        dr = DiceResult(total=12, rolls=[7], expression="1d20+5")
        d = dr.to_dict()
        assert d["total"] == 12
        assert d["expression"] == "1d20+5"


# ===========================================================================
# roll_dice — basic expressions
# ===========================================================================


class TestRollDiceBasic:
    def test_1d20_returns_1_to_20(self):
        for _ in range(50):
            result = roll_dice("1d20")
            assert 1 <= result.total <= 20
            assert len(result.rolls) == 1

    def test_2d6_total_within_range(self):
        for _ in range(50):
            result = roll_dice("2d6")
            assert 2 <= result.total <= 12
            assert len(result.rolls) == 2

    def test_d20_shorthand(self):
        """'d20' is shorthand for '1d20'."""
        for _ in range(20):
            result = roll_dice("d20")
            assert 1 <= result.total <= 20
            assert len(result.rolls) == 1

    def test_4d4_number_of_rolls(self):
        result = roll_dice("4d4")
        assert len(result.rolls) == 4
        assert 4 <= result.total <= 16

    def test_expression_stored(self):
        result = roll_dice("3d6")
        assert result.expression == "3d6"

    def test_individual_rolls_sum_to_total(self):
        """Without a modifier, sum of rolls always equals total."""
        for _ in range(30):
            result = roll_dice("4d6")
            assert sum(result.rolls) == result.total

    def test_case_insensitive(self):
        result = roll_dice("2D6")
        assert len(result.rolls) == 2


# ===========================================================================
# roll_dice — modifiers
# ===========================================================================


class TestRollDiceModifiers:
    def test_positive_modifier_added(self):
        with patch("random.randint", return_value=3):
            result = roll_dice("2d6+4")
        # 3 + 3 dice + 4 modifier = 10
        assert result.total == 10

    def test_negative_modifier_subtracted(self):
        with patch("random.randint", return_value=5):
            result = roll_dice("2d8-2")
        # 5 + 5 dice − 2 modifier = 8
        assert result.total == 8

    def test_positive_modifier_range(self):
        for _ in range(30):
            result = roll_dice("1d20+5")
            assert 6 <= result.total <= 25

    def test_negative_modifier_range(self):
        for _ in range(30):
            result = roll_dice("1d6-1")
            assert 0 <= result.total <= 5

    def test_modifier_does_not_affect_individual_rolls(self):
        """Individual rolls list should not include the modifier."""
        with patch("random.randint", return_value=4):
            result = roll_dice("2d6+3")
        assert result.rolls == [4, 4]
        assert result.total == 11  # 4 + 4 + 3

    def test_zero_modifier_positive(self):
        """Edge case: +0 should leave result unchanged."""
        with patch("random.randint", return_value=6):
            result = roll_dice("1d6+0")
        assert result.total == 6

    def test_large_modifier(self):
        with patch("random.randint", return_value=1):
            result = roll_dice("1d20+100")
        assert result.total == 101

    def test_modifier_that_makes_total_negative(self):
        with patch("random.randint", return_value=1):
            result = roll_dice("1d4-10")
        assert result.total == -9


# ===========================================================================
# roll_dice — invalid expressions
# ===========================================================================


class TestRollDiceInvalid:
    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            roll_dice("")

    def test_no_dice_raises(self):
        with pytest.raises(ValueError):
            roll_dice("notadice")

    def test_0d6_raises(self):
        with pytest.raises(ValueError):
            roll_dice("0d6")

    def test_1d1_raises(self):
        """A die needs at least 2 sides."""
        with pytest.raises(ValueError):
            roll_dice("1d1")

    def test_just_a_number_raises(self):
        with pytest.raises(ValueError):
            roll_dice("42")


# ===========================================================================
# calculate_modifier
# ===========================================================================


class TestCalculateModifier:
    def test_d20_standard_modifier(self):
        """Standard 5e modifier: (stat - 10) // 2."""
        assert calculate_modifier(10, "(VALUE - 10) // 2") == 0
        assert calculate_modifier(16, "(VALUE - 10) // 2") == 3
        assert calculate_modifier(8, "(VALUE - 10) // 2") == -1

    def test_value_directly(self):
        assert calculate_modifier(5, "VALUE") == 5

    def test_floor_applied_to_floats(self):
        """floor((8 - 10) / 2) = floor(-1.0) = -1 (NOT 0)."""
        assert calculate_modifier(8, "(VALUE - 10) / 2") == -1

    def test_identity_functions_available(self):
        assert calculate_modifier(7, "abs(VALUE - 10)") == 3

    def test_max_min_available(self):
        assert calculate_modifier(5, "max(0, VALUE - 10)") == 0
        assert calculate_modifier(15, "max(0, VALUE - 10)") == 5
        assert calculate_modifier(3, "min(VALUE, 5)") == 3
        assert calculate_modifier(8, "min(VALUE, 5)") == 5

    def test_floor_ceil_available(self):
        assert calculate_modifier(7, "floor(VALUE / 3)") == 2
        assert calculate_modifier(7, "ceil(VALUE / 3)") == 3

    def test_int_conversion(self):
        assert calculate_modifier(10, "int(VALUE * 1.5)") == 15

    def test_zero_modifier(self):
        assert calculate_modifier(10, "0") == 0

    def test_constant_formula(self):
        assert calculate_modifier(99, "5") == 5

    # ------------------------------------------------------------------
    # Sandbox safety
    # ------------------------------------------------------------------

    def test_import_blocked(self):
        result = calculate_modifier(1, "import os")
        assert result == 0

    def test_dunder_blocked(self):
        result = calculate_modifier(1, "().__class__.__bases__[0].__subclasses__()")
        assert result == 0

    def test_exec_blocked(self):
        result = calculate_modifier(1, "exec('import os')")
        assert result == 0

    def test_eval_nested_blocked(self):
        result = calculate_modifier(1, "eval('1+1')")
        assert result == 0

    def test_open_blocked(self):
        result = calculate_modifier(1, "open('/etc/passwd').read()")
        assert result == 0

    def test_syntax_error_returns_0(self):
        result = calculate_modifier(5, "VALUE +++ nonsense...")
        assert result == 0

    def test_division_by_zero_returns_0(self):
        result = calculate_modifier(5, "VALUE / 0")
        assert result == 0

    def test_unknown_name_returns_0(self):
        result = calculate_modifier(5, "UNKNOWN_VAR + 1")
        assert result == 0


# ===========================================================================
# Integration: roll_dice feeds calculate_modifier via Resolver pattern
# ===========================================================================


class TestDiceAndModifierIntegration:
    def test_attack_roll_with_str_modifier(self):
        """Attack roll: 1d20 + STR modifier (STR=14 → +2)."""
        with patch("random.randint", return_value=12):
            roll = roll_dice("1d20")
        mod = calculate_modifier(14, "(VALUE - 10) // 2")
        assert roll.total == 12
        assert mod == 2
        assert roll.total + mod == 14

    def test_critical_hit_still_applies_modifier(self):
        with patch("random.randint", return_value=20):
            roll = roll_dice("1d20")
        mod = calculate_modifier(18, "(VALUE - 10) // 2")
        assert roll.total == 20
        assert mod == 4
        assert roll.total + mod == 24
