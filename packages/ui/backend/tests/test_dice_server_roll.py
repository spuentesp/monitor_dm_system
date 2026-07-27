"""Server-authoritative dice rolling (tap-to-roll roll model).

The default roll model has the SERVER generate the dice, not the browser.
These tests lock that the roll originates server-side, is graded against the
pending check, and that the manual/marker guards behave correctly.
"""

from __future__ import annotations

from unittest.mock import patch

from monitor_agents.loops.scene_orchestrator_support import (
    _ROLL_REQUEST_MARKER,
    _server_roll_from_pending,
)

_GRADED = {
    "critical_success",
    "success",
    "partial_success",
    "failure",
    "critical_failure",
}


def _pending(**over):
    base = {
        "spec": "1d20+2",
        "stat": "FIN",
        "difficulty_class": 10,
        "modifier": 2,
        "roll_under": False,
        "action_type": "action",
        "intent_type": "action",
        "reason": "FIN check",
        "original_action": "I hack the panel",
    }
    base.update(over)
    return base


def test_server_roll_is_authoritative_and_graded():
    session = {"scene_id": "s1", "pending_dice_request": _pending()}
    out = _server_roll_from_pending(session, f"{_ROLL_REQUEST_MARKER} FIN check: roll 1d20+2.")
    assert out is not None
    narrated, res = out
    assert res["resolution_type"] == "dice"
    assert res["success_level"] in _GRADED
    # The server generated a real d20 — the value lives in roll_detail.
    rolls = res["roll_detail"]["rolls"]
    assert rolls and 1 <= rolls[0] <= 20
    assert res["roll_total"] == res["roll_detail"]["total"]
    assert res["stat"] == "FIN"
    assert res["difficulty_class"] == 10
    # narrated_input is the original action the roll was for.
    assert narrated == "I hack the panel"


def test_server_roll_determinism_via_patched_rng():
    session = {
        "scene_id": "s1",
        "pending_dice_request": _pending(spec="1d20", modifier=0, difficulty_class=10),
    }
    with patch("monitor_data.utils.dice.random.randint", return_value=15):
        out = _server_roll_from_pending(session, f"{_ROLL_REQUEST_MARKER} roll")
    assert out is not None
    _, res = out
    assert res["roll_detail"]["rolls"] == [15]
    assert res["roll_total"] == 15
    assert res["success_level"] == "success"  # 15 >= DC 10


def test_server_roll_ignored_without_marker():
    session = {"pending_dice_request": _pending()}
    assert _server_roll_from_pending(session, "I keep working the panel") is None


def test_server_roll_ignored_without_pending():
    assert _server_roll_from_pending({}, f"{_ROLL_REQUEST_MARKER} roll") is None


def test_scene_loop_signature_tracks_roll_model():
    """Changing the roll model must invalidate the cached SceneLoop so the new
    roll_mode takes effect."""
    from monitor_ui.routers.chat_loops import scene_loop_signature

    base = {"play_mode": "dice_game_system"}
    sig_tap = scene_loop_signature({**base, "roll_model": "tap"}, scene_id="s", story_id="t")
    sig_gm = scene_loop_signature({**base, "roll_model": "gm"}, scene_id="s", story_id="t")
    assert sig_tap != sig_gm
