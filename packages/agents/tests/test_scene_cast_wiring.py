"""Scene-loop cast wiring: narrate, extract_memories, persist_memories (Phase 4).

Cross-component wiring tests: each test asserts the real callee (Narrator
``narrate_turn``, the extractor's ``extract_memories``, ``gather_npc_scene_context``
via ``call_tool``, ``mongodb_create_memory``) is invoked with the expected
arguments.
"""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from monitor_agents.cast import build_cast
from monitor_agents.loops import scene_loop as sl
from monitor_agents.npc_voice.npc_voice import NPCIntentModule

PC1 = str(uuid4())
PC2 = str(uuid4())
NPC1 = str(uuid4())


class _StubFactory:
    def __init__(self, narrator: Any, extractor: Any = None) -> None:
        self._narrator = narrator
        self._extractor = extractor or types.SimpleNamespace(
            extract_new_entities=AsyncMock(return_value={}),
            extract_memories=AsyncMock(return_value={"memories_to_persist": []}),
            extract_facts=AsyncMock(return_value={}),
        )
        self._canonkeeper = types.SimpleNamespace(end_scene=AsyncMock(return_value=None))

    def create_narrator(self) -> Any:
        return self._narrator

    def create_extractor(self) -> Any:
        return self._extractor

    def create_canonkeeper(self) -> Any:
        return self._canonkeeper


class _SpyCallTool:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool_name, arguments))
        value = self.responses.get(tool_name)
        return value() if callable(value) else value


def _fake_intent_forward(self, npc_name, npc_agenda, npc_desires, recalled_memories, current_action, role=None):
    return types.SimpleNamespace(intent="stay quiet")


def _state(scene_id, *, user_input="I ask about the ledger", **overrides: Any) -> sl.SceneState:
    defaults: dict[str, Any] = dict(
        scene_id=scene_id,
        story_id=uuid4(),
        universe_id=uuid4(),
        user_input=user_input,
        actor_id=PC1,
        actor_context={"id": PC1, "name": "Ana"},
        entity_context=[
            {"id": PC1, "name": "Ana", "entity_type": "character"},
            {"id": NPC1, "name": "Vex", "entity_type": "character"},
        ],
        npc_profiles={NPC1: {"name": "Vex", "desires": ["keep secrets"]}},
    )
    defaults.update(overrides)
    return sl.SceneState(**defaults)


