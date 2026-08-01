"""Foreshadowing agent + narrator block + SceneState plumbing."""

from __future__ import annotations

import uuid as _uuid

import pytest

from monitor_agents.narrator.agent import _foreshadowing_block
from monitor_agents.foreshadowing.agent import ForeshadowingAgent


def _open(summary: str, target_turn: int, planted_by_turn: int = 0, status: str = "open") -> dict:
    return {
        "foreshadowing_id": str(_uuid.uuid4()),
        "summary": summary,
        "target_turn": target_turn,
        "planted_by_turn": planted_by_turn,
        "status": status,
    }


def test_block_empty_when_no_items() -> None:
    assert _foreshadowing_block([], turns_count=5) == ""
    assert _foreshadowing_block(None, turns_count=5) == ""


def test_block_renders_items() -> None:
    items = [_open("a", 10), _open("b", 15)]
    block = _foreshadowing_block(items, turns_count=5, cap=5)
    assert "OPEN FORESHADOWING" in block
    assert "a" in block
    assert "b" in block
    assert "target turn 10" in block


def test_block_flags_overdue() -> None:
    items = [_open("overdue", 3)]
    block = _foreshadowing_block(items, turns_count=8)
    assert "overdue" in block
    assert "overdue — pay off soon" in block


def test_block_caps_items_and_chars() -> None:
    items = [_open("x" * 500, t) for t in range(8)]
    block = _foreshadowing_block(items, turns_count=0, cap=5, max_chars=80)
    assert block.count("- ") == 5
    assert "x" * 81 not in block


def test_block_skips_paid_items() -> None:
    items = [_open("paid", 5, status="paid"), _open("still open", 5)]
    block = _foreshadowing_block(items, turns_count=5)
    assert "still open" in block
    assert "paid" not in block


@pytest.mark.asyncio
async def test_agent_propose_returns_parsed_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke test: agent parses JSON outputs into a {plants, payoffs} dict."""
    import contextlib
    import dspy

    class _Stub(dspy.Module):
        def __init__(self) -> None:
            pass

        def __call__(self, **kwargs):  # type: ignore[no-untyped-def]
            return dspy.Prediction(
                plants='[{"summary":"a captain trembles","target_turn":12}]',
                payoffs="[]",
            )

    from monitor_agents.foreshadowing import agent as fs_agent_mod
    monkeypatch.setattr(fs_agent_mod, "dspy", dspy)
    # Avoid hitting the real DSPy runtime (network blocked in tests).
    monkeypatch.setattr(
        fs_agent_mod, "dspy_context_for",
        lambda *a, **k: contextlib.nullcontext(),
    )
    agent = ForeshadowingAgent()
    monkeypatch.setattr(agent, "_module", _Stub(), raising=False)
    out = await agent.propose(
        scene_id=_uuid.uuid4(),
        story_id=_uuid.uuid4(),
        narrative_text="The captain looked on.",
        entities=[{"name": "Captain", "id": str(_uuid.uuid4())}],
        player_action="wave at the captain",
    )
    assert len(out["plants"]) == 1
    assert out["plants"][0]["summary"] == "a captain trembles"
    assert out["plants"][0]["target_turn"] == 12
    assert out["payoffs"] == []