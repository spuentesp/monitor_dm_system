"""finalize_preplay — chosen start, skip path, situation opening (Phase 2).

Tasks 4, 5, 7: the chosen start (or the seed's first option on the skip
path) is materialized during the bootstrap; the opening narrates the
situation — place, people, what is at stake — and ends on a prompt to act.
The authored-module-intro-first precedence is preserved.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

import monitor_data.tools.mongodb_tools as mongo_tools
from monitor_agents.loops import preplay_finalize as pf
from monitor_agents.world_seed.materialize import resolve_chosen_start

pytestmark = pytest.mark.unit


def _option_dict() -> dict[str, Any]:
    return {
        "option_id": "dockside-heist-1",
        "title": "Dockside Heist",
        "summary": "A ledger is missing.",
        "location": "The Docks",
        "location_description": "rain-slick quay",
        "npcs": [
            {"name": "Mara", "description": "harbourmaster", "want": "the ledger back"},
            {"name": "Tobias", "description": "smuggler", "want": "a way out"},
        ],
        "hook": "The tide-locks ledger is gone.",
        "player_role": "the stranger with a forged key",
        "threads": [
            {"title": "The Missing Ledger", "description": "gone", "category": "mystery", "urgency": "high"},
            {"title": "Tobias Owes Someone", "description": "a debt", "category": "promise", "urgency": "medium"},
        ],
        "generated": False,
    }


def _session() -> dict[str, Any]:
    return {
        "id": "sess-1",
        "universe_id": str(uuid4()),
        "character_id": str(uuid4()),
        "speaker_label": "Vex",
        "story_premise": "a heist on the tide-locks",
        "tone": "grim",
        "director_notes": [],
        "start_options": [_option_dict()],
        "story_agreements": {"story_premise": "a heist on the tide-locks", "confirmed": False},
    }


class _FakeNarrator:
    """Stands in for Narrator with a canned opening; records its context."""

    received: dict[str, Any] = {}
    text: str = "Rain hammers the quay. Mara watches you from the ledger house. What do you do?"
    raises: bool = False

    async def generate_opening(self, **kwargs: Any) -> str:
        cls = type(self)
        cls.received = kwargs
        if cls.raises:
            raise RuntimeError("llm down")
        return cls.text


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    _FakeNarrator.received = {}
    _FakeNarrator.raises = False
    _FakeNarrator.text = "Rain hammers the quay. Mara watches you from the ledger house. What do you do?"
    story_id, scene_id = str(uuid4()), str(uuid4())

    async def _fake_bootstrap(session: dict[str, Any], **kwargs: Any) -> tuple[str, str, None]:
        session["story_id"] = story_id
        session["scene_id"] = scene_id
        # Simulate the real wrapper's materialization side effect.
        from monitor_agents.world_seed import materialize_chosen_start

        await materialize_chosen_start(session, story_id=story_id)
        return story_id, scene_id, None

    async def _fake_seed_canon(session: dict[str, Any]) -> None:
        session["canon_seeded"] = True

    monkeypatch.setattr(pf, "bootstrap_story_scene_with_start", _fake_bootstrap)
    monkeypatch.setattr(pf, "seed_canon_from_session_zero", _fake_seed_canon)
    monkeypatch.setattr(pf, "Narrator", _FakeNarrator)
    monkeypatch.setattr(mongo_tools, "mongodb_get_knowledge_pack", lambda pack_id: None)

    async def _fake_ensure(session: dict[str, Any]) -> list[dict[str, Any]]:
        return [option for option in (session.get("start_options") or []) if isinstance(option, dict)]

    monkeypatch.setattr(pf, "ensure_start_options", _fake_ensure)
    _patch_materialize_deps(monkeypatch)
    yield


def _patch_materialize_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_agents.world_seed import materialize as mat

    async def _fake_bulk(self: Any, proposals: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return {"committed": len(proposals), "errors": []}

    class _Resp:
        proposal_id = uuid4()

    class _Profile:
        profile_id = "profile-1"

    async def _fake_resolve(universe_id: str, name: str) -> str | None:
        return str(uuid4())

    async def _fake_pc_name(session: dict[str, Any], universe_id: str) -> str | None:
        return str(session.get("speaker_label") or "") or None

    monkeypatch.setattr(CanonKeeper, "bulk_commit_proposals", _fake_bulk)
    monkeypatch.setattr(mongo_tools, "mongodb_create_proposed_change", lambda params: _Resp())
    monkeypatch.setattr(mongo_tools, "mongodb_create_npc_profile", lambda params: _Profile())
    monkeypatch.setattr(mat, "_entity_name_to_id", _fake_resolve)
    monkeypatch.setattr(mat, "_pc_name", _fake_pc_name)

    class _Coll:
        def find(self, query: dict[str, Any]) -> Any:
            class _C(list):
                def limit(self, _n: int) -> Any:
                    return self

            return _C()

    class _Mongo:
        def get_collection(self, _name: str) -> _Coll:
            return _Coll()

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: _Mongo())


# ─── task 7: the skip path still gets a seeded opening ───────────────────────


@pytest.mark.asyncio
async def test_finalize_without_explicit_choice_picks_first_option():
    session = _session()
    narrative, metadata = await pf.finalize_preplay(session, system_doc=None)

    assert session["chosen_start_option_id"] == "dockside-heist-1"
    assert metadata["materialized_start"]["option_id"] == "dockside-heist-1"
    assert metadata["preplay_finalized"] is True
    assert session["phase"] == "active_play"


# ─── task 5: the opening narrates the situation ──────────────────────────────


@pytest.mark.asyncio
async def test_opening_narration_receives_the_situation_brief():
    session = _session()
    await pf.finalize_preplay(session, system_doc=None)

    context = _FakeNarrator.received["context"]
    entities_context = context["entities"][0]["context"]
    assert "STARTING SITUATION" in entities_context
    assert "The Docks" in entities_context
    assert "Mara" in entities_context
    assert "The tide-locks ledger is gone." in entities_context
    # Task 5: the prompt to act is part of the request.
    assert "prompt to act" in _FakeNarrator.received["user_input"]


@pytest.mark.asyncio
async def test_template_opening_names_location_npcs_and_prompt_when_llm_fails():
    _FakeNarrator.raises = True
    session = _session()
    narrative, _ = await pf.finalize_preplay(session, system_doc=None)

    assert "The Docks" in narrative
    assert "Mara" in narrative
    assert "Tobias" in narrative
    assert "The tide-locks ledger is gone." in narrative
    assert narrative.rstrip().endswith("What do you do?")


# ─── precedence: authored module intro first ─────────────────────────────────


@pytest.mark.asyncio
async def test_module_intro_used_verbatim_when_no_situation(monkeypatch: pytest.MonkeyPatch):
    class _Pack:
        intro_text = "Read aloud: the bells of the drowned cathedral toll."

    monkeypatch.setattr(mongo_tools, "mongodb_get_knowledge_pack", lambda pack_id: _Pack())
    session = _session()
    session["pack_id"] = str(uuid4())
    session["start_options"] = []  # no materialized situation
    session.pop("chosen_start_option_id", None)

    narrative, _ = await pf.finalize_preplay(session, system_doc=None)
    assert narrative == "Read aloud: the bells of the drowned cathedral toll."


@pytest.mark.asyncio
async def test_module_intro_stays_first_when_situation_is_narrated(monkeypatch: pytest.MonkeyPatch):
    class _Pack:
        intro_text = "Read aloud: the bells of the drowned cathedral toll."

    monkeypatch.setattr(mongo_tools, "mongodb_get_knowledge_pack", lambda pack_id: _Pack())
    session = _session()
    session["pack_id"] = str(uuid4())

    narrative, _ = await pf.finalize_preplay(session, system_doc=None)
    # The authored intro leads; the situation narration follows.
    assert narrative.startswith("Read aloud: the bells of the drowned cathedral toll.")
    assert "Mara watches you" in narrative


# ─── the opening must name the place and at least two NPCs ───────────────────


@pytest.mark.asyncio
async def test_opening_names_location_and_two_npcs_even_when_narration_glosses():
    _FakeNarrator.text = "The night is quiet, and the city sleeps."  # names nobody
    session = _session()
    narrative, _ = await pf.finalize_preplay(session, system_doc=None)

    assert "The Docks" in narrative
    assert "Mara" in narrative
    assert "Tobias" in narrative
    assert narrative.rstrip().endswith("What do you do?")


# ─── chosen option honored ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_materializes_the_explicitly_chosen_option():
    session = _session()
    session["start_options"].append({**_option_dict(), "option_id": "last-watch-2", "title": "The Last Watch"})
    session["chosen_start_option_id"] = "last-watch-2"

    _, metadata = await pf.finalize_preplay(session, system_doc=None)
    assert metadata["materialized_start"]["option_id"] == "last-watch-2"
    assert resolve_chosen_start(session).option_id == "last-watch-2"
