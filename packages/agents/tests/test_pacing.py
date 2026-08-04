"""Pacing derivation + narrator block."""

from __future__ import annotations

import pytest

from monitor_agents.narrator.agent import _pace_block, compute_pacing


@pytest.mark.parametrize(
    "turns,props,expected_tempo_range,expected_phase",
    [
        (0, 0, (0.35, 0.5), "setup"),
        (5, 1, (0.25, 0.35), "rising"),
        # t=15, p=1: tempo=0.4+0.6-0.3=0.7 → peak (>=0.7 AND p>=1)
        (15, 1, (0.65, 0.75), "peak"),
        # t=10, p=4: tempo=0.4+0.4-1.2=−0.4 → clamped 0.0 → falling (<=0.3 AND t>5)
        (10, 4, (0.0, 0.05), "falling"),
        (35, 0, (1.0, 1.0), "coda"),
    ],
)
def test_compute_pacing_matrix(turns, props, expected_tempo_range, expected_phase) -> None:
    out = compute_pacing(turns_count=turns, recent_proposal_count=props)
    assert expected_tempo_range[0] <= out["tempo"] <= expected_tempo_range[1]
    assert out["phase"] == expected_phase


def test_pace_block_renders_when_non_default() -> None:
    assert "PACE: tempo=0.62 phase=peak" in _pace_block({"tempo": 0.62, "phase": "peak"})


def test_pace_block_silent_when_default() -> None:
    assert _pace_block({"tempo": 0.5, "phase": "setup"}) == ""
    assert _pace_block(None) == ""
    assert _pace_block("junk") == ""


def test_pace_block_caps_tempo() -> None:
    # Even with crazy values, we render exactly one line.
    assert _pace_block({"tempo": 5.0, "phase": "peak"}).count("\n\nPACE") == 1
