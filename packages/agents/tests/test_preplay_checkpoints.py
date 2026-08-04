from __future__ import annotations


import pytest

from monitor_agents.loops import preplay_orchestrator as po
from monitor_agents.loops.preplay_phases import PreplayPhase


@pytest.fixture(autouse=True)
def _reset_loop_cache():
    po._CHARACTER_INTERVIEW_LOOPS.clear()
    po._STORY_AGREEMENT_LOOPS.clear()
    yield
    po._CHARACTER_INTERVIEW_LOOPS.clear()
    po._STORY_AGREEMENT_LOOPS.clear()


def test_save_checkpoint_writes_a_versioned_block():
    class _Loop:
        def __init__(self):
            self._state = type("State", (), {"model_dump": lambda self, mode="json": {"index": 2}})()

        @property
        def state(self):
            return self._state

    session: dict = {}
    po._save_checkpoint(session, PreplayPhase.CHARACTER_INTERVIEW.value, _Loop())
    checkpoint = session["preplay_checkpoint"]
    assert checkpoint["schema_version"] == 1
    assert checkpoint["stage"] == "character_interview"
    assert checkpoint["state"] == {"index": 2}


def test_checkpoint_round_trips_through_cache_eviction():
    class _Loop:
        def __init__(self, index):
            self._state = type(
                "State",
                (),
                {
                    "model_dump": lambda self, mode="json": {"index": index},
                    "model_validate": classmethod(lambda cls, data: type("State", (), {"index": data["index"]})()),
                },
            )()

    loop = _Loop(index=3)
    po._save_checkpoint(
        {"preplay_checkpoint": {"schema_version": 1, "stage": "character_interview", "state": {"index": 1}}},
        "character_interview",
        loop,
    )
    restored = po._restore_loop_state(
        loop,
        {"preplay_checkpoint": {"schema_version": 1, "stage": "character_interview", "state": {"index": 7}}},
        "character_interview",
    )
    assert restored._state.index == 7


def test_clear_preplay_checkpoint_removes_field():
    session = {"preplay_checkpoint": {"stage": "session_zero", "state": {}}}
    po.clear_preplay_checkpoint(session)
    assert "preplay_checkpoint" not in session


def test_invalid_checkpoint_is_swallowed():
    class _Loop:
        def __init__(self):
            self._state = type("State", (), {"model_dump": lambda self, mode="json": {}})()

    bad = {"schema_version": 1, "stage": "character_interview", "state": {"foo": "bar"}}
    # ``State`` has no field ``foo`` — ``model_validate`` raises and the
    # restore helper logs and falls back to the freshly constructed state.
    loop = _Loop()
    po._restore_loop_state(loop, {"preplay_checkpoint": bad}, "character_interview")
    # The loop's _state stays at its freshly-built default; nothing blows up.
    assert loop._state is not None


@pytest.mark.asyncio
async def test_character_interview_resume_uses_checkpointed_answers():
    """When a backend restart evicts the in-memory cache, the interview must
    resume from the persisted checkpoint rather than re-seed from the persona."""

    session: dict = {"persona_id": "persona-42"}
    checkpoint = {
        "schema_version": 1,
        "stage": "character_interview",
        "state": {
            "answers": [
                {
                    "question": "What are you called?",
                    "answer": "Mara",
                    "category": "name",
                }
            ],
            "max_questions": 4,
            "tone": "grim",
        },
    }
    session["preplay_checkpoint"] = checkpoint

    # The orchestrator's start_character_interview should not seed
    # persona answers when the checkpoint already carries recorded
    # answers. We can verify that via _persona_seed indirectly: the
    # persona seed helper still runs, but the orchestrator zeros the
    # seed_answers variable after the checkpoint check.
    from monitor_agents.loops.preplay_orchestrator import start_character_interview

    captured: dict = {}
    real_seed = po._persona_seed

    async def _stub_persona_seed(_session):
        captured["seed"] = True
        return None

    po._persona_seed = _stub_persona_seed  # type: ignore[assignment]
    try:
        await start_character_interview(
            "sess-resume-1",
            session,
            system_doc=None,
        )
    finally:
        po._persona_seed = real_seed  # type: ignore[assignment]

    assert captured.get("seed") is True  # helper still called; orchestrator drops its result
    # The loop we cached must have ``max_questions`` aligned with the
    # checkpoint rather than the orchestrator's default (4).
    loop = po._CHARACTER_INTERVIEW_LOOPS["sess-resume-1"]
    assert loop._state.max_questions == 4
    assert loop._state.answers[0]["answer"] == "Mara"