class TestNarrateNode:
    @pytest.mark.asyncio
    async def test_passes_cast_and_npc_context_to_the_narrator(self):
        scene_id = uuid4()
        scene_cast = build_cast(
            controlled_ids=[PC1, PC2],
            speaker_id=PC1,
            entity_context=[{"id": NPC1, "name": "Vex", "entity_type": "character"}],
            scene_id=str(scene_id),
        )
        narrate_turn = AsyncMock(
            return_value={
                "narrative_text": "prose",
                "proposals": [],
                "turn_id": "t1",
                "minutes_elapsed": 5,
            }
        )
        call_tool = _SpyCallTool(
            {
                "neo4j_list_agendas": [],
                "qdrant_search_memories": {"results": [{"memory_id": "m1", "text": "saw it"}]},
                "mongodb_get_memory": {"memory_id": "m1", "text": "saw it"},
                "neo4j_list_facts": [{"statement": "the ledger is gone", "witnesses": [NPC1, PC1]}],
            }
        )
        narrator = types.SimpleNamespace(narrate_turn=narrate_turn, call_tool=call_tool)

        with (
            patch.object(sl, "get_agent_factory", lambda: _StubFactory(narrator)),
            patch.object(NPCIntentModule, "forward", _fake_intent_forward),
        ):
            result = await sl.narrate(_state(scene_id, cast=scene_cast))

        assert result["narrative_text"] == "prose"
        kwargs = narrate_turn.await_args.kwargs
        context = kwargs["context"]

        # Task 1: the cast reaches the Narrator.
        assert {m["entity_id"] for m in context["cast"]["members"]} == {PC1, PC2, NPC1}
        assert context["cast"]["members"][0]["is_speaker"] is True

        # Tasks 7-9: per-NPC recall, known facts, and intent reach the Narrator.
        assert context["npc_memories"][NPC1]["memories"] == ["saw it"]
        assert context["npc_facts"][NPC1]["facts"] == ["the ledger is gone"]
        assert context["npc_intents"] == [{"entity_id": NPC1, "name": "Vex", "intent": "stay quiet"}]

        # The recall went through the shared NPCVoice recall contract.
        assert any(c[0] == "qdrant_search_memories" for c in call_tool.calls)

    @pytest.mark.asyncio
    async def test_stamps_witnesses_on_fact_proposals(self):
        scene_id = uuid4()
        scene_cast = build_cast(
            controlled_ids=[PC1],
            speaker_id=PC1,
            npc_profiles={NPC1: {"name": "Vex"}},
            scene_id=str(scene_id),
        )
        narrate_turn = AsyncMock(
            return_value={
                "narrative_text": "prose",
                "proposals": [
                    {
                        "change_type": "fact",
                        "content": {"statement": "the ledger vanished", "fact_type": "occurrence"},
                    },
                    {"change_type": "ENTITY", "content": {"name": "new guy"}},
                ],
                "turn_id": "t1",
            }
        )
        narrator = types.SimpleNamespace(narrate_turn=narrate_turn)

        with patch.object(sl, "get_agent_factory", lambda: _StubFactory(narrator)):
            result = await sl.narrate(_state(scene_id, cast=scene_cast))

        proposals = result["pending_proposals"]
        fact = next(p for p in proposals if p["change_type"] == "fact")
        entity = next(p for p in proposals if p["change_type"] == "ENTITY")
        # Task 8: facts written in play carry the cast witnesses (Task 8).
        assert set(fact["witnesses"]) == {PC1, NPC1}
        assert set(fact["content"]["witnesses"]) == {PC1, NPC1}
        assert set(fact["content"]["properties"]["witnesses"]) == {PC1, NPC1}
        # Non-fact proposals are left alone.
        assert "witnesses" not in entity

    @pytest.mark.asyncio
    async def test_turn_proceeds_when_enrichment_fails(self):
        scene_id = uuid4()
        scene_cast = build_cast(
            controlled_ids=[PC1],
            speaker_id=PC1,
            npc_profiles={NPC1: {"name": "Vex"}},
            scene_id=str(scene_id),
        )
        narrate_turn = AsyncMock(return_value={"narrative_text": "prose", "proposals": [], "turn_id": "t1"})

        async def _broken_call_tool(tool_name, arguments):
            raise RuntimeError("mcp down")

        narrator = types.SimpleNamespace(narrate_turn=narrate_turn, call_tool=_broken_call_tool)
        record_mock = AsyncMock(return_value=None)

        with (
            patch.object(sl, "get_agent_factory", lambda: _StubFactory(narrator)),
            patch.object(sl.RoleplayErrorRecorder, "record", record_mock),
            patch.object(NPCIntentModule, "forward", _fake_intent_forward),
        ):
            result = await sl.narrate(_state(scene_id, cast=scene_cast))

        assert result["narrative_text"] == "prose"
        # Failures are recorded, not swallowed silently.
        assert record_mock.await_count >= 1


class TestExtractMemoriesNode:
    @pytest.mark.asyncio
    async def test_extractor_receives_full_cast(self):
        scene_id = uuid4()
        scene_cast = build_cast(
            controlled_ids=[PC1, PC2],
            speaker_id=PC1,
            npc_profiles={NPC1: {"name": "Vex"}},
            scene_id=str(scene_id),
        )
        extract = AsyncMock(return_value={"memories_to_persist": []})
        extractor = types.SimpleNamespace(
            extract_new_entities=AsyncMock(return_value={}),
            extract_memories=extract,
            extract_facts=AsyncMock(return_value={}),
        )
        state = _state(scene_id, narrative_text="prose", cast=scene_cast)

        with patch.object(sl, "get_agent_factory", lambda: _StubFactory(None, extractor)):
            await sl.extract_memories(state)

        kwargs = extract.await_args.kwargs
        # Join task 2: the node hands the extractor the full cast (witnesses),
        # and the extractor picks the acting/speaking member only.
        assert {m["entity_id"] for m in kwargs["cast"]} == {PC1, PC2, NPC1}
        assert kwargs["scene_id"] == scene_id
        assert kwargs["universe_id"] == state.universe_id
        assert kwargs["narrative_text"] == "prose"


