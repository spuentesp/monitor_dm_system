"""Story review includes a character recap (session-0 closing review)."""

from __future__ import annotations

from typing import Any

import pytest

from monitor_agents.loops import preplay_orchestrator
from monitor_agents.loops.preplay_orchestrator import _character_recap


def test_character_recap_renders_known_fields() -> None:
    session: dict[str, Any] = {
        "character_summary": {
            "character_name": "Vex",
            "concept": "exiled cartographer",
            "appearance": "ink-stained hands, one clouded eye",
            "backstory": "Mapped the drowned coast. " * 40,
        }
    }
    recap = _character_recap(session)
    assert "CHARACTER REVIEW" in recap
    assert "Name: Vex" in recap
    assert "cartographer" in recap
    assert "clouded eye" in recap
    assert len(recap) < 800  # backstory excerpt bounded


def test_character_recap_empty_is_silent() -> None:
    assert _character_recap({}) == ""
    assert _character_recap({"character_summary": "junk"}) == ""


@pytest.mark.asyncio
async def test_completed_agreements_prefixed_with_recap(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeLoop:
        async def process_player_input(self, text: str) -> dict[str, Any]:
            return {
                "complete": True,
                "gm_message": "AGREEMENTS SUMMARY: premise, tone, lines.",
                "agreements": None,
            }

    monkeypatch.setattr(preplay_orchestrator, "get_story_agreements_loop", lambda *a, **k: _FakeLoop())
    monkeypatch.setattr(preplay_orchestrator, "_save_checkpoint", lambda *a, **k: None)
    state = preplay_orchestrator.PreplayState(
        session_id="s1",
        user_content="looks good",
        session_data={
            "phase": "session_zero",
            "character_summary": {"character_name": "Vex", "concept": "exiled cartographer"},
        },
        system_doc=None,
        gsr_available=False,
    )
    result = await preplay_orchestrator.handle_story_agreements(state)
    assert result["response_text"].startswith("CHARACTER REVIEW")
    assert "AGREEMENTS SUMMARY" in result["response_text"]
    assert result["metadata"]["type"] == "story_agreements_summary"
