"""build_gm_opening narrates the materialized starting situation (Phase 2).

Task 5: the generated opening names where the PC is, who is there, and what
is happening — while the existing precedence holds: authored module intro
first, resume recap second, generated opening third.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_ui.routers.chat_opening import build_gm_opening


def _session() -> dict:
    return {
        "universe_id": str(uuid4()),
        "tone": "grim",
        "system_label": "Mistlands Core",
        "materialized_start": {
            "location": "The Docks",
            "location_description": "rain-slick quay",
            "npcs": [{"name": "Mara", "want": "the ledger back"}],
            "hook": "The tide-locks ledger is gone.",
            "player_role": "the stranger",
        },
    }


@pytest.mark.asyncio
async def test_cold_open_narrates_the_situation():
    """Cross-component: Narrator.generate_opening is invoked with the
    situation brief in its context and a situation-narrating instruction."""
    session = _session()
    with patch("monitor_ui.routers.chat_opening.Narrator") as MockNarrator:
        instance = MockNarrator.return_value
        instance.generate_opening = AsyncMock(return_value="Rain hammers the quay as Mara watches the ledger house.")

        text, meta = await build_gm_opening("sess-1", session, session_game_system_doc=lambda _s: None)

    assert "Mara watches" in text
    _, kwargs = instance.generate_opening.await_args
    entities_context = kwargs["context"]["entities"][0]["context"]
    assert "STARTING SITUATION" in entities_context
    assert "The Docks" in entities_context
    assert "narrate the starting situation" in kwargs["user_input"]


@pytest.mark.asyncio
async def test_fallback_opening_leads_with_the_situation():
    session = _session()
    with patch("monitor_ui.routers.chat_opening.Narrator") as MockNarrator:
        instance = MockNarrator.return_value
        instance.generate_opening = AsyncMock(side_effect=RuntimeError("llm down"))

        text, meta = await build_gm_opening("sess-2", session, session_game_system_doc=lambda _s: None)

    assert text.startswith("PLACE: The Docks")
    assert "Mara" in text
