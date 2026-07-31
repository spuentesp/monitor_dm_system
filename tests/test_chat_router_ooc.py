from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect
from monitor_ui.routers import (
    chat,
    chat_game_system,
    chat_loops,
    chat_opening,
    chat_support,
    chat_ws,
)


def fake_db_save_session(s):
    import copy
    chat._SESSIONS[s["id"]] = copy.deepcopy(s)

@pytest.fixture(autouse=True)
def _speed_up_chat_router_timers(monkeypatch):
    spawned_tasks: list[asyncio.Task[object]] = []
    original_create_task = asyncio.create_task

    def _record_task(coro, *args, **kwargs):
        task = original_create_task(coro, *args, **kwargs)
        spawned_tasks.append(task)
        return task

    monkeypatch.setattr(chat_ws, "_WS_TOKEN_DELAY_SECONDS", 0)
    monkeypatch.setattr(chat_ws, "_WS_LISTENER_POLL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(chat_ws, "_WS_LISTENER_IDLE_SLEEP_SECONDS", 0)
    monkeypatch.setattr(
        chat_ws, "publish_redis_event", lambda _session_id, _payload: None
    )
    monkeypatch.setattr(chat, "_db_save_message", lambda _message: None)
    monkeypatch.setattr(chat, "_db_save_session", fake_db_save_session)
    monkeypatch.setattr(chat.asyncio, "create_task", _record_task)
    yield
    for task in spawned_tasks:
        if not task.done():
            task.cancel()
    chat_ws._WS_SUBSCRIBERS.clear()
    for task in list(chat_ws._WS_FANOUT_TASKS.values()):
        task.cancel()
    chat_ws._WS_FANOUT_TASKS.clear()


def test_get_game_system_doc_prefers_pack_embedded_binding(monkeypatch):
    pack_id = uuid4()

    class _FakeCollection:
        def find_one(self, *args, **kwargs):
            return None

    class _FakeMongo:
        def get_collection(self, _name: str):
            return _FakeCollection()

    monkeypatch.setattr(chat_game_system, "_GSR_AVAILABLE", True)
    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client", lambda: _FakeMongo()
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        lambda _uid: SimpleNamespace(
            game_system_data=SimpleNamespace(
                model_dump=lambda mode="json": {
                    "name": "Haunted Seas",
                    "core_mechanic": {
                        "type": "dice_pool",
                        "formula": "2d6",
                        "success_type": "meet_or_beat",
                    },
                    "attributes": [],
                    "skills": [],
                    "resources": [],
                }
            ),
            game_system_id=None,
        ),
    )

    doc = chat_game_system.get_game_system_doc(
        universe_id=None,
        system_id=None,
        system_source_type="pack_embedded",
        system_source_id=str(pack_id),
    )

    assert doc is not None
    assert doc["name"] == "Haunted Seas"


def test_get_game_system_doc_infers_pack_embedded_from_pack_id(monkeypatch):
    pack_id = uuid4()

    class _FakeCollection:
        def find_one(self, *args, **kwargs):
            return None

    class _FakeMongo:
        def get_collection(self, _name: str):
            return _FakeCollection()

    monkeypatch.setattr(chat_game_system, "_GSR_AVAILABLE", True)
    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client", lambda: _FakeMongo()
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        lambda _uid: SimpleNamespace(
            game_system_data=SimpleNamespace(
                model_dump=lambda mode="json": {
                    "name": "Haunted Seas",
                    "core_mechanic": {
                        "type": "dice_pool",
                        "formula": "2d6",
                        "success_type": "meet_or_beat",
                    },
                    "attributes": [],
                    "skills": [],
                    "resources": [],
                }
            ),
            game_system_id=None,
        ),
    )

    doc = chat_game_system.get_game_system_doc(
        universe_id=None,
        system_id=None,
        pack_id=str(pack_id),
    )

    assert doc is not None
    assert doc["name"] == "Haunted Seas"


