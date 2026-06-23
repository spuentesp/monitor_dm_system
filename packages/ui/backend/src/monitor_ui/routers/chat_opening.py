"""
Chat opening helpers — story/scene bootstrap and GM opening messages.

Extracted from chat.py to isolate session initialisation from the router.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import suppress
from typing import Any

from .chat_support import as_uuid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional layer imports (graceful degradation)
# ---------------------------------------------------------------------------

try:
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

    _BOOTSTRAP_AVAILABLE = True
except Exception:  # noqa: BLE001
    _BOOTSTRAP_AVAILABLE = False

try:
    from monitor_agents.loops.scene_loop import SceneLoop

    _AGENTS_AVAILABLE = True
except Exception:  # noqa: BLE001
    SceneLoop = None  # type: ignore[assignment,misc]
    _AGENTS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Story / scene bootstrap
# ---------------------------------------------------------------------------


def bootstrap_story_scene(
    session: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    """Best-effort bootstrap of a story + opening scene for a play session."""
    if not _BOOTSTRAP_AVAILABLE:
        return (
            session.get("story_id"),
            session.get("scene_id"),
            "bootstrap tools unavailable",
        )

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

            # Seed an opening "central conflict" plot thread so the co-pilot's
            # unresolved-threads panel (CF-3) is non-empty from turn 1 and the
            # GM has the main arc tracked (T-094).
            with suppress(Exception):
                thread_title = str(
                    session.get("title")
                    or session.get("universe_label")
                    or "The central mystery"
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
    except Exception as exc:  # noqa: BLE001
        return story_id, scene_id, str(exc)


# ---------------------------------------------------------------------------
# Opening hook — lore + entity-driven scene introduction
# ---------------------------------------------------------------------------


async def fetch_opening_hook(session: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch lore material for the opening scene: axioms, lore facts, location entities.

    Returns a dict with keys: axioms, facts, locations, system_name, tone.
    All values are lists of strings (or empty lists on failure).
    """
    universe_id = session.get("universe_id")
    result: dict[str, Any] = {
        "axioms": [],
        "facts": [],
        "locations": [],
        "system_name": session.get("system_label")
        or session.get("multiverse_label")
        or "",
        "tone": session.get("tone", "dramatic"),
    }
    if not universe_id:
        return result
    try:
        from monitor_data.db.neo4j import get_neo4j_client  # noqa: PLC0415

        neo = get_neo4j_client()

        # Axioms — world-level truths
        axiom_rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (a:Axiom) WHERE a.universe_id = $uid "
            "RETURN a.statement AS s ORDER BY a.confidence DESC LIMIT 5",
            {"uid": universe_id},
        )
        if not axiom_rows:
            axiom_rows = await asyncio.to_thread(
                neo.execute_read,
                "MATCH (a:Axiom) RETURN a.statement AS s "
                "ORDER BY a.confidence DESC LIMIT 5",
                {},
            )
        result["axioms"] = [r["s"] for r in axiom_rows if r.get("s")]

        # LoreFacts — grounded narrative facts for scene atmosphere
        fact_rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (f:Fact) WHERE f.universe_id = $uid "
            "RETURN f.statement AS s ORDER BY f.confidence DESC LIMIT 6",
            {"uid": universe_id},
        )
        if not fact_rows:
            fact_rows = await asyncio.to_thread(
                neo.execute_read,
                "MATCH (f:Fact) RETURN f.statement AS s "
                "ORDER BY f.confidence DESC LIMIT 6",
                {},
            )
        result["facts"] = [r["s"] for r in fact_rows if r.get("s")]

        # Location entities — for concrete scene anchoring
        loc_rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (e:Entity) WHERE e.entity_type = 'location' "
            "AND (e.universe_id = $uid OR e.is_archetype = true) "
            "RETURN e.name AS name, e.description AS desc LIMIT 4",
            {"uid": universe_id},
        )
        result["locations"] = [
            f"{r['name']}: {r.get('desc', '')}" for r in loc_rows if r.get("name")
        ]

    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_opening_hook failed: %s", exc)
    return result


# ---------------------------------------------------------------------------
# Opening message builder — evocative single GM message
# ---------------------------------------------------------------------------


async def build_gm_opening(
    session_id: str,
    session: dict[str, Any],
    *,
    session_game_system_doc: Any,
) -> tuple[str, dict[str, Any]]:
    """
    Build a single immersive GM opening message.

    Order:
    1. Fetch lore material (axioms, facts, locations)
    2. Use an LLM call to compose an in-fiction scene-setting paragraph
    3. End with one in-world question, never a form or list
    """
    lore = await fetch_opening_hook(session)
    tone = lore["tone"]
    system_name = lore["system_name"]
    axioms = lore["axioms"]
    facts = lore["facts"]
    locations = lore["locations"]

    # Try an LLM-generated atmospheric opening if agents are available.
    if _AGENTS_AVAILABLE and (axioms or facts or system_name):
        try:
            from monitor_agents.narrator import Narrator
            from monitor_data.tools.mongodb_tools import mongodb_get_gm_profile

            # Load GM profile if configured
            gm_profile: dict[str, Any] | None = None
            gm_profile_id = session.get("gm_profile_id")
            if gm_profile_id:
                try:
                    profile_res = mongodb_get_gm_profile(uuid.UUID(gm_profile_id))
                    if profile_res:
                        gm_profile = profile_res.model_dump()
                except Exception as e:
                    logger.debug("Failed to load GM profile for opening: %s", e)

            lore_context = []
            if locations:
                lore_context.append("Locations: " + "; ".join(locations[:2]))
            if facts:
                lore_context.append("World facts: " + " | ".join(facts[:3]))
            if axioms:
                lore_context.append("World truths: " + " | ".join(axioms[:2]))

            narrator = Narrator()
            narrative = (
                await narrator.generate_opening(
                    user_input="(session opening — set the scene and ask who the player is)",
                    context={
                        "entities": [{"context": "\n".join(lore_context)}]
                        if lore_context
                        else [],
                        "memories": [],
                        "turns": [],
                    },
                    game_context=session_game_system_doc(session),
                    session_tone=tone,
                    gm_profile=gm_profile,
                )
            ).strip()
            if narrative and len(narrative) > 40:
                return narrative, {
                    "type": "gm_opening",
                    "lore_used": bool(lore_context),
                }
        except Exception as exc:  # noqa: BLE001
            logger.debug("build_gm_opening LLM call failed: %s", exc)

    # Fallback: compose from lore strings without LLM
    parts: list[str] = []

    opener_candidates = facts[:2] + axioms[:2]
    if locations:
        parts.append(locations[0].split(":")[0].strip() + ".")
    if opener_candidates:
        for stmt in opener_candidates[:2]:
            s = stmt.rstrip(".")
            if s:
                parts.append(s + ".")

    _OPENING_QUESTIONS = {
        "grim": "Who are you, and what broke to bring you here?",
        "horror": "You are here. Who are you — and what did you bring with you?",
        "dramatic": "Who are you, and what do you want from this?",
        "heroic": "Who are you — and what quest drives you forward?",
        "mystery": "You are here for a reason. Who are you, really?",
        "adventure": "So — who are you, and what's the plan?",
    }
    parts.append(
        _OPENING_QUESTIONS.get(
            tone.lower(), "Who are you, and where does your story begin?"
        )
    )

    text = (
        "  ".join(parts) if parts else "Who are you, and where does your story begin?"
    )
    return text, {"type": "gm_opening"}
