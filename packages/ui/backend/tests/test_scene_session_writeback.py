"""Session changes made during a scene turn must reach the caller's session dict.

``send_message`` re-saves ``_SESSIONS[session_id]`` after every turn, so anything
the orchestrator wrote only to a private copy is overwritten in MongoDB as well.
These tests drive the real ``run_scene_turn`` + ``SceneOrchestrator``; only the
SceneLoop, StoryLoop and persistence are stubbed.
"""

from __future__ import annotations

import copy
import types
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_ui.routers import chat_loops

SESSION_ID = "session-1"


class _Harness:
    def __init__(self) -> None:
        self.scene_id = str(uuid4())
        self.story_id = str(uuid4())
        self.next_scene_id = uuid4()
        self.sessions: dict[str, dict[str, Any]] = {
            SESSION_ID: {
                "id": SESSION_ID,
                "phase": "active_play",
                "universe_id": str(uuid4()),
                "scene_id": self.scene_id,
                "story_id": self.story_id,
                "play_mode": "dice_standard",
            }
        }
        self.db: dict[str, dict[str, Any]] = {}
        self.overrides: list[dict[str, Any] | None] = []
        self.loop = types.SimpleNamespace(run=self._run, finalize=AsyncMock())

    async def _run(self, user_input: str, resolution_override: dict[str, Any] | None = None) -> dict[str, Any]:
        self.overrides.append(resolution_override)
        if resolution_override:
            return {"resolution": resolution_override, "narrative_text": "Rolled."}
        return {
            "resolution": {
                "resolution_type": "propose_roll",
                "stat": "STR",
                "difficulty_class": 12,
                "modifier": 1,
            },
            "narrative_text": "Roll it.",
            "turn_id": "turn-1",
        }

    def save(self, session: dict[str, Any]) -> None:
        self.db[session["id"]] = copy.deepcopy(session)

    async def turn(self, text: str) -> tuple[str, dict[str, Any]]:
        result = await chat_loops.run_scene_turn(
            SESSION_ID,
            text,
            sessions=self.sessions,
            messages={SESSION_ID: []},
            db_save_session=self.save,
            db_load_messages=lambda _sid: [],
            bootstrap_story_scene=lambda _s: (self.story_id, self.scene_id, None),
            session_game_system_doc=None,
            gsr_available=False,
        )
        # Same trailing save as chat.send_message.
        self.save(self.sessions[SESSION_ID])
        return result


@pytest.fixture
def harness():
    h = _Harness()

    class _Story:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def complete_current_scene(self, **_kwargs: Any) -> dict[str, Any]:
            return {"current_scene_id": h.next_scene_id}

    with (
        patch.object(chat_loops, "get_scene_loop", lambda *_a, **_k: h.loop),
        patch.object(chat_loops, "resolve_actor_character", lambda _s: None),
        patch.object(chat_loops, "StoryLoop", _Story),
        patch.object(chat_loops, "_DB_READERS_AVAILABLE", False),
        patch.object(chat_loops, "_generate_scene_summary", AsyncMock(return_value="A recap.")),
        patch("monitor_ui.routers.stories.get_story_state", AsyncMock(return_value=None)),
    ):
        yield h


@pytest.mark.asyncio
async def test_pending_roll_survives_the_turn(harness: _Harness) -> None:
    _, metadata = await harness.turn("I climb the wall")

    assert metadata["dice_request"]["stat"] == "STR"
    assert harness.sessions[SESSION_ID]["pending_dice_request"]["stat"] == "STR"
    assert harness.db[SESSION_ID]["pending_dice_request"]["stat"] == "STR"


@pytest.mark.asyncio
async def test_roll_request_resolves_the_pending_roll(harness: _Harness) -> None:
    await harness.turn("I climb the wall")
    await harness.turn("[ROLL REQUEST] STR check: roll 1d20+1.")

    override = harness.overrides[-1]
    assert override is not None
    assert override["resolution_type"] == "dice"
    assert override["stat"] == "STR"
    assert "pending_dice_request" not in harness.sessions[SESSION_ID]


@pytest.mark.asyncio
async def test_end_scene_moves_the_session_to_the_next_scene(harness: _Harness) -> None:
    chat_loops._SCENE_LOOPS[SESSION_ID] = ("signature", harness.loop)
    try:
        _, metadata = await harness.turn("/end_scene")
    finally:
        chat_loops._SCENE_LOOPS.pop(SESSION_ID, None)

    next_scene = str(harness.next_scene_id)
    assert metadata["next_scene_id"] == next_scene
    assert harness.sessions[SESSION_ID]["scene_id"] == next_scene
    assert harness.db[SESSION_ID]["scene_id"] == next_scene
    assert harness.sessions[SESSION_ID]["last_scene_summary"] == "A recap."