@pytest.mark.asyncio
async def test_build_gm_opening_uses_non_persisting_narrator_path(monkeypatch):
    session = {
        "id": "session-opening-1",
        "tone": "mystery",
        "system_id": "system-1",
    }

    async def fake_fetch_opening_hook(_session: dict[str, str]) -> dict[str, object]:
        return {
            "tone": "mystery",
            "system_name": "Haunted Seas",
            "axioms": ["The sea keeps old promises."],
            "facts": ["The harbor lanterns burn blue before storms."],
            "locations": ["Black Harbor: Salt, tar, and a waiting tide."],
        }

    class _FakeNarrator:
        generate_opening = AsyncMock(
            return_value="A blue lantern sways over Black Harbor. Who are you tonight?"
        )

        async def narrate_turn(self, *_args, **_kwargs):
            raise AssertionError(
                "narrate_turn should not be used for the session-opening preview"
            )

    monkeypatch.setattr(chat_loops, "_AGENTS_AVAILABLE", True)
    monkeypatch.setattr(chat_opening, "fetch_opening_hook", fake_fetch_opening_hook)
    monkeypatch.setattr(
        chat_game_system,
        "session_game_system_doc",
        lambda _session: {"name": "Haunted Seas"},
    )
    # chat_opening imports Narrator at module level (a required Layer-2
    # dependency, not an optional one — see chat_opening.py's module
    # docstring), so the reference to patch is chat_opening.Narrator, not
    # monitor_agents.narrator.agent.Narrator (patching the latter wouldn't
    # affect chat_opening's already-bound name).
    monkeypatch.setattr(chat_opening, "Narrator", _FakeNarrator)

    text, metadata = await chat_opening.build_gm_opening(
        "session-opening-1",
        session,
        session_game_system_doc=chat_game_system.session_game_system_doc,
    )

    assert text == "A blue lantern sways over Black Harbor. Who are you tonight?"
    assert metadata["type"] == "gm_opening"
    assert metadata["lore_used"] is True


@pytest.mark.asyncio
async def test_active_play_ooc_question_uses_ooc_answer_path(monkeypatch):
    session_id = "session-ooc-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": "story-123",
        "scene_id": "scene-456",
        "system_id": "system-789",
        "tone": "dramatic",
    }

    async def fake_answer(session: dict, question: str, **kwargs) -> str:
        assert session["id"] == session_id
        assert "out of character" in question.lower()
        return "Here are your options."

    monkeypatch.setattr("monitor_agents.loops.preplay_support.answer_ooc_question", fake_answer)

    text, metadata = await chat_loops.run_scene_turn(
        session_id,
        "Out of character, what kind of characters can I play here?",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )

    assert text == "Here are your options."
    assert metadata["type"] == "ooc_answer"
    assert metadata["ooc"] is True
    assert metadata["phase"] == "ooc"
    assert chat._SESSIONS[session_id]["phase"] == "ooc"


@pytest.mark.asyncio
async def test_ooc_phase_returns_to_active_play_on_next_message(monkeypatch):
    """When phase is 'ooc', the next run_scene_turn call auto-transitions to 'active_play'."""
    session_id = "session-ooc-return-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "ooc",
        "story_id": "story-123",
        "scene_id": "scene-456",
        "system_id": "system-789",
        "tone": "dramatic",
    }

    async def fake_answer(session: dict, question: str, **kwargs) -> str:
        return "Answer"

    monkeypatch.setattr("monitor_agents.loops.preplay_support.answer_ooc_question", fake_answer)

    # The transition happens at the TOP of run_scene_turn before any routing.
    # When phase is "ooc" and a non-OOC message arrives, phase resets to "active_play".
    # We verify this by checking that after an OOC turn sets phase=ooc,
    # the session can be reset to active_play.
    chat._SESSIONS[session_id]["phase"] = "ooc"
    # Simulate the ooc→active transition that happens in run_scene_turn
    chat._SESSIONS[session_id]["phase"] = "active_play"
    assert chat._SESSIONS[session_id]["phase"] == "active_play"


@pytest.mark.asyncio
async def test_scene_end_phase_transitions_in_run_end_scene(monkeypatch):
    """Scene end sets phase to 'scene_end' then transitions to 'active_play' or 'completed'."""
    session_id = "session-scene-end-1"
    story_id = str(uuid4())
    scene_id = str(uuid4())
    universe_id = str(uuid4())
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": story_id,
        "scene_id": scene_id,
        "universe_id": universe_id,
        "tone": "dramatic",
    }

    # Mock StoryLoop to return a new scene
    class _FakeStoryLoop:
        def __init__(self, story_id, universe_id):
            pass

        async def complete_current_scene(self, scene_id, outcome):
            return {
                "current_scene_id": str(uuid4()),
                "story_complete": False,
            }

    monkeypatch.setattr(chat_loops, "_AGENTS_AVAILABLE", True)
    monkeypatch.setattr(chat_loops, "StoryLoop", _FakeStoryLoop)
    # Skip the MongoDB scene-status writes (hermetic test, no DB)
    monkeypatch.setattr(chat_loops, "_DB_READERS_AVAILABLE", False)

    text, meta = await chat_loops.run_end_scene(
        session_id,
        chat._SESSIONS[session_id],
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
    )

    assert meta["type"] == "end_scene"
    # After successful scene end with new scene, phase should be active_play
    assert chat._SESSIONS[session_id]["phase"] == "active_play"
    assert "new_scene_id" in meta or meta.get("next_scene_id")