class TestSceneEndMemoryPass:
    """Scene end: one summary memory per cast member who never acted
    (join Task 2). Both scene-end paths (automatic routing and
    ``SceneLoop.finalize``) reach ``complete_current_scene``."""

    @pytest.mark.asyncio
    async def test_the_scene_end_pass_extracts_for_the_non_actors(self):
        from datetime import UTC, datetime

        scene_id = uuid4()
        scene_cast = build_cast(
            controlled_ids=[PC1, PC2],
            speaker_id=PC1,
            npc_profiles={NPC1: {"name": "Vex"}},
            scene_id=str(scene_id),
        )
        state = _state(
            scene_id,
            cast=scene_cast,
            scene_actors=[PC1],  # Ana acted; Bor and Vex never spoke
            narrative_text="the last prose",
            previous_turns=[{"speaker": "Ana", "text": "I search the room"}],
            time_ref=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
        )
        extract_scene = AsyncMock(
            return_value={
                "memories_to_persist": [
                    {
                        "text": "Vex watched Ana search",
                        "importance": 5,
                        "entity_id": NPC1,
                        "universe_id": str(state.universe_id),
                        "witnesses": [PC1, PC2, NPC1],
                    },
                    {
                        "text": "Bor was not there",
                        "importance": 3,
                        "entity_id": PC2,
                        "universe_id": str(state.universe_id),
                        "witnesses": [PC1, PC2, NPC1],
                    },
                ]
            }
        )
        extractor = types.SimpleNamespace(
            extract_new_entities=AsyncMock(return_value={}),
            extract_memories=AsyncMock(return_value={"memories_to_persist": []}),
            extract_facts=AsyncMock(return_value={}),
            extract_scene_memories=extract_scene,
        )
        create_memory_mock = MagicMock(return_value=None)

        with (
            patch.object(sl, "get_agent_factory", lambda: _StubFactory(None, extractor)),
            patch("monitor_agents.agent_factory.get_agent_factory", lambda: _StubFactory(None, extractor)),
            patch("monitor_data.tools.mongodb_tools.mongodb_create_memory", create_memory_mock),
        ):
            result = await sl.complete_current_scene(state)

        # The scene transition is unaffected.
        assert result["scene_complete"] is True
        # One call for the whole scene, narrowed to the members who never acted.
        assert extract_scene.await_count == 1
        kwargs = extract_scene.await_args.kwargs
        assert set(kwargs["extract_for_ids"]) == {PC2, NPC1}
        assert {m["entity_id"] for m in kwargs["cast"]} == {PC1, PC2, NPC1}
        assert "I search the room" in kwargs["transcript"]
        assert "the last prose" in kwargs["transcript"]
        # Persisted under each owner with witnesses, universe_id and time_ref.
        assert create_memory_mock.call_count == 2
        by_owner = {call.args[0].entity_id: call.args[0] for call in create_memory_mock.call_args_list}
        assert set(by_owner) == {UUID(PC2), UUID(NPC1)}
        vex = by_owner[UUID(NPC1)]
        assert vex.universe_id == state.universe_id
        assert set(vex.witnesses) == {UUID(PC1), UUID(PC2), UUID(NPC1)}
        assert vex.metadata["time_ref"].startswith("1012-03-01T09:00")

    @pytest.mark.asyncio
    async def test_a_failed_scene_end_pass_does_not_block_the_transition(self):
        scene_id = uuid4()
        scene_cast = build_cast(
            controlled_ids=[PC1],
            speaker_id=PC1,
            npc_profiles={NPC1: {"name": "Vex"}},
            scene_id=str(scene_id),
        )
        state = _state(scene_id, cast=scene_cast, scene_actors=[PC1])
        extractor = types.SimpleNamespace(
            extract_new_entities=AsyncMock(return_value={}),
            extract_memories=AsyncMock(return_value={"memories_to_persist": []}),
            extract_facts=AsyncMock(return_value={}),
            extract_scene_memories=AsyncMock(side_effect=RuntimeError("mcp down")),
        )
        record_mock = AsyncMock(return_value=None)

        with (
            patch.object(sl, "get_agent_factory", lambda: _StubFactory(None, extractor)),
            patch("monitor_agents.agent_factory.get_agent_factory", lambda: _StubFactory(None, extractor)),
            patch.object(sl.RoleplayErrorRecorder, "record", record_mock),
        ):
            result = await sl.complete_current_scene(state)

        assert result["scene_complete"] is True
        # The failure is recorded, not swallowed silently.
        assert record_mock.await_count == 1
        assert "scene_end_memory_extraction_failed" in record_mock.await_args.kwargs["message"]

    @pytest.mark.asyncio
    async def test_a_member_who_acted_gets_no_second_scene_memory(self):
        scene_id = uuid4()
        scene_cast = build_cast(
            controlled_ids=[PC1],
            speaker_id=PC1,
            scene_id=str(scene_id),
        )
        state = _state(scene_id, cast=scene_cast, scene_actors=[PC1], narrative_text="prose")
        extract_scene = AsyncMock(return_value={"memories_to_persist": []})
        extractor = types.SimpleNamespace(
            extract_new_entities=AsyncMock(return_value={}),
            extract_memories=AsyncMock(return_value={"memories_to_persist": []}),
            extract_facts=AsyncMock(return_value={}),
            extract_scene_memories=extract_scene,
        )

        with (
            patch.object(sl, "get_agent_factory", lambda: _StubFactory(None, extractor)),
            patch("monitor_agents.agent_factory.get_agent_factory", lambda: _StubFactory(None, extractor)),
            patch("monitor_data.tools.mongodb_tools.mongodb_create_memory", MagicMock(return_value=None)),
        ):
            await sl.complete_current_scene(state)

        # Everyone present acted — no scene-end extraction runs at all.
        assert extract_scene.await_count == 0


