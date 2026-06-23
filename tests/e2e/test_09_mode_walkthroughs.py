"""
Mode walkthroughs (FINAL_FABLE T-029/T-030/T-031).

One scripted end-to-end pass per product mode, driving the LIVE backend over
HTTP (like test_07) plus the data layer in-process where the public API has
no creation path. Tests skip when the backend is unreachable.

Written UI versions of these walkthroughs live in docs/gameplay-examples/.

Use cases: MP-5..MP-9, M-1/M-2, CF-4..CF-8, P-4, P-18, Q-state.
"""

from __future__ import annotations

import os
from typing import Any, Dict
from uuid import uuid4

import pytest
import requests

API = os.environ.get("MONITOR_API_URL", "http://localhost:8001/api")

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


def _backend_up() -> bool:
    try:
        return requests.get(f"{API}/health", timeout=5).status_code == 200
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
def live_backend() -> str:
    if not _backend_up():
        pytest.skip(f"live backend not reachable at {API}")
    return API


@pytest.fixture(scope="module")
def walkthrough_universe(live_backend: str) -> Dict[str, Any]:
    """Fresh multiverse + universe created through the public API."""
    mv = requests.post(
        f"{live_backend}/universes/multiverses",
        json={"name": f"Walkthrough MV {uuid4().hex[:6]}", "description": "T-029"},
        timeout=30,
    )
    mv.raise_for_status()
    mv_id = mv.json()["id"]

    u = requests.post(
        f"{live_backend}/universes/universes",
        json={
            "multiverse_id": mv_id,
            "name": f"Walkthrough U {uuid4().hex[:6]}",
            "description": "Mode walkthrough universe",
            "genre": "fantasy",
        },
        timeout=30,
    )
    u.raise_for_status()
    return {"multiverse_id": mv_id, "universe_id": u.json()["id"]}


# ─────────────────────────────────────────────────────────────────────────────
# T-029 — World Architect: pack with content → apply → world state shows it
# ─────────────────────────────────────────────────────────────────────────────


def test_world_architect_walkthrough(live_backend: str, walkthrough_universe: Dict[str, Any]) -> None:
    from monitor_data.schemas.knowledge_packs import (
        ExtractedEntityArchetype,
        ExtractedLoreFact,
        KnowledgePackCreate,
        KnowledgePackStatus,
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools import mongodb_create_knowledge_pack

    universe_id = walkthrough_universe["universe_id"]

    # 1. Curate a small pack (in-process — the manual-curation path)
    pack = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name=f"Millhaven Pack {uuid4().hex[:6]}",
            description="Walkthrough content pack",
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            status=KnowledgePackStatus.READY,
            entity_archetypes=[
                ExtractedEntityArchetype(
                    name="Barnaby the Innkeeper",
                    entity_type="character",
                    description="A nervous innkeeper who knows too much.",
                ),
                ExtractedEntityArchetype(
                    name="Millhaven Cemetery",
                    entity_type="location",
                    description="Fog-bound graveyard at the village edge.",
                ),
            ],
            lore_facts=[
                ExtractedLoreFact(
                    statement="An unnatural mist rises in Millhaven after dusk.",
                    source_ref="walkthrough",
                )
            ],
        )
    )

    # 2a. Review path (MP-5): apply creates PENDING proposals for the GM
    applied = requests.post(
        f"{live_backend}/ingest/packs/{pack.id}/apply/{universe_id}",
        json={"mode": "full"},
        timeout=120,
    )
    assert applied.status_code == 200, applied.text
    review = applied.json()
    assert review["status"] == "review_pending"
    assert review["proposals_created"] >= 3, review

    # 2b. Direct path: canonize a second pack straight into the universe
    pack2 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name=f"Millhaven Canon {uuid4().hex[:6]}",
            description="Walkthrough direct-canonize pack",
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            status=KnowledgePackStatus.READY,
            entity_archetypes=[
                ExtractedEntityArchetype(
                    name="Barnaby the Innkeeper",
                    entity_type="character",
                    description="A nervous innkeeper who knows too much.",
                )
            ],
            lore_facts=[
                ExtractedLoreFact(
                    statement="An unnatural mist rises in Millhaven after dusk.",
                    source_ref="walkthrough",
                )
            ],
        )
    )
    canonized = requests.post(
        f"{live_backend}/ingest/packs/{pack2.id}/canonize",
        json={
            "multiverse_id": walkthrough_universe["multiverse_id"],
            "universe_id": universe_id,
        },
        timeout=180,
    )
    assert canonized.status_code == 200, canonized.text

    # 3. The world state endpoint shows the new canon (O1)
    state = requests.get(
        f"{live_backend}/universes/universes/{universe_id}/state", timeout=60
    )
    assert state.status_code == 200, state.text
    payload = state.json()
    names = {e.get("name") for e in payload.get("entities", [])}
    assert "Barnaby the Innkeeper" in names, f"entities: {sorted(filter(None, names))}"


# ─────────────────────────────────────────────────────────────────────────────
# T-030 — GM Co-Pilot: hooks → contradictions → prep → handout → canon review
# ─────────────────────────────────────────────────────────────────────────────