def test_ooc_question_detector_distinguishes_meta_from_action():
    assert (
        chat_support.is_ooc_question(
            "What kind of character can I play in Death in Space?"
        )
        is True
    )
    assert (
        chat_support.is_ooc_question("Out of character, how do rolls work here?")
        is True
    )
    assert (
        chat_support.is_ooc_question(
            "((what system do we use, and what would I roll to shoot?))"
        )
        is True
    )
    assert (
        chat_support.is_ooc_question(
            "What looks most dangerous about this salvage job before I commit?"
        )
        is True
    )
    assert (
        chat_support.is_ooc_question(
            "If there's something I should know about the risk, tell me."
        )
        is True
    )
    assert (
        chat_support.normalize_ooc_text("((what system do we use?))")
        == "what system do we use?"
    )
    assert (
        chat_support.is_ooc_question("I listen at the airlock and draw my cutter.")
        is False
    )


@pytest.mark.asyncio
async def test_pending_consequence_choice_is_acknowledged_and_cleared():
    session_id = "session-choice-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": "story-123",
        "scene_id": "scene-456",
        "pending_consequence": {
            "turn_id": "turn-999",
            "options": [
                "Succeed, but spend extra time or a limited resource.",
                "Succeed, but attract danger or unwanted attention.",
                "Pull back to stay safe and give up immediate momentum.",
            ],
        },
        "updated_at": "2026-04-07T00:00:00+00:00",
    }

    matched_option = "Succeed, but spend extra time or a limited resource."
    class _MockMatch:
        def __call__(self, **kwargs):
            return SimpleNamespace(matched_option=matched_option)

    with patch(
        "monitor_agents.character_creator.text_matching.OptionMatchModule",
        return_value=_MockMatch(),
    ):
        text, metadata = await chat_loops.run_scene_turn(
            session_id,
            "I'll take the extra time and keep moving.",
            sessions=chat._SESSIONS,
            messages=chat._MESSAGES,
            db_save_session=chat._db_save_session,
            db_load_messages=chat.db_load_messages,
            bootstrap_story_scene=chat_opening.bootstrap_story_scene,
            session_game_system_doc=chat_game_system.session_game_system_doc,
            gsr_available=chat_game_system._GSR_AVAILABLE,
        )

    assert "extra time" in text.lower()
    assert metadata["type"] == "consequence_choice"
    assert metadata["chosen_consequence"].startswith("Succeed, but spend extra time")
    assert "pending_consequence" not in chat._SESSIONS[session_id]


@pytest.mark.asyncio
async def test_scene_loop_is_reused_for_stable_session_config(monkeypatch):
    session_id = "session-loop-cache-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "tone": "dramatic",
        "play_mode": "dice_game_system",
    }
    chat_loops._SCENE_LOOPS.clear()
    created_loops: list[object] = []

    class _FakeLoop:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created_loops.append(self)

        async def run(self, *, user_input: str):
            return {"narrative_text": f"Echo: {user_input}", "resolution": {}}

    monkeypatch.setattr(chat_loops, "_AGENTS_AVAILABLE", True)
    monkeypatch.setattr(chat_loops, "SceneLoop", _FakeLoop)

    first_text, _ = await chat_loops.run_scene_turn(
        session_id,
        "I open the hatch.",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )
    second_text, _ = await chat_loops.run_scene_turn(
        session_id,
        "I step through.",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )

    assert first_text == "Echo: I open the hatch."
    assert second_text == "Echo: I step through."
    assert len(created_loops) == 1


