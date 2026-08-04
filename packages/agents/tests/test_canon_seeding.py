"""One-time canon seeding from Session-Zero outcomes at begin_story."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

import monitor_data.tools.mongodb_tools as mongo_tools
from monitor_agents.loops.preplay_finalize import seed_canon_from_session_zero


def _session() -> dict[str, Any]:
    return {
        "universe_id": str(uuid4()),
        "character_id": str(uuid4()),
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "story_premise": "a heist on the tide-locks",
        "tone": "grim",
        "director_notes": [],
        "character_summary": {
            "character_name": "Vex",
            "concept": "exiled cartographer",
            "appearance": "ink-stained hands",
            "backstory": "Mapped the drowned coast.",
        },
    }


@pytest.mark.asyncio
async def test_seed_writes_memory_and_director_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Any] = []

    class _Res:
        memory_id = uuid4()

    def _fake_create(params: Any) -> Any:
        created.append(params)
        return _Res()

    monkeypatch.setattr(mongo_tools, "mongodb_create_memory", _fake_create)
    session = _session()
    await seed_canon_from_session_zero(session)

    assert session["canon_seeded"] is True
    assert len(created) == 1
    params = created[0]
    assert "Vex" in params.text and "ink-stained hands" in params.text
    assert params.metadata["story_id"] == session["story_id"]
    assert params.importance == 0.9
    assert "Story premise: a heist on the tide-locks" in session["director_notes"]
    assert "Tone: grim" in session["director_notes"]


@pytest.mark.asyncio
async def test_seed_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mongo_tools,
        "mongodb_create_memory",
        lambda params: pytest.fail("must not write twice"),
    )
    session = _session()
    session["canon_seeded"] = True
    await seed_canon_from_session_zero(session)  # no exception, no writes


@pytest.mark.asyncio
async def test_seed_failure_does_not_raise_and_still_marks_seeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(params: Any) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(mongo_tools, "mongodb_create_memory", _boom)
    session = _session()
    await seed_canon_from_session_zero(session)  # must not raise
    assert session["canon_seeded"] is True
    # Director notes are independent of the memory write.
    assert "Tone: grim" in session["director_notes"]
