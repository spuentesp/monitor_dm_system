"""The acting owner reaches tool calls made by the loops (multi-tenancy A.3).

The UI binds the owner twice: ``resolve_principal`` sets the owner context
for the request/turn, and the loop constructors receive ``owner_id`` from the
session doc. These tests prove the owner survives ``asyncio.to_thread`` and
the LangGraph nodes the loops run, and that one test per loop
(SceneLoop / StoryLoop / ConversationLoop) reaches the real guarded write
tool with the owner visible at the assertion boundary.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import anyio
import pytest
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

import monitor_agents.loops.scene_loop as scene_loop_mod
import monitor_agents.loops.story_loop as story_loop_mod
from monitor_data.schemas.conversations import ConversationMode

from monitor_data.schemas.memories import MemoryCreate
from monitor_data.tenancy import OwnerViolationError, get_owner_id, set_owner_id
from monitor_data.tools.mongodb_tools.memories import mongodb_create_memory

_OWNER_A = str(uuid4())
_OWNER_B = str(uuid4())


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Any:
    tests_dir = Path(__file__).resolve().parents[2] / "data-layer" / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from _tenancy_fakes import install_fakes

    mongo, neo4j, pg = install_fakes(monkeypatch)

    # The loops compile their graphs against a MongoDB checkpointer; the fake
    # graphs below never touch it, so keep MongoDBSaver offline.
    class _NullSaver:
        def __enter__(self) -> _NullSaver:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        @classmethod
        def from_conn_string(cls, *args: Any, **kwargs: Any) -> _NullSaver:
            return cls()

    monkeypatch.setattr(scene_loop_mod, "MongoDBSaver", _NullSaver)
    monkeypatch.setattr(story_loop_mod, "MongoDBSaver", _NullSaver)

    # ConversationLoop's writes travel through the in-process MCP server.
    from monitor_data.server import discover_tools

    discover_tools()
    return mongo, neo4j, pg


def _memory_write(universe_id: str, entity_id: str) -> Any:
    """Invoke the real guarded memory tool (the write the loops perform)."""
    return mongodb_create_memory(
        MemoryCreate(universe_id=UUID(universe_id), entity_id=UUID(entity_id), text="loop memory")
    )


class _FakeCompiled:
    def __init__(self, target: Any) -> None:
        self._target = target

    async def ainvoke(self, payload: dict[str, Any], config: Any = None) -> dict[str, Any]:
        return self._target(payload)

    async def aget_state(self, config: Any) -> Any:
        class _Snapshot:
            values: dict[str, Any] = {}

        return _Snapshot()


def _fake_graph(target: Any) -> Any:
    class _Graph:
        def compile(self, checkpointer: Any = None) -> _FakeCompiled:
            return _FakeCompiled(target)

    return _Graph()


class TestContextPropagation:
    async def test_owner_context_survives_to_thread(self) -> None:
        set_owner_id(_OWNER_A)
        try:
            seen = await anyio.to_thread.run_sync(get_owner_id)
            assert seen == _OWNER_A
        finally:
            set_owner_id(None)

    async def test_owner_context_survives_langgraph_nodes(self, fakes: Any) -> None:
        mongo, neo4j, pg = fakes
        universe, entity = str(uuid4()), str(uuid4())
        pg.owned_universes.add(universe)
        neo4j.universe_by_id[entity] = universe

        class State(BaseModel):
            universe_id: str
            entity_id: str
            done: bool = False

        def sync_node(state: State) -> dict[str, Any]:
            _memory_write(state.universe_id, state.entity_id)
            return {"done": True}

        async def async_node(state: State) -> dict[str, Any]:
            await anyio.to_thread.run_sync(_memory_write, state.universe_id, state.entity_id)
            return {"done": True}

        graph = StateGraph(State)
        graph.add_node("sync_node", sync_node)
        graph.add_node("async_node", async_node)
        graph.set_entry_point("sync_node")
        graph.add_edge("sync_node", "async_node")
        graph.add_edge("async_node", END)
        compiled = graph.compile()

        set_owner_id(_OWNER_B)
        try:
            result = await compiled.ainvoke({"universe_id": universe, "entity_id": entity})
        finally:
            set_owner_id(None)
        assert result["done"] is True
        # Both nodes ran the guarded tool with the owner visible: the registry
        # was consulted for (universe, owner) once per write.
        assert pg.world_get_for_owner_calls == [(universe, _OWNER_B), (universe, _OWNER_B)]
        assert len(mongo.get_collection("character_memories").insert_calls) == 2


class TestSceneLoopOwnerReachesTool:
    async def test_scene_loop_forwards_session_owner_to_tool_call(self, fakes: Any) -> None:
        mongo, neo4j, pg = fakes
        universe, entity, owner = str(uuid4()), str(uuid4()), str(uuid4())
        pg.owned_universes.add(universe)
        neo4j.universe_by_id[entity] = universe

        def target(payload: dict[str, Any]) -> dict[str, Any]:
            _memory_write(universe, entity)
            return {**payload, "narrative_text": "ok"}

        with patch.object(scene_loop_mod, "build_scene_graph", lambda: _fake_graph(target)):
            loop = scene_loop_mod.SceneLoop(
                scene_id=uuid4(),
                story_id=uuid4(),
                universe_id=UUID(universe),
                owner_id=owner,  # what chat_loops.get_scene_loop passes from the session
            )
            result = await loop.run(user_input="hello")

        assert result["narrative_text"] == "ok"
        assert (universe, owner) in pg.world_get_for_owner_calls, "owner did not reach the tool call"
        assert mongo.get_collection("character_memories").insert_calls, "tool write did not happen"

    async def test_scene_loop_refuses_when_session_owner_is_foreign(self, fakes: Any) -> None:
        mongo, neo4j, pg = fakes
        universe, entity, owner = str(uuid4()), str(uuid4()), str(uuid4())
        neo4j.universe_by_id[entity] = universe  # universe NOT in owner's registry set

        def target(payload: dict[str, Any]) -> dict[str, Any]:
            _memory_write(universe, entity)
            return payload

        with patch.object(scene_loop_mod, "build_scene_graph", lambda: _fake_graph(target)):
            loop = scene_loop_mod.SceneLoop(
                scene_id=uuid4(),
                story_id=uuid4(),
                universe_id=UUID(universe),
                owner_id=owner,
            )
            with pytest.raises(OwnerViolationError):
                await loop.run(user_input="hello")
        assert mongo.total_write_calls == 0
        assert (universe, owner) in pg.world_get_for_owner_calls


class TestStoryLoopOwnerReachesTool:
    async def test_story_loop_forwards_session_owner_to_tool_call(self, fakes: Any) -> None:
        mongo, _neo4j, pg = fakes
        universe, owner = str(uuid4()), str(uuid4())
        pg.owned_universes.add(universe)

        def target(payload: dict[str, Any]) -> dict[str, Any]:
            from monitor_data.schemas.stories import StoryLedgerEntryCreate
            from monitor_data.tools.mongodb_tools.stories import mongodb_append_story_ledger_entry

            mongodb_append_story_ledger_entry(
                StoryLedgerEntryCreate(
                    story_id=UUID(str(payload["story_id"])),
                    universe_id=UUID(universe),
                    scene_id=uuid4(),
                    summary="The scene ended.",
                    start_time=datetime.now(UTC),
                    end_time=datetime.now(UTC),
                )
            )
            return {**payload, "started": True}

        async def _no_seed(self: Any, state: Any) -> Any:
            return state

        with (
            patch.object(story_loop_mod, "build_story_graph", lambda: _fake_graph(target)),
            patch.object(story_loop_mod.StoryLoop, "_seed_in_game_time", _no_seed),
        ):
            loop = story_loop_mod.StoryLoop(
                story_id=uuid4(),
                universe_id=UUID(universe),
                owner_id=owner,  # what chat_loops passes from the session
            )
            result = await loop.start_or_resume()

        assert result["started"] is True
        assert (universe, owner) in pg.world_get_for_owner_calls, "owner did not reach the tool call"
        assert mongo.get_collection("story_ledger").insert_calls, "tool write did not happen"


class TestConversationLoopOwnerReachesTool:
    async def test_conversation_loop_flush_reaches_tool_call(self, fakes: Any) -> None:
        mongo, _neo4j, pg = fakes
        universe, entity, owner = str(uuid4()), str(uuid4()), str(uuid4())
        pg.owned_universes.add(universe)

        from monitor_agents.loops.conversation_loop import ConversationLoop

        loop = ConversationLoop(
            conversation_id=uuid4(),
            universe_id=UUID(universe),
            mode=ConversationMode.DIRECT,
            npc_ids=[UUID(entity)],
            owner_id=owner,  # what chat_loops passes from the session
        )
        loop.state.deferred_memory_writes = [
            {
                "npc_id": UUID(entity),
                "player_said": "Hello",
                "npc_said": "Well met",
                "conversation_id": loop.state.conversation_id,
                "universe_id": UUID(universe),
            }
        ]
        flushed = await loop.flush_memory_writes()

        assert flushed == 1
        assert (universe, owner) in pg.world_get_for_owner_calls, "owner did not reach the tool call"
        assert mongo.get_collection("character_memories").insert_calls, "tool write did not happen"

    async def test_conversation_loop_flush_writes_nothing_for_foreign_owner(self, fakes: Any) -> None:
        mongo, _neo4j, pg = fakes
        universe, entity, owner = str(uuid4()), str(uuid4()), str(uuid4())

        from monitor_agents.loops.conversation_loop import ConversationLoop

        loop = ConversationLoop(
            conversation_id=uuid4(),
            universe_id=UUID(universe),
            mode=ConversationMode.DIRECT,
            npc_ids=[UUID(entity)],
            owner_id=owner,
        )
        loop.state.deferred_memory_writes = [
            {
                "npc_id": UUID(entity),
                "player_said": "Hello",
                "npc_said": "Well met",
                "conversation_id": loop.state.conversation_id,
                "universe_id": UUID(universe),
            }
        ]
        await loop.flush_memory_writes()

        # The tool refused at the boundary: the MCP surface reports tool
        # errors as text (BaseAgent.call_tool), but nothing is written.
        assert mongo.total_write_calls == 0
        assert (universe, owner) in pg.world_get_for_owner_calls