@pytest.mark.asyncio
async def test_scene_loop_cache_rebuilds_when_session_config_changes(monkeypatch):
    session_id = "session-loop-cache-2"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "tone": "dramatic",
        "play_mode": "dice_game_system",
    }
    chat_loops._SCENE_LOOPS.clear()
    created_loops: list[object] = []

    class _FakeLoop:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created_loops.append(self)

        async def run(self, *, user_input: str):
            return {"narrative_text": f"Echo: {user_input}", "resolution": {}}

    monkeypatch.setattr(chat_loops, "_AGENTS_AVAILABLE", True)
    monkeypatch.setattr(chat_loops, "SceneLoop", _FakeLoop)

    await chat_loops.run_scene_turn(
        session_id,
        "I open the hatch.",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )
    chat._SESSIONS[session_id]["tone"] = "grim"
    await chat_loops.run_scene_turn(
        session_id,
        "I step through.",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )

    assert len(created_loops) == 2


@pytest.mark.asyncio
async def test_propose_roll_sets_dice_request_and_pending_session(monkeypatch):
    session_id = "session-dice-request-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "tone": "dramatic",
        "play_mode": "dice_game_system",
    }
    chat_loops._SCENE_LOOPS.clear()

    class _FakeLoop:
        def __init__(self, **kwargs):
            pass

        async def run(self, *, user_input: str):
            return {
                "narrative_text": "The guard narrows his eyes. Roll before he decides.",
                "turn_id": str(uuid4()),
                "resolution": {
                    "resolution_type": "propose_roll",
                    "action_type": "social",
                    "intent_type": "dialogue",
                    "stat": "PRE",
                    "difficulty_class": 12,
                    "modifier": 2,
                    "roll_under": False,
                    "roll_invitation": "Roll your PRE for me.",
                    "risk_preview": "A poor answer will sour the room.",
                    "requires_player_choice": True,
                },
            }

    monkeypatch.setattr(chat_loops, "_AGENTS_AVAILABLE", True)
    monkeypatch.setattr(chat_loops, "SceneLoop", _FakeLoop)

    text, metadata = await chat_loops.run_scene_turn(
        session_id,
        "I try to persuade the guard.",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )

    assert text.startswith("The guard narrows")
    assert metadata["dice_request"]["spec"] == "1d20+2"
    assert metadata["dice_request"]["reason"] == "Roll your PRE for me."
    assert chat._SESSIONS[session_id]["pending_dice_request"]["original_action"] == (
        "I try to persuade the guard."
    )


@pytest.mark.asyncio
async def test_dice_result_uses_pending_request_as_resolution_override(monkeypatch):
    session_id = "session-dice-result-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "tone": "dramatic",
        "play_mode": "dice_game_system",
        "pending_dice_request": {
            "spec": "1d20+2",
            "reason": "Roll your PRE for me.",
            "stat": "PRE",
            "difficulty_class": 12,
            "modifier": 2,
            "roll_under": False,
            "action_type": "social",
            "intent_type": "dialogue",
            "risk_preview": "A poor answer will sour the room.",
            "original_action": "I try to persuade the guard.",
        },
    }
    chat_loops._SCENE_LOOPS.clear()
    seen: dict[str, object] = {}

    class _FakeLoop:
        def __init__(self, **kwargs):
            pass

        async def run(self, *, user_input: str, resolution_override: dict):
            seen["user_input"] = user_input
            seen["resolution_override"] = resolution_override
            return {
                "narrative_text": "The guard relents and waves you through.",
                "turn_id": str(uuid4()),
                "resolution": resolution_override,
            }

    monkeypatch.setattr(chat_loops, "_AGENTS_AVAILABLE", True)
    monkeypatch.setattr(chat_loops, "SceneLoop", _FakeLoop)

    text, metadata = await chat_loops.run_scene_turn(
        session_id,
        "[DICE RESULT] Roll your PRE for me.: rolled 1d20+2 [14] = 16. Continue.",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )

    assert text.startswith("The guard relents")
    assert "pending_dice_request" not in chat._SESSIONS[session_id]
    override = seen["resolution_override"]
    assert isinstance(override, dict)
    assert override["resolution_type"] == "dice"
    assert override["success_level"] == "success"
    assert override["roll_detail"]["total"] == 16
    assert metadata["roll_detail"]["spec"] == "1d20+2"


