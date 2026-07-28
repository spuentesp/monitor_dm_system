import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from monitor_ui.routers.chat_loops import (
    scene_loop_signature,
    _build_story_state_dict,
    get_scene_loop,
    pop_scene_loop,
    pop_character_creation_loop,
    pop_session_zero_loop,
    run_preplay_turn,
    run_world_architect_turn,
    run_scene_turn,
    pop_conversation_loop,
    run_end_scene,
    run_recap_command,
    run_start_conversation,
    run_conversation_turn,
    _generate_scene_summary,
    run_ooc_turn,
    _SCENE_LOOPS,
    _STORY_STATES,
    _CONVERSATION_LOOPS,
)
import sys
import importlib
@pytest.fixture(autouse=True)
def reset_caches():
    _SCENE_LOOPS.clear()
    _STORY_STATES.clear()
    _CONVERSATION_LOOPS.clear()
    yield
    _SCENE_LOOPS.clear()
    _STORY_STATES.clear()
    _CONVERSATION_LOOPS.clear()

def test_scene_loop_signature():
    session = {
        "speaker_character_id": str(uuid.uuid4()),
        "play_mode": "narrative",
        "system_id": "sys1",
        "pack_id": "pack1",
        "system_source_type": "type1",
        "system_source_id": "src1",
        "tone": "dramatic",
        "gm_profile_id": "gm1",
        "roll_model": "tap"
    }
    sig = scene_loop_signature(session, scene_id="scene1", story_id="story1")
    assert sig[0] == "scene1"
    assert sig[1] == "story1"
    assert sig[2] == "narrative"
    assert sig[3] == "sys1"

def test_build_story_state_dict():
    session = {"universe_id": "u1", "story_premise": "cool story"}
    _STORY_STATES["s1"] = {"active_threads": 5}
    res = _build_story_state_dict(session, story_id="s1")
    assert res is not None
    assert res["story_id"] == "s1"
    assert res["universe_id"] == "u1"
    assert res["story_premise"] == "cool story"
    assert res["active_threads"] == 5

    res_none = _build_story_state_dict({}, story_id="s1")
    assert res_none is None

@patch("monitor_ui.routers.chat_loops._BOOTSTRAP_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.mongodb_get_gm_profile")
@patch("monitor_ui.routers.chat_loops.SceneLoop")
def test_get_scene_loop_with_gm_profile(MockSceneLoop, mock_get_profile):
    mock_profile = MagicMock()
    mock_profile.model_dump.return_value = {"profile": "test"}
    mock_get_profile.return_value = mock_profile

    session = {"universe_id": str(uuid.uuid4()), "gm_profile_id": str(uuid.uuid4())}
    sid, stid = str(uuid.uuid4()), str(uuid.uuid4())
    loop = get_scene_loop("sess1", session, scene_id=sid, story_id=stid)
    assert loop is not None
    assert "sess1" in _SCENE_LOOPS
    
    # test cache hit
    loop2 = get_scene_loop("sess1", session, scene_id=sid, story_id=stid)
    assert loop2 == loop

    # test max loops
    for i in range(35):
        get_scene_loop(f"sess_{i}", session, scene_id=str(uuid.uuid4()), story_id=str(uuid.uuid4()))
    assert len(_SCENE_LOOPS) == 32

@patch("monitor_ui.routers.chat_loops._BOOTSTRAP_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.mongodb_get_gm_profile")
@patch("monitor_ui.routers.chat_loops.SceneLoop")
def test_get_scene_loop_gm_profile_fail(MockSceneLoop, mock_get_profile):
    mock_get_profile.side_effect = Exception("failed")
    session = {"universe_id": str(uuid.uuid4()), "gm_profile_id": str(uuid.uuid4())}
    loop = get_scene_loop("sess1", session, scene_id=str(uuid.uuid4()), story_id=str(uuid.uuid4()))
    assert loop is not None

def test_pop_scene_loop():
    _SCENE_LOOPS["sess1"] = (None, None)
    pop_scene_loop("sess1")
    assert "sess1" not in _SCENE_LOOPS
    pop_scene_loop("sess1")

