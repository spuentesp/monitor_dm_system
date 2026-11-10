"""Scene-cast refresh + speaker switching (Phase 4 Tasks 1, 3).

Two controlled characters alternate as speaker; each ``get_scene_loop`` call
must refresh the cast carried on the loop (``SceneLoop.cast`` →
``SceneState.cast``) so the next turn sees who is speaking now.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

from monitor_ui.routers import chat_loops


class _FakeLoop:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.chat_log = kwargs.get("chat_log")
        self.cast = kwargs.get("cast")


CHAR_A = str(uuid4())
CHAR_B = str(uuid4())


def _session(speaker: str) -> dict[str, Any]:
    return {
        "speaker_character_id": speaker,
        "character_id": speaker,
        "controlled_character_ids": [CHAR_A, CHAR_B],
    }


def _names(_ids: list[str]) -> dict[str, str]:
    return {CHAR_A: "Ana", CHAR_B: "Bor"}


def _personas(_ids: list[str]) -> dict[str, dict[str, Any]]:
    return {CHAR_A: {"persona_id": "p1", "persona_name": "Ana Persona"}}


def _run(session: dict[str, Any], scene_id: str, story_id: str) -> Any:
    with (
        patch.object(chat_loops, "SceneLoop", _FakeLoop),
        patch(
            "monitor_ui.routers.character_resolution.resolve_character_names",
            _names,
        ),
        patch(
            "monitor_ui.routers.character_resolution.resolve_controlled_personas",
            _personas,
        ),
    ):
        return chat_loops.get_scene_loop(
            "session-1",
            session,
            scene_id=scene_id,
            story_id=story_id,
            actor_context={"id": session["speaker_character_id"], "name": "Ana"},
        )


def test_speaker_switch_refreshes_the_cast_on_the_next_turn() -> None:
    chat_loops._SCENE_LOOPS.clear()
    scene_id = str(uuid4())
    story_id = str(uuid4())
    try:
        # Turn 1: Ana speaks.
        loop_a = _run(_session(CHAR_A), scene_id, story_id)
        cast = loop_a.cast
        assert cast is not None
        assert cast.by_id(CHAR_A).is_speaker is True
        assert cast.by_id(CHAR_B).is_speaker is False
        assert loop_a.kwargs["actor_id"] is not None

        # Turn 2: the user switches to Bor. The signature (which keys on the
        # actor) differs, so a fresh loop is built AND the cast refreshes.
        loop_b = _run(_session(CHAR_B), scene_id, story_id)
        assert loop_b is not loop_a
        cast = loop_b.cast
        assert cast.by_id(CHAR_B).is_speaker is True
        assert cast.by_id(CHAR_A).is_speaker is False
    finally:
        chat_loops._SCENE_LOOPS.clear()


def test_cached_loop_still_refreshes_the_cast() -> None:
    chat_loops._SCENE_LOOPS.clear()
    scene_id = str(uuid4())
    story_id = str(uuid4())
    try:
        loop1 = _run(_session(CHAR_A), scene_id, story_id)
        loop2 = _run(_session(CHAR_A), scene_id, story_id)
        # Same signature → same cached loop…
        assert loop2 is loop1
        # …but the cast is refreshed on every call, on the loop itself (so a
        # backend restart between turns cannot change what the nodes see).
        cast = loop2.cast
        assert cast is not None
        assert cast.by_id(CHAR_A).is_speaker is True
    finally:
        chat_loops._SCENE_LOOPS.clear()


def test_cast_carries_personas_and_matches_controlled_ids() -> None:
    chat_loops._SCENE_LOOPS.clear()
    scene_id = str(uuid4())
    story_id = str(uuid4())
    try:
        loop = _run(_session(CHAR_A), scene_id, story_id)
        cast = loop.cast
        assert cast is not None
        # The cast panel / done-when: the roster matches the session's
        # controlled ids exactly.
        assert {m.entity_id for m in cast.user_characters()} == {CHAR_A, CHAR_B}
        assert cast.by_id(CHAR_A).persona_name == "Ana Persona"
    finally:
        chat_loops._SCENE_LOOPS.clear()