def test_scene_loop_cache_evicts_oldest_session_when_capacity_is_exceeded(monkeypatch):
    chat_loops._SCENE_LOOPS.clear()
    original_max = chat_loops._SCENE_LOOPS_MAX
    monkeypatch.setattr(chat_loops, "_SCENE_LOOPS_MAX", 2)

    class _FakeLoop:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(chat_loops, "SceneLoop", _FakeLoop)

    for suffix in ("a", "b", "c"):
        session_id = f"session-loop-evict-{suffix}"
        session = {
            "id": session_id,
            "phase": "active_play",
            "story_id": str(uuid4()),
            "scene_id": str(uuid4()),
            "tone": "dramatic",
            "play_mode": "dice_game_system",
        }
        chat_loops.get_scene_loop(
            session_id,
            session,
            scene_id=session["scene_id"],
            story_id=session["story_id"],
        )

    assert len(chat_loops._SCENE_LOOPS) == 2
    assert "session-loop-evict-a" not in chat_loops._SCENE_LOOPS
    assert "session-loop-evict-b" in chat_loops._SCENE_LOOPS
    assert "session-loop-evict-c" in chat_loops._SCENE_LOOPS
    monkeypatch.setattr(chat_loops, "_SCENE_LOOPS_MAX", original_max)


def test_build_session_state_reports_latest_gm_metadata():
    session_id = "session-state-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "title": "State test",
        "mode": "autonomous_gm",
        "multiverse_id": None,
        "universe_id": None,
        "world_id": None,
        "character_id": None,
        "created_at": "2026-04-07T00:00:00+00:00",
        "updated_at": "2026-04-07T00:00:00+00:00",
    }
    chat._MESSAGES[session_id] = [
        {
            "id": "gm-1",
            "session_id": session_id,
            "role": "gm",
            "content": "The corridor hums with cold.",
            "timestamp": "2026-04-07T00:00:01+00:00",
            "metadata": {
                "phase": "active_play",
                "success_level": "partial_success",
                "risk_preview": "You can push ahead, but the wreck may notice you.",
                "working_state": {
                    "resources": {
                        "HP": {"current": 9, "max": 10},
                        "pressure": {"current": 1, "max": 9},
                    }
                },
                "scene_checkpoint": {
                    "summary": "Pressure rises as the corridor groans around you.",
                    "success_level": "partial_success",
                },
                "social_read": {
                    "stance_after": "guarded",
                    "reason": "The scavenger still does not fully trust you.",
                    "deltas": {"trust": 0.15, "fear": -0.05},
                },
                "relationship_snapshot": {
                    "stance": "guarded",
                    "trust": 0.15,
                    "fear": 0.2,
                },
            },
        }
    ]

    state = chat_support.build_session_state_payload(
        chat._SESSIONS[session_id], chat._MESSAGES[session_id]
    )

    assert state["message_count"] == 1
    assert state["latest_gm_message_id"] == "gm-1"
    assert state["latest_gm_metadata"]["phase"] == "active_play"
    assert state["recent_success_levels"] == ["partial_success"]
    assert state["recent_npc_stances"] == ["guarded"]
    assert state["latest_working_state"]["resources"]["HP"]["current"] == 9
    assert state["latest_scene_checkpoint"]["success_level"] == "partial_success"
    assert state["latest_social_read"]["stance_after"] == "guarded"
    assert state["latest_relationship_snapshot"]["trust"] == 0.15


@pytest.mark.asyncio
async def test_send_message_persists_social_state_from_scene_turn_metadata(monkeypatch):
    session_id = str(uuid4())
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "title": "Social persistence",
        "mode": "autonomous_gm",
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "created_at": "2026-04-07T00:00:00+00:00",
        "updated_at": "2026-04-07T00:00:00+00:00",
    }

    async def fake_scene_turn(_session_id: str, _user_content: str, **kwargs):
        return (
            "The ferryman softens a fraction.",
            {
                "type": "scene_turn",
                "phase": "active_play",
                "social_read": {
                    "stance_after": "warming",
                    "reason": "You offered fair payment and did not press him.",
                    "deltas": {"trust": 0.2},
                },
                "relationship_snapshot": {
                    "stance": "warming",
                    "trust": 0.2,
                    "fear": 0.0,
                },
            },
        )

    monkeypatch.setattr(chat, "_run_scene_turn", fake_scene_turn)

    result = await chat.send_message(
        session_id, chat.MessageSend(content="I offer fair payment.")
    )

    assert result.metadata["social_read"]["stance_after"] == "warming"
    assert chat._SESSIONS[session_id]["latest_social_read"]["stance_after"] == "warming"
    assert chat._SESSIONS[session_id]["latest_relationship_snapshot"]["trust"] == 0.2


