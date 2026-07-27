"""
Stories router — story arc evaluation and narrative state overrides.

Exposes the StoryLoop state (Gap 4) to the UI for tracking plot threads,
narrative tension, and arc progression, plus browse endpoints (T-072) so
universes can show the stories, scenes, and turns that happened inside them.
"""

from __future__ import annotations

import logging
from datetime import UTC
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from langgraph.checkpoint.mongodb import MongoDBSaver
from monitor_agents.loops.story_loop import StoryState, build_story_graph
from monitor_data.config import settings
from pydantic import BaseModel

from .chat_schemas import StoryPatch, StoryResponse
from .ingest_shared import db_op

logger = logging.getLogger(__name__)

router = APIRouter()

# Mounted at /api (not /api/stories) for scene-scoped routes.
scenes_router = APIRouter()


# ─── Browse schemas (T-072) ───────────────────────────────────


class StorySummary(BaseModel):
    """A story as recorded in the graph, for universe drill-down lists."""

    id: UUID
    universe_id: UUID
    title: str
    story_type: str
    theme: str | None = None
    premise: str | None = None
    status: str
    scene_count: int = 0
    created_at: str
    completed_at: str | None = None


class StoryListOut(BaseModel):
    stories: list[StorySummary]
    total: int


class SceneSummaryOut(BaseModel):
    """Scene metadata without turn bodies (kept light for timelines)."""

    id: UUID
    story_id: UUID
    title: str
    purpose: str = ""
    status: str
    narrative_order: int | None = None
    summary: str = ""
    turn_count: int = 0
    created_at: str
    updated_at: str
    completed_at: str | None = None


class TurnOut(BaseModel):
    turn_id: str | None = None
    speaker: str | None = None
    entity_id: str | None = None
    text: str = ""
    timestamp: str | None = None


class ThreadOut(BaseModel):
    """A plot thread (graph-tracked when available, checkpoint label otherwise)."""

    id: str | None = None
    title: str
    thread_type: str | None = None
    status: str
    urgency: str | None = None
    priority: str | None = None
    source: str = "graph"  # "graph" | "checkpoint"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


# ─── Browse endpoints (T-072) ─────────────────────────────────


