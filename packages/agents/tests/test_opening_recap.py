"""Opening recap (LAST SCENE block + SceneState)."""

from __future__ import annotations

import uuid as _uuid


from monitor_agents.narrator.agent import _opening_recap_block
from monitor_agents.loops.scene_loop import SceneState


def test_block_empty_when_blank() -> None:
    assert _opening_recap_block("") == ""
    assert _opening_recap_block(None) == ""


def test_block_renders_single_line() -> None:
    out = _opening_recap_block("The captain revealed the map to the drowned coast.")
    assert "LAST SCENE" in out
    assert "drowned coast" in out


def test_block_truncates_long_text() -> None:
    long_text = "x" * 500
    out = _opening_recap_block(long_text, max_chars=80)
    assert "x" * 81 not in out


def test_block_normalizes_whitespace() -> None:
    out = _opening_recap_block("line one\nline two\nline three")
    assert "line one" in out
    assert "\n" not in out.replace("\n\nLAST SCENE", "")


def test_scene_state_carries_opening_recap() -> None:
    state = SceneState(scene_id=_uuid.uuid4(), story_id=_uuid.uuid4())
    state.opening_recap = "The captain trembled."
    assert state.opening_recap == "The captain trembled."