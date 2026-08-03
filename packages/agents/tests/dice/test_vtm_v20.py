"""Tests for the VtM V20 dice engine (sub-plan 4)."""
from __future__ import annotations

import random

import pytest

from monitor_agents.dice import (
    VtMContestedCheck,
    vt_contested_pool,
    vt_rouse_check,
    vt_willpower_reroll,
)
from monitor_agents.dice.vtm_v20 import VtMV20Engine


class TestVtMContestedCheck:
    """Core mechanic: roll N d10s, count successes >= difficulty."""

    def test_engine_name(self):
        assert VtMV20Engine().name == "vtm_v20"

    def test_all_successes_when_difficulty_one(self):
        """Difficulty 1 is trivial — every die is a success."""
        rolls_iter = iter([1] * 5)
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            res = vt_contested_pool(pool_size=5, difficulty=1)
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert res.successes == 5
        assert res.botches == 5  # all dice showed 1
        assert res.passed

    def test_no_successes_when_difficulty_eleven(self):
        """Difficulty 11 is impossible — zero successes on any die."""
        rolls_iter = iter([10] * 5)
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            res = vt_contested_pool(pool_size=5, difficulty=11)
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert res.successes == 0

    def test_botch_detected_with_no_successes(self):
        """Zero successes + any 1s = botch (VtM rule)."""
        # All dice below DC 6, with 3 botches (1s).
        rolls = [1, 1, 1, 4, 5]
        rolls_iter = iter(rolls)
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            res = vt_contested_pool(pool_size=5, difficulty=6)
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert res.successes == 0
        assert res.botches == 3
        assert not res.passed

    def test_hunger_dice_flag_messy_critical(self):
        """Hunger + ≥1 success + botches = messy critical (V5)."""
        rolls = [1, 1, 3, 4, 7]
        rolls_iter = iter(rolls)
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            res = vt_contested_pool(
                pool_size=5, difficulty=6, hunger=2,
            )
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert res.successes == 1
        assert res.botches == 2
        assert res.messy_critical
        assert not res.bestial_failure

    def test_hunger_zero_successes_bestial_failure(self):
        """Hunger + 0 successes = bestial failure."""
        rolls = [1, 1, 3, 4, 5]
        rolls_iter = iter(rolls)
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            res = vt_contested_pool(
                pool_size=5, difficulty=6, hunger=2,
            )
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert res.successes == 0
        assert res.bestial_failure

    def test_willpower_reroll_improves_zero_success_roll(self):
        """WP reroll: 0-success roll is rerolled and a 6 succeeds."""
        # First roll: all failures at DC 6. Second roll (after WP
        # reroll): all 6s succeed.
        rolls_iter = iter([2, 3, 4, 5, 5, 6, 6, 6, 6, 6])
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            res = vt_contested_pool(
                pool_size=5, difficulty=6, use_willpower=True,
            )
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert res.willpower_spent == 1
        assert res.successes == 5
        assert res.passed

    def test_willpower_not_spent_when_already_succeeding(self):
        """If the roll already has successes, no WP reroll is triggered."""
        rolls = [6, 6, 6, 3, 2]
        rolls_iter = iter(rolls)
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            res = vt_contested_pool(
                pool_size=5, difficulty=6, use_willpower=True,
            )
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert res.willpower_spent == 0
        assert res.successes == 3

    def test_hunger_capped_to_pool(self):
        """Hunger > pool is capped at pool size."""
        rolls = [7, 7, 7]
        rolls_iter = iter(rolls)
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            res = vt_contested_pool(
                pool_size=3, difficulty=6, hunger=10,
            )
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert res.hunger_dice == 3  # capped to pool


class TestVtMRouseCheck:
    """V5 rouse check: 1d10, 1+ = no Hunger. Never fails on 1d10."""

    def test_rouse_returns_success(self):
        res = vt_rouse_check()
        assert res["engine"] == "vtm_v20"
        assert res["roll_type"] == "rouse_check"
        assert res["success"] is True
        assert 1 <= res["roll"] <= 10

    def test_rouse_roll_in_range(self):
        for _ in range(50):
            res = vt_rouse_check()
            assert 1 <= res["roll"] <= 10


class TestVtMWillpowerReroll:
    """Standalone reroll helper."""

    def test_reroll_only_failed_dice(self):
        rolls = [8, 8, 3, 2]
        rolls_iter = iter([6, 6])
        random.randint = lambda a, b: next(rolls_iter)  # type: ignore[assignment]
        try:
            new = vt_willpower_reroll(rolls, difficulty=6)
        finally:
            random.randint = random._inst.randint  # type: ignore[attr-defined]
        assert new == [8, 8, 6, 6]

    def test_reroll_keeps_successful_dice(self):
        rolls = [9, 10, 7]
        new = vt_willpower_reroll(rolls, difficulty=6)
        assert new == [9, 10, 7]
