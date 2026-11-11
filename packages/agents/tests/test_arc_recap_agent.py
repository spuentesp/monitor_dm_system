"""CF-12: RecapAgent.generate_arc_recap — campaign-level (story-arc) recap.

Pins the map-reduce chunking (scene recaps -> arc beats per chunk -> one
campaign synthesis), the empty-story edge (no LLM call, no persistence),
the accepted-proposals-only canon filter, the detail length controls, and
idempotent persistence (one upsert per story per generation).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from monitor_agents.recap.agent import ARC_RECAP_CHUNK_SIZE, RecapAgent
from monitor_data.schemas.arc_recaps import ArcRecap, ArcRecapCreate, ArcRecapDetail
from monitor_data.schemas.base import ProposalStatus


def _scene(index: int) -> dict:
    return {
        "scene_id": str(uuid4()),
        "title": f"Scene {index}",
        "status": "completed",
        "narrative_order": index,
        "summary": f"The party did thing number {index}.",
        "updated_at": f"1012-03-{index:02d}T11:00:00+00:00",
    }


def _scenes_result(n: int) -> dict:
    return {"scenes": [_scene(i) for i in range(1, n + 1)], "total": n, "limit": 1000, "offset": 0}


class _BeatsPrediction:
    def __init__(self, text: str) -> None:
        self.arc_beats = text


class _CampaignPrediction:
    def __init__(self, text: str) -> None:
        self.recap_markdown = text


def _install_reads(
    agent: RecapAgent,
    *,
    outline: dict | None = None,
    scenes: dict | None = None,
    facts: list | None = None,
    accepted: dict | None = None,
    threads: dict | None = None,
) -> dict:
    """Patch run_sync_read with a dispatcher keyed on the reader function name."""
    calls: dict[str, list] = {"save": [], "proposals_filter": []}
    saved_recaps: list[ArcRecap] = []

    async def _dispatch(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        name = getattr(func, "__name__", str(func))
        if name == "mongodb_get_story_outline":
            return outline
        if name == "mongodb_list_scenes":
            return scenes or {"scenes": [], "total": 0}
        if name == "neo4j_list_facts":
            return facts or []
        if name == "mongodb_list_proposed_changes":
            calls["proposals_filter"].append(args[0] if args else kwargs.get("filters"))
            return accepted or {"proposed_changes": [], "total": 0}
        if name == "neo4j_list_plot_threads":
            return threads or {"threads": [], "total": 0}
        if name == "mongodb_save_arc_recap":
            params: ArcRecapCreate = args[0]
            calls["save"].append(params)
            now = datetime.now(UTC)
            recap = ArcRecap(recap_id=uuid4(), generated_at=now, updated_at=now, **params.model_dump())
            saved_recaps.append(recap)
            return recap
        raise AssertionError(f"unexpected read: {name}")

    patcher = patch("monitor_agents.recap.agent.run_sync_read", new=AsyncMock(side_effect=_dispatch))
    patcher.start()
    return {"calls": calls, "saved": saved_recaps, "patcher": patcher}


def _stub_arc_module(agent: RecapAgent) -> dict:
    chunk_calls: list[dict] = []
    synth_calls: list[dict] = []

    def _summarize_chunk(**kwargs):  # type: ignore[no-untyped-def]
        chunk_calls.append(kwargs)
        return _BeatsPrediction(f"- beats for chunk {len(chunk_calls)}")

    def _synthesize(**kwargs):  # type: ignore[no-untyped-def]
        synth_calls.append(kwargs)
        return _CampaignPrediction("## Major Arcs\n- The campaign so far.\n")

    agent.arc_module.summarize_chunk = _summarize_chunk  # type: ignore[method-assign]
    agent.arc_module.synthesize_campaign = _synthesize  # type: ignore[method-assign]
    return {"chunks": chunk_calls, "synth": synth_calls}


@pytest.mark.asyncio
async def test_arc_recap_chunks_scene_recaps_then_synthesizes():
    agent = RecapAgent()
    n_scenes = 2 * ARC_RECAP_CHUNK_SIZE + 1  # 3 chunks
    scenes_result = _scenes_result(n_scenes)
    reads = _install_reads(agent, outline={"beats": ["beat one"]}, scenes=scenes_result)
    stub = _stub_arc_module(agent)
    try:
        recap = await agent.generate_arc_recap(uuid4(), uuid4())
    finally:
        reads["patcher"].stop()

    assert recap is not None
    assert len(stub["chunks"]) == 3
    assert len(stub["synth"]) == 1
    # each chunk carries at most ARC_RECAP_CHUNK_SIZE scene entries
    import json

    scene_ids = [s["scene_id"] for s in scenes_result["scenes"]]
    chunked_ids: list[str] = []
    for call in stub["chunks"]:
        chunk = json.loads(call["scene_recaps"])
        assert len(chunk) <= ARC_RECAP_CHUNK_SIZE
        chunked_ids.extend(entry["scene_id"] for entry in chunk)
    assert chunked_ids == scene_ids  # every scene covered, oldest first, exactly once
    # persistence happened exactly once, covering all scenes
    assert len(reads["calls"]["save"]) == 1
    saved = reads["calls"]["save"][0]
    assert saved.scene_count == n_scenes
    assert saved.last_scene_id == UUID(scene_ids[-1])
    assert saved.scenes_watermark == f"1012-03-{n_scenes:02d}T11:00:00+00:00"
    assert recap.recap_markdown.startswith("## Major Arcs")


@pytest.mark.asyncio
async def test_arc_recap_empty_story_returns_none_without_llm_or_persistence():
    agent = RecapAgent()
    reads = _install_reads(agent, outline={"beats": []}, scenes={"scenes": []}, facts=[], accepted={"proposed_changes": []})

    def _boom(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("LLM must not be called for an empty story")

    agent.arc_module.summarize_chunk = _boom  # type: ignore[method-assign]
    agent.arc_module.synthesize_campaign = _boom  # type: ignore[method-assign]
    try:
        result = await agent.generate_arc_recap(uuid4(), uuid4())
    finally:
        reads["patcher"].stop()

    assert result is None
    assert reads["calls"]["save"] == []


@pytest.mark.asyncio
async def test_arc_recap_only_counts_accepted_proposals():
    agent = RecapAgent()
    reads = _install_reads(
        agent,
        outline={"beats": ["b"]},
        scenes=_scenes_result(1),
        accepted={"proposed_changes": [{"change_type": "create_fact", "content": {"description": "The king died."}}]},
    )
    _stub_arc_module(agent)
    try:
        recap = await agent.generate_arc_recap(uuid4(), uuid4())
    finally:
        reads["patcher"].stop()

    assert recap is not None
    filters = reads["calls"]["proposals_filter"]
    assert len(filters) == 1
    assert filters[0].status == ProposalStatus.ACCEPTED
    assert filters[0].story_id is not None


@pytest.mark.asyncio
async def test_arc_recap_detail_levels_passed_to_llm_and_stored():
    agent = RecapAgent()
    reads = _install_reads(agent, outline={"beats": ["b"]}, scenes=_scenes_result(2))
    stub = _stub_arc_module(agent)
    try:
        recap = await agent.generate_arc_recap(uuid4(), uuid4(), detail="detailed")
    finally:
        reads["patcher"].stop()

    assert recap is not None
    assert all(call["detail"] == "detailed" for call in stub["chunks"])
    assert stub["synth"][0]["detail"] == "detailed"
    assert recap.detail == ArcRecapDetail.DETAILED


@pytest.mark.asyncio
async def test_arc_recap_rejects_unknown_detail():
    agent = RecapAgent()
    with pytest.raises(ValueError, match="detail must be one of"):
        await agent.generate_arc_recap(uuid4(), uuid4(), detail="huge")


@pytest.mark.asyncio
async def test_arc_recap_persist_false_skips_save_but_returns_recap():
    agent = RecapAgent()
    reads = _install_reads(agent, outline={"beats": ["b"]}, scenes=_scenes_result(3))
    _stub_arc_module(agent)
    try:
        recap = await agent.generate_arc_recap(uuid4(), uuid4(), persist=False)
    finally:
        reads["patcher"].stop()

    assert recap is not None
    assert reads["calls"]["save"] == []
    assert recap.scene_count == 3
    assert recap.scenes_watermark == "1012-03-03T11:00:00+00:00"


@pytest.mark.asyncio
async def test_arc_recap_persistence_is_idempotent_per_story():
    """Two generations for the same story issue one upsert each with the same
    story_id; the storage layer keeps a single doc (see test_arc_recap_tools)."""
    agent = RecapAgent()
    story_id = uuid4()
    reads = _install_reads(agent, outline={"beats": ["b"]}, scenes=_scenes_result(2))
    _stub_arc_module(agent)
    try:
        first = await agent.generate_arc_recap(story_id, uuid4())
        second = await agent.generate_arc_recap(story_id, uuid4())
    finally:
        reads["patcher"].stop()

    assert first is not None and second is not None
    saves = reads["calls"]["save"]
    assert len(saves) == 2
    assert all(s.story_id == story_id for s in saves)
    # each generation returns the recap the storage layer stored for it
    assert first.recap_id == reads["saved"][0].recap_id
    assert second.recap_id == reads["saved"][1].recap_id
