"""Contract tests for the additive `ws.phase` events (UI-2).

These tests assert:
  * phase events precede `start` (so the frontend can render "thinking"
    copy during the dead-air-before-stream gap)
  * the turn still completes if a phase emit fails (back-compat)
  * unknown phase values from older clients are tolerated by the
    frontend reducer (covered in `use-turn-machine.test.ts`)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from monitor_ui.routers.chat_ws import fanout_completed_gm_message


def _gm_msg(content: str = "Hello world.") -> dict:
    return {
        "id": "msg-abc",
        "role": "gm",
        "content": content,
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_phase_events_precede_start():
    """Phase events must arrive before `start` so the UI can show 'thinking' copy."""
    captured: list[dict] = []

    async def fake_fanout(session_id, payload, *, exclude=None, publish=True):
        captured.append(payload)

    with patch("monitor_ui.routers.chat_ws.fanout_event", side_effect=fake_fanout):
        await fanout_completed_gm_message("sess-1", _gm_msg())

    types = [p.get("type") for p in captured]
    assert types[0] == "phase"
    assert types[1] == "phase"
    # Both phase events must come before start
    assert "start" in types
    assert types.index("start") > 1
    # Token + done still follow
    assert "token" in types
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_phase_events_carry_message_id():
    """Each phase event references the upcoming message so the frontend
    can correlate (or drop, if it turns out the message is a stale one)."""
    captured: list[dict] = []

    async def fake_fanout(session_id, payload, *, exclude=None, publish=True):
        captured.append(payload)

    with patch("monitor_ui.routers.chat_ws.fanout_event", side_effect=fake_fanout):
        await fanout_completed_gm_message("sess-1", _gm_msg())

    phase_events = [p for p in captured if p.get("type") == "phase"]
    assert phase_events, "expected at least one phase event"
    for ev in phase_events:
        assert ev["message_id"] == "msg-abc"


@pytest.mark.asyncio
async def test_turn_completes_if_phase_emit_fails():
    """If a phase emit raises, the turn still streams start/token/done.
    This is the back-compat guarantee — old clients ignore phases."""
    call_count = {"n": 0}

    async def flaky_fanout(session_id, payload, *, exclude=None, publish=True):
        call_count["n"] += 1
        if payload.get("type") == "phase":
            raise RuntimeError("simulated emit failure")
        # pass-through for non-phase events

    with patch("monitor_ui.routers.chat_ws.fanout_event", side_effect=flaky_fanout):
        # Must not raise
        await fanout_completed_gm_message("sess-1", _gm_msg())

    # At least one non-phase event still fired (start or token or done)
    assert call_count["n"] >= 4  # 2 phases + start + token + done


@pytest.mark.asyncio
async def test_known_phase_values_are_well_formed():
    """Phase values match the frontend's known set (see
    `use-turn-machine.ts:phase-mapping`); unknown values fall through
    to 'Thinking…' copy."""
    known = {"assembling_context", "narrating"}

    captured: list[dict] = []

    async def fake_fanout(session_id, payload, *, exclude=None, publish=True):
        captured.append(payload)

    with patch("monitor_ui.routers.chat_ws.fanout_event", side_effect=fake_fanout):
        await fanout_completed_gm_message("sess-1", _gm_msg())

    phases = [p["phase"] for p in captured if p.get("type") == "phase"]
    assert phases, "expected phase events"
    for phase in phases:
        assert phase in known, f"unknown phase emitted: {phase}"