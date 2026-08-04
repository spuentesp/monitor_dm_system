"""Tests for the raw recent-chat tail (RECENT TABLE CONVERSATION channel)."""

from __future__ import annotations

from typing import Any

from monitor_agents.loops.scene_loop import _chat_tail
from monitor_agents.narrator.agent import _recent_chat_block


def _msg(role: str, content: str, mode: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": role, "content": content}
    if mode:
        msg["metadata"] = {"chat_mode": mode}
    return msg


def test_chat_tail_takes_last_six_and_labels_mode() -> None:
    log = [_msg("player", f"m{i}") for i in range(8)]
    log[7] = _msg("player", "ooc note", "ooc")
    tail = _chat_tail(log)
    assert len(tail) == 6
    assert tail[0]["content"] == "m2"
    assert tail[-1] == {"role": "player", "mode": "ooc", "content": "ooc note"}
    assert tail[0]["mode"] == "ic"


def test_chat_tail_handles_junk() -> None:
    assert _chat_tail(None) == []
    assert _chat_tail([{"role": "player"}, "junk", {"content": ""}]) == []


def test_recent_chat_block_renders_and_caps_tokens() -> None:
    # 10 short lines (~6-8 tokens each) and a tight budget — only the
    # most-recent few should fit, and the block must include the header
    # and a labeled line.
    tail = [{"role": "gm", "mode": "ic", "content": "short line"} for _ in range(10)]
    full = "[IC] gm: " + "short line" * 100  # baseline of "no truncation"
    block = _recent_chat_block(tail, max_tokens=20)
    assert "RECENT TABLE CONVERSATION" in block
    assert "[IC] gm:" in block
    assert len(block) < len(full) + 100  # meaningfully smaller than unbounded


def test_recent_chat_block_empty_is_silent() -> None:
    assert _recent_chat_block([]) == ""
    assert _recent_chat_block(None) == ""
