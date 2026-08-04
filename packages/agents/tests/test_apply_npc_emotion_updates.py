"""apply_npc_emotion_updates: diff-and-write for scene-mode NPC emotions."""

from __future__ import annotations

import uuid as _uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.narrator.agent import apply_npc_emotion_updates


class _FakeState:
    def __init__(
        self, npc_profiles: dict[str, Any], entity_context: list[dict[str, Any]], universe_id: str = "u1"
    ) -> None:
        self.npc_profiles = npc_profiles
        self.entity_context = entity_context
        self.universe_id = universe_id


def _profile(name: str, entity_id: str, *, current_emo: str = "neutral") -> dict[str, Any]:
    return {
        "name": name,
        "entity_id": entity_id,
        "current_emotional_state_by_universe": {"u1": current_emo},
    }


@pytest.mark.asyncio
async def test_empty_input_writes_nothing() -> None:
    state = _FakeState({}, [])
    with patch("monitor_data.tools.mongodb_tools.mongodb_update_npc_profile") as m:
        n = await apply_npc_emotion_updates(state, {})
    assert n == 0
    assert m.call_count == 0


@pytest.mark.asyncio
async def test_change_is_written() -> None:
    eid = str(_uuid.uuid4())
    state = _FakeState(
        npc_profiles={eid: _profile("Vex", eid, current_emo="wary")},
        entity_context=[{"id": eid, "name": "Vex"}],
    )
    with patch("monitor_data.tools.mongodb_tools.mongodb_update_npc_profile", new_callable=AsyncMock) as m:
        n = await apply_npc_emotion_updates(state, {"Vex": "resolute"})
    assert n == 1
    args, _ = m.call_args
    assert str(args[0]) == eid
    update = args[1]
    assert update.current_emotional_state == "resolute"
    assert update.current_emotional_state_by_universe == {"u1": "resolute"}


@pytest.mark.asyncio
async def test_same_value_skips_write() -> None:
    eid = str(_uuid.uuid4())
    state = _FakeState(
        npc_profiles={eid: _profile("Vex", eid, current_emo="wary")},
        entity_context=[{"id": eid, "name": "Vex"}],
    )
    with patch("monitor_data.tools.mongodb_tools.mongodb_update_npc_profile", new_callable=AsyncMock) as m:
        n = await apply_npc_emotion_updates(state, {"Vex": "wary"})
    assert n == 0
    assert m.call_count == 0


@pytest.mark.asyncio
async def test_unknown_name_is_silently_ignored() -> None:
    state = _FakeState({}, [])
    with patch("monitor_data.tools.mongodb_tools.mongodb_update_npc_profile", new_callable=AsyncMock) as m:
        n = await apply_npc_emotion_updates(state, {"Nobody": "happy"})
    assert n == 0
    assert m.call_count == 0


@pytest.mark.asyncio
async def test_write_failure_is_swallowed() -> None:
    eid = str(_uuid.uuid4())
    state = _FakeState(
        npc_profiles={eid: _profile("Vex", eid, current_emo="wary")},
        entity_context=[{"id": eid, "name": "Vex"}],
    )

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("db down")

    with patch("monitor_data.tools.mongodb_tools.mongodb_update_npc_profile", new=_boom):
        n = await apply_npc_emotion_updates(state, {"Vex": "resolute"})  # must not raise
    assert n == 0


@pytest.mark.asyncio
async def test_case_and_whitespace_insensitive_match() -> None:
    eid = str(_uuid.uuid4())
    state = _FakeState(
        npc_profiles={eid: _profile("Vex", eid, current_emo="wary")},
        entity_context=[{"id": eid, "name": "Vex"}],
    )
    with patch("monitor_data.tools.mongodb_tools.mongodb_update_npc_profile", new_callable=AsyncMock) as m:
        n = await apply_npc_emotion_updates(state, {"  vex  ": "resolute"})
    assert n == 1
    assert m.call_count == 1