def test_pop_character_creation_loop():
    pop_character_creation_loop("sess1")

def test_pop_session_zero_loop():
    pop_session_zero_loop("sess1")

@pytest.mark.asyncio
async def test_run_preplay_turn():
    sessions = {"s1": {"phase": "session_zero", "system_label": "sys"}}
    
    with patch("monitor_agents.loops.preplay_orchestrator.PreplayOrchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.ainvoke.return_value = {"session_data": {"phase": "next"}, "response_text": "resp", "metadata": {"a": 1}}
        MockOrch.ainvoke = mock_orch.ainvoke
        
        with patch("monitor_ui.routers.chat_opening.fetch_opening_hook", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"axioms": ["a"], "facts": ["f"]}
            
            with patch("monitor_agents.session_zero.ground_world_lore") as mock_ground:
                mock_ground.return_value = ["a", "f"]
                
                sys_doc = {
                    "character_creation": {
                        "backgrounds": [{"name": "bg1"}],
                        "steps": [{"title": "step1"}],
                        "logic": [{"prompt_template": "logic1"}]
                    }
                }
                resp, meta = await run_preplay_turn(
                    "s1", "hi", sessions=sessions, messages={},
                    db_save_session=MagicMock(), db_save_message=MagicMock(),
                    session_game_system_doc=sys_doc, gsr_available=True
                )
                assert resp == "resp"
                assert meta == {"a": 1}

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._WORLD_ARCHITECT_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.WorldBuildingLoop")
async def test_run_world_architect_turn(MockWBL):
    mock_loop = AsyncMock()
    uid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    mock_loop.run.return_value = {"universe_id": uid, "multiverse_id": mid, "response_text": "world built", "committed_count": 1}
    MockWBL.return_value = mock_loop
    
    sessions = {"s1": {"universe_id": uid}}
    msgs = {"s1": [{"role": "player", "content": "build"}]}
    
    resp, meta = await run_world_architect_turn("s1", "build", sessions=sessions, messages=msgs, db_save_session=MagicMock(), db_load_messages=MagicMock())
    assert resp == "world built"
    assert meta["committed"] == 1
    assert meta["universe_id"] == uid
    assert meta["multiverse_id"] == mid
    
    # Missing session
    resp, meta = await run_world_architect_turn("s2", "build", sessions=sessions, messages=msgs, db_save_session=MagicMock(), db_load_messages=MagicMock())
    assert resp == "Session not found."

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._WORLD_ARCHITECT_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.WorldBuildingLoop")
async def test_run_world_architect_turn_exception(MockWBL):
    mock_loop = AsyncMock()
    mock_loop.run.side_effect = Exception("failed")
    MockWBL.return_value = mock_loop
    
    sessions = {"s1": {"universe_id": str(uuid.uuid4())}}
    msgs = {"s1": [{"role": "player", "content": "build"}]}
    resp, meta = await run_world_architect_turn("s1", "build", sessions=sessions, messages=msgs, db_save_session=MagicMock(), db_load_messages=MagicMock())
    assert "encountered an issue" in resp
    assert "error" in meta

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._WORLD_ARCHITECT_AVAILABLE", False)
async def test_run_world_architect_turn_unavailable():
    sessions = {"s1": {"universe_id": str(uuid.uuid4())}}
    resp, meta = await run_world_architect_turn("s1", "build", sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock())
    assert "not available" in resp

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.SceneOrchestrator")
@patch("monitor_ui.routers.chat_loops.resolve_actor_character")
async def test_run_scene_turn(mock_resolve, MockSO):
    mock_so = AsyncMock()
    mock_so.run.return_value = ("scene out", {"m": 1})
    MockSO.return_value = mock_so
    
    mock_char = MagicMock()
    mock_char.model_dump.return_value = {"char": "yes"}
    mock_resolve.return_value = mock_char

    sessions = {"s1": {"scene_id": "sc1", "story_id": "st1"}}
    resp, meta = await run_scene_turn("s1", "act", sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock(), session_game_system_doc=MagicMock(), gsr_available=True)
    assert resp == "scene out"
    
    # Missing session
    resp, meta = await run_scene_turn("s2", "act", sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock(), session_game_system_doc=MagicMock(), gsr_available=True)
    assert resp == "Session not found."

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", False)
async def test_run_scene_turn_unavailable():
    sessions = {"s1": {"scene_id": "sc1", "story_id": "st1"}}
    resp, meta = await run_scene_turn("s1", "act", sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock(), session_game_system_doc=MagicMock(), gsr_available=True)
    assert "standing by" in resp

def test_pop_conversation_loop():
    _CONVERSATION_LOOPS["s1"] = None
    pop_conversation_loop("s1")
    assert "s1" not in _CONVERSATION_LOOPS

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops._DB_READERS_AVAILABLE", True)
async def test_run_end_scene():
    scene_id = str(uuid.uuid4())
    story_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    session = {"scene_id": scene_id, "story_id": story_id, "universe_id": universe_id}
    sessions = {"s1": session}
    
    mock_loop = AsyncMock()
    _SCENE_LOOPS["s1"] = (("sig",), mock_loop)
    
    with patch("monitor_ui.routers.chat_loops.StoryLoop") as MockSL:
        mock_sl = AsyncMock()
        mock_sl.complete_current_scene.return_value = {"current_scene_id": str(uuid.uuid4()), "story_complete": True}
        MockSL.return_value = mock_sl
        
        with patch("monitor_ui.routers.chat_loops.run_sync_read", new_callable=AsyncMock) as _mock_sync:
            with patch("monitor_ui.routers.chat_loops._generate_scene_summary", new_callable=AsyncMock) as _mock_summ:
                _mock_summ.return_value = "summary"
                resp, meta = await run_end_scene("s1", session, sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock())
                
                assert "world has moved forward" in resp
                assert "conclusion" in resp
                assert meta["scene_status"] == "completed"
                assert meta["scene_loop_reset"] is True

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", True)
async def test_run_end_scene_error():
    session = {"scene_id": str(uuid.uuid4()), "story_id": str(uuid.uuid4()), "universe_id": str(uuid.uuid4())}
    sessions = {"s1": session}
    mock_loop = AsyncMock()
    mock_loop.finalize.side_effect = Exception("failed")
    _SCENE_LOOPS["s1"] = (("sig",), mock_loop)
    resp, meta = await run_end_scene("s1", session, sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock())
    assert "error" in meta
    
    session_no_scene = {"story_id": str(uuid.uuid4())}
    resp, meta = await run_end_scene("s1", session_no_scene, sessions={"s1": session_no_scene}, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock())
    assert "No active scene" in resp

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._RECAP_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.RecapAgent")
async def test_run_recap_command(MockRecap):
    mock_agent = AsyncMock()
    mock_agent.generate_recap.return_value = "Long recap text over 20 chars."
    MockRecap.return_value = mock_agent
    session = {"story_id": str(uuid.uuid4()), "universe_id": str(uuid.uuid4())}
    resp, meta = await run_recap_command(session)
    assert resp == "Long recap text over 20 chars."
    
    mock_agent.generate_recap.return_value = ""
    resp, meta = await run_recap_command(session)
    assert "Every legend starts with a first step." in resp

    mock_agent.generate_recap.side_effect = Exception("failed")
    resp, meta = await run_recap_command(session)
    assert "couldn't gather the story threads" in resp

    resp, meta = await run_recap_command({})
    assert "No story is active" in resp

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._RECAP_AVAILABLE", False)
async def test_run_recap_command_unavailable():
    session = {"story_id": str(uuid.uuid4()), "universe_id": str(uuid.uuid4())}
    resp, meta = await run_recap_command(session)
    assert "not available" in resp

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._CONVERSATION_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.ConversationLoop")
async def test_run_start_conversation(MockCL):
    uid = str(uuid.uuid4())
    session = {"universe_id": uid, "scene_id": str(uuid.uuid4()), "story_id": str(uuid.uuid4())}
    
    with patch("monitor_data.db.neo4j.get_neo4j_client") as MockNeo:
        mock_client = MagicMock()
        mock_client.execute_read.return_value = [{"id": str(uuid.uuid4()), "name": "Bob"}]
        MockNeo.return_value = mock_client
        
        mock_cl_instance = AsyncMock()
        MockCL.start = AsyncMock(return_value=mock_cl_instance)
        
        resp, meta = await run_start_conversation("s1", "Bob", session, db_save_session=MagicMock())
        assert "Bob" in resp
        assert meta["npc_name"] == "Bob"

        # Missing NPC
        mock_client.execute_read.return_value = []
        resp, meta = await run_start_conversation("s1", "Alice", session, db_save_session=MagicMock())
        assert "I don't know anyone named" in resp

        # Exception
        mock_client.execute_read.side_effect = Exception("failed")
        resp, meta = await run_start_conversation("s1", "Alice", session, db_save_session=MagicMock())
        assert "trouble looking up" in resp

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._CONVERSATION_AVAILABLE", False)
async def test_run_start_conversation_unavailable():
    uid = str(uuid.uuid4())
    session = {"universe_id": uid}
    resp, meta = await run_start_conversation("s1", "Bob", session, db_save_session=MagicMock())
    assert "not available" in resp
    
    resp, meta = await run_start_conversation("s1", "Bob", {}, db_save_session=MagicMock())
    assert "No universe is bound" in resp

@pytest.mark.asyncio
async def test_run_conversation_turn():
    mock_loop = AsyncMock()
    mock_loop.step.return_value = [{"npc_name": "Bob", "text": "Hello", "emotional_state": "happy"}]
    _CONVERSATION_LOOPS["s1"] = mock_loop
    
    session = {"conversation_npc_name": "Bob"}
    resp, meta = await run_conversation_turn("s1", "hi", session, db_save_session=MagicMock())
    assert "Bob" in resp
    assert "Hello" in resp
    
    mock_loop.step.return_value = []
    resp, meta = await run_conversation_turn("s1", "hi", session, db_save_session=MagicMock())
    assert "says nothing" in resp

    mock_loop.step.side_effect = Exception("failed")
    resp, meta = await run_conversation_turn("s1", "hi", session, db_save_session=MagicMock())
    assert "breaks off" in resp
    
    resp, meta = await run_conversation_turn("s2", "hi", {}, db_save_session=MagicMock())
    assert "conversation has ended" in resp

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", True)
@patch("monitor_agents.narrator.agent.Narrator")
async def test_generate_scene_summary(MockNarrator):
    mock_narrator = AsyncMock()
    mock_narrator.generate_opening.return_value = "A summary."
    MockNarrator.return_value = mock_narrator
    
    msgs = {"s1": [{"role": "player", "content": "hi"}, {"role": "system", "content": "skip"}]}
    resp = await _generate_scene_summary("s1", msgs)
    assert resp == "A summary."

    msgs = {"s1": []}
    resp = await _generate_scene_summary("s1", msgs)
    assert resp == ""

    mock_narrator.generate_opening.side_effect = Exception("failed")
    resp = await _generate_scene_summary("s1", {"s1": [{"role": "player", "content": "hi"}]})
    assert resp == "The scene concludes."

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._CHARACTER_RESOLUTION_AVAILABLE", True)
async def test_run_ooc_turn():
    with patch("monitor_ui.routers.chat_loops.resolve_actor_character") as mock_resolve:
        mock_char = MagicMock()
        mock_char.model_dump.return_value = {"name": "Bob", "description": "desc", "personality": "pers", "first_message": "hi", "gm_notes": "notes", "is_ooc_persona": True}
        mock_resolve.return_value = mock_char
        
        with patch("monitor_agents.narrator.agent.Narrator") as MockNarrator:
            mock_narrator = AsyncMock()
            mock_narrator.narrate_turn.return_value = {"narrative_text": "resp text"}
            MockNarrator.return_value = mock_narrator
            
            resp, meta = await run_ooc_turn("s1", "hello", "char1", sessions={"s1": {}}, messages={}, db_save_session=MagicMock())
            assert resp == "resp text"
            assert meta["character_name"] == "Bob"

            mock_narrator.narrate_turn.side_effect = Exception("failed")
            resp, meta = await run_ooc_turn("s1", "hello", "char1", sessions={"s1": {}}, messages={}, db_save_session=MagicMock())
            assert "unavailable" in resp

    with patch("monitor_ui.routers.chat_loops.resolve_actor_character") as mock_resolve:
        mock_resolve.return_value = None
        with patch("monitor_ui.routers.character_storage.get_character") as mock_get:
            mock_get.return_value = None
            resp, meta = await run_ooc_turn("s1", "hello", "char1", sessions={"s1": {}}, messages={}, db_save_session=MagicMock())
            assert "Character not found" in resp

@pytest.mark.asyncio
async def test_run_preplay_turn_branches():
    sessions = {"s1": {"phase": "awaiting_character", "system_label": "sys"}}
    
    with patch("monitor_agents.loops.preplay_orchestrator.PreplayOrchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.ainvoke.return_value = {"session_data": {"phase": "next"}, "response_text": "resp", "metadata": {"a": 1}}
        MockOrch.ainvoke = mock_orch.ainvoke
        
        with patch("monitor_ui.routers.chat_opening.fetch_opening_hook", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("failed")
            with patch("monitor_agents.session_zero.ground_world_lore") as mock_ground:
                mock_ground.side_effect = Exception("failed")
                sys_doc = {
                    "character_creation": {}
                }
                resp, meta = await run_preplay_turn(
                    "s1", "hi", sessions=sessions, messages={},
                    db_save_session=MagicMock(), db_save_message=MagicMock(),
                    session_game_system_doc=lambda s: sys_doc, gsr_available=True
                )
                assert resp == "resp"
                
@pytest.mark.asyncio
async def test_run_preplay_turn_session_zero():
    sessions = {"s1": {"phase": "session_zero", "system_label": "sys"}}
    
    with patch("monitor_agents.loops.preplay_orchestrator.PreplayOrchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.ainvoke.return_value = {"session_data": {"phase": "next"}, "response_text": "resp", "metadata": {"a": 1}}
        MockOrch.ainvoke = mock_orch.ainvoke
        
        with patch("monitor_ui.routers.chat_opening.fetch_opening_hook", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("failed")
            with patch("monitor_agents.session_zero.ground_world_lore") as mock_ground:
                mock_ground.side_effect = Exception("failed")
                
                resp, meta = await run_preplay_turn(
                    "s1", "hi", sessions=sessions, messages={},
                    db_save_session=MagicMock(), db_save_message=MagicMock(),
                    session_game_system_doc=None, gsr_available=True
                )
                assert resp == "resp"

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.SceneOrchestrator")
@patch("monitor_ui.routers.chat_loops.resolve_actor_character")
async def test_run_scene_turn_callbacks(mock_resolve, MockSO):
    mock_so = AsyncMock()
    # Intercept callbacks and test them
    def side_effect(state_dict):
        cbs = state_dict["callbacks"]
        cbs.set_story_state_cache("st1", {"a": 1})
        return ("scene out", {"m": 1})

    mock_so.run.side_effect = side_effect
    MockSO.return_value = mock_so
    
    mock_resolve.side_effect = Exception("failed")

    sessions = {"s1": {"scene_id": "sc1", "story_id": "st1"}}
    resp, meta = await run_scene_turn("s1", "act", sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock(), session_game_system_doc=MagicMock(), gsr_available=True)
    assert resp == "scene out"
    assert _STORY_STATES["st1"] == {"a": 1}

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops._DB_READERS_AVAILABLE", True)
async def test_run_end_scene_branches():
    scene_id = str(uuid.uuid4())
    story_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    session = {"scene_id": scene_id, "story_id": story_id, "universe_id": universe_id}
    sessions = {"s1": session}
    
    # Test branch where loop_instance is None
    _SCENE_LOOPS["s1"] = (("sig",), None)
    
    with patch("monitor_ui.routers.chat_loops.StoryLoop") as MockSL:
        mock_sl = AsyncMock()
        mock_sl.complete_current_scene.return_value = {"current_scene_id": None, "story_complete": False}
        MockSL.return_value = mock_sl
        
        with patch("monitor_ui.routers.chat_loops.run_sync_read", new_callable=AsyncMock) as _mock_sync:
            with patch("monitor_ui.routers.chat_loops._generate_scene_summary", new_callable=AsyncMock) as _mock_summ:
                _mock_summ.return_value = "summary"
                resp, meta = await run_end_scene("s1", session, sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock())
                
                assert meta["scene_status"] == "completed"

@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._CONVERSATION_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops.ConversationLoop")
async def test_run_start_conversation_exception(MockCL):
    session = {"universe_id": str(uuid.uuid4()), "scene_id": str(uuid.uuid4()), "story_id": str(uuid.uuid4())}
    with patch("monitor_data.db.neo4j.get_neo4j_client") as MockNeo:
        mock_client = MagicMock()
        mock_client.execute_read.return_value = [{"id": str(uuid.uuid4()), "name": "Bob"}]
        MockNeo.return_value = mock_client
        MockCL.start = AsyncMock(side_effect=Exception("failed start"))
        
        resp, meta = await run_start_conversation("s1", "Bob", session, db_save_session=MagicMock())
        assert "Couldn't start" in resp

@pytest.mark.asyncio
async def test_generate_scene_summary_branches():
    # Only user/gm/player turns are processed
    msgs = {"s1": [{"role": "user", "content": "hi"}, {"role": "gm", "content": "hello"}]}
    with patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", False):
        resp = await _generate_scene_summary("s1", msgs)
        assert resp == "The scene concludes."

def test_cache_popping_exceptions():
    with patch("monitor_ui.routers.chat_loops._SCENE_LOOPS") as mock_loops:
        mock_loops.pop.side_effect = NameError("err")
        pop_scene_loop("s1")
        



def test_import_errors():
    # Save the original modules
    original_modules = dict(sys.modules)
    
    # Block monitor_agents entirely to force ImportError in all try blocks
    with patch.dict('sys.modules', {
        'monitor_agents': None,
        'monitor_agents.llm_errors': None,
        'monitor_agents.loops': None,
        'monitor_agents.loops.scene_loop': None,
        'monitor_agents.loops.world_building_loop': None,
        'monitor_agents.loops.character_creation_loop': None,
        'monitor_agents.loops.session_zero_loop': None,
        'monitor_agents.loops.conversation_loop': None,
        'monitor_agents.recap.agent': None,
        'monitor_data.tools.mongodb_tools': None,
        'monitor_ui.routers.character_resolution': None,
        'monitor_agents.utils.db_readers': None
    }):
        import monitor_ui.routers.chat_loops
        importlib.reload(monitor_ui.routers.chat_loops)
        
        assert getattr(monitor_ui.routers.chat_loops, '_AGENTS_AVAILABLE', True) is False
        assert not monitor_ui.routers.chat_loops._WORLD_ARCHITECT_AVAILABLE
        assert not monitor_ui.routers.chat_loops._CHAR_CREATION_AVAILABLE
        assert not monitor_ui.routers.chat_loops._SESSION_ZERO_AVAILABLE
        assert not monitor_ui.routers.chat_loops._CONVERSATION_AVAILABLE
        assert not monitor_ui.routers.chat_loops._RECAP_AVAILABLE
        assert not monitor_ui.routers.chat_loops._BOOTSTRAP_AVAILABLE
        assert not monitor_ui.routers.chat_loops._CHARACTER_RESOLUTION_AVAILABLE
        assert not monitor_ui.routers.chat_loops._DB_READERS_AVAILABLE
        
    # Restore and reload
    sys.modules.update(original_modules)
    import monitor_ui.routers.chat_loops
    importlib.reload(monitor_ui.routers.chat_loops)

@pytest.mark.asyncio
@patch('monitor_ui.routers.chat_loops._AGENTS_AVAILABLE', True)
@patch('monitor_ui.routers.chat_loops._DB_READERS_AVAILABLE', True)
async def test_run_end_scene_story_complete_branch():
    scene_id = str(uuid.uuid4())
    story_id = str(uuid.uuid4())
    universe_id = str(uuid.uuid4())
    session = {'scene_id': scene_id, 'story_id': story_id, 'universe_id': universe_id}
    sessions = {'s1': session}
    
    _SCENE_LOOPS['s1'] = (('sig',), None)
    
    with patch('monitor_ui.routers.chat_loops.StoryLoop') as MockSL:
        mock_sl = AsyncMock()
        mock_sl.complete_current_scene.return_value = {'current_scene_id': str(uuid.uuid4()), 'story_complete': True}
        MockSL.return_value = mock_sl
        
        with patch('monitor_ui.routers.chat_loops.run_sync_read', new_callable=AsyncMock) as _mock_sync:
            with patch('monitor_ui.routers.chat_loops._generate_scene_summary', new_callable=AsyncMock) as _mock_summ:
                _mock_summ.return_value = 'summary'
                resp, meta = await run_end_scene('s1', session, sessions=sessions, messages={}, db_save_session=MagicMock(), db_load_messages=MagicMock(), bootstrap_story_scene=MagicMock())
                
                assert meta['story_complete'] is True
                assert meta['scene_transition'] is True

@pytest.mark.asyncio
@patch('monitor_ui.routers.chat_loops._WORLD_ARCHITECT_AVAILABLE', True)
@patch('monitor_ui.routers.chat_loops.WorldBuildingLoop')
async def test_run_world_architect_turn_no_ids(MockWBL):
    mock_loop = AsyncMock()
    mock_loop.run.return_value = {'universe_id': None, 'multiverse_id': None, 'response_text': 'text', 'committed_count': 1}
    MockWBL.return_value = mock_loop
    
    sessions = {'s1': {}}
    resp, meta = await run_world_architect_turn('s1', 'build', sessions=sessions, messages={'s1': []}, db_save_session=MagicMock(), db_load_messages=MagicMock())
    assert meta.get('universe_id') is None
    assert meta.get('multiverse_id') is None

@pytest.mark.asyncio
async def test_run_ooc_turn_no_name_and_notes():
    with patch('monitor_ui.routers.chat_loops.resolve_actor_character') as mock_resolve:
        mock_char = MagicMock()
        mock_char.model_dump.return_value = {}
        mock_resolve.return_value = mock_char
        
        with patch('monitor_ui.routers.character_storage.get_character') as mock_get:
            mock_get.return_value = {'id': 'c1'}
            with patch('monitor_agents.narrator.agent.Narrator') as MockNarrator:
                mock_narrator = AsyncMock()
                mock_narrator.narrate_turn.return_value = {'narrative_text': 'resp text'}
                MockNarrator.return_value = mock_narrator
                
                resp, meta = await run_ooc_turn('s1', 'hello', 'char1', sessions={'s1': {}}, messages={}, db_save_session=MagicMock())
                assert resp == 'resp text'
            
@pytest.mark.asyncio
async def test_run_ooc_turn_name_and_notes_only():
    with patch('monitor_ui.routers.chat_loops.resolve_actor_character') as mock_resolve:
        mock_char = MagicMock()
        mock_char.model_dump.return_value = {'name': 'Alice', 'gm_notes': 'notes here'}
        mock_resolve.return_value = mock_char
        
        with patch('monitor_ui.routers.character_storage.get_character') as mock_get:
            mock_get.return_value = {'name': 'Alice', 'gm_notes': 'notes here'}
            with patch('monitor_agents.narrator.agent.Narrator') as MockNarrator:
                mock_narrator = AsyncMock()
                mock_narrator.narrate_turn.return_value = {'narrative_text': 'resp text'}
                MockNarrator.return_value = mock_narrator
                
                resp, meta = await run_ooc_turn('s1', 'hello', 'char1', sessions={'s1': {}}, messages={}, db_save_session=MagicMock())
                assert resp == 'resp text'
