"""Tests for the TABLE TALK narrator context block (read side)."""

from __future__ import annotations

from monitor_agents.narrator.agent import _table_talk_block
from monitor_agents.loops.scene_loop import SceneState


def _pairs(n: int) -> list[dict[str, str]]:
    return [{"question": f"q{i}", "answer": f"a{i}", "timestamp": "t"} for i in range(n)]


def test_table_talk_block_renders_pairs() -> None:
    block = _table_talk_block(_pairs(2))
    assert "TABLE TALK" in block
    assert "never reference this channel in fiction" in block
    assert "Q: q0\nA: a0\n" in block
    assert "Q: q1\nA: a1\n" in block


def test_table_talk_block_empty_is_silent() -> None:
    assert _table_talk_block([]) == ""
    assert _table_talk_block(None) == ""
    assert _table_talk_block("junk") == ""


def test_table_talk_block_caps_entries_and_chars() -> None:
    pairs = _pairs(12)
    pairs.append({"question": "x" * 500, "answer": "y" * 500, "timestamp": "t"})
    block = _table_talk_block(pairs)
    assert block.count("Q:") == 8  # cap
    assert "x" * 301 not in block  # 300-char truncation
    assert "q3" not in block  # oldest dropped


def test_scene_state_carries_ooc_exchanges() -> None:
    import uuid

    exchanges = _pairs(1)
    state = SceneState(
        scene_id=uuid.uuid4(),
        story_id=uuid.uuid4(),
        ooc_exchanges=exchanges,
    )
    assert state.ooc_exchanges == exchanges