def test_gm_copilot_walkthrough(live_backend: str, walkthrough_universe: Dict[str, Any]) -> None:
    from monitor_data.schemas.base import Authority
    from monitor_data.schemas.base import ProposalType
    from monitor_data.schemas.proposed_changes import ProposedChangeCreate
    from monitor_data.schemas.stories import StoryCreate, StoryStatus, StoryType
    from monitor_data.tools.mongodb_tools import mongodb_create_proposed_change
    from monitor_data.tools.neo4j_tools import neo4j_create_story

    universe_id = walkthrough_universe["universe_id"]

    story = neo4j_create_story(
        StoryCreate(
            universe_id=universe_id,
            title="The Shadow Conspiracy",
            story_type=StoryType.CAMPAIGN,
            theme="mystery",
            premise="Villagers vanish into the mist.",
            status=StoryStatus.ACTIVE,
        )
    )
    story_id = str(story.id)

    # CF-4 plot hooks / CF-5 contradictions / CF-7 prep / CF-6 handouts
    hooks = requests.post(
        f"{live_backend}/gm/hooks",
        json={"universe_id": universe_id, "story_id": story_id, "max_hooks": 3},
        timeout=180,
    )
    assert hooks.status_code == 200, hooks.text
    assert isinstance(hooks.json().get("hooks"), list)

    contradictions = requests.post(
        f"{live_backend}/gm/contradictions",
        json={"universe_id": universe_id},
        timeout=180,
    )
    assert contradictions.status_code == 200, contradictions.text
    assert isinstance(contradictions.json().get("contradictions"), list)

    prep = requests.post(
        f"{live_backend}/gm/session-prep",
        json={"universe_id": universe_id, "story_id": story_id},
        timeout=180,
    )
    assert prep.status_code == 200, prep.text

    handout = requests.post(
        f"{live_backend}/gm/handouts",
        json={
            "universe_id": universe_id,
            "story_id": story_id,
            "handout_type": "session_recap",
        },
        timeout=180,
    )
    assert handout.status_code == 200, handout.text

    # CF-8 canon review queue: propose (scene-scoped) → list → accept
    from monitor_data.schemas.scenes import SceneCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_scene

    scene = mongodb_create_scene(
        SceneCreate(
            story_id=story.id,
            universe_id=universe_id,
            title="Recording: night one",
            purpose="Co-pilot walkthrough capture",
        )
    )

    proposal = mongodb_create_proposed_change(
        ProposedChangeCreate(
            scene_id=scene.scene_id,
            story_id=story.id,
            change_type=ProposalType.FACT,
            content={"statement": "Magda the elder is missing."},
            authority=Authority.GM,
            proposer="walkthrough",
        )
    )

    queue = requests.get(
        f"{live_backend}/stories/{story_id}/canon-queue", timeout=60
    )
    assert queue.status_code == 200, queue.text
    queue_ids = {
        p.get("proposal_id")
        for scene_review in queue.json().get("scenes", [])
        for p in scene_review.get("pending", [])
    }
    assert str(proposal.proposal_id) in queue_ids, f"queue ids: {queue_ids}"

    verdict = requests.post(
        f"{live_backend}/canon-review/verdicts",
        json={
            "decided_by": "Walkthrough GM",
            "items": [
                {
                    "proposal_id": str(proposal.proposal_id),
                    "decision": "accepted",
                    "reason": "Confirmed at the table.",
                }
            ],
        },
        timeout=60,
    )
    assert verdict.status_code == 200, verdict.text
    assert verdict.json()[0]["status"] == "accepted"


# ─────────────────────────────────────────────────────────────────────────────
# T-031 — Autonomous GM extras: oracle + dice resolution structure
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_autonomous_gm_extras_walkthrough(walkthrough_universe: Dict[str, Any]) -> None:
    from monitor_agents.oracle import Oracle
    from monitor_agents.resolver import Resolver

    # P-18: the oracle answers an unknown-state question with a canonical
    # outcome in the yes/no(+and/but) space.
    oracle = Oracle()
    result = oracle.resolve_question(
        question="Is the cellar door locked?",
        tension_score=0.7,
    )
    outcome = result["outcome"] if isinstance(result, dict) else result.outcome
    assert str(getattr(outcome, "value", outcome)) in {
        "yes",
        "no",
        "yes_and",
        "yes_but",
        "no_and",
        "no_but",
    }, result

    # P-4: a committed attack in dice mode produces a structured resolution.
    resolver = Resolver()
    res = await resolver.resolve_turn(
        scene_id=str(uuid4()),
        user_input="I swing my sword at the possessed villager!",
        context={
            "entities": [
                {"name": "Kael", "properties": {"attributes": {"Strength": 14}}}
            ]
        },
        play_mode="dice_standard",
    )
    assert res["resolution_type"] in {"dice", "propose_roll", "trivial", "narrative"}
    if res["resolution_type"] == "dice":
        assert res["roll_total"] is not None
    assert res["success_level"]
