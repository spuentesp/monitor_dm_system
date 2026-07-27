"""
Tests for _split_narration_blocks (GM narration markup — OOC asides).

((double parentheses)) mark a fourth-wall-breaking OOC aside; everything
else is in-fiction narration/dialogue and renders unchanged (markdown
handles *action* italics natively, no split needed for that marker).
"""

from __future__ import annotations

from monitor_cli.commands.play import _split_narration_blocks


def test_plain_text_passthrough():
    assert _split_narration_blocks("You draw your rivet gun.") == [(False, "You draw your rivet gun.")]


def test_single_ooc_block():
    assert _split_narration_blocks("((No roll needed for that.))") == [(True, "No roll needed for that.")]


def test_mixed_narration_and_ooc():
    text = "You draw your rivet gun. ((This is a hard-mode encounter.))"
    assert _split_narration_blocks(text) == [
        (False, "You draw your rivet gun."),
        (True, "This is a hard-mode encounter."),
    ]


def test_ooc_then_narration():
    text = "((By the way, no dice here.)) You step into the corridor."
    assert _split_narration_blocks(text) == [
        (True, "By the way, no dice here."),
        (False, "You step into the corridor."),
    ]


def test_multiple_ooc_blocks():
    text = "((First note)) some prose ((second note))"
    assert _split_narration_blocks(text) == [
        (True, "First note"),
        (False, "some prose"),
        (True, "second note"),
    ]


def test_ooc_block_spanning_newlines():
    text = "((This is a longer\naside that spans\nmultiple lines.))"
    assert _split_narration_blocks(text) == [(True, "This is a longer\naside that spans\nmultiple lines.")]


def test_empty_string():
    assert _split_narration_blocks("") == []


def test_consecutive_ooc_blocks_no_gap():
    text = "((first))((second))"
    assert _split_narration_blocks(text) == [
        (True, "first"),
        (True, "second"),
    ]


def test_whitespace_only_segments_dropped():
    text = "((note))   \n   the rest"
    assert _split_narration_blocks(text) == [
        (True, "note"),
        (False, "the rest"),
    ]


def test_triple_parens_tolerated():
    """Models occasionally emit (((...))) instead of exactly ((...)) —
    caught live 2026-07-20 in a real GM response. 2+ parens on each side
    must still be recognized as one OOC block."""
    text = "((( The intent is sound, but roll your Tech for me next turn. )))"
    assert _split_narration_blocks(text) == [(True, "The intent is sound, but roll your Tech for me next turn.")]
