"""NPCProfile seeding for entities created via the extraction pipeline."""

from __future__ import annotations

import uuid as _uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.loops.scene_loop import seed_npc_profiles_for_accepted_proposals


def _char_proposal(name: str, *, description: str = "A wandering stranger.", universe_id: str = "") -> dict[str, Any]:
    return {
        "proposal_type": "ENTITY",
        "content": {
            "name": name,
            "entity_type": "CHARACTER",
            "description": description,
            "universe_id": universe_id,
        },
        "summary": f"New entity: {name}",
        "confidence": 0.9,
        "authority": "SYSTEM",
        "proposer": "narrator",
    }


def _other_proposal() -> dict[str, Any]:
    return {
        "proposal_type": "FACT",
        "content": {"fact": "The sun is bright."},
        "summary": "Fact",
        "confidence": 0.9,
        "authority": "SYSTEM",
        "proposer": "narrator",
    }


@pytest.mark.asyncio
async def test_skips_non_character_proposals() -> None:
    universe = str(_uuid.uuid4())
    with patch("monitor_data.tools.mongodb_tools.mongodb_create_npc_profile", new_callable=AsyncMock) as m:
        n = await seed_npc_profiles_for_accepted_proposals(
            [_other_proposal(), _other_proposal()],
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    assert n == 0
    assert m.call_count == 0


@pytest.mark.asyncio
async def test_creates_profile_for_character_proposal() -> None:
    universe = str(_uuid.uuid4())
    entity_id = _uuid.uuid4()
    fake_entity = {"id": str(entity_id), "name": "Vex", "universe_id": universe}
    captured: dict[str, Any] = {}

    def _fake_create(params: Any) -> Any:
        captured["params"] = params
        return None

    with (
        patch(
            "monitor_agents.loops.scene_loop._lookup_entity_by_name_and_universe",
            new=AsyncMock(return_value=fake_entity),
        ),
        patch("monitor_data.tools.mongodb_tools.mongodb_create_npc_profile", new=_fake_create),
    ):
        n = await seed_npc_profiles_for_accepted_proposals(
            [_char_proposal("Vex", description="A wandering stranger with a scar.", universe_id=universe)],
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    assert n == 1
    assert "params" in captured
    params = captured["params"]
    assert str(params.entity_id) == str(entity_id)
    assert params.current_emotional_state == "neutral"
    assert "scar" in (params.gm_notes or "")


@pytest.mark.asyncio
async def test_skips_when_entity_not_found_in_neo4j() -> None:
    universe = str(_uuid.uuid4())
    called: list[Any] = []

    def _fake_create(params: Any) -> Any:
        called.append(params)
        return None

    with (
        patch(
            "monitor_agents.loops.scene_loop._lookup_entity_by_name_and_universe",
            new=AsyncMock(return_value=None),
        ),
        patch("monitor_data.tools.mongodb_tools.mongodb_create_npc_profile", new=_fake_create),
    ):
        n = await seed_npc_profiles_for_accepted_proposals(
            [_char_proposal("Ghost", universe_id=universe)],
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    assert n == 0
    assert called == []


@pytest.mark.asyncio
async def test_failure_does_not_raise() -> None:
    universe = str(_uuid.uuid4())
    fake_entity = {"id": str(_uuid.uuid4()), "name": "Vex", "universe_id": universe}

    def _boom(params: Any) -> None:
        raise RuntimeError("db down")

    with (
        patch(
            "monitor_agents.loops.scene_loop._lookup_entity_by_name_and_universe",
            new=AsyncMock(return_value=fake_entity),
        ),
        patch("monitor_data.tools.mongodb_tools.mongodb_create_npc_profile", new=_boom),
    ):
        n = await seed_npc_profiles_for_accepted_proposals(
            [_char_proposal("Vex", universe_id=universe)],
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    assert n == 0  # did not raise, just logged


@pytest.mark.asyncio
async def test_empty_proposals_returns_zero() -> None:
    n = await seed_npc_profiles_for_accepted_proposals(
        [],
        universe_id=_uuid.uuid4(),
        scene_id=_uuid.uuid4(),
        story_id=_uuid.uuid4(),
    )
    assert n == 0


@pytest.mark.asyncio
async def test_mixed_proposals_only_seeds_characters() -> None:
    universe = str(_uuid.uuid4())
    char_entity_id = _uuid.uuid4()
    fake_char_entity = {"id": str(char_entity_id), "name": "Vex", "universe_id": universe}
    called: list[Any] = []

    def _fake_create(params: Any) -> Any:
        called.append(params)
        return None

    proposals = [
        _char_proposal("Vex", universe_id=universe),
        {
            "proposal_type": "ENTITY",
            "content": {
                "name": "The Tavern",
                "entity_type": "LOCATION",
                "description": "A dimly lit corner of the docks.",
                "universe_id": universe,
            },
            "summary": "New location",
            "confidence": 0.9,
            "authority": "SYSTEM",
            "proposer": "narrator",
        },
        _other_proposal(),
    ]

    with (
        patch(
            "monitor_agents.loops.scene_loop._lookup_entity_by_name_and_universe",
            new=AsyncMock(return_value=fake_char_entity),
        ),
        patch("monitor_data.tools.mongodb_tools.mongodb_create_npc_profile", new=_fake_create),
    ):
        n = await seed_npc_profiles_for_accepted_proposals(
            proposals,
            universe_id=_uuid.UUID(universe),
            scene_id=_uuid.uuid4(),
            story_id=_uuid.uuid4(),
        )
    # Only the CHARACTER proposal is seeded; LOCATION and FACT are skipped.
    assert n == 1
    assert len(called) == 1
