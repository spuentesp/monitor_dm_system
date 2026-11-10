"""Pre-play restart/resume and the orchestrator's world-seed wiring.

Phase 2 task 8: pre-play checkpoints survive a backend restart at every
step, including after the start is chosen and before the opening is
written. Also covers the cross-component call: the orchestrator invokes
WorldSeed.generate_start_options with the session's universe and packs.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from monitor_agents.loops import preplay_orchestrator as po
from monitor_agents.loops.preplay_phases import PreplayPhase
from monitor_agents.loops.preplay_support import ensure_start_options

pytestmark = pytest.mark.unit


OPTIONS = [
    {
        "option_id": "dockside-heist-1",
        "title": "Dockside Heist",
        "summary": "A ledger is missing.",
        "location": "The Docks",
        "location_description": "",
        "npcs": [{"name": "Mara", "description": "", "want": "the ledger"}],
        "hook": "The tide-locks ledger is gone.",
        "player_role": "",
        "threads": [{"title": "The Missing Ledger", "description": "", "category": "mystery", "urgency": "high"}],
        "generated": False,
    },
    {
        "option_id": "last-watch-2",
        "title": "The Last Watch",
        "summary": "Something at the wall.",
        "location": "The Wall",
        "location_description": "",
        "npcs": [{"name": "Tobias", "description": "", "want": "a way out"}],
        "hook": "The wall is failing.",
        "player_role": "",
        "threads": [{"title": "The Failing Wall", "description": "", "category": "threat", "urgency": "high"}],
        "generated": False,
    },
]


@pytest.fixture(autouse=True)
def _clear_caches():
    po._CHARACTER_INTERVIEW_LOOPS.clear()
    po._SESSION_ZERO_LOOPS.clear()
    yield
    po._CHARACTER_INTERVIEW_LOOPS.clear()
    po._SESSION_ZERO_LOOPS.clear()


def _session() -> dict[str, Any]:
    return {
        "id": "sess-1",
        "universe_id": str(uuid4()),
        "pack_id": str(uuid4()),
        "system_source_id": str(uuid4()),
        "tone": "grim",
        "system_label": "Mistlands Core",
        "start_options": [dict(option) for option in OPTIONS],
        "start_options_source": "canon",
        "start_question_text": "How would you like to begin?",
    }


def _state(session: dict[str, Any], user_content: str) -> Any:
    return po.PreplayState(
        session_id=session["id"],
        user_content=user_content,
        session_data=session,
        system_doc=None,
        gsr_available=False,
        world_lore=["The tide-locks failed once."],
        system_context="",
    )


def _stub_resolve_authored(monkeypatch: pytest.MonkeyPatch) -> None:
    from monitor_agents.loops import preplay_support

    monkeypatch.setattr(po, "resolve_authored_questions", lambda *args, **kwargs: [])
    monkeypatch.setattr(preplay_support, "resolve_authored_questions", lambda *args, **kwargs: [])


# ─── cross-component: WorldSeed is invoked with the session's world ──────────


@pytest.mark.asyncio
async def test_start_interview_invokes_world_seed_with_universe_and_packs(monkeypatch: pytest.MonkeyPatch):
    from monitor_agents.world_seed.seed import WorldSeed

    called: dict[str, Any] = {}

    async def _fake_seed(self: Any, **kwargs: Any) -> Any:
        called.update(kwargs)

        class _Result:
            source = "canon"
            options = []

        return _Result()

    monkeypatch.setattr(WorldSeed, "generate_start_options", _fake_seed)
    _stub_resolve_authored(monkeypatch)

    session = _session()
    session.pop("start_options")
    session.pop("start_question_text")
    await po.start_character_interview("sess-seed", session, system_doc=None)

    assert called["universe_id"] == session["universe_id"]
    assert set(called["pack_ids"]) == {session["pack_id"], session["system_source_id"]}
    assert called["system_name"] == "Mistlands Core"
    assert called["tone"] == "grim"


@pytest.mark.asyncio
async def test_start_interview_first_question_carries_start_option_chips(monkeypatch: pytest.MonkeyPatch):
    _stub_resolve_authored(monkeypatch)
    session = _session()
    message, metadata = await po.start_character_interview("sess-2", session, system_doc=None)

    assert metadata["category"] == "start_choice"
    assert metadata["question_number"] == 1
    titles = [chip["title"] for chip in metadata["start_options"]]
    assert titles == ["Dockside Heist", "The Last Watch"]
    assert "How would you like to begin?" in message
    assert "Surprise me" in metadata["suggested_answers"]


# ─── task 8: restart mid-flow continues from the same question ───────────────


async def _answered_session_after_q1(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Run the interview through question 1, then snapshot what a backend
    restart would persist."""
    _stub_resolve_authored(monkeypatch)
    session = _session()
    await po.start_character_interview(session["id"], session, system_doc=None)
    session["chosen_start_option_id"] = "dockside-heist-1"  # start picked on Q1
    result = await po.handle_character_interview(_state(session, "Dockside Heist"))
    assert result["metadata"]["question_number"] == 2
    # PreplayState copies session_data; the mutated copy is authoritative
    # (run_preplay_turn stores it back the same way).
    return dict(result["session_data"])


