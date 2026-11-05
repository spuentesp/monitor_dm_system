"""Live state in a light-RP conversation: real ConversationLoop and NPCVoice logic,
with storage and the LLM stubbed."""

from __future__ import annotations

import asyncio
import time
import types
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_agents.loops import conversation_loop as cl
from monitor_agents.npc_voice import agent as npc_mod

NPC, UNIVERSE, PLAYER = uuid4(), uuid4(), uuid4()


class _Store:
    def __init__(self) -> None:
        self.prompts: list[dict[str, Any]] = []
        self.profile_updates: list[dict[str, Any]] = []
        self.deltas = ["trust:+0.1"] * 10
        self.emotions = ["warm", "wary", "calm", "calm", "calm"]
        self.llm_seconds = 0.0

    async def call_tool(self, _agent: Any, name: str, args: dict[str, Any]) -> Any:
        if name == "mongodb_create_conversation":
            return {"conversation_id": str(uuid4())}
        if name == "neo4j_get_entity":
            return {"name": "Mira", "properties": {"role": "innkeeper"}}
        if name == "mongodb_get_npc_profile":
            return {"current_emotional_state": "neutral", "traits": {}, "triggers": []}
        if name == "neo4j_list_facts":
            return []
        if name == "qdrant_search_memories":
            return {"results": []}
        if name == "mongodb_update_npc_profile":
            self.profile_updates.append(args["params"])
        return {}

    def predict(self, **kwargs: Any) -> Any:
        time.sleep(self.llm_seconds)
        self.prompts.append(kwargs)
        turn = len(self.prompts) - 1
        return types.SimpleNamespace(
            npc_response=f"reply {turn}",
            emotional_state_after=self.emotions[turn],
            relationship_delta=self.deltas[turn],
        )


@pytest.fixture
async def chat():
    store = _Store()

    async def call_tool(agent: Any, name: str, args: dict[str, Any]) -> Any:
        return await store.call_tool(agent, name, args)

    with (
        patch.object(npc_mod.NPCVoice, "call_tool", call_tool),
        patch.object(npc_mod, "NPCDirectVoiceModule", lambda: store.predict),
        patch("monitor_agents.context_assembly.agent.ContextAssembly._fetch_runtime_profile", return_value={}, create=True),
    ):
        loop = await cl.ConversationLoop.start(
            universe_id=UNIVERSE, mode=cl.ConversationMode.DIRECT, npc_ids=[NPC], player_entity_id=PLAYER
        )
        yield loop, store


@pytest.mark.asyncio
async def test_llm_call_does_not_block_the_event_loop(chat: Any) -> None:
    loop, store = chat
    store.llm_seconds = 0.3
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    await loop.step("Hello")
    task.cancel()

    assert ticks >= 10


@pytest.mark.asyncio
async def test_relationship_builds_across_turns(chat: Any) -> None:
    loop, store = chat
    for line in ("one", "two", "three"):
        await loop.step(line)

    states = [u["relationship_states"][str(PLAYER)] for u in store.profile_updates]
    assert [s["trust"] for s in states] == [0.1, 0.2, 0.3]
    assert [s["familiarity"] for s in states] == [0.05, 0.1, 0.15]
    by_universe = store.profile_updates[-1]["relationship_states_by_universe"][str(UNIVERSE)][str(PLAYER)]
    assert by_universe["trust"] == 0.3


@pytest.mark.asyncio
async def test_prompt_sees_the_latest_emotion_and_stance(chat: Any) -> None:
    loop, store = chat
    for line in ("one", "two", "three"):
        await loop.step(line)

    assert [p["current_emotional_state"].split(";")[0] for p in store.prompts] == ["neutral", "warm", "wary"]
    assert "trust +0.20" in store.prompts[2]["personality_summary"]


@pytest.mark.asyncio
async def test_unchanged_emotion_stops_producing_proposals(chat: Any) -> None:
    loop, store = chat
    store.emotions = ["calm", "calm", "calm"]
    store.deltas = ["none"] * 3
    for line in ("one", "two", "three"):
        await loop.step(line)

    assert sum(p["change_type"] == "state_change" for p in loop.state.pending_proposals) == 1


@pytest.mark.asyncio
async def test_history_excludes_the_line_being_answered(chat: Any) -> None:
    loop, store = chat
    await loop.step("Hello")
    await loop.step("Who are you?")

    assert store.prompts[0]["conversation_history"] == "(no prior turns)"
    assert store.prompts[1]["conversation_history"].splitlines() == ["player: Hello", "Mira: reply 0"]
    assert store.prompts[1]["player_said"] == "Who are you?"


@pytest.mark.asyncio
async def test_lorebook_scan_does_not_count_the_current_line_as_history() -> None:
    state = cl.ConversationState(
        conversation_id=uuid4(),
        universe_id=UNIVERSE,
        mode=cl.ConversationMode.DIRECT,
        npc_ids=[],
        lorebook_character_ids=["card"],
        current_player_input="Now",
        turns=[{"text": "Earlier"}, {"text": "Now", "speaker_role": "player"}],
    )
    calls: dict[str, Any] = {}

    async def call_tool(_agent: Any, name: str, args: dict[str, Any]) -> Any:
        calls[name] = args
        return {}

    with patch.object(npc_mod.NPCVoice, "call_tool", call_tool):
        await cl.generate_npc_responses(state)

    assert calls["mongodb_scan_lorebook"]["history"] == ["Earlier"]


@pytest.mark.parametrize(
    ("delta", "trust", "affinity", "fear"),
    [
        ("hostility:+0.2", 0.3, -0.1, 0.05),
        ("hostility:-0.2", 0.7, 0.1, -0.05),
    ],
)
def test_hostile_axes_respect_the_delta_sign(delta: str, trust: float, affinity: float, fear: float) -> None:
    voice = npc_mod.NPCVoice.__new__(npc_mod.NPCVoice)
    profile = {"relationship_states": {str(PLAYER): {"trust": 0.5}}}
    snapshot = voice._build_relationship_snapshot(profile, PLAYER, delta, "calm")
    assert (snapshot["trust"], snapshot["affinity"], snapshot["fear"]) == (trust, affinity, fear)


def test_easing_hostility_is_not_a_hostile_relationship() -> None:
    voice = npc_mod.NPCVoice.__new__(npc_mod.NPCVoice)
    profile = {"relationship_states": {str(PLAYER): {"trust": 0.5}}}
    proposals = voice._build_proposals(NPC, "hostility:-0.2", "calm", profile, PLAYER)
    relationship = next(p for p in proposals if p["change_type"] == "relationship")
    assert relationship["content"]["rel_type"] != "HOSTILE_TO"
