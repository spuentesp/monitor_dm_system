"""
Tests for monitor_data.utils.dice — roll_dice and calculate_modifier.
"""

import pytest

from monitor_data.utils.dice import DiceResult, calculate_modifier, roll_dice

# ---------------------------------------------------------------------------
# roll_dice
# ---------------------------------------------------------------------------


class TestRollDice:
    def test_returns_dice_result_instance(self):
        result = roll_dice("1d6")
        assert isinstance(result, DiceResult)

    def test_single_die_in_range(self):
        for _ in range(20):
            result = roll_dice("1d6")
            assert 1 <= result.total <= 6

    def test_multiple_dice_in_range(self):
        for _ in range(20):
            result = roll_dice("3d6")
            assert 3 <= result.total <= 18

    def test_d20_shorthand(self):
        result = roll_dice("d20")
        assert 1 <= result.total <= 20
        assert len(result.rolls) == 1

    def test_positive_modifier_applied(self):
        for _ in range(20):
            result = roll_dice("1d6+3")
            assert 4 <= result.total <= 9

    def test_negative_modifier_applied(self):
        for _ in range(20):
            result = roll_dice("1d6-1")
            assert 0 <= result.total <= 5

    def test_expression_stored_normalised(self):
        result = roll_dice(" 2d8 ")
        assert result.expression == "2d8"

    def test_rolls_list_has_correct_count(self):
        result = roll_dice("4d6")
        assert len(result.rolls) == 4

    def test_rolls_are_in_per_die_range(self):
        result = roll_dice("5d10")
        assert all(1 <= r <= 10 for r in result.rolls)

    def test_to_dict_structure(self):
        result = roll_dice("2d4+1")
        d = result.to_dict()
        assert set(d.keys()) == {"total", "rolls", "kept_rolls", "expression"}
        assert isinstance(d["total"], int)
        assert isinstance(d["rolls"], list)
        assert isinstance(d["kept_rolls"], list)
        assert isinstance(d["expression"], str)

    def test_case_insensitive(self):
        result = roll_dice("1D6")
        assert 1 <= result.total <= 6

    def test_invalid_expression_raises_value_error(self):
        with pytest.raises(ValueError, match="Unrecognised"):
            roll_dice("notadice")

    def test_zero_amount_raises_value_error(self):
        with pytest.raises(ValueError):
            roll_dice("0d6")

    def test_one_sided_die_raises_value_error(self):
        with pytest.raises(ValueError):
            roll_dice("1d1")

    def test_spaces_in_expression_accepted(self):
        result = roll_dice("  1d20+5  ")
        assert 6 <= result.total <= 25


# ---------------------------------------------------------------------------
# calculate_modifier
# ---------------------------------------------------------------------------


class TestCalculateModifier:
    def test_dnd_ability_modifier_16(self):
        assert calculate_modifier(16, "(VALUE - 10) // 2") == 3

    def test_dnd_ability_modifier_10(self):
        assert calculate_modifier(10, "(VALUE - 10) // 2") == 0

    def test_dnd_ability_modifier_8(self):
        assert calculate_modifier(8, "(VALUE - 10) // 2") == -1

    def test_identity_formula(self):
        assert calculate_modifier(7, "VALUE") == 7

    def test_constant_formula(self):
        assert calculate_modifier(99, "5") == 5

    def test_abs_builtin_allowed(self):
        assert calculate_modifier(-3, "abs(VALUE)") == 3

    def test_min_max_builtins_allowed(self):
        assert calculate_modifier(15, "min(VALUE, 10)") == 10
        assert calculate_modifier(5, "max(VALUE, 10)") == 10

    def test_floor_builtin_allowed(self):
        assert calculate_modifier(7, "floor(VALUE / 2)") == 3

    def test_ceil_builtin_allowed(self):
        assert calculate_modifier(7, "ceil(VALUE / 2)") == 4

    def test_float_result_floored(self):
        assert calculate_modifier(3, "VALUE / 2") == 1

    def test_blocked_import_returns_zero(self):
        assert calculate_modifier(1, "import os") == 0

    def test_blocked_dunder_returns_zero(self):
        assert calculate_modifier(1, "__import__('os')") == 0

    def test_blocked_exec_returns_zero(self):
        assert calculate_modifier(1, "exec('x=1')") == 0

    def test_blocked_eval_returns_zero(self):
        assert calculate_modifier(1, "eval('1+1')") == 0

    def test_blocked_open_returns_zero(self):
        assert calculate_modifier(1, "open('/etc/passwd')") == 0

    def test_blocked_os_returns_zero(self):
        assert calculate_modifier(1, "os.getcwd()") == 0

    def test_blocked_sys_returns_zero(self):
        assert calculate_modifier(1, "sys.exit()") == 0

    def test_syntax_error_returns_zero(self):
        assert calculate_modifier(1, "VALUE +++") == 0

    def test_division_by_zero_returns_zero(self):
        assert calculate_modifier(0, "10 // VALUE") == 0
