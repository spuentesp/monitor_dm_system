"""Session bootstrap — story + scene creation as a Layer-2 helper.

Extracted from ``packages/ui/backend/src/monitor_ui/routers/chat_opening.py``
so both the FastAPI router and the e2e harness script can depend on it
without one Layer-3 caller reaching into another.

Public surface:

    bootstrap_story_scene(session: dict) -> (story_id, scene_id, error_or_None)

Pure synchronous helper. Writes the Story to Neo4j and the Scene to
MongoDB; returns the generated IDs and writes them back into the
``session`` dict. Best-effort during the secondary canonization steps
(story outline, opening plot thread) — failures there bubble up to the
caller via the returned error string.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from typing import Any

from monitor_data.schemas.base import (
    PlotThreadType,
    SceneStatus,
    StoryStatus,
    StoryType,
    ThreadPriority,
    ThreadUrgency,
)
from monitor_data.schemas.scenes import SceneCreate
from monitor_data.schemas.stories import StoryCreate
from monitor_data.schemas.story_outlines import PlotThreadCreate, StoryOutlineCreate
from monitor_data.tools.mongodb_tools import (
    mongodb_create_scene,
    mongodb_create_story_outline,
)
from monitor_data.tools.neo4j_tools.stories import (
    neo4j_create_plot_thread,
    neo4j_create_story,
)


def as_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def bootstrap_story_scene(
    session: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    """Create a story + opening scene for a play session.

    Returns ``(story_id, scene_id, error_or_None)``. IDs are also written
    back to ``session['story_id']`` / ``session['scene_id']``.
    """
    universe_id = as_uuid(session.get("universe_id") or session.get("world_id"))
    if universe_id is None:
        return session.get("story_id"), session.get("scene_id"), "no universe selected"

    story_id = session.get("story_id")
    scene_id = session.get("scene_id")
    pc_uuid = as_uuid(session.get("character_id"))
    pc_ids = [pc_uuid] if pc_uuid else []

    try:
        if not story_id:
            theme = f"{session.get('tone', 'dramatic')} {str(session.get('mode', 'autonomous_gm')).replace('_', ' ')}".strip()
            premise = (
                "Session started from the Play Console. "
                "The story should continue from player chat input and persist accepted changes in this universe."
            )
            created_story = neo4j_create_story(
                StoryCreate(
                    universe_id=universe_id,
                    title=str(session.get("title") or "New Story"),
                    story_type=StoryType.CAMPAIGN,
                    theme=theme,
                    premise=premise,
                    status=StoryStatus.ACTIVE,
                    pc_ids=pc_ids,
                    game_system_id=as_uuid(session.get("system_id")),
                )
            )
            story_id = str(created_story.id)
            session["story_id"] = story_id

            with suppress(Exception):
                mongodb_create_story_outline(
                    StoryOutlineCreate(
                        story_id=created_story.id,
                        theme=theme,
                        premise=premise,
                    )
                )

            # Seed an opening "central conflict" plot thread so the
            # co-pilot's unresolved-threads panel is non-empty from turn 1
            # and the GM has the main arc tracked.
            with suppress(Exception):
                thread_title = str(
                    session.get("title") or session.get("universe_label") or "The central mystery"
                ).strip()[:200]
                neo4j_create_plot_thread(
                    PlotThreadCreate(
                        story_id=created_story.id,
                        title=thread_title,
                        thread_type=PlotThreadType.MAIN,
                        priority=ThreadPriority.MAIN,
                        urgency=ThreadUrgency.MEDIUM,
                    )
                )

        if not scene_id and story_id:
            scene_title = f"{session.get('title') or 'Story'} — Opening Scene"
            purpose = (
                "Human-led session capture and review"
                if session.get("mode") == "gm_assistant"
                else "Opening scene for interactive play"
            )
            created_scene = mongodb_create_scene(
                SceneCreate(
                    story_id=uuid.UUID(str(story_id)),
                    universe_id=universe_id,
                    title=scene_title[:200],
                    purpose=purpose,
                    status=SceneStatus.ACTIVE,
                    participating_entities=pc_ids,
                )
            )
            scene_id = str(created_scene.scene_id)
            session["scene_id"] = scene_id

        return story_id, scene_id, None
    except Exception as exc:
        return story_id, scene_id, str(exc)
