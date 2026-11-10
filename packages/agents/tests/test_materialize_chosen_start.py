"""Materializing the chosen start — CanonKeeper proposals, NPC profiles.

Phase 2 task 4: the chosen option becomes state — location and NPCs as
entity instances (not archetypes) with NPC profiles and agendas, 2-3 plot
threads, the PC placed at the location — all through CanonKeeper as
proposals accepted for the opening. Task 6: pack agendas and plot threads
left behind by apply are committed when the story exists.

Every cross-component call asserts the real callee was invoked with the
expected arguments.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

import monitor_data.tools.mongodb_tools as mongo_tools
import monitor_data.tools.neo4j_tools.entities as neo_entities
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.world_seed import materialize as mat
from monitor_agents.world_seed.materialize import (
    materialize_chosen_start,
    prepare_starting_situation,
    resolve_chosen_start,
    situation_brief,
)

pytestmark = pytest.mark.unit

MARA_ID = str(uuid4())
TOBIAS_ID = str(uuid4())
DOCKS_ID = str(uuid4())


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
        "story_id": str(uuid4()),
        "character_id": str(uuid4()),
        "speaker_label": "Vex",
        "start_options": [_option_dict()],
    }


# ─── chosen-start resolution (task 7 skip contract) ──────────────────────────


def test_resolve_chosen_start_defaults_to_first_option():
    session = _session()
    option = resolve_chosen_start(session)
    assert option is not None
    assert option.option_id == "dockside-heist-1"
    assert session["chosen_start_option_id"] == "dockside-heist-1"


def test_resolve_chosen_start_honours_explicit_choice():
    session = _session()
    session["start_options"].append({**_option_dict(), "option_id": "last-watch-2", "title": "The Last Watch"})
    session["chosen_start_option_id"] = "last-watch-2"
    option = resolve_chosen_start(session)
    assert option is not None
    assert option.option_id == "last-watch-2"


def test_situation_brief_names_place_people_and_stakes():
    session = _session()
    session["materialized_start"] = {
        "location": "The Docks",
        "location_description": "rain-slick quay",
        "npcs": [{"name": "Mara", "want": "the ledger back"}],
        "hook": "The tide-locks ledger is gone.",
        "player_role": "the stranger",
    }
    brief = situation_brief(session)
    assert "The Docks" in brief
    assert "Mara" in brief
    assert "the ledger back" in brief
    assert "The tide-locks ledger is gone." in brief


# ─── materialization through CanonKeeper (task 4) ────────────────────────────


@pytest.mark.asyncio
async def test_materialize_commits_proposals_through_canonkeeper(monkeypatch: pytest.MonkeyPatch):
    """Cross-component: CanonKeeper.bulk_commit_proposals receives the
    entity instances (not archetypes), agendas, plot threads (with the
    story attached), and the PC placement relationship."""
    commit_calls: list[dict[str, Any]] = []

    async def _fake_bulk(self: Any, proposals: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        commit_calls.append({"proposals": proposals, "kwargs": kwargs})
        return {"committed": len(proposals), "errors": []}

    monkeypatch.setattr(CanonKeeper, "bulk_commit_proposals", _fake_bulk)
    _patch_proposal_staging(monkeypatch)
    _patch_npc_profiles(monkeypatch)
    _patch_name_resolution(monkeypatch)
    _patch_pack_proposal_query(monkeypatch, docs=[])

    session = _session()
    result = await materialize_chosen_start(session)

    assert result["option_id"] == "dockside-heist-1"
    # Three commit passes: entities, agendas, then threads + placement.
    assert len(commit_calls) == 3
    all_proposals = [p for call in commit_calls for p in call["proposals"]]
    types = [p["proposal_type"] for p in all_proposals]
    assert types.count("entity") == 3  # location + two NPCs
    assert types.count("create_agenda") == 2
    assert types.count("create_plot_thread") == 2
    assert types.count("entity_relationship") == 1

    by_type: dict[str, list[dict[str, Any]]] = {}
    for proposal in all_proposals:
        by_type.setdefault(proposal["proposal_type"], []).append(proposal)

    location = next(p for p in by_type["entity"] if p["payload"]["entity_type"] == "location")
    assert location["payload"]["name"] == "The Docks"
    assert location["payload"]["is_archetype"] is False

    npc = next(p for p in by_type["entity"] if p["payload"]["name"] == "Mara")
    assert npc["payload"]["is_archetype"] is False
    assert npc["payload"]["properties"]["want"] == "the ledger back"

    agenda = next(p for p in by_type["create_agenda"] if "Mara" in p["payload"]["title"])
    assert agenda["payload"]["description"] == "the ledger back"
    assert agenda["payload"]["owner_id"] == MARA_ID

    thread = next(p for p in by_type["create_plot_thread"] if p["payload"]["title"] == "The Missing Ledger")
    assert thread["story_id"] == session["story_id"]
    assert thread["payload"]["urgency"] == "high"

    placement = by_type["entity_relationship"][0]
    assert placement["payload"] == {
        "from_entity": "Vex",
        "rel_type": "located_in",
        "to_entity": "The Docks",
        "description": "Vex begins at The Docks.",
        "confidence": 1.0,
    }

    # The commit is scoped to the universe and skips contradiction checks
    # (it is the opening, not new evidence).
    assert commit_calls[0]["kwargs"]["universe_id"] is not None
    assert commit_calls[0]["kwargs"]["contradiction_check"] is False


@pytest.mark.asyncio
async def test_materialize_creates_npc_profiles_for_instances(monkeypatch: pytest.MonkeyPatch):
    """Cross-component: mongodb_create_npc_profile is invoked with the
    committed entity instance ids and each NPC's want."""
    created: list[Any] = []

    class _Profile:
        profile_id = "profile-1"

    def _fake_profile(params: Any) -> Any:
        created.append(params)
        return _Profile()

    monkeypatch.setattr(mongo_tools, "mongodb_create_npc_profile", _fake_profile)
    monkeypatch.setattr(CanonKeeper, "bulk_commit_proposals", _fake_bulk_ok)
    _patch_proposal_staging(monkeypatch)
    _patch_name_resolution(monkeypatch)
    _patch_pack_proposal_query(monkeypatch, docs=[])

    session = _session()
    result = await materialize_chosen_start(session)

    assert len(created) == 2
    by_entity = {str(p.entity_id): p for p in created}
    assert MARA_ID in by_entity
    assert by_entity[MARA_ID].desires == ["the ledger back"]
    assert by_entity[MARA_ID].gm_notes == "harbourmaster"
    assert len(result["profiles"]) == 2