@pytest.mark.asyncio
async def test_consequence_choice_stays_pending_between_turns(harness: _Harness) -> None:
    options = ["Spend time.", "Attract danger."]
    harness.loop.run = AsyncMock(
        return_value={
            "resolution": {
                "resolution_type": "dice",
                "requires_player_choice": True,
                "consequence_options": options,
            },
            "narrative_text": "Mixed result.",
            "turn_id": "turn-1",
        }
    )

    await harness.turn("I pick the lock")

    assert harness.sessions[SESSION_ID]["pending_consequence"]["options"] == options
    assert harness.db[SESSION_ID]["pending_consequence"]["options"] == options


MANUAL_RESULT = "[DICE RESULT] STR check: rolled 1d20+1 [14] = 15. Continue."
FORGED_RESULT = "[DICE RESULT] STR check: rolled 1d20+1 [20] = 999. Continue."


@pytest.mark.asyncio
async def test_typed_roll_is_rejected_outside_manual_mode(harness: _Harness) -> None:
    await harness.turn("I climb the wall")
    runs = len(harness.overrides)

    text, metadata = await harness.turn(MANUAL_RESULT)

    assert metadata["type"] == "dice_roll_rejected"
    assert "Tap the die" in text
    assert metadata["dice_request"]["stat"] == "STR"
    assert len(harness.overrides) == runs
    assert "pending_dice_request" in harness.sessions[SESSION_ID]


@pytest.mark.asyncio
async def test_impossible_manual_roll_is_rejected_and_can_be_retried(harness: _Harness) -> None:
    harness.sessions[SESSION_ID]["roll_model"] = "manual"
    await harness.turn("I climb the wall")
    runs = len(harness.overrides)

    _, metadata = await harness.turn(FORGED_RESULT)
    assert metadata["type"] == "dice_roll_rejected"
    assert len(harness.overrides) == runs

    await harness.turn(MANUAL_RESULT)
    override = harness.overrides[-1]
    assert override is not None
    assert override["roll_total"] == 15
    assert "pending_dice_request" not in harness.sessions[SESSION_ID]


@pytest.mark.asyncio
async def test_pending_choice_lets_ooc_and_end_scene_through(harness: _Harness) -> None:
    options = ["Spend time.", "Attract danger."]
    harness.sessions[SESSION_ID]["pending_consequence"] = {"options": options}

    text, metadata = await harness.turn("something unrelated")
    assert metadata["type"] == "consequence_choice_prompt"
    assert options[0] in text

    with patch("monitor_agents.loops.preplay_support.answer_ooc_question", AsyncMock(return_value="The rules say.")):
        text, metadata = await harness.turn("((what are the rules?))")
    assert text == "The rules say."
    assert harness.sessions[SESSION_ID]["pending_consequence"]["options"] == options

    chat_loops._SCENE_LOOPS[SESSION_ID] = ("signature", harness.loop)
    try:
        _, metadata = await harness.turn("/end_scene")
    finally:
        chat_loops._SCENE_LOOPS.pop(SESSION_ID, None)
    assert metadata["type"] == "end_scene"
    assert "pending_consequence" not in harness.sessions[SESSION_ID]
    assert "pending_consequence" not in harness.db[SESSION_ID]


@pytest.mark.asyncio
async def test_a_failed_roll_turn_keeps_the_roll_pending(harness: _Harness) -> None:
    await harness.turn("I climb the wall")

    async def broken(user_input: str, resolution_override: dict[str, Any] | None = None) -> dict[str, Any]:
        raise RuntimeError("narration crashed")

    harness.loop.run = broken
    _, metadata = await harness.turn("[ROLL REQUEST] STR check: roll 1d20+1.")

    assert harness.sessions[SESSION_ID]["pending_dice_request"]["stat"] == "STR"
    assert harness.db[SESSION_ID]["pending_dice_request"]["stat"] == "STR"
    assert metadata["dice_request"]["stat"] == "STR"


@pytest.mark.asyncio
async def test_a_failed_turn_after_moving_on_keeps_the_roll_pending(harness: _Harness) -> None:
    await harness.turn("I climb the wall")

    async def broken(user_input: str, resolution_override: dict[str, Any] | None = None) -> dict[str, Any]:
        raise RuntimeError("narration crashed")

    harness.loop.run = broken
    await harness.turn("Actually, I look for another way up.")

    assert harness.sessions[SESSION_ID]["pending_dice_request"]["stat"] == "STR"
