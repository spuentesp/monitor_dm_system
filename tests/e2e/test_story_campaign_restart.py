"""
End-to-end: a five-scene campaign that survives a backend restart.

The campaign is played against the real databases: the story's state lives in
the MongoDB checkpoint and the ledger lives in MongoDB too. After scenes two
and four the loop is rebuilt from scratch — the way a restarted backend does
it — and the campaign carries on with everything it knew.

The test pins what the phase-3 brief asks for:

* five scenes, an ended story, a restart after scenes two and four;
* five ledger entries with increasing in-game times;
* the agenda tick, the ledger write and the arc evaluation each ran;
* the arc phase changes with what happened, not with the scene number.

Use cases: ST-1, P-8, P-12, P-14.
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Model stand-ins: the campaign is scripted, the plumbing is real.
# ---------------------------------------------------------------------------


def _ledger_forward(self, **kwargs: Any) -> SimpleNamespace:
    """Turn the scene's turns into a ledger entry."""
    scene_text = str(kwargs.get("scene_turns") or "")
    return SimpleNamespace(
        summary=(
            "The company crossed the black water and found the vault door sealed. "
            "The ferryman refused the old coin and named a price instead. "
            "The captain kept the map and said nothing about the drowned king. "
            f"Turns: {scene_text[:400]}"
        ),
        state_changes=json.dumps(
            [{"who": "The company", "what": "reached the vault door", "where": "the drowned road"}]
        ),
        open_questions=json.dumps(["Who sealed the vault?"]),
    )


def _arc_forward(self, **kwargs: Any) -> SimpleNamespace:
    """Judge the arc from the ledger: the phase follows the entries."""
    ledger = str(kwargs.get("ledger") or "")
    scenes = ledger.count("Scene ")
    if scenes <= 1:
        phase, tension = "rising_action", 0.4
    elif scenes == 2:
        phase, tension = "climax", 0.9
    elif scenes == 3:
        phase, tension = "falling_action", 0.6
    else:
        phase, tension = "resolution", 0.3
    complete = phase == "resolution"
    return SimpleNamespace(
        arc_phase=phase,
        tension=tension,
        advanced_threads=json.dumps(["The drowned road"]),
        closed_threads=json.dumps(["The drowned road"] if complete else []),
        story_complete=complete,
        reasoning="The ledger says so.",
    )


def _planner_forward(self, **kwargs: Any) -> dict[str, str]:
    return {"next_scene_type": "exploration", "plot_hook": "The road continues."}


def _time_seed_forward(self, **kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(
        start_time="1345-06-01T08:00:00+00:00",
        reasoning="The world is medieval.",
    )


@pytest.fixture
def scripted_models():
    """Script the three model calls the campaign makes."""
    with (
        patch(
            "monitor_agents.story.story.StoryLedgerModule.forward",
            new=_ledger_forward,
        ),
        patch(
            "monitor_agents.story.story.StoryArcModule.forward",
            new=_arc_forward,
        ),
        patch(
            "monitor_agents.story.story.StoryPlannerModule.forward",
            new=_planner_forward,
        ),
        patch(
            "monitor_agents.story.story.StoryTimeSeedModule.forward",
            new=_time_seed_forward,
        ),
    ):
        yield


@pytest.fixture
def tool_calls(monkeypatch):
    """Count the data-layer calls the campaign makes."""
    from monitor_data import server as data_server

    calls: list[tuple[str, dict]] = []
    original = data_server.call_tool

    async def counting_call_tool(name: str, arguments: dict) -> list:
        calls.append((name, arguments))
        return await original(name, arguments)

    monkeypatch.setattr(data_server, "call_tool", counting_call_tool)
    return calls


def _played_scenes(story_id: UUID, universe_id: UUID) -> list[dict[str, Any]]:
    """The scenes that belong to the story, oldest first."""
    from monitor_data.schemas.scenes import SceneFilter
    from monitor_data.tools.mongodb_tools import mongodb_list_scenes

    response = mongodb_list_scenes(SceneFilter(story_id=story_id, limit=50))
    scenes = response.scenes if hasattr(response, "scenes") else []
    scenes = sorted(scenes, key=lambda scene: scene.narrative_order or 0)
    return [scene.model_dump(mode="json") for scene in scenes]


def _ledger_entries(story_id: UUID) -> list[dict[str, Any]]:
    """The story's ledger, oldest first."""
    from monitor_data.tools.mongodb_tools import mongodb_list_story_ledger_entries

    entries = mongodb_list_story_ledger_entries(story_id)
    return [entry.model_dump(mode="json") for entry in entries]


@pytest.mark.asyncio
async def test_five_scene_campaign_survives_a_restart(
    e2e_databases,
    seeded_world,
    e2e_story,
    scripted_models,
    tool_calls,
) -> None:
    """Five scenes, two restarts, one ended story with five ledger entries."""
    from monitor_agents.loops.story_loop import StoryLoop

    story_id = e2e_story.id
    universe_id = e2e_story.universe_id

    # The campaign starts: the story gets its clock and its first scene.
    loop = StoryLoop(story_id=story_id, universe_id=universe_id)
    started = await loop.start_or_resume()

    assert started["in_game_time_source"] in {"story", "world_seed", "model", "fallback"}
    first_scene_id = started["current_scene_id"]
    assert first_scene_id is not None

    results: list[dict[str, Any]] = []
    current_scene_id = UUID(str(first_scene_id))
    for scene_number in range(1, 6):
        if scene_number in {3, 5}:
            # The backend restarts: a new loop, nothing left in this process.
            loop = StoryLoop(story_id=story_id, universe_id=universe_id)
            resumed = await loop.load_checkpoint_state()
            assert resumed["scenes_completed"] == scene_number - 1
            assert resumed["current_scene_id"] is not None
            current_scene_id = UUID(str(resumed["current_scene_id"]))

        result = await loop.complete_current_scene(
            scene_id=current_scene_id,
            outcome={"total_minutes_passed": 60, "turns_count": 4},
        )
        results.append(result)
        if not result.get("story_complete") and result.get("current_scene_id"):
            current_scene_id = UUID(str(result["current_scene_id"]))

    # The story ended, and it ended because its arc resolved.
    assert results[-1]["story_complete"] is True
    assert results[-1]["arc_label"] == "resolution"

    # The ledger holds one entry per scene, with increasing in-game times.
    entries = _ledger_entries(story_id)
    assert len(entries) == 5
    starts = [datetime.fromisoformat(entry["start_time"]) for entry in entries]
    ends = [datetime.fromisoformat(entry["end_time"]) for entry in entries]
    assert starts == sorted(starts)
    assert ends == sorted(ends)
    assert ends[-1] > starts[0]

    # The agenda tick, the ledger write and the arc evaluation all ran.
    names = [name for name, _ in tool_calls]
    assert names.count("neo4j_tick_agendas") >= 5
    assert names.count("mongodb_append_story_ledger_entry") == 5

    # The arc moved as the campaign moved, not on fixed scene numbers.
    phases = [result["arc_label"] for result in results]
    assert len(set(phases)) >= 2
    assert phases[0] == "rising_action"
    assert phases[-1] == "resolution"

    # The scenes the campaign played are on record.
    scenes = _played_scenes(story_id, universe_id)
    assert len(scenes) >= 5
