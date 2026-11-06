from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from monitor_agents.loops import scene_loop, story_loop


@contextmanager
def _saver_context(saver):
    yield saver


@pytest.mark.asyncio
async def test_scene_retains_pending_roll_and_turn_count_across_invocations(monkeypatch):
    saver = MemorySaver()
    monkeypatch.setattr(scene_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
    seen = []

    async def turn(state):
        seen.append((state.pending_roll, state.turns_count, state.resolution))
        return {
            "pending_roll": {"stat": "Strength"} if len(seen) == 1 else None,
            "turns_count": state.turns_count + 1,
            "resolution": {"old": True},
        }

    graph = StateGraph(scene_loop.SceneState)
    graph.add_node("turn", turn)
    graph.set_entry_point("turn")
    graph.add_edge("turn", END)
    loop = scene_loop.SceneLoop(scene_id=uuid4(), story_id=uuid4())
    loop._graph = graph
    await loop.run("first")
    result = await loop.run("second")
    assert seen == [(None, 0, None), ({"stat": "Strength"}, 1, None)]
    assert result["turns_count"] == 2
    assert result["pending_roll"] is None


@pytest.mark.asyncio
async def test_story_completion_checkpoints_progress_and_resume(monkeypatch):
    saver = MemorySaver()
    monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
    monkeypatch.setattr(
        story_loop,
        "simulate_world_advance",
        AsyncMock(
            side_effect=lambda s: {"in_game_time": s.in_game_time + timedelta(minutes=s.last_scene_duration_minutes)}
        ),
    )
    monkeypatch.setattr(story_loop, "evaluate_arc", AsyncMock(return_value={"tension_score": 0.7}))
    monkeypatch.setattr(story_loop, "transition_scene", AsyncMock(side_effect=lambda s: {"current_scene_id": uuid4()}))
    loop = story_loop.StoryLoop(uuid4(), uuid4())
    loop.call_tool = AsyncMock(return_value=[])
    first = await loop.complete_current_scene(uuid4(), {"total_minutes_passed": 10})
    second = await loop.complete_current_scene(first["current_scene_id"], {"total_minutes_passed": 20})
    resumed = await loop.start_or_resume()
    assert second["scenes_completed"] == 2
    assert second["in_game_time"] == datetime(1000, 1, 1, 12, 30, tzinfo=timezone.utc)
    assert resumed["scenes_completed"] == 2
    assert resumed["tension_score"] == 0.7
    assert resumed["current_scene_id"] == second["current_scene_id"]


@pytest.mark.asyncio
async def test_combat_node_routes_result_to_narration_and_persistence(monkeypatch):
    entity_id = uuid4()
    combat = {
        "narrative_text": "The blow lands.",
        "combatants": [{"entity_id": str(entity_id), "is_pc": True, "hp_current": 7}],
    }
    monkeypatch.setattr(scene_loop, "_run_combat", AsyncMock(return_value=combat))
    state = scene_loop.SceneState(
        scene_id=uuid4(),
        story_id=uuid4(),
        user_input="attack",
        resolution={"action_type": "combat"},
        entity_context=[{"id": str(entity_id), "properties": {"hp": 10}}],
    )
    result = await scene_loop.run_combat_node(state)
    assert result["combat_result"] == combat
    assert scene_loop._extract_combat_resource_deltas(result["combat_result"], state.entity_context)[0]["delta"] == -3


@pytest.mark.asyncio
async def test_narrator_persists_combat_text_with_turn(monkeypatch):
    from monitor_agents.narrator.agent import Narrator

    narrator = Narrator()
    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Opening.", [], 1, [], None))
    narrator._persist_turn = AsyncMock(return_value=str(uuid4()))
    result = await narrator.narrate_turn(
        scene_id=uuid4(), user_input="attack", resolution={}, context={"combat_narrative": "The blow lands."}
    )
    assert result["narrative_text"] == "Opening.\n\nThe blow lands."
    assert narrator._persist_turn.await_args.kwargs["narrative_text"] == result["narrative_text"]


@pytest.mark.asyncio
async def test_profiles_use_newly_assembled_entities(monkeypatch):
    from monitor_agents.utils import db_readers

    entity_id = uuid4()
    profile = SimpleNamespace(entity_id=entity_id, model_dump=lambda **_: {"name": "Vex"})
    assembly = SimpleNamespace(
        assemble=AsyncMock(return_value={"entities": [{"id": str(entity_id)}]}),
        check_and_compress_if_needed=AsyncMock(return_value={"entities": [{"id": str(entity_id)}]}),
    )
    monkeypatch.setattr(
        scene_loop, "get_agent_factory", lambda: SimpleNamespace(create_context_assembly=lambda: assembly)
    )
    calls = []

    async def read(fn, *args, **kwargs):
        calls.append((fn.__name__, args))
        if fn.__name__ == "mongodb_get_npc_profiles_by_entities":
            return [profile]
        return None

    monkeypatch.setattr(db_readers, "run_sync_read", read)
    result = await scene_loop.load_context(scene_loop.SceneState(scene_id=uuid4(), story_id=uuid4()))
    assert result["npc_profiles"][str(entity_id)]["name"] == "Vex"
    assert ("mongodb_get_npc_profiles_by_entities", ([entity_id],)) in calls


@pytest.mark.asyncio
async def test_combat_deltas_reach_working_state_persistence(monkeypatch):
    from monitor_agents.services.persistence_service import PersistenceService
    from monitor_agents.utils import db_readers

    entity_id = uuid4()
    persistence = AsyncMock(return_value={})
    monkeypatch.setattr(PersistenceService, "persist_working_state", persistence)

    async def read(fn, *args, **kwargs):
        if fn.__name__ == "mongodb_create_resolution":
            return SimpleNamespace(id=uuid4())
        return None

    monkeypatch.setattr(db_readers, "run_sync_read", read)
    state = scene_loop.SceneState(
        scene_id=uuid4(),
        story_id=uuid4(),
        actor_id=entity_id,
        turn_id=uuid4(),
        user_input="attack",
        narrative_text="A hit.",
        resolution={"resolution_type": "narrative"},
        entity_context=[{"id": str(entity_id), "properties": {"hp": 10}}],
        resource_deltas=[{"resource_key": "mana", "delta": -1}],
        combat_result={"combatants": [{"entity_id": str(entity_id), "is_pc": True, "hp_current": 7}]},
    )
    await scene_loop.persist_turn_artifacts(state)
    deltas = persistence.await_args.kwargs["resource_deltas"]
    assert [(d["resource_key"], d["delta"]) for d in deltas] == [("mana", -1), ("HP", -3)]


@pytest.mark.asyncio
async def test_scene_completion_does_not_force_story_completion(monkeypatch):
    saver = MemorySaver()
    monkeypatch.setattr(story_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
    monkeypatch.setattr(story_loop, "simulate_world_advance", AsyncMock(return_value={}))
    monkeypatch.setattr(story_loop, "evaluate_arc", AsyncMock(return_value={"story_complete": False}))
    next_scene = uuid4()
    monkeypatch.setattr(story_loop, "transition_scene", AsyncMock(return_value={"current_scene_id": next_scene}))
    finalize = AsyncMock()
    monkeypatch.setattr(story_loop, "finalize_story", finalize)
    loop = story_loop.StoryLoop(uuid4(), uuid4())
    loop.call_tool = AsyncMock(return_value=[])
    result = await loop.complete_current_scene(uuid4(), {"scene_complete": True})
    assert result["story_complete"] is False
    assert result["current_scene_id"] == next_scene
    finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_combat_resumes_and_npc_acts_before_player(monkeypatch):
    from monitor_agents.loops import combat_loop

    pc_id, npc_id = uuid4(), uuid4()
    entities = [
        {"id": str(pc_id), "name": "PC", "properties": {"role": "PC", "hp": 10}},
        {"id": str(npc_id), "name": "NPC", "properties": {"hp": 10}},
    ]
    rolls = []
    actions = []

    async def initiative(state):
        rolls.append(True)
        return {
            "initiative_order": [npc_id, pc_id],
            "current_index": 0,
            "current_combatant_id": npc_id,
            "awaiting_pc_input": False,
        }

    async def resolve(state):
        actions.append((state.current_combatant_id, state.user_input))
        target = next(c for c in state.combatants if c.entity_id != state.current_combatant_id)
        target.hp_current -= 1
        return {"combatants": [c.model_dump() for c in state.combatants]}

    async def narration(state):
        return {"narrative_text": f"{state.current_combatant_id} acts"}

    monkeypatch.setattr(combat_loop, "roll_initiative", initiative)
    monkeypatch.setattr(combat_loop, "resolve_combat_action", resolve)
    monkeypatch.setattr(combat_loop, "narrate_combat", narration)
    args = dict(scene_id=uuid4(), story_id=uuid4(), entity_context=entities, game_context={}, source_profile={})
    first = await scene_loop._run_combat(**args, user_input="first attack")
    second = await scene_loop._run_combat(**args, user_input="second attack", previous_combat=first["combat_state"])
    assert rolls == [True]
    assert actions[0] == (npc_id, "NPC attacks PC")
    assert actions[1] == (pc_id, "first attack")
    assert actions[3] == (pc_id, "second attack")
    assert first["starting_hp"][str(pc_id)] == 10
    assert second["starting_hp"][str(pc_id)] == 8
    assert second["combat_state"]["round_number"] > first["combat_state"]["round_number"]
    assert str(pc_id) in first["narrative_text"] and str(npc_id) in first["narrative_text"]
    assert scene_loop._extract_combat_resource_deltas(second, entities)[0]["delta"] == -1


@pytest.mark.asyncio
async def test_group_conversation_passes_first_npc_response_to_second(monkeypatch):
    from monitor_agents.loops import conversation_loop
    from monitor_agents.npc_voice.agent import NPCVoice
    from monitor_data.schemas.conversations import ConversationMode

    first, second = uuid4(), uuid4()
    histories = []

    async def respond(self, **kwargs):
        histories.append(kwargs["conversation_history"])
        return {"npc_response": str(kwargs["npc_id"]), "emotional_state_after": {}}

    monkeypatch.setattr(NPCVoice, "respond_direct", respond)
    state = conversation_loop.ConversationState(
        conversation_id=uuid4(),
        universe_id=uuid4(),
        mode=ConversationMode.DIRECT,
        npc_ids=[first, second],
        current_player_input="hello",
        turns=[{"speaker_role": "player", "text": "hello"}],
    )
    result = await conversation_loop.generate_npc_responses(state)
    assert len(result["current_npc_responses"]) == 2
    assert histories[1][-1]["entity_id"] == str(first)


@pytest.mark.asyncio
async def test_finalize_bypasses_turn_generation_and_turn_limit_marks_complete(monkeypatch):
    saver = MemorySaver()
    monkeypatch.setattr(scene_loop.MongoDBSaver, "from_conn_string", lambda _: _saver_context(saver))
    monkeypatch.setattr(scene_loop, "_SCENE_GRAPH_TEMPLATE", None)
    calls = []

    async def load(state):
        return {}

    async def resolve(state):
        calls.append("resolve")
        return {"resolution": {"resolution_type": "narrative"}}

    async def narrate(state):
        calls.append("narrate")
        return {"turns_count": state.turns_count + 1}

    async def complete(state):
        calls.append("complete")
        return {"scene_complete": True}

    async def empty(state):
        return {}

    monkeypatch.setattr(scene_loop, "load_context", load)
    monkeypatch.setattr(scene_loop, "resolve_action", resolve)
    monkeypatch.setattr(scene_loop, "narrate", narrate)
    monkeypatch.setattr(scene_loop, "complete_current_scene", complete)
    for name in (
        "run_combat_node",
        "extract_new_entities",
        "extract_memories",
        "extract_facts",
        "persist_memories_node",
        "check_consistency",
        "check_events",
        "check_foreshadowing",
        "persist_turn_artifacts",
        "canonize_checkpoint",
    ):
        monkeypatch.setattr(scene_loop, name, empty)
    loop = scene_loop.SceneLoop(scene_id=uuid4(), story_id=uuid4(), max_turns=1)
    result = await loop.run("look")
    assert result["scene_complete"] is True
    assert calls == ["resolve", "narrate", "complete"]
    calls.clear()
    other = scene_loop.SceneLoop(scene_id=uuid4(), story_id=uuid4())
    await other.finalize()
    assert calls == ["complete"]