@router.get("", response_model=StoryListOut)
async def list_stories(
    universe_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> StoryListOut:
    """List stories, optionally filtered to one universe."""
    from monitor_data.schemas.stories import StoryFilter, StoryStatus
    from monitor_data.tools.neo4j_tools import neo4j_list_stories

    with db_op("Story database unavailable"):
        params = StoryFilter(
            universe_id=UUID(universe_id) if universe_id else None,
            status=StoryStatus(status) if status else None,
            limit=max(1, min(limit, 500)),
            offset=max(0, offset),
        )
        result = neo4j_list_stories(params)

    stories = [
        StorySummary(
            id=s.id,
            universe_id=s.universe_id,
            title=s.title,
            story_type=getattr(s.story_type, "value", str(s.story_type)),
            theme=s.theme,
            premise=s.premise,
            status=getattr(s.status, "value", str(s.status)),
            scene_count=s.scene_count,
            created_at=_iso(s.created_at) or "",
            completed_at=_iso(s.completed_at),
        )
        for s in result.stories
    ]
    return StoryListOut(stories=stories, total=result.total)


@router.get("/{story_id}/scenes", response_model=list[SceneSummaryOut])
async def list_story_scenes(story_id: UUID, limit: int = 200) -> list[SceneSummaryOut]:
    """Scene timeline for a story (oldest first), without turn bodies."""
    from monitor_data.schemas.scenes import SceneFilter
    from monitor_data.tools.mongodb_tools import mongodb_list_scenes

    with db_op("Scene database unavailable"):
        result = mongodb_list_scenes(
            SceneFilter(
                story_id=story_id,
                limit=max(1, min(limit, 500)),
                sort_by="created_at",
                sort_order="asc",
            )
        )

    return [
        SceneSummaryOut(
            id=sc.scene_id,
            story_id=sc.story_id,
            title=sc.title,
            purpose=sc.purpose or "",
            status=getattr(sc.status, "value", str(sc.status)),
            narrative_order=sc.narrative_order,
            summary=sc.summary or "",
            turn_count=len(sc.turns or []),
            created_at=_iso(sc.created_at) or "",
            updated_at=_iso(sc.updated_at) or "",
            completed_at=_iso(sc.completed_at),
        )
        for sc in result.scenes
    ]


@router.get("/{story_id}/threads", response_model=list[ThreadOut])
async def list_story_threads(story_id: UUID, only_open: bool = True) -> list[ThreadOut]:
    """Plot threads for a story: graph-tracked threads, falling back to the
    StoryLoop checkpoint's active/completed thread labels."""
    threads: list[ThreadOut] = []
    try:
        from monitor_data.schemas.story_outlines import PlotThreadFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_plot_threads

        result = neo4j_list_plot_threads(PlotThreadFilter(story_id=story_id, limit=200))
        for t in result.threads:
            status = getattr(t.status, "value", str(t.status))
            if only_open and status in ("resolved", "abandoned"):
                continue
            threads.append(
                ThreadOut(
                    id=str(t.id),
                    title=t.title,
                    thread_type=getattr(t.thread_type, "value", str(t.thread_type)),
                    status=status,
                    urgency=getattr(t.urgency, "value", str(t.urgency)),
                    priority=getattr(t.priority, "value", str(t.priority)),
                    source="graph",
                )
            )
    except Exception as exc:
        logger.warning("plot-thread lookup failed for %s: %s", story_id, exc)

    if not threads:
        state = await get_story_state(story_id)
        if state:
            threads = [ThreadOut(title=label, status="open", source="checkpoint") for label in state.active_threads]
            if not only_open:
                threads += [
                    ThreadOut(title=label, status="resolved", source="checkpoint") for label in state.completed_threads
                ]
    return threads


@scenes_router.get("/scenes/{scene_id}/turns", response_model=list[TurnOut])
async def get_scene_turns(scene_id: UUID, limit: int = 30) -> list[TurnOut]:
    """Most recent turns of a scene, oldest first (transcript order)."""
    from monitor_data.tools.mongodb_tools import mongodb_get_recent_turns

    with db_op("Scene database unavailable"):
        turns = mongodb_get_recent_turns(scene_id, limit=max(1, min(limit, 50)))

    return [
        TurnOut(
            turn_id=str(t.get("turn_id")) if t.get("turn_id") else None,
            speaker=t.get("speaker"),
            entity_id=str(t.get("entity_id")) if t.get("entity_id") else None,
            text=t.get("text", ""),
            timestamp=_iso(t.get("timestamp")),
        )
        for t in turns
    ]


async def get_story_state(story_id: UUID) -> StoryState | None:
    """Load the current story state from MongoDB checkpoints."""
    try:
        graph = build_story_graph()
        with MongoDBSaver.from_conn_string(settings.mongodb_uri) as checkpointer:
            compiled = graph.compile(checkpointer=checkpointer)
            thread_id = f"story-{story_id}"
            config = {"configurable": {"thread_id": thread_id}}

            current = await compiled.aget_state(config)  # type: ignore
            if current and current.values:
                # Handle cases where in_game_time might be stored as string in some checkpointers
                vals = dict(current.values)
                return StoryState(**vals)
    except Exception as exc:
        logger.warning("Failed to load story state for %s: %s", story_id, exc)
    return None


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(story_id: UUID) -> StoryResponse:
    """Get the current narrative state of a story arc.

    Stories that exist in Neo4j but have not run a StoryLoop turn yet have no
    checkpoint state — return a sane default view instead of 404ing (T-050);
    404 is reserved for stories that genuinely do not exist.
    """
    state = await get_story_state(story_id)
    if not state:
        from datetime import datetime

        from monitor_data.tools.neo4j_tools import neo4j_get_story

        try:
            record = neo4j_get_story(story_id)
        except Exception:
            record = None
        if record is None:
            raise HTTPException(status_code=404, detail="Story not found")
        return StoryResponse(
            story_id=story_id,
            universe_id=record.universe_id,
            arc_label="Opening",
            tension_score=0.5,
            active_threads=[],
            completed_threads=[],
            current_scene_id=None,
            story_complete=False,
            in_game_time=datetime.now(UTC).isoformat(),
            world_ticks=0,
            scenes_completed=0,
        )

    return StoryResponse(
        story_id=state.story_id,
        universe_id=state.universe_id,
        arc_label=state.arc_label,
        tension_score=state.tension_score,
        active_threads=state.active_threads,
        completed_threads=state.completed_threads,
        current_scene_id=state.current_scene_id,
        story_complete=state.story_complete,
        in_game_time=state.in_game_time.isoformat(),
        world_ticks=state.world_ticks,
        scenes_completed=state.scenes_completed,
    )


@router.patch("/{story_id}", response_model=StoryResponse)
async def patch_story(story_id: UUID, body: StoryPatch) -> StoryResponse:
    """
    Override story state fields (DM override).

    Allows the GM to manually shift narrative tension, rename plot threads,
    or force an arc phase transition.
    """
    state = await get_story_state(story_id)
    if not state:
        raise HTTPException(status_code=404, detail="Story not found")

    graph = build_story_graph()
    with MongoDBSaver.from_conn_string(settings.mongodb_uri) as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
        thread_id = f"story-{story_id}"
        config = {"configurable": {"thread_id": thread_id}}

        update: dict[str, Any] = {}
        if body.arc_label is not None:
            update["arc_label"] = body.arc_label
        if body.tension_score is not None:
            update["tension_score"] = body.tension_score
        if body.active_threads is not None:
            update["active_threads"] = body.active_threads

        if update:
            await compiled.aupdate_state(config, update)  # type: ignore

        # Reload for response
        current = await compiled.aget_state(config)  # type: ignore
        if not current or not current.values:
            raise HTTPException(status_code=500, detail="Failed to reload story state after update")

        final_state = StoryState(**current.values)

    return StoryResponse(
        story_id=final_state.story_id,
        universe_id=final_state.universe_id,
        arc_label=final_state.arc_label,
        tension_score=final_state.tension_score,
        active_threads=final_state.active_threads,
        completed_threads=final_state.completed_threads,
        current_scene_id=final_state.current_scene_id,
        story_complete=final_state.story_complete,
        in_game_time=final_state.in_game_time.isoformat(),
        world_ticks=final_state.world_ticks,
        scenes_completed=final_state.scenes_completed,
    )
