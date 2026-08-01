"""NPC STATE narrator block + SceneState plumbing."""

from __future__ import annotations

import uuid as _uuid
from typing import Any

import pytest

from monitor_agents.narrator.agent import _npc_state_block
from monitor_agents.loops.scene_loop import SceneState


def _profile(name: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "entity_id": str(_uuid.uuid4()),
        "name": name,
        "values": [],
        "fears": [],
        "desires": [],
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "speech_style": None,
        "current_emotional_state": "neutral",
        "current_emotional_state_by_universe": {},
        "relationship_states": {},
        "relationship_states_by_universe": {},
    }
    base.update(overrides)
    return base


def test_block_empty_when_no_profiles() -> None:
    assert _npc_state_block({}, universe_id="u1", player_id="p1") == ""
    assert _npc_state_block(None, universe_id="u1", player_id="p1") == ""
    assert _npc_state_block("junk", universe_id="u1", player_id="p1") == ""


def test_block_renders_emotion_and_relationship() -> None:
    prof = _profile(
        "Vex",
        current_emotional_state_by_universe={"u1": "wary"},
        relationship_states_by_universe={
            "u1": {"p1": {"disposition": "grudging_respect", "score": 0.4}}
        },
        speech_style="clipped, marine slang",
    )
    block = _npc_state_block({"eid": prof}, universe_id="u1", player_id="p1")
    assert "NPC STATE" in block
    assert "Vex" in block
    assert "wary" in block
    assert "grudging_respect" in block
    assert "clipped, marine slang" in block


def test_block_caps_characters_and_npcs() -> None:
    profiles = {
        f"e{i}": _profile(f"NPC {i}", current_emotional_state_by_universe={"u1": "angry" * 200})
        for i in range(8)
    }
    block = _npc_state_block(profiles, universe_id="u1", player_id="p1", cap=4, max_chars=80)
    assert block.count("- NPC") == 4  # cap
    assert "angry" * 81 not in block  # char cap


def test_block_silent_when_emotion_and_relationship_absent() -> None:
    prof = _profile("Quiet")  # no state at all
    assert _npc_state_block({"e": prof}, universe_id="u1", player_id="p1") == ""


def test_scene_state_carries_npc_profiles() -> None:
    state = SceneState(scene_id=_uuid.uuid4(), story_id=_uuid.uuid4())
    state.npc_profiles = {"eid": _profile("Vex")}
    assert "eid" in state.npc_profiles