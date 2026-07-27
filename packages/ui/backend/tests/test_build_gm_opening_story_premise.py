"""Regression tests: build_gm_opening threads session["story_premise"]
through to the Narrator as a hard content constraint on the opening scene
(character-template plan, Q3) -- and still produces a real opening (via the
non-LLM fallback template) when the LLM call itself fails, rather than
silently discarding the player's stated intent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_ui.routers.chat_opening import build_gm_opening


@pytest.mark.asyncio
async def test_story_premise_passed_through_to_narrator():
    session = {
        "universe_id": str(uuid4()),
        "tone": "grim",
        "story_premise": "heist against a rival Prince, no combat",
    }

    with patch("monitor_ui.routers.chat_opening.Narrator") as MockNarrator:
        instance = MockNarrator.return_value
        instance.generate_opening = AsyncMock(return_value="The Prince's tower glitters, and you are already inside.")

        text, meta = await build_gm_opening(
            "sess-1",
            session,
            session_game_system_doc=lambda _s: None,
        )

    assert "Prince's tower" in text
    assert meta["type"] == "gm_opening"
    assert meta["premise_used"] is True
    instance.generate_opening.assert_awaited_once()
    _, kwargs = instance.generate_opening.await_args
    assert kwargs["story_premise"] == "heist against a rival Prince, no combat"


@pytest.mark.asyncio
async def test_no_story_premise_passes_none_and_behaves_as_before():
    # system_label alone is enough to make fetch_opening_hook's system_name
    # truthy, reaching the LLM branch without needing real DB-backed lore --
    # isolates this test from the (separately covered) premise-alone gate.
    session = {
        "universe_id": str(uuid4()),
        "tone": "dramatic",
        "system_label": "Test System",
    }

    with patch("monitor_ui.routers.chat_opening.Narrator") as MockNarrator:
        instance = MockNarrator.return_value
        instance.generate_opening = AsyncMock(return_value="The lobby lights flicker on against the gathering dark.")

        text, meta = await build_gm_opening(
            "sess-2",
            session,
            session_game_system_doc=lambda _s: None,
        )

    assert meta["premise_used"] is False
    _, kwargs = instance.generate_opening.await_args
    assert kwargs["story_premise"] is None


@pytest.mark.asyncio
async def test_premise_alone_triggers_llm_path_with_no_lore():
    """A universe with no axioms/facts/system_name must still attempt the
    LLM path when a premise is set -- the non-LLM fallback is a fixed
    template that can't honor free-text steering."""
    session = {
        "universe_id": str(uuid4()),
        "tone": "dramatic",
        "story_premise": "survival horror, no combat, focus on isolation",
    }

    with patch("monitor_ui.routers.chat_opening.Narrator") as MockNarrator:
        instance = MockNarrator.return_value
        instance.generate_opening = AsyncMock(return_value="Alone. The lights are out.")

        await build_gm_opening("sess-3", session, session_game_system_doc=lambda _s: None)

    instance.generate_opening.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_template_still_surfaces_premise_when_llm_fails():
    """If the LLM call itself fails, the deterministic fallback template
    must still surface the stated premise rather than a fully generic
    question -- the player's intent shouldn't vanish on an LLM hiccup."""
    session = {
        "universe_id": str(uuid4()),
        "tone": "dramatic",
        "story_premise": "political intrigue, low violence",
    }

    with patch("monitor_ui.routers.chat_opening.Narrator") as MockNarrator:
        instance = MockNarrator.return_value
        instance.generate_opening = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        text, meta = await build_gm_opening(
            "sess-4",
            session,
            session_game_system_doc=lambda _s: None,
        )

    assert "political intrigue, low violence" in text
    assert meta == {"type": "gm_opening"}