class TestPersistMemoriesNode:
    @pytest.mark.asyncio
    async def test_persists_per_owner_with_witnesses(self):
        scene_id = uuid4()
        story_id = uuid4()
        pc1 = uuid4()
        n1 = uuid4()
        state = _state(
            scene_id,
            story_id=story_id,
            memories_to_persist=[
                {
                    "text": "Ana remembers",
                    "importance": 6,
                    "emotional_valence": 0.1,
                    "entity_id": str(pc1),
                    "universe_id": str(state_universe := uuid4()),
                    "witnesses": [str(pc1), str(n1)],
                },
                {
                    "text": "Vex remembers",
                    "importance": 3,
                    "emotional_valence": -0.2,
                    "entity_id": str(n1),
                    "universe_id": str(state_universe),
                    "witnesses": [str(pc1), str(n1)],
                },
            ],
        )
        create_memory_mock = MagicMock(return_value=types.SimpleNamespace(memory_id=uuid4()))

        with patch("monitor_data.tools.mongodb_tools.mongodb_create_memory", create_memory_mock):
            result = await sl.persist_memories_node(state)

        assert result["memories_to_persist"] == []
        assert create_memory_mock.call_count == 2
        by_owner = {call.args[0].entity_id: call.args[0] for call in create_memory_mock.call_args_list}
        # Task 6: persisted under each character's own entity_id...
        assert set(by_owner) == {pc1, n1}
        ana = by_owner[pc1]
        assert ana.text == "Ana remembers"
        assert ana.universe_id == state_universe
        assert ana.scene_id == scene_id
        # Task 8: with the cast witnesses on the record.
        assert set(ana.witnesses) == {pc1, n1}
        assert ana.metadata["witnesses"] == [str(pc1), str(n1)]
        assert ana.metadata["story_id"] == str(story_id)

    @pytest.mark.asyncio
    async def test_failed_memories_stay_for_the_scene_end_retry(self):
        state = _state(
            uuid4(),
            memories_to_persist=[
                {
                    "text": "keep me",
                    "entity_id": str(uuid4()),
                    "universe_id": str(uuid4()),
                }
            ],
        )
        create_memory_mock = MagicMock(side_effect=ValueError("entity not found"))
        record_mock = AsyncMock(return_value=None)

        with (
            patch("monitor_data.tools.mongodb_tools.mongodb_create_memory", create_memory_mock),
            patch.object(sl.RoleplayErrorRecorder, "record", record_mock),
        ):
            result = await sl.persist_memories_node(state)

        assert [m["text"] for m in result["memories_to_persist"]] == ["keep me"]
        assert record_mock.await_count == 1
