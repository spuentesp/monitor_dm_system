"""NPC scene enrichment: recall, known facts, intents (Phase 4 Tasks 7-9).

Cross-component wiring tests: each test asserts the real callee (the MCP
``call_tool`` contract, the LIGHT-tier ``NPCIntentModule``) is invoked with
the expected arguments.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_agents.cast import build_cast
from monitor_agents.npc_voice import agent as npc_agent
from monitor_agents.npc_voice.agent import (
    compute_npc_intents,
    gather_npc_scene_context,
    recall_memories_for,
)
from monitor_agents.npc_voice.npc_voice import NPCIntentModule


class _SpyCallTool:
    """Records every (tool, args) call and answers from a canned map."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool_name, arguments))
        value = self.responses.get(tool_name)
        return value() if callable(value) else value


class TestRecallMemoriesFor:
    @pytest.mark.asyncio
    async def test_calls_qdrant_search_with_npc_scoped_params(self):
        npc_id = str(uuid4())
        universe_id = str(uuid4())
        spy = _SpyCallTool({"qdrant_search_memories": {"results": []}})

        result = await recall_memories_for(spy, npc_id, "the missing ledger", universe_id=universe_id, top_k=3)

        assert result == []
        tool, args = spy.calls[0]
        assert tool == "qdrant_search_memories"
        assert args["params"] == {
            "entity_id": npc_id,
            "query_text": "the missing ledger",
            "top_k": 3,
            "universe_id": universe_id,
        }

    @pytest.mark.asyncio
    async def test_hydrates_memory_text_from_mongodb(self):
        memory_id = str(uuid4())
        spy = _SpyCallTool(
            {
                "qdrant_search_memories": {"results": [{"memory_id": memory_id, "text": None}]},
                "mongodb_get_memory": {"memory_id": memory_id, "text": "I saw the captain take it."},
            }
        )

        result = await recall_memories_for(spy, str(uuid4()), "ledger", top_k=3)

        assert result[0]["text"] == "I saw the captain take it."
        assert ("mongodb_get_memory", {"memory_id": memory_id}) in spy.calls

    @pytest.mark.asyncio
    async def test_npc_voice_recall_delegates_to_shared_path(self):
        spy = _SpyCallTool({"qdrant_search_memories": {"results": []}})
        voice = npc_agent.NPCVoice()
        voice.call_tool = spy  # type: ignore[method-assign]
        npc_id = uuid4()

        await voice._recall_memories(npc_id, "query", universe_id=uuid4(), top_k=2)

        tool, args = spy.calls[0]
        assert tool == "qdrant_search_memories"
        assert args["params"]["entity_id"] == str(npc_id)
        assert args["params"]["top_k"] == 2