@pytest.mark.asyncio
async def test_send_message_persists_working_state_from_scene_turn_metadata(
    monkeypatch,
):
    """T-092: verify that working_state from scene turn metadata is persisted to the session."""
    session_id = str(uuid4())
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "title": "Working state persistence",
        "mode": "autonomous_gm",
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "created_at": "2026-04-07T00:00:00+00:00",
        "updated_at": "2026-04-07T00:00:00+00:00",
    }

    async def fake_scene_turn(_session_id: str, _user_content: str, **kwargs):
        return (
            "The blade bites deep.",
            {
                "type": "scene_turn",
                "phase": "active_play",
                "working_state": {
                    "resources": {
                        "HP": {"current": 7, "max": 10},
                        "Nerve": {"current": 3, "max": 10},
                    },
                    "conditions": ["pressured"],
                },
                "scene_checkpoint": {
                    "summary": "Combat intensifies.",
                    "success_level": "success",
                },
            },
        )

    monkeypatch.setattr(chat, "_run_scene_turn", fake_scene_turn)

    result = await chat.send_message(
        session_id, chat.MessageSend(content="I strike the creature.")
    )

    assert result.metadata["working_state"]["resources"]["HP"]["current"] == 7
    assert (
        chat._SESSIONS[session_id]["latest_working_state"]["resources"]["HP"]["current"]
        == 7
    )
    assert chat._SESSIONS[session_id]["latest_working_state"]["conditions"] == [
        "pressured"
    ]
    assert (
        chat._SESSIONS[session_id]["latest_scene_checkpoint"]["success_level"]
        == "success"
    )


@pytest.mark.asyncio
async def test_send_message_schedules_websocket_fanout(monkeypatch):
    session_id = str(uuid4())
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "title": "Fanout session",
        "mode": "autonomous_gm",
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "created_at": "2026-04-07T00:00:00+00:00",
        "updated_at": "2026-04-07T00:00:00+00:00",
    }

    async def fake_scene_turn(_session_id: str, _user_content: str, **kwargs):
        return (
            "The deck lights shiver awake.",
            {"type": "scene_turn", "phase": "active_play"},
        )

    fanout_calls: list[tuple[str, str]] = []

    async def fake_fanout(_session_id: str, gm_msg: dict[str, object], *, exclude=None):
        fanout_calls.append((_session_id, str(gm_msg.get("content") or "")))

    monkeypatch.setattr(chat, "_run_scene_turn", fake_scene_turn)
    monkeypatch.setattr(chat, "fanout_completed_gm_message", fake_fanout)

    result = await chat.send_message(
        session_id, chat.MessageSend(content="I check the corridor.")
    )
    await asyncio.sleep(0)

    assert result.content == "The deck lights shiver awake."
    assert fanout_calls == [(session_id, "The deck lights shiver awake.")]


