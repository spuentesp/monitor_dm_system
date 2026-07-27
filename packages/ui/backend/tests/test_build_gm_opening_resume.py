"""Regression tests: build_gm_opening's resume-aware branch
(PLAY_AND_FORGE_DIRECTION.md S5).

is_resume=True with an existing story_id should synthesize a "story so
far" recap via RecapAgent instead of generating a cold open -- and must
fall back to the cold-open path if the recap can't be produced, rather
than failing the whole session-creation flow.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_ui.routers.chat_opening import build_gm_opening


@pytest.mark.asyncio
async def test_resume_with_existing_story_uses_recap_agent():
    session = {
        "universe_id": str(uuid4()),
        "story_id": str(uuid4()),
        "tone": "grim",
    }

    with patch("monitor_agents.recap.agent.RecapAgent") as MockRecap:
        instance = MockRecap.return_value
        instance.generate_recap = AsyncMock(
            return_value="The crew barely escaped the collapsing station. Echo is still missing."
        )

        text, meta = await build_gm_opening(
            "sess-1",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=True,
        )

    assert "Echo is still missing" in text
    assert meta == {"type": "gm_opening", "resume": True}
    instance.generate_recap.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_without_story_id_falls_back_to_cold_open():
    session = {"universe_id": str(uuid4()), "tone": "dramatic"}

    text, meta = await build_gm_opening(
        "sess-2",
        session,
        session_game_system_doc=lambda _s: None,
        is_resume=True,
    )

    # No story_id -> resume branch never fires -> ordinary cold-open fallback text.
    assert meta.get("resume") is not True
    assert isinstance(text, str) and text


@pytest.mark.asyncio
async def test_resume_falls_back_to_cold_open_when_recap_fails():
    session = {
        "universe_id": str(uuid4()),
        "story_id": str(uuid4()),
        "tone": "dramatic",
    }

    with patch("monitor_agents.recap.agent.RecapAgent") as MockRecap:
        instance = MockRecap.return_value
        instance.generate_recap = AsyncMock(side_effect=RuntimeError("boom"))

        text, meta = await build_gm_opening(
            "sess-3",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=True,
        )

    assert meta.get("resume") is not True
    assert isinstance(text, str) and text


@pytest.mark.asyncio
async def test_is_resume_false_never_calls_recap_agent():
    session = {
        "universe_id": str(uuid4()),
        "story_id": str(uuid4()),
        "tone": "dramatic",
    }

    with patch("monitor_agents.recap.agent.RecapAgent") as MockRecap:
        await build_gm_opening(
            "sess-4",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=False,
        )
        MockRecap.assert_not_called()