class TestComputeNpcIntents:
    @pytest.mark.asyncio
    async def test_one_light_call_per_npc_with_agenda_desires_memories(self):
        captured: list[dict[str, Any]] = []

        def _fake_forward(self, npc_name, npc_agenda, npc_desires, recalled_memories, current_action, role=None):
            captured.append(
                {
                    "npc_name": npc_name,
                    "npc_agenda": npc_agenda,
                    "npc_desires": npc_desires,
                    "recalled_memories": recalled_memories,
                    "current_action": current_action,
                }
            )
            return SimpleNamespace(intent=f"{npc_name} hides the truth")

        with patch.object(NPCIntentModule, "forward", _fake_forward):
            intents = await compute_npc_intents(
                npcs=[
                    {
                        "entity_id": "n1",
                        "name": "Vex",
                        "profile": {"desires": ["promotion"], "fears": ["court-martial"]},
                        "memories": ["saw the ledger vanish"],
                    }
                ],
                current_action="I ask about the ledger",
                agendas_by_npc={"n1": "Keep the smuggling quiet"},
            )

        assert intents == [{"entity_id": "n1", "name": "Vex", "intent": "Vex hides the truth"}]
        call = captured[0]
        assert call["npc_name"] == "Vex"
        assert call["npc_agenda"] == "Keep the smuggling quiet"
        assert "promotion" in call["npc_desires"]
        assert "court-martial" in call["npc_desires"]
        assert json.loads(call["recalled_memories"]) == ["saw the ledger vanish"]
        assert call["current_action"] == "I ask about the ledger"

    @pytest.mark.asyncio
    async def test_capped_at_four(self):
        calls: list[str] = []

        def _fake_forward(self, npc_name, npc_agenda, npc_desires, recalled_memories, current_action, role=None):
            calls.append(npc_name)
            return SimpleNamespace(intent="act")

        with patch.object(NPCIntentModule, "forward", _fake_forward):
            intents = await compute_npc_intents(
                npcs=[{"entity_id": f"n{i}", "name": f"NPC{i}", "profile": {}, "memories": []} for i in range(6)],
                current_action="hi",
            )

        assert len(calls) == 4
        assert len(intents) == 4

    @pytest.mark.asyncio
    async def test_failure_records_and_skips_that_npc(self):
        def _boom(self, npc_name, npc_agenda, npc_desires, recalled_memories, current_action, role=None):
            if npc_name == "Bad":
                raise RuntimeError("llm down")
            return SimpleNamespace(intent="fine")

        from unittest.mock import AsyncMock

        record_mock = AsyncMock(return_value=None)
        with (
            patch.object(NPCIntentModule, "forward", _boom),
            patch.object(npc_agent.RoleplayErrorRecorder, "record", record_mock),
        ):
            intents = await compute_npc_intents(
                npcs=[
                    {"entity_id": "n1", "name": "Bad", "profile": {}, "memories": []},
                    {"entity_id": "n2", "name": "Good", "profile": {}, "memories": []},
                ],
                current_action="hi",
            )

        assert intents == [{"entity_id": "n2", "name": "Good", "intent": "fine"}]
        assert record_mock.await_count == 1


class TestGatherNpcSceneContext:
    @pytest.mark.asyncio
    async def test_wires_recall_facts_filter_and_intents(self):
        npc_id = str(uuid4())
        other_witness = str(uuid4())
        cast = build_cast(
            controlled_ids=["pc1"],
            speaker_id="pc1",
            npc_profiles={npc_id: {"name": "Vex", "desires": ["keep secrets"]}},
            scene_id=str(uuid4()),
        )
        spy = _SpyCallTool(
            {
                "neo4j_list_agendas": [
                    {"owner_id": npc_id, "title": "Protect the crew", "description": "hide the smuggling"},
                ],
                "qdrant_search_memories": {"results": [{"memory_id": "m1", "text": "I saw the ledger vanish."}]},
                "mongodb_get_memory": {"memory_id": "m1", "text": "I saw the ledger vanish."},
                "neo4j_list_facts": [
                    {"statement": "witnessed fact", "witnesses": [npc_id]},
                    {"statement": "scene-2 secret", "witnesses": [other_witness]},
                    {"statement": "common lore", "witnesses": []},
                ],
            }
        )

        def _fake_forward(self, npc_name, npc_agenda, npc_desires, recalled_memories, current_action, role=None):
            return SimpleNamespace(intent="cover up the theft")

        with patch.object(NPCIntentModule, "forward", _fake_forward):
            out = await gather_npc_scene_context(
                spy,
                cast=cast,
                npc_profiles={npc_id: {"name": "Vex", "desires": ["keep secrets"]}},
                current_action="I ask about the ledger",
                universe_id=str(uuid4()),
            )

        # Task 7: top memories recalled for the NPC STATE block.
        assert out["npc_memories"][npc_id]["memories"] == ["I saw the ledger vanish."]
        # Task 8: only witnessed / told / common-knowledge facts survive.
        assert out["npc_facts"][npc_id]["facts"] == ["witnessed fact", "common lore"]
        # Task 9: one-line intent delivered to the narrator.
        assert out["npc_intents"] == [{"entity_id": npc_id, "name": "Vex", "intent": "cover up the theft"}]

        # The recall went through the NPCVoice-shared contract (Task 7).
        recall_calls = [c for c in spy.calls if c[0] == "qdrant_search_memories"]
        assert len(recall_calls) == 1
        assert recall_calls[0][1]["params"]["entity_id"] == npc_id
        assert recall_calls[0][1]["params"]["top_k"] == 3

        # The facts were fetched for the NPC entity (Task 8 read path).
        assert ("neo4j_list_facts", {"entity_id": npc_id, "limit": 10}) in spy.calls