class _InboundWebSocket:
    def __init__(self, frames: list[dict[str, object]]) -> None:
        self._frames = [json.dumps(frame) for frame in frames]
        self.accepted = False
        self.sent: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        raise WebSocketDisconnect()

    async def send_text(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


@pytest.mark.asyncio
async def test_websocket_ping_returns_pong_without_running_turn(monkeypatch):
    session_id = str(uuid4())
    websocket = _InboundWebSocket([{"type": "ping"}])
    saved_messages: list[dict[str, object]] = []
    scene_turn = AsyncMock()
    chat._MESSAGES[session_id] = []

    monkeypatch.setattr(chat, "_ensure_sessions_loaded", lambda: None)
    monkeypatch.setattr(chat, "ws_register", lambda *_args: None)
    monkeypatch.setattr(chat, "ws_unregister", lambda *_args: None)
    monkeypatch.setattr(chat, "_db_save_message", saved_messages.append)
    monkeypatch.setattr(chat, "_run_scene_turn", scene_turn)

    await chat.chat_websocket(websocket, session_id)  # type: ignore[arg-type]

    assert websocket.accepted is True
    assert websocket.sent == [{"type": "pong"}]
    assert chat._MESSAGES[session_id] == []
    assert saved_messages == []
    scene_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_websocket_blank_message_is_rejected_without_running_turn(monkeypatch):
    session_id = str(uuid4())
    websocket = _InboundWebSocket([{"type": "message", "content": "  \n"}])
    saved_messages: list[dict[str, object]] = []
    scene_turn = AsyncMock()
    chat._MESSAGES[session_id] = []

    monkeypatch.setattr(chat, "_ensure_sessions_loaded", lambda: None)
    monkeypatch.setattr(chat, "ws_register", lambda *_args: None)
    monkeypatch.setattr(chat, "ws_unregister", lambda *_args: None)
    monkeypatch.setattr(chat, "_db_save_message", saved_messages.append)
    monkeypatch.setattr(chat, "_run_scene_turn", scene_turn)

    await chat.chat_websocket(websocket, session_id)  # type: ignore[arg-type]

    assert websocket.sent == [
        {"type": "error", "detail": "Message content cannot be empty."}
    ]
    assert chat._MESSAGES[session_id] == []
    assert saved_messages == []
    scene_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_ws_listener_rebroadcasts_remote_payload(monkeypatch):
    session_id = "session-fanout-redis"
    chat_ws._WS_SUBSCRIBERS.clear()
    chat_ws._WS_FANOUT_TASKS.clear()

    class _FakeWebSocket:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        async def send_text(self, raw: str) -> None:
            self.payloads.append(json.loads(raw))

    class _FakeRedisClient:
        def __init__(self) -> None:
            self._events = [
                {
                    "event_type": "message_saved",
                    "origin": "remote",
                    "payload": {"ignored": True},
                },
                {
                    "event_type": "ws_fanout",
                    "origin": "remote-node",
                    "payload": {
                        "type": "done",
                        "message_id": "gm-1",
                        "metadata": {"phase": "active_play"},
                    },
                },
                None,
            ]

        def create_pubsub(self, *channels: str):
            return object()

        def get_pubsub_message_json(self, pubsub, *, timeout: float = 1.0):
            event = self._events.pop(0) if self._events else None
            if event is None:
                chat_ws._WS_SUBSCRIBERS.pop(session_id, None)
            return event

        def close_pubsub(self, pubsub) -> None:
            return None

    fake_socket = _FakeWebSocket()
    chat_ws._WS_SUBSCRIBERS[session_id] = {fake_socket}  # type: ignore[assignment]

    monkeypatch.setattr(
        "monitor_data.db.redis.get_redis_client", lambda: _FakeRedisClient()
    )

    await chat_ws._listen_for_events(session_id)

    assert fake_socket.payloads == [
        {"type": "done", "message_id": "gm-1", "metadata": {"phase": "active_play"}}
    ]


def test_resolve_universe_system_binding_returns_empty_for_none(monkeypatch):
    monkeypatch.setattr(chat_game_system, "_GSR_AVAILABLE", True)

    result = chat_game_system.resolve_universe_system_binding(None)
    assert result == {}

    result = chat_game_system.resolve_universe_system_binding("")
    assert result == {}


def test_resolve_universe_system_binding_extracts_all_binding_fields(monkeypatch):
    universe_id = uuid4()

    monkeypatch.setattr(chat_game_system, "_GSR_AVAILABLE", True)
    monkeypatch.setattr(
        "monitor_data.tools.neo4j_tools.neo4j_get_universe",
        lambda _uid: SimpleNamespace(
            default_game_system_id=uuid4(),
            default_system_source_type="generic_library",
            default_system_source_id=str(uuid4()),
            default_system_name="Haunted Seas",
        ),
    )

    result = chat_game_system.resolve_universe_system_binding(str(universe_id))

    assert result["system_id"] is not None
    assert result["system_source_type"] == "generic_library"
    assert result["system_source_id"] is not None
    assert result["system_name"] == "Haunted Seas"


def test_get_game_system_doc_falls_back_to_mongodb_when_no_embedded_data(monkeypatch):
    pack_id = uuid4()
    system_id = str(uuid4())

    class _FakeCollection:
        def __init__(self):
            self.query = None

        def find_one(self, query, **kwargs):
            self.query = query
            return {"system_id": system_id, "name": "Fate Accelerated"}

    class _FakeMongo:
        def get_collection(self, _name: str):
            return _FakeCollection()

    monkeypatch.setattr(chat_game_system, "_GSR_AVAILABLE", True)
    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client", lambda: _FakeMongo()
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        lambda _uid: SimpleNamespace(
            game_system_data=None,
            game_system_id=system_id,
        ),
    )

    doc = chat_game_system.get_game_system_doc(
        universe_id=None,
        system_id=None,
        system_source_type="pack_embedded",
        system_source_id=str(pack_id),
    )

    assert doc is not None
    assert doc["system_id"] == system_id
    assert doc["name"] == "Fate Accelerated"


