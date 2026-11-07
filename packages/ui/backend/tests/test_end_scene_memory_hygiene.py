"""End-of-scene memory hygiene must actually run (regression: kwargs to anyio run_sync)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_ui.routers.chat_loops import _SCENE_LOOPS, run_end_scene


@pytest.mark.asyncio
@patch("monitor_ui.routers.chat_loops._AGENTS_AVAILABLE", True)
@patch("monitor_ui.routers.chat_loops._DB_READERS_AVAILABLE", True)
async def test_end_scene_forgets_stale_memories_for_the_story() -> None:
    story_id = uuid.uuid4()
    session = {
        "scene_id": str(uuid.uuid4()),
        "story_id": str(story_id),
        "universe_id": str(uuid.uuid4()),
    }
    _SCENE_LOOPS["s1"] = (("sig",), AsyncMock())
    forget = MagicMock(return_value=3)
    try:
        with (
            patch("monitor_ui.routers.chat_loops.StoryLoop") as story_loop_cls,
            patch("monitor_ui.routers.chat_loops.run_sync_read", new_callable=AsyncMock),
            patch(
                "monitor_ui.routers.chat_loops._generate_scene_summary",
                new_callable=AsyncMock,
                return_value="summary",
            ),
            patch("monitor_data.tools.mongodb_tools.mongodb_forget_stale_memories", forget),
        ):
            story_loop_cls.return_value.complete_current_scene = AsyncMock(
                return_value={"current_scene_id": str(uuid.uuid4()), "story_complete": True}
            )
            await run_end_scene(
                "s1",
                session,
                sessions={"s1": session},
                messages={},
                db_save_session=MagicMock(),
                db_load_messages=MagicMock(),
                bootstrap_story_scene=MagicMock(),
            )
    finally:
        _SCENE_LOOPS.pop("s1", None)

    forget.assert_called_once_with(story_id=story_id)