@pytest.mark.asyncio
async def test_materialize_is_idempotent_per_option(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(CanonKeeper, "bulk_commit_proposals", _fake_bulk_ok)
    _patch_proposal_staging(monkeypatch)
    _patch_npc_profiles(monkeypatch)
    _patch_name_resolution(monkeypatch)
    _patch_pack_proposal_query(monkeypatch, docs=[])

    session = _session()
    first = await materialize_chosen_start(session)
    second = await materialize_chosen_start(session)
    assert first == second
    assert session["start_option"]["option_id"] == "dockside-heist-1"


@pytest.mark.asyncio
async def test_materialize_commits_leftover_pack_agendas_and_plot_threads(monkeypatch: pytest.MonkeyPatch):
    """Task 6: the pack's agendas and plot threads that apply-time left
    pending (or unresolved for want of a story) are committed once the
    opening story exists — and nothing else from the pack."""
    seen_query: dict[str, Any] = {}
    commit_calls: list[dict[str, Any]] = []

    async def _fake_bulk(self: Any, proposals: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        commit_calls.append({"proposals": proposals, "kwargs": kwargs})
        return {"committed": len(proposals), "errors": []}

    monkeypatch.setattr(CanonKeeper, "bulk_commit_proposals", _fake_bulk)
    _patch_proposal_staging(monkeypatch)
    _patch_npc_profiles(monkeypatch)
    _patch_name_resolution(monkeypatch)
    docs = [
        {"proposal_id": "p-agenda", "proposal_type": "create_agenda", "source": "knowledge_pack:" + str(uuid4())},
        {"proposal_id": "p-thread", "proposal_type": "create_plot_thread", "source": "knowledge_pack:" + str(uuid4())},
        {"proposal_id": "p-fact", "proposal_type": "create_lore_fact", "source": "knowledge_pack:" + str(uuid4())},
    ]
    _patch_pack_proposal_query(monkeypatch, docs=docs, captured=seen_query)

    session = _session()
    await materialize_chosen_start(session)

    assert seen_query["proposal_type"]["$in"] == ["create_agenda", "create_plot_thread"]
    pack_call = commit_calls[-1]
    committed_ids = {p["proposal_id"] for p in pack_call["proposals"]}
    assert committed_ids == {"p-agenda", "p-thread"}
    pack_thread = next(p for p in pack_call["proposals"] if p["proposal_id"] == "p-thread")
    assert pack_thread["story_id"] == session["story_id"]


# ─── pack apply path (task 6) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prepare_starting_situation_runs_seed_and_materializes_first(
    monkeypatch: pytest.MonkeyPatch,
):
    """Cross-component: WorldSeed.generate_start_options is invoked with the
    universe id and pack ids, and the first option is materialized."""
    seed_calls: dict[str, Any] = {}
    from monitor_agents.world_seed.seed import WorldSeed

    async def _fake_seed(self: Any, **kwargs: Any) -> Any:
        seed_calls.update(kwargs)
        return SimpleNamespace(
            universe_id=str(kwargs["universe_id"]),
            source="canon",
            options=[
                SimpleNamespace(
                    option_id="dockside-heist-1",
                    chip_dict=lambda: {"option_id": "dockside-heist-1", "title": "Dockside Heist"},
                    model_dump=lambda **_k: _option_dict(),
                )
            ],
            to_chips=lambda: [{"option_id": "dockside-heist-1", "title": "Dockside Heist"}],
        )

    materialize_calls: list[dict[str, Any]] = []

    async def _fake_materialize(session: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        materialize_calls.append({"session": session, "kwargs": kwargs})
        return {"option_id": "dockside-heist-1"}

    monkeypatch.setattr(WorldSeed, "generate_start_options", _fake_seed)
    monkeypatch.setattr(mat, "materialize_chosen_start", _fake_materialize)

    universe_id = str(uuid4())
    result = await prepare_starting_situation(universe_id, pack_ids=["pack-7"])

    assert seed_calls["universe_id"] == universe_id
    assert seed_calls["pack_ids"] == ["pack-7"]
    assert materialize_calls[0]["session"]["chosen_start_option_id"] == "dockside-heist-1"
    assert materialize_calls[0]["kwargs"]["universe_id"] == universe_id
    assert result["options"][0]["title"] == "Dockside Heist"


# ─── session bootstrap wrapper (task 4) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_bootstrap_with_start_invokes_materialization(monkeypatch: pytest.MonkeyPatch):
    """Cross-component: bootstrap_story_scene_with_start runs the sync
    bootstrap and then materializes the chosen start through
    materialize_chosen_start with the created story and universe."""
    from monitor_agents.loops import session_bootstrap

    calls: dict[str, Any] = {}

    def _fake_bootstrap(session: dict[str, Any]) -> tuple[str, str, None]:
        calls["bootstrap_session"] = session
        return "story-1", "scene-1", None

    async def _fake_materialize(session: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls["materialize_kwargs"] = kwargs
        calls["materialize_session"] = session
        return {"option_id": "dockside-heist-1"}

    monkeypatch.setattr(session_bootstrap, "bootstrap_story_scene", _fake_bootstrap)
    monkeypatch.setattr("monitor_agents.world_seed.materialize_chosen_start", _fake_materialize)

    session = _session()
    story_id, scene_id, error = await session_bootstrap.bootstrap_story_scene_with_start(session)

    assert (story_id, scene_id, error) == ("story-1", "scene-1", None)
    assert calls["bootstrap_session"] is session
    assert calls["materialize_kwargs"] == {"story_id": "story-1", "universe_id": session["universe_id"]}


@pytest.mark.asyncio
async def test_bootstrap_with_start_survives_materialization_failure(monkeypatch: pytest.MonkeyPatch):
    from monitor_agents.loops import session_bootstrap

    monkeypatch.setattr(
        session_bootstrap,
        "bootstrap_story_scene",
        lambda session: ("story-1", "scene-1", None),
    )

    async def _boom(session: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("keeper down")

    monkeypatch.setattr("monitor_agents.world_seed.materialize_chosen_start", _boom)

    story_id, scene_id, error = await session_bootstrap.bootstrap_story_scene_with_start(_session())
    assert story_id == "story-1"
    assert scene_id == "scene-1"
    assert error is not None and "start materialization failed" in error


# ─── shared patches ──────────────────────────────────────────────────────────


async def _fake_bulk_ok(self: Any, proposals: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    return {"committed": len(proposals), "errors": []}


def _patch_proposal_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        def __init__(self, proposal_id: Any) -> None:
            self.proposal_id = proposal_id

    def _fake_create(params: Any) -> Any:
        return _Resp(uuid4())

    monkeypatch.setattr(mongo_tools, "mongodb_create_proposed_change", _fake_create)


def _patch_npc_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Profile:
        profile_id = "profile-1"

    monkeypatch.setattr(mongo_tools, "mongodb_create_npc_profile", lambda params: _Profile())


def _patch_name_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_resolve(universe_id: str, name: str) -> str | None:
        return {"Mara": MARA_ID, "Tobias": TOBIAS_ID, "The Docks": DOCKS_ID}.get(name)

    monkeypatch.setattr(mat, "_entity_name_to_id", _fake_resolve)

    async def _fake_pc_name(session: dict[str, Any], universe_id: str) -> str | None:
        return str(session.get("speaker_label") or "") or None

    monkeypatch.setattr(mat, "_pc_name", _fake_pc_name)

    def _fake_get_entity(entity_id: Any) -> Any:
        return SimpleNamespace(id=entity_id, name="Vex")

    monkeypatch.setattr(neo_entities, "neo4j_get_entity", _fake_get_entity)


def _patch_pack_proposal_query(
    monkeypatch: pytest.MonkeyPatch,
    *,
    docs: list[dict[str, Any]],
    captured: dict[str, Any] | None = None,
) -> None:
    class _Cursor(list):
        def limit(self, _n: int) -> "_Cursor":
            return self

    class _Coll:
        def find(self, query: dict[str, Any]) -> _Cursor:
            if captured is not None:
                captured.update(query)
            allowed = query.get("proposal_type", {}).get("$in")
            matched = [dict(doc) for doc in docs if allowed is None or doc.get("proposal_type") in allowed]
            return _Cursor(matched)

    class _Mongo:
        def get_collection(self, _name: str) -> _Coll:
            return _Coll()

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: _Mongo())