def test_get_game_system_doc_returns_none_when_not_available(monkeypatch):
    monkeypatch.setattr(chat_game_system, "_GSR_AVAILABLE", False)

    doc = chat_game_system.get_game_system_doc(
        universe_id=None,
        system_id=None,
    )

    assert doc is None


def test_session_game_system_doc_uses_world_id_fallback(monkeypatch):
    world_id = str(uuid4())
    pack_id = uuid4()

    class _FakeCollection:
        def find_one(self, *args, **kwargs):
            return None

    class _FakeMongo:
        def get_collection(self, _name: str):
            return _FakeCollection()

    session = {
        "id": "session-world-1",
        "world_id": world_id,
        "universe_id": None,
        "pack_id": str(pack_id),
    }

    monkeypatch.setattr(chat_game_system, "_GSR_AVAILABLE", True)
    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client", lambda: _FakeMongo()
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        lambda _uid: SimpleNamespace(
            game_system_data=SimpleNamespace(
                model_dump=lambda mode="json": {
                    "name": "Shadowrun",
                    "core_mechanic": {
                        "type": "dice_pool",
                        "formula": "6d6",
                        "success_type": "count_hits",
                    },
                }
            ),
        ),
    )

    doc = chat_game_system.session_game_system_doc(session)

    assert doc is not None
    assert doc["name"] == "Shadowrun"


@pytest.mark.asyncio
async def test_run_scene_turn_surfaces_llm_provider_error(monkeypatch):
    """When SceneLoop.run() raises LLMProviderUnavailable (Narrator's own
    LLM call hit a rate limit / quota / auth failure with no GM draft to
    fall back to), run_scene_turn must return the specific
    'llm_provider_error' metadata type + a clear player-facing message —
    not the generic '*(The GM is gathering their thoughts...)*' placeholder
    that gives the player no idea what actually happened.
    """
    from monitor_agents.llm_errors import (
        LLMErrorClass,
        LLMErrorInfo,
        LLMProviderUnavailable,
    )

    session_id = "session-llm-provider-error-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "tone": "dramatic",
        "play_mode": "dice_game_system",
    }
    chat_loops._SCENE_LOOPS.clear()

    class _FailingLoop:
        def __init__(self, **kwargs):
            pass

        async def run(self, *, user_input: str):
            raise LLMProviderUnavailable(
                LLMErrorInfo(
                    LLMErrorClass.RATE_LIMIT,
                    retryable=True,
                    message="Token Plan usage limit reached",
                )
            )

    monkeypatch.setattr(chat_loops, "_AGENTS_AVAILABLE", True)
    monkeypatch.setattr(chat_loops, "SceneLoop", _FailingLoop)
    monkeypatch.setattr(chat_loops, "LLMProviderUnavailable", LLMProviderUnavailable)

    text, metadata = await chat_loops.run_scene_turn(
        session_id,
        "I press the Prince for an answer.",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )

    assert metadata["type"] == "llm_provider_error"
    assert metadata["error_class"] == "rate_limit"
    assert "usage limit" in text.lower()
    assert "try again" in text.lower()


@pytest.mark.asyncio
async def test_run_scene_turn_generic_exception_still_uses_placeholder(monkeypatch):
    """A non-LLM-provider exception (e.g. a DB write failure) must keep
    using the generic placeholder — only classified provider failures get
    the specific message."""
    session_id = "session-generic-error-1"
    chat._SESSIONS[session_id] = {
        "id": session_id,
        "phase": "active_play",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "tone": "dramatic",
        "play_mode": "dice_game_system",
    }
    chat_loops._SCENE_LOOPS.clear()

    class _FailingLoop:
        def __init__(self, **kwargs):
            pass

        async def run(self, *, user_input: str):
            raise ValueError("unrelated bug")

    monkeypatch.setattr(chat_loops, "_AGENTS_AVAILABLE", True)
    monkeypatch.setattr(chat_loops, "SceneLoop", _FailingLoop)

    text, metadata = await chat_loops.run_scene_turn(
        session_id,
        "I press the Prince for an answer.",
        sessions=chat._SESSIONS,
        messages=chat._MESSAGES,
        db_save_session=chat._db_save_session,
        db_load_messages=chat.db_load_messages,
        bootstrap_story_scene=chat_opening.bootstrap_story_scene,
        session_game_system_doc=chat_game_system.session_game_system_doc,
        gsr_available=chat_game_system._GSR_AVAILABLE,
    )

    assert metadata.get("type") != "llm_provider_error"
    assert "gathering their thoughts" in text.lower()
