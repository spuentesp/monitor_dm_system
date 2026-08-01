"""Tests for OOC exchange persistence (TABLE TALK channel, write side)."""

from __future__ import annotations

from typing import Any

import pytest

from monitor_agents.loops.preplay_support import (
    OOC_EXCHANGES_CAP,
    answer_ooc_question,
    record_ooc_exchange,
)


def test_record_ooc_exchange_appends_and_caps() -> None:
    session: dict[str, Any] = {}
    for i in range(OOC_EXCHANGES_CAP + 3):
        record_ooc_exchange(session, f"question {i}", f"answer {i}")
    exchanges = session["ooc_exchanges"]
    assert len(exchanges) == OOC_EXCHANGES_CAP
    # Oldest dropped: first surviving entry is question 3.
    assert exchanges[0]["question"] == "question 3"
    assert exchanges[-1]["question"] == f"question {OOC_EXCHANGES_CAP + 2}"
    assert set(exchanges[0]) == {"question", "answer", "timestamp"}


@pytest.mark.asyncio
async def test_answer_ooc_question_records_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even the fallback (LLM down) answer must be recorded."""
    import dspy

    class _BoomPredict:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __call__(self, **kwargs: Any) -> Any:
            raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(dspy, "Predict", _BoomPredict)
    session: dict[str, Any] = {"director_notes": []}
    answer = await answer_ooc_question(
        session,
        "((what do I roll to sneak?))",
        session_game_system_doc=None,
        gsr_available=False,
    )
    assert answer
    exchanges = session.get("ooc_exchanges")
    assert isinstance(exchanges, list) and len(exchanges) == 1
    assert exchanges[0]["answer"] == answer
    assert "sneak" in exchanges[0]["question"]