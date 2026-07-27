"""Hermetic coverage for the full-loop harness.

These tests don't hit a real model. They exercise:
  * the scenarios module loads + scripted pairs are well-formed
  * the InstructablePlayer + MockSpec produce a deterministic (player, GM)
    interaction shape that bootstrap_session can build on

Live verification (real Ollama) is gated separately by the user's
manual recipe in docs/testing/HARNESS_FULL_LOOP.md — hermetic CI cannot
prove the loop completes with a real model.
"""

from __future__ import annotations

import pytest
from monitor_agents.players import (
    InstructablePlayer,
    MockSpec,
    PlayerContext,
    ScriptedSpec,
    coherence_count,
)

from scripts.e2e_full_loop_scenarios import (
    DIS_SCENARIOS,
    SCENARIOS,
    SYSTEM_ID_BY_WORLD,
    VTM_SCENARIOS,
    scripted_pairs,
)

# ============================================================================
# Scenarios — single source of truth for both run + test
# ============================================================================


def test_scenarios_load_and_resolve_system_ids() -> None:
    assert len(VTM_SCENARIOS) >= 2
    assert len(DIS_SCENARIOS) >= 2
    for s in VTM_SCENARIOS + DIS_SCENARIOS:
        assert s.name in SCENARIOS
        assert s.world_id in SYSTEM_ID_BY_WORLD
        assert scripted_pairs(s) == [
            (t.player_action, t.intent) for t in s.scripted_opens
        ]


def test_dis_salvage_seed_mentions_oxygen() -> None:
    s = SCENARIOS["dis_salvage"]
    assert "Ozymandias" in s.seed


# ============================================================================
# MockSpec — what --mock-llm uses in the harness
# ============================================================================


@pytest.mark.asyncio
async def test_mock_player_serves_scripted_lines_then_falls_back() -> None:
    player = InstructablePlayer(
        spec=MockSpec(
            lines=[("I look around.", "observe"), ("I take stock.", "reflection")],
        ),
        context=PlayerContext(concept="Rook", seed="Ozymandias"),
    )
    a1, i1 = await player.next()
    assert a1 == "I look around."
    a2, _ = await player.next()
    assert a2 == "I take stock."
    a3, i3 = await player.next()
    # MockSpec returns its fallback when the list is exhausted.
    assert a3 == "I take stock of the situation."
    assert i3 == "fallback mock"


@pytest.mark.asyncio
async def test_observe_keeps_buffer_bounded() -> None:
    player = InstructablePlayer(
        spec=MockSpec(lines=[("a", "x")]),
        context=PlayerContext(concept="x", seed=""),
        recent_turns_max=3,
    )
    for i in range(50):
        player.observe(gm_text=f"gm {i}", player_text=f"pl {i}", intent="x")
    assert len(player._recent_turns) <= 6  # 2 * recent_turns_max


# ============================================================================
# Shape integration smoke (no LLM, no DB) — proves the data shape pieces
# fit together the way the harness wires them.
# ============================================================================


def test_player_source_label_uses_spec_class_name() -> None:
    from scripts.e2e_full_loop import player_source_label

    p_scripted = InstructablePlayer(
        spec=ScriptedSpec(arc=[]),
        context=PlayerContext(concept="x", seed=""),
    )
    p_mock = InstructablePlayer(
        spec=MockSpec(lines=[]),
        context=PlayerContext(concept="x", seed=""),
    )
    assert player_source_label(p_scripted) == "scripted"
    assert player_source_label(p_mock) == "mock"


def test_coherence_overlap_for_unrelated_texts() -> None:
    assert coherence_count("the smith stands alone", "pirate treasure hidden cave") == 0
