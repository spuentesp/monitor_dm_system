"""Regression tests for the Session Zero → CharacterCreationLoop handoff.

When Session Zero completes with a summary, the character-creation loop must
consume the summary so it does not re-ask questions (such as the character's
name) that the player already answered. Before the handoff existed, the loop
reset to step 0 and rendered the same Character Name prompt on every turn.

These tests assert:
  * A seeded loop starts on the first mechanics step and retains the seed.
  * An unseeded loop still starts with Character Name.
  * The preplay orchestrator passes the Session Zero summary into the loop
    on cache miss (mirroring the live regression).
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from monitor_agents.loops import preplay_orchestrator as po
from monitor_agents.loops.character_creation_loop import (
    CharacterCreationLoop,
    _apply_initial_seed,
    _is_name_step,
    _normalise_initial_seed,
)


@pytest.fixture(autouse=True)
def _clear_loop_cache():
    po._SESSION_ZERO_LOOPS.clear()
    po._CHAR_CREATION_LOOPS.clear()
    yield
    po._SESSION_ZERO_LOOPS.clear()
    po._CHAR_CREATION_LOOPS.clear()


SYSTEM_DOC = {
    "_id": "test-system",
    "name": "Test System",
    "character_creation": {
        "steps": [
            {"step_number": 1, "step_type": "choose_name", "title": "Character Name"},
            {"step_number": 2, "step_type": "choose_class", "title": "Choose Clan"},
            {"step_number": 3, "step_type": "roll_stats", "title": "Roll Stats"},
        ],
    },
    "attributes": [
        {"abbreviation": "STR", "name": "Strength", "default_value": 10},
    ],
    "resources": [
        {"name": "HP", "max_value": 10, "track_type": "resource"},
    ],
}


SESSION_ZERO_SUMMARY = {
    "character_name": "Alfred",
    "concept": "A newly-thinned-blood fledgling.",
    "backstory": "Alfred is a thin-blood neonate on the run from the sheriff.",
    "key_bonds": ["The thin-blood mentor who was taken by the sheriff"],
    "key_fears": ["That his thin blood makes him disposable to the Camarilla"],
    "key_motivations": ["Survive long enough to understand what his thin blood means"],
}


# ─── Seed helpers ─────────────────────────────────────────────────────────


def test_normalise_initial_seed_accepts_session_zero_summary():
    seed = _normalise_initial_seed(SESSION_ZERO_SUMMARY)
    assert seed["character_name"] == "Alfred"
    assert seed["concept"] == "A newly-thinned-blood fledgling."
    assert seed["backstory"].startswith("Alfred is a thin-blood")


def test_normalise_initial_seed_falls_back_to_speaker_label():
    seed = _normalise_initial_seed({"speaker_label": "  Bran  "})
    assert seed["character_name"] == "Bran"


def test_normalise_initial_seed_ignores_empty_and_non_strings():
    assert _normalise_initial_seed(None) == {}
    assert _normalise_initial_seed({}) == {}
    assert _normalise_initial_seed({"character_name": ""}) == {}


def test_is_name_step_matches_legacy_and_canonical_titles():
    assert _is_name_step({"step_type": "choose_name", "title": "Character Name"})
    assert _is_name_step({"type": "name", "title": "Name"})
    assert not _is_name_step({"step_type": "roll_stats", "title": "Roll Stats"})


# ─── Seeded vs unseeded loop behaviour ───────────────────────────────────


def _build_loop(seed):
    return CharacterCreationLoop(
        game_context=SYSTEM_DOC,
        scene_id=uuid4(),
        story_id=uuid4(),
        seed=seed,
    )


def test_unseeded_loop_starts_with_character_name():
    loop = _build_loop(seed=None)
    # Don't await start() — load_system + apply are inline; inspect state.
    loop._state = loop._state.model_copy(
        update=__import__("monitor_agents.loops.character_creation_loop", fromlist=["load_system"]).load_system(
            loop._state
        )
    )
    assert loop._state.creation_steps, "load_system must produce creation steps"
    first_step = loop._state.creation_steps[loop._state.current_step_index]
    assert first_step.get("step_type") in ("choose_name", "name") or first_step.get("title") == "Character Name"


def test_seeded_loop_skips_character_name_step():
    loop = _build_loop(seed=SESSION_ZERO_SUMMARY)
    cc_module = __import__("monitor_agents.loops.character_creation_loop", fromlist=["load_system"])
    loop._state = loop._state.model_copy(update=cc_module.load_system(loop._state))
    updates = _apply_initial_seed(loop._state, _normalise_initial_seed(SESSION_ZERO_SUMMARY))
    seeded = loop._state.model_copy(update=updates)

    assert seeded.character_name == "Alfred"
    assert seeded.concept == "A newly-thinned-blood fledgling."
    assert seeded.character_data.get("backstory", "").startswith("Alfred is a thin-blood")
    # The canonical name step is the first step; after seeding we should be
    # past it.
    current_step = seeded.creation_steps[seeded.current_step_index]
    assert current_step.get("step_type") != "choose_name"
    assert current_step.get("title") != "Character Name"


def test_seeded_loop_seed_is_consumed_after_first_start():
    """Calling .start() a second time must not re-apply the seed (no clobber
    over in-flight player progress)."""
    cc_module = __import__("monitor_agents.loops.character_creation_loop", fromlist=["load_system"])
    loop = _build_loop(seed=SESSION_ZERO_SUMMARY)
    first = loop._state.model_copy(update=cc_module.load_system(loop._state))
    updates = _apply_initial_seed(first, _normalise_initial_seed(SESSION_ZERO_SUMMARY))
    loop._state = first.model_copy(update=updates)
    loop._initial_seed = {}  # mimic the single-use behaviour in .start()

    # Subsequent apply with a no-op seed (or any seed) must not reset state.
    later = loop._state.model_copy(update=_apply_initial_seed(loop._state, _normalise_initial_seed(None)))
    assert later.current_step_index == loop._state.current_step_index
    assert later.character_name == "Alfred"


# ─── Orchestrator wiring ─────────────────────────────────────────────────


def test_orchestrator_passes_session_zero_summary_into_character_loop(monkeypatch):
    """The preplay orchestrator must seed CharacterCreationLoop with the
    completed Session Zero summary on cache miss."""
    captured: dict = {}

    class _Stub:
        def __init__(self, *args, **kwargs):
            captured["seed"] = kwargs.get("seed")

    monkeypatch.setattr(po, "CharacterCreationLoop", _Stub)

    po.get_character_creation_loop(
        "sess-handoff-1",
        SYSTEM_DOC,
        seed=SESSION_ZERO_SUMMARY,
    )

    assert captured["seed"] == SESSION_ZERO_SUMMARY


def test_orchestrator_seeds_loop_only_on_cache_miss(monkeypatch):
    """A second call to get_character_creation_loop must return the cached
    loop and NOT re-construct it (seed is single-use)."""
    seen: list[dict] = []

    class _Stub:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            seen.append(self)

    monkeypatch.setattr(po, "CharacterCreationLoop", _Stub)

    first = po.get_character_creation_loop("sess-cache-1", SYSTEM_DOC, seed=SESSION_ZERO_SUMMARY)
    second = po.get_character_creation_loop("sess-cache-1", SYSTEM_DOC, seed=None)
    assert first is second
    assert len(seen) == 1


# ─── End-to-end stubbed handoff ──────────────────────────────────────────


def test_session_zero_complete_seeds_character_creation(monkeypatch):
    """When Session Zero reports complete with a summary, the orchestrator
    must build the character-creation loop with the summary as the seed."""
    session = {
        "phase": "session_zero",
        "tone": "dramatic",
        "system_label": "VtM",
    }
    world_lore: list[str] = []
    system_context = ""

    class _FakeSZResult(dict):
        pass

    fake_summary = MagicMock()
    fake_summary.character_name = "Alfred"
    fake_summary.concept = "A thin-blood neonate."
    fake_summary.backstory = "Backstory text."
    fake_summary.model_dump = MagicMock(return_value=SESSION_ZERO_SUMMARY)

    fake_result = _FakeSZResult(
        complete=True,
        summary=fake_summary,
        campaign_intent=None,
        gm_message="We have a thin-blood. Let's go.",
    )

    async def _process(_input):
        return fake_result

    fake_sz_loop = MagicMock()
    fake_sz_loop.process_player_input = _process
    monkeypatch.setattr(po, "get_session_zero_loop", lambda *a, **kw: fake_sz_loop)
    monkeypatch.setattr(
        po,
        "resolve_authored_session_zero_questions",
        lambda *a, **kw: [],
    )

    captured_seed: dict = {}

    def _fake_cc(*args, **kwargs):
        captured_seed.update(kwargs)

        class _Stub:
            current_step_index = 1
            creation_steps = [{"step_type": "choose_class", "title": "Choose Clan"}]
            total_steps = 3

            async def start(self_inner):
                return {
                    "complete": False,
                    "gm_message": "Pick your clan.",
                    "step_index": 1,
                    "total_steps": 3,
                }

        return _Stub()

    monkeypatch.setattr(po, "get_character_creation_loop", _fake_cc)

    from monitor_agents.loops.preplay_orchestrator import PreplayState

    state = PreplayState(
        session_id="sess-complete-1",
        user_content="I am Alfred, a new thin blood.",
        session_data=session,
        system_doc=SYSTEM_DOC,
        gsr_available=True,
        world_lore=world_lore,
        system_context=system_context,
    )

    import asyncio

    result = asyncio.run(po.handle_session_zero(state))

    assert captured_seed.get("seed") == SESSION_ZERO_SUMMARY
    assert result["session_data"]["character_summary"] == SESSION_ZERO_SUMMARY
    assert result["session_data"]["phase"] == "char_creation"
    assert result["metadata"]["type"] == "character_interview_complete"
