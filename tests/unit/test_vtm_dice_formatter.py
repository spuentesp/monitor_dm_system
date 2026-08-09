"""Tests for the VtM session shared helpers -- specifically the dice highlight formatter."""

from __future__ import annotations

import pytest

from scripts._shared_vtm import format_dice_highlight, utc_timestamp


class TestFormatDiceHighlight:
    def test_empty_result_returns_empty_string(self) -> None:
        assert format_dice_highlight("I attack", None) == ""
        assert format_dice_highlight("I attack", {}) == ""

    def test_vtm_dice_pool_successes(self) -> None:
        result = {"pool_size": 5, "successes": 3, "botches": 0, "results": [6, 7, 5, 2, 1]}
        out = format_dice_highlight("I leap the fence", result)
        assert "I leap the fence" in out
        assert "5 dice" in out
        assert "3 successes" in out
        assert "0 botches" in out

    def test_vtm_dice_pool_botch(self) -> None:
        result = {"pool_size": 4, "successes": 0, "botches": 2, "results": [1, 1, 5, 3]}
        out = format_dice_highlight("I stalk the alley", result)
        assert "0 successes" in out
        assert "2 botches" in out

    def test_falls_back_to_unknown_keys(self) -> None:
        result = {"pool_size": 2, "successes": 1, "botches": 0}
        out = format_dice_highlight("I check", result)
        assert "2 dice" in out
        assert "1 successes" in out


class TestUtcTimestamp:
    def test_returns_filesafe_string(self) -> None:
        ts = utc_timestamp()
        assert len(ts) == 16  # YYYYMMDDTHHMMSSZ
        assert ts.endswith("Z")
        assert "T" in ts