"""Session bootstrap — story + scene creation as a Layer-2 helper.

Extracted from ``packages/ui/backend/src/monitor_ui/routers/chat_opening.py``
so both the FastAPI router and the e2e harness script can depend on it
without one Layer-3 caller reaching into another.

Public surface:

    bootstrap_story_scene(session: dict) -> (story_id, scene_id, error_or_None)
    bootstrap_story_scene_with_start(session: dict) -> (story_id, scene_id, error_or_None)

``bootstrap_story_scene`` is the pure synchronous helper: it writes the
Story to Neo4j and the Scene to MongoDB; returns the generated IDs and
writes them back into the ``session`` dict. Best-effort during the
secondary canonization steps (story outline, opening plot thread) —
failures there bubble up to the caller via the returned error string.

``bootstrap_story_scene_with_start`` (Phase 2 guided start) additionally
materializes the chosen start option — location and NPC instances, NPC
profiles and agendas, 2-3 plot threads, the PC placed at the location —
through CanonKeeper as proposals accepted for the opening. It is async
because the CanonKeeper commit path is; the sync helper keeps its contract
for the existing callers.
"""

from __future__ import annotations

import asyncio
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


def _chosen_start_option(session: dict[str, Any]) -> dict[str, Any]:
    """The chosen start option as a plain dict, or ``{}``.

    Reads only the session dict (sync-safe): the option chosen in pre-play
    (or the first option under the skip-to-play contract).
    """
    raw_options = [option for option in (session.get("start_options") or []) if isinstance(option, dict)]
    if not raw_options:
        return {}
    chosen_id = session.get("chosen_start_option_id")
    for option in raw_options:
        if option.get("option_id") == chosen_id:
            return option
    return raw_options[0]


def bootstrap_story_scene(
    session: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    """Create a story + opening scene for a play session.

    Returns ``(story_id, scene_id, error_or_None)``. IDs are also written
    back to ``session['story_id']`` / ``session['scene_id']``.

    Start-aware (Phase 2): when pre-play chose a start option, its hook and
    threads ground the story premise and the opening plot thread instead of
    generic placeholders.
    """
    universe_id = as_uuid(session.get("universe_id") or session.get("world_id"))
    if universe_id is None:
        return session.get("story_id"), session.get("scene_id"), "no universe selected"

    story_id = session.get("story_id")
    scene_id = session.get("scene_id")
    character_ids = [
        session.get("character_id"),
        *(session.get("controlled_character_ids") or []),
    ]
    pc_ids = list(
        dict.fromkeys(character_id for value in character_ids if (character_id := as_uuid(value)) is not None)
    )
    start_option = _chosen_start_option(session)

    try:
        if not story_id:
            agreements = session.get("story_agreements") or {}
            agreed_themes = agreements.get("themes") if isinstance(agreements, dict) else []
            theme_parts = [session.get("tone", "dramatic"), *(agreed_themes or [])]
            theme = " ".join(str(part).strip() for part in theme_parts if str(part).strip())[:500]
            start_hook = str(start_option.get("hook") or start_option.get("summary") or "").strip()
            premise = str(
                (agreements.get("story_premise") if isinstance(agreements, dict) else None)
                or session.get("story_premise")
                or start_hook
                or session.get("session_intro", {}).get("intro_text")
                or "A new story begins with the selected player character."
            ).strip()
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
            # and the GM has the main arc tracked. When the player chose a
            # start option, the option's main thread names the conflict.
            with suppress(Exception):
                option_threads = [t for t in (start_option.get("threads") or []) if isinstance(t, dict)]
                if option_threads and str(option_threads[0].get("title") or "").strip():
                    thread_title = str(option_threads[0]["title"]).strip()[:200]
                else:
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
    except Exception as exc:  # noqa: BLE001  # reason: falls back to `story_id, scene_id, str(exc)` on failure (in bootstrap_story_scene)
        return story_id, scene_id, str(exc)


async def bootstrap_story_scene_with_start(
    session: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    """Bootstrap the story/scene and materialize the chosen start option.

    The materialization (Phase 2 guided start) turns the chosen option into
    state: the location and NPCs as entity instances (not archetypes) with
    NPC profiles and agendas, 2-3 plot threads, and the PC placed at the
    location — all through CanonKeeper as proposals accepted for the
    opening. Also commits pack agendas and plot threads left pending (or
    unresolved) by pack apply, now that a story exists.
    """
    story_id, scene_id, error = await asyncio.to_thread(bootstrap_story_scene, session)
    if story_id and not error:
        try:
            from monitor_agents.world_seed import materialize_chosen_start

            await materialize_chosen_start(
                session,
                story_id=story_id,
                universe_id=str(session.get("universe_id") or session.get("world_id") or "") or None,
            )
        except Exception as exc:  # noqa: BLE001  # reason: a failed materialization must not lose the bootstrapped story (in bootstrap_story_scene_with_start)
            error = f"start materialization failed: {exc}"
    return story_id, scene_id, error