@pytest.mark.asyncio
async def test_restart_mid_interview_resumes_on_the_same_question(monkeypatch: pytest.MonkeyPatch):
    session = await _answered_session_after_q1(monkeypatch)

    # Simulate a backend restart: in-memory loop caches are gone.
    po._CHARACTER_INTERVIEW_LOOPS.clear()
    _stub_resolve_authored(monkeypatch)

    loop = po.get_character_interview_loop(
        session["id"],
        session,
        [],
        "",
        authored_questions=None,
    )
    # The orchestrator's cache-miss path restores from the checkpoint.
    restored = po._restore_loop_state(loop, session, PreplayPhase.CHARACTER_INTERVIEW.value)
    assert restored._state.question_number == 2
    assert restored._state.current_question
    assert restored._state.current_question == session["preplay_checkpoint"]["state"]["current_question"]
    assert restored._max_questions == 4


@pytest.mark.asyncio
async def test_restart_after_start_chosen_keeps_choice_and_question(monkeypatch: pytest.MonkeyPatch):
    session = await _answered_session_after_q1(monkeypatch)
    assert session["chosen_start_option_id"] == "dockside-heist-1"
    assert session["preplay_checkpoint"]["state"]["question_number"] == 2

    po._CHARACTER_INTERVIEW_LOOPS.clear()
    _stub_resolve_authored(monkeypatch)

    result = await po.handle_character_interview(_state(session, "I want the ledger."))
    # The turn after the restart continues the series — it does not re-ask
    # the start question, and the chosen option survives.
    assert result["metadata"]["question_number"] == 3
    assert result["session_data"]["chosen_start_option_id"] == "dockside-heist-1"


@pytest.mark.asyncio
async def test_restart_does_not_regenerate_the_start_question(monkeypatch: pytest.MonkeyPatch):
    """The model-written question text is cached on the session, so a
    rebuilt setup re-asks the identical question."""
    session = await _answered_session_after_q1(monkeypatch)
    po._CHARACTER_INTERVIEW_LOOPS.clear()

    async def _boom(**kwargs: Any) -> Any:
        raise AssertionError("must not regenerate the start question on resume")

    monkeypatch.setattr(po, "ask_start_options_question", _boom)
    _stub_resolve_authored(monkeypatch)

    plan_questions, plan_total, start_options = await po._interview_setup(session, [], None)
    assert plan_questions is not None
    assert plan_questions[0]["question_text"] == "How would you like to begin?"
    assert plan_total == 4
    assert len(start_options) == 2


# ─── start choice resolution wiring ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_interview_records_chosen_option_from_answer(monkeypatch: pytest.MonkeyPatch):
    _stub_resolve_authored(monkeypatch)
    session = _session()
    await po.start_character_interview(session["id"], session, system_doc=None)
    result = await po.handle_character_interview(_state(session, "Let's take the Last Watch."))
    assert result["metadata"]["question_number"] == 2
    assert result["session_data"]["chosen_start_option_id"] == "last-watch-2"


@pytest.mark.asyncio
async def test_ensure_start_options_caches_on_session(monkeypatch: pytest.MonkeyPatch):
    """Cross-component: WorldSeed.generate_start_options is invoked once and
    its result cached on the session dict."""
    from monitor_agents.world_seed.seed import WorldSeed

    calls: list[Any] = []

    async def _fake_seed(self: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)

        class _Opt:
            def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
                return {"option_id": "a-1", "title": "A"}

        class _Result:
            source = "generated"
            options = [_Opt()]

        return _Result()

    monkeypatch.setattr(WorldSeed, "generate_start_options", _fake_seed)
    session = {"universe_id": str(uuid4()), "tone": "grim"}

    first = await ensure_start_options(session)
    second = await ensure_start_options(session)

    assert first == [{"option_id": "a-1", "title": "A"}]
    assert first is not second  # copies, but same content
    assert second == first
    assert len(calls) == 1
    assert session["start_options_source"] == "generated"
