"""
Guided start walkthrough (Phase 2).

One scripted end-to-end pass per world type — a fresh Quick World universe
and an applied-pack universe — driving the LIVE backend over HTTP (like
test_09) plus the data layer in-process where the public API has no
creation path. Tests skip when the backend is unreachable.

The scripted player reaches active play in at most 5 GM turns; the opening
names the materialized location and at least two NPCs (instances in Neo4j,
profiles in MongoDB); the story carries at least two plot threads; and the
start options differ between the two worlds.

Use cases: P-1, P-15, P-2, MP-7, M-12.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID, uuid4

import pytest
import requests

API = os.environ.get("MONITOR_API_URL", "http://localhost:8001/api")

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


@pytest.fixture(scope="module")
def guided_start_notes() -> dict[str, Any]:
    """Shared notes across the two world walkthroughs (option chip titles)."""
    return {}


def _backend_up() -> bool:
    try:
        return requests.get(f"{API}/health", timeout=5).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def live_backend() -> str:
    if not _backend_up():
        pytest.skip(f"live backend not reachable at {API}")
    return API


# ─── scripted player helpers ─────────────────────────────────────────────────


def _create_session(
    live_backend: str, universe_id: str, multiverse_id: str | None
) -> dict[str, Any]:
    response = requests.post(
        f"{live_backend}/chat",
        json={
            "title": f"Guided Start {uuid4().hex[:6]}",
            "mode": "autonomous_gm",
            "tone": "grim",
            "universe_id": universe_id,
            "multiverse_id": multiverse_id,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _send(live_backend: str, session_id: str, content: str) -> dict[str, Any]:
    response = requests.post(
        f"{live_backend}/chat/{session_id}/send",
        json={"content": content},
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def _play_guided_start(
    live_backend: str, session_id: str, first_meta: dict[str, Any]
) -> list[dict[str, Any]]:
    """Scripted player: pick the first start option, answer briefly, skip to
    play. Returns the GM messages after the creation question. Reaching
    active play must take at most 5 GM turns including the creation
    question (GM turn 1).
    """
    options = first_meta.get("start_options") or [{}]
    picked = options[0].get("title") or "Surprise me"
    gm_messages: list[dict[str, Any]] = []

    gm_messages.append(_send(live_backend, session_id, picked))
    gm_messages.append(
        _send(
            live_backend, session_id, "My name is Wren, a tide-lock scribe with a stolen key. done"
        )
    )

    # Skip to play (task 7): must still produce a seeded opening that
    # materializes the chosen start.
    response = requests.post(f"{live_backend}/chat/{session_id}/skip-preplay", timeout=240)
    response.raise_for_status()
    gm_messages.append(response.json())
    return gm_messages


def _assert_reached_active_play(
    live_backend: str, session_id: str, gm_turn_count: int
) -> dict[str, Any]:
    assert gm_turn_count <= 5, f"reached active play in {gm_turn_count} GM turns (max 5)"
    state = requests.get(f"{live_backend}/chat/{session_id}/state", timeout=60)
    state.raise_for_status()
    payload = state.json()
    phase = (payload.get("session") or {}).get("phase") or payload.get("phase")
    assert phase == "active_play", f"phase is {phase!r}"
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Quick World universe
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def quick_world(live_backend: str) -> dict[str, Any]:
    response = requests.post(
        f"{live_backend}/forge/quick-world",
        json={"seed": f"a rain-soaked port where the tide-locks are failing {uuid4().hex[:4]}"},
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "universe_id": data["universe_id"],
        "multiverse_id": data.get("multiverse_id"),
        "world_name": data.get("world_name", ""),
    }


def test_quick_world_guided_start_reaches_active_play(
    live_backend: str, quick_world: dict[str, Any], guided_start_notes: dict[str, Any]
) -> None:
    session = _create_session(
        live_backend, quick_world["universe_id"], quick_world["multiverse_id"]
    )
    session_id = session["id"]
    messages = requests.get(f"{live_backend}/chat/{session_id}/messages", timeout=60).json()
    assert messages, "session creation must produce the first GM question"
    first_meta = messages[-1].get("metadata") or {}
    assert first_meta.get("category") == "start_choice", first_meta
    quick_titles = [chip.get("title") for chip in first_meta.get("start_options", [])]
    assert quick_titles, "the start question must carry structured start options for the UI chips"
    guided_start_notes["quick_titles"] = quick_titles

    gm_messages = _play_guided_start(live_backend, session_id, first_meta)
    # GM turns: creation question + one per scripted player step.
    _assert_reached_active_play(live_backend, session_id, gm_turn_count=1 + len(gm_messages))

    opening = gm_messages[-1]
    assert (opening.get("metadata") or {}).get("preplay_finalized") is True
    materialized = (opening.get("metadata") or {}).get("materialized_start") or {}
    picked_option_id = (first_meta.get("start_options") or [{}])[0].get("option_id")
    assert materialized.get("option_id") == picked_option_id, (
        f"materialized {materialized.get('option_id')!r}, picked {picked_option_id!r}"
    )
    location = materialized.get("location") or ""
    npc_names = [npc.get("name") for npc in materialized.get("npcs", []) if npc.get("name")]
    assert location, f"no location materialized: {materialized}"
    assert len(npc_names) >= 2, f"expected 2+ NPCs materialized: {materialized}"

    # Done-when: the opening names the location and at least two NPCs.
    text = opening.get("content", "")
    assert location.lower() in text.lower(), f"opening does not name {location!r}"
    named = [name for name in npc_names if name.lower() in text.lower()]
    assert len(named) >= 2, f"opening names only {named} of {npc_names}"

    _assert_world_state(
        quick_world["universe_id"], location, npc_names, opening["metadata"]["story_id"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Applied-pack universe
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def pack_world(live_backend: str) -> dict[str, Any]:
    from monitor_data.schemas.knowledge_packs import (
        ExtractedAgenda,
        ExtractedEntityArchetype,
        ExtractedLoreFact,
        ExtractedPlotThread,
        KnowledgePackCreate,
        KnowledgePackStatus,
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools import mongodb_create_knowledge_pack

    pack = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name=f"Guided Start Pack {uuid4().hex[:6]}",
            description="Walkthrough content pack for the guided start",
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            status=KnowledgePackStatus.READY,
            entity_archetypes=[
                ExtractedEntityArchetype(
                    name="Sister Aveline",
                    entity_type="character",
                    description="A bell-keeper of the drowned cathedral.",
                ),
                ExtractedEntityArchetype(
                    name="Cass the Ferryman",
                    entity_type="character",
                    description="Ferries the dead across the flooded nave.",
                ),
                ExtractedEntityArchetype(
                    name="The Drowned Cathedral",
                    entity_type="location",
                    description="A cathedral half-sunk in the harbour.",
                ),
            ],
            lore_facts=[
                ExtractedLoreFact(
                    statement="The cathedral bells ring below the waterline.",
                    source_ref="walkthrough",
                )
            ],
            agendas=[
                ExtractedAgenda(
                    title="Silence the bells", description="Aveline wants the bells stopped."
                ),
            ],
            plot_threads=[
                ExtractedPlotThread(
                    title="Who rings the bells", description="The ringers drowned years ago."
                ),
                ExtractedPlotThread(
                    title="Cass's last fare", description="One passenger never paid."
                ),
            ],
        )
    )

    applied = requests.post(
        f"{live_backend}/ingest/packs/{pack.id}/apply/new-world",
        json={"world_name": f"Drowned See {uuid4().hex[:4]}"},
        timeout=180,
    )
    assert applied.status_code == 201, applied.text
    result = applied.json()
    assert result.get("can_prepare_starting_situation") is True

    # Accept and commit the pack's proposals so the universe holds canon.
    proposals = requests.get(
        f"{live_backend}/ingest/packs/{pack.id}/proposals",
        params={"status": "pending", "per_page": 500},
        timeout=60,
    )
    proposals.raise_for_status()
    pending = proposals.json()["proposals"]
    if pending:
        reviewed = requests.post(
            f"{live_backend}/ingest/proposals/batch",
            json={
                "actions": [
                    {
                        "proposal_id": p["proposal_id"],
                        "action": "accept",
                        "reason": "walkthrough auto-accept",
                    }
                    for p in pending
                ]
            },
            timeout=120,
        )
        reviewed.raise_for_status()
        committed = requests.post(f"{live_backend}/ingest/packs/{pack.id}/commit", timeout=180)
        committed.raise_for_status()

    return {
        "universe_id": result["universe_id"],
        "multiverse_id": result.get("multiverse_id"),
        "pack_id": str(pack.id),
    }


def test_pack_world_guided_start_reaches_active_play(
    live_backend: str, pack_world: dict[str, Any], guided_start_notes: dict[str, Any]
) -> None:
    session = _create_session(live_backend, pack_world["universe_id"], pack_world["multiverse_id"])
    session_id = session["id"]
    messages = requests.get(f"{live_backend}/chat/{session_id}/messages", timeout=60).json()
    first_meta = messages[-1].get("metadata") or {}
    pack_titles = [chip.get("title") for chip in first_meta.get("start_options", [])]
    assert pack_titles, "the pack world must also present structured start options"
    guided_start_notes["pack_titles"] = pack_titles

    gm_messages = _play_guided_start(live_backend, session_id, first_meta)
    _assert_reached_active_play(live_backend, session_id, gm_turn_count=1 + len(gm_messages))

    opening = gm_messages[-1]
    materialized = (opening.get("metadata") or {}).get("materialized_start") or {}
    location = materialized.get("location") or ""
    npc_names = [npc.get("name") for npc in materialized.get("npcs", []) if npc.get("name")]
    assert location and len(npc_names) >= 2, materialized
    text = opening.get("content", "")
    assert location.lower() in text.lower()
    named = [name for name in npc_names if name.lower() in text.lower()]
    assert len(named) >= 2, f"opening names only {named} of {npc_names}"

    _assert_world_state(
        pack_world["universe_id"], location, npc_names, opening["metadata"]["story_id"]
    )


def test_start_options_differ_between_worlds(guided_start_notes: dict[str, Any]) -> None:
    quick_titles = guided_start_notes.get("quick_titles") or []
    pack_titles = guided_start_notes.get("pack_titles") or []
    assert quick_titles and pack_titles
    assert set(quick_titles) != set(pack_titles), (
        f"start options must differ between worlds: {quick_titles} vs {pack_titles}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Resume after a backend restart (manual step — see docstring)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.skip(
    reason=(
        "Killing the backend mid-flow is a manual step: run this suite once, "
        "kill the backend after the second GM question, restart it, and "
        "continue sending — the next question must be the same one. The "
        "unit-level equivalent is covered in "
        "packages/agents/tests/test_preplay_restart_resume.py."
    )
)
def test_resume_after_backend_restart(live_backend: str) -> None:  # pragma: no cover
    raise NotImplementedError


# ─── shared world-state assertions ───────────────────────────────────────────


def _assert_world_state(
    universe_id: str, location: str, npc_names: list[str], story_id: str
) -> None:
    """Done-when: instances in Neo4j with profiles in MongoDB; 2+ threads."""
    from monitor_data.schemas.entities import EntityFilter
    from monitor_data.schemas.story_outlines import PlotThreadFilter
    from monitor_data.tools.mongodb_tools import mongodb_get_npc_profiles_by_entities
    from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities
    from monitor_data.tools.neo4j_tools.stories import neo4j_list_plot_threads

    listing = neo4j_list_entities(EntityFilter(universe_id=UUID(universe_id), limit=200))
    instances = {e.name: e for e in listing.entities if not e.is_archetype}
    assert location in instances, f"location instance missing: {sorted(instances)}"
    npc_ids = []
    for name in npc_names:
        assert name in instances, f"NPC instance missing: {name}"
        assert instances[name].entity_type.value.lower() == "character"
        npc_ids.append(instances[name].id)

    profiles = mongodb_get_npc_profiles_by_entities(npc_ids)
    assert len(profiles) >= 2, f"NPC profiles in MongoDB must back the NPC instances: {profiles}"

    threads = neo4j_list_plot_threads(PlotThreadFilter(story_id=UUID(story_id), limit=50))
    assert len(threads.threads) >= 2, (
        f"expected at least 2 plot threads, got {len(threads.threads)}"
    )
