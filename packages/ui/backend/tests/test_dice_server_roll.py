"""Server-authoritative dice rolling (tap-to-roll roll model).

The default roll model has the SERVER generate the dice, not the browser.
These tests lock that the roll originates server-side, is graded against the
pending check, and that the manual/marker guards behave correctly.
"""

from __future__ import annotations

import pytest


from unittest.mock import patch

from monitor_agents.loops.scene_orchestrator_support import (
    _ROLL_REQUEST_MARKER,
    _manual_roll_rejection,
    _resolved_roll_from_pending,
    _server_roll_from_pending,
)

pytestmark = pytest.mark.usefixtures("local_auth_mode")

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


def _manual_session(**over):
    return {"roll_model": "manual", "pending_dice_request": _pending(**over)}


def _result(spec: str, dice: str, total: int) -> str:
    return f"[DICE RESULT] FIN check: rolled {spec}{dice} = {total}. Continue."


def test_manual_roll_at_the_limits_of_the_spec_is_accepted():
    for dice, total in ((" [1]", 3), (" [20]", 22), ("", 3), ("", 22)):
        assert _manual_roll_rejection(_manual_session(), _result("1d20+2", dice, total)) is None


def test_manual_roll_outside_the_spec_is_rejected():
    for total in (2, 23, 999):
        assert _manual_roll_rejection(_manual_session(), _result("1d20+2", "", total))


def test_manual_roll_with_inconsistent_dice_is_rejected():
    for dice, total in ((" [21]", 22), (" [5]", 20), (" [5, 6]", 13), (" [0]", 2)):
        assert _manual_roll_rejection(_manual_session(), _result("1d20+2", dice, total))


def test_claimed_spec_cannot_widen_the_range():
    session = _manual_session()
    content = _result("1d20+50", "", 60)
    assert _manual_roll_rejection(session, content)
    assert _resolved_roll_from_pending(session, content) is None


def test_typed_roll_needs_the_manual_roll_model():
    content = _result("1d20+2", " [10]", 12)
    for roll_model in ("tap", "gm", None):
        session = {"roll_model": roll_model, "pending_dice_request": _pending()}
        assert _manual_roll_rejection(session, content)
        assert _resolved_roll_from_pending(session, content) is None


def test_guard_ignores_ordinary_prose_and_rejects_unsolicited_roll_markers():
    assert _manual_roll_rejection({"roll_model": "tap"}, "I keep working the panel") is None
    assert _manual_roll_rejection(_manual_session(), "I keep working the panel") is None
    assert _manual_roll_rejection({"roll_model": "tap"}, _result("1d20", "", 10))
    assert _manual_roll_rejection({"roll_model": "manual"}, _result("1d20", "", 10))
    assert _manual_roll_rejection({"roll_model": "tap"}, f"{_ROLL_REQUEST_MARKER} roll 1d20")


def test_manual_natural_uses_the_spec_modifier_for_roll_under():
    session = _manual_session(spec="1d20", modifier=3, difficulty_class=10, roll_under=True)
    resolved = _resolved_roll_from_pending(session, _result("1d20", "", 12))
    assert resolved is not None
    # natural 12 <= target 13 (DC 10 + 3); subtracting the modifier would misread it as 9.
    assert "1d20(12)" in resolved[1]["roll_breakdown"]
    assert resolved[1]["roll_detail"]["spec"] == "1d20"


def test_server_roll_advantage_and_disadvantage_keep_expected_die():
    adv_session = {
        "scene_id": "s1",
        "pending_dice_request": _pending(spec="2d20kh1+2", modifier=2, difficulty_class=18, roll_mode="advantage"),
    }
    seq = iter([4, 17])
    with patch("monitor_data.utils.dice.random.randint", side_effect=lambda _a, _b: next(seq)):
        out = _server_roll_from_pending(adv_session, f"{_ROLL_REQUEST_MARKER} roll")
    assert out is not None
    _, res = out
    assert res["roll_detail"]["rolls"] == [4, 17]
    assert res["roll_detail"]["kept_rolls"] == [17]
    assert res["roll_total"] == 19
    assert res["success_level"] == "success"
    assert "2d20kh1(17) + 2 = 19" in res["roll_breakdown"]

    dis_session = {
        "scene_id": "s1",
        "pending_dice_request": _pending(spec="2d20kl1-1", modifier=-1, difficulty_class=10, roll_mode="disadvantage"),
    }
    seq2 = iter([18, 5])
    with patch("monitor_data.utils.dice.random.randint", side_effect=lambda _a, _b: next(seq2)):
        out2 = _server_roll_from_pending(dis_session, f"{_ROLL_REQUEST_MARKER} roll")
    assert out2 is not None
    _, res2 = out2
    assert res2["roll_detail"]["kept_rolls"] == [5]
    assert res2["roll_total"] == 4
    assert res2["success_level"] == "failure"


def test_server_and_manual_roll_support_dice_pool_systems():
    pool_pending = _pending(
        spec="4d10",
        modifier=0,
        difficulty_class=6,
        mechanic_type="dice_pool",
        pool_size=4,
        pool_die_sides=10,
        success_threshold=7,
    )
    session = {"scene_id": "s1", "pending_dice_request": pool_pending}
    seq = iter([8, 3, 7, 10])
    with patch("monitor_data.utils.dice.random.randint", side_effect=lambda _a, _b: next(seq)):
        out = _server_roll_from_pending(session, f"{_ROLL_REQUEST_MARKER} roll pool")
    assert out is not None
    _, res = out
    assert res["roll_type"] == "pool"
    assert res["roll_total"] == 3
    assert res["success"] is True
    assert "3 successes (diff 7)" in res["roll_breakdown"]

    manual_pool = {"roll_model": "manual", "pending_dice_request": pool_pending}
    assert _manual_roll_rejection(manual_pool, _result("4d10", " [8, 3, 7, 10]", 3)) is None
    assert _manual_roll_rejection(manual_pool, _result("4d10", " [8, 3, 7, 10]", 4))
    resolved_manual = _resolved_roll_from_pending(manual_pool, _result("4d10", " [1, 2, 3, 4]", 0))
    assert resolved_manual is not None
    assert resolved_manual[1]["success_level"] == "critical_failure"
