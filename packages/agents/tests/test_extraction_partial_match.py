"""Partial-match dedup for newly extracted entities."""

from __future__ import annotations

from monitor_agents.extraction.agent import _is_partial_match


def test_partial_match_substring() -> None:
    assert _is_partial_match("Vex", ["Captain Vex", "Old Tomas"])


def test_partial_match_first_word() -> None:
    assert _is_partial_match("the captain", ["Captain Vex"])


def test_no_match_when_distinct() -> None:
    assert not _is_partial_match("Tomas", ["Vex", "Mira"])


def test_case_insensitive() -> None:
    assert _is_partial_match("vex", ["Captain Vex"])


def test_short_known_name_does_not_match_unrelated() -> None:
    # Known "Old" is 3 chars — too short to risk a false positive.
    assert not _is_partial_match("Vex", ["Old", "Mira"])


def test_too_short_new_name_does_not_match() -> None:
    # "Xi" is 2 chars — too short to dedup on.
    assert not _is_partial_match("Xi", ["Captain Vex"])


def test_short_title_new_name_does_not_match_short_known() -> None:
    # Both are 3 chars — too risky to dedup.
    assert not _is_partial_match("Sir", ["Old Tomas"])


def test_empty_known_list_returns_false() -> None:
    assert not _is_partial_match("Vex", [])


def test_last_word_match() -> None:
    # "Vex" matches the last word of "Captain Vex".
    assert _is_partial_match("Vex", ["Captain Vex"])


def test_substring_both_directions() -> None:
    # "Vex" is a substring of "Captain Vex"; "Captain Vex" is a substring of
    # itself — either way, match.
    assert _is_partial_match("Vex", ["Captain Vex the Bold"])


def test_empty_inputs_return_false() -> None:
    assert not _is_partial_match("", ["Captain Vex"])
    assert not _is_partial_match("Vex", [""])
    assert not _is_partial_match("Vex", [None])  # type: ignore[list-item]
