"""Finalize pre-play exactly once and generate the first in-fiction opening."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from monitor_agents.loops.session_bootstrap import bootstrap_story_scene
from monitor_agents.narrator.agent import Narrator
from monitor_agents.story_agreements import StoryAgreements

log = structlog.get_logger()


async def finalize_preplay(
    session: dict[str, Any],
    *,
    system_doc: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Confirm agreements, bootstrap Story/Scene, and narrate the opening."""

    if not session.get("character_id"):
        raise ValueError("A player character must be selected or created before play begins.")

    raw_agreements = session.get("story_agreements")
    if not isinstance(raw_agreements, dict):
        raise ValueError("Session Zero agreements must be completed before play begins.")

    agreements = StoryAgreements.model_validate(raw_agreements)
    confirmed_at = datetime.now(UTC)
    agreements = agreements.model_copy(
        update={"confirmed": True, "confirmed_at": confirmed_at}
    )
    session["story_agreements"] = agreements.model_dump(mode="json")
    if agreements.story_premise:
        session["story_premise"] = agreements.story_premise
    if agreements.tone:
        session["tone"] = agreements.tone

    story_id, scene_id, bootstrap_error = await asyncio.to_thread(
        bootstrap_story_scene,
        session,
    )
    session["story_id"] = story_id
    session["scene_id"] = scene_id
    if not story_id or not scene_id:
        raise RuntimeError(bootstrap_error or "Story/scene bootstrap did not return IDs.")

    gm_profile = await _load_gm_profile(session.get("gm_profile_id"))
    intro = session.get("session_intro") or {}
    character = session.get("character_summary") or {}
    context_text = _opening_context(intro, character, agreements)

    try:
        narrative = (
            await Narrator().generate_opening(
                user_input=(
                    "(Begin the first in-fiction scene now. The character and table "
                    "agreements are final. Establish an immediate situation and end "
                    "with room for the player to act.)"
                ),
                context={
                    "entities": [{"context": context_text}],
                    "memories": [],
                    "turns": [],
                },
                game_context=system_doc,
                session_tone=session.get("tone", "dramatic"),
                gm_profile=gm_profile,
                story_premise=session.get("story_premise"),
            )
        ).strip()
    except Exception as exc:
        log.warning("preplay.opening_failed", error=str(exc))
        narrative = ""

    if not narrative:
        name = session.get("speaker_label") or "Your character"
        premise = agreements.story_premise or "the situation before you"
        narrative = f"{name} stands at the threshold of {premise}. What do you do?"

    session["phase"] = "active_play"
    session["preplay_finalized_at"] = confirmed_at.isoformat()
    # The checkpoint is no longer needed once we have begun play; the
    # persisted session now carries confirmed agreements, the bound PC,
    # and the bootstrapped Story/Scene IDs.
    session.pop("preplay_checkpoint", None)
    return narrative, {
        "type": "gm_opening",
        "phase": "active_play",
        "preplay_finalized": True,
        "story_id": story_id,
        "scene_id": scene_id,
        "bootstrap_error": bootstrap_error,
        "session_intro": intro,
        "story_agreements": session["story_agreements"],
    }


async def _load_gm_profile(profile_id: Any) -> dict[str, Any] | None:
    if not profile_id:
        return None
    try:
        from monitor_data.tools.mongodb_tools import mongodb_get_gm_profile

        profile = await asyncio.to_thread(
            mongodb_get_gm_profile,
            UUID(str(profile_id)),
        )
        return profile.model_dump() if profile else None
    except Exception as exc:
        log.warning("preplay.gm_profile_load_failed", error=str(exc))
        return None


def _opening_context(
    intro: dict[str, Any],
    character: dict[str, Any],
    agreements: StoryAgreements,
) -> str:
    lines = "\n".join(f"- {item}" for item in agreements.lines) or "- none stated"
    veils = "\n".join(f"- {item}" for item in agreements.veils) or "- none stated"
    themes = ", ".join(agreements.themes) or "(none stated)"
    return "\n\n".join(
        [
            "SETTING FRAME (facts only):\n" + str(intro.get("intro_text") or ""),
            (
                "PLAYER CHARACTER:\n"
                f"Name: {character.get('character_name') or '(see actor profile)'}\n"
                f"Concept: {character.get('concept') or '(see actor profile)'}\n"
                f"Backstory: {character.get('backstory') or '(see actor profile)'}"
            ),
            (
                "STORY AGREEMENTS:\n"
                f"Premise: {agreements.story_premise}\n"
                f"Themes wanted: {themes}\n"
                f"Character role: {agreements.pc_role}\n"
                f"Pacing: {agreements.pacing}"
            ),
            (
                "HARD CONTENT CONSTRAINTS:\n"
                "LINES — never depict, introduce, imply, or make central:\n"
                f"{lines}\n"
                "VEILS — may exist, but fade to black before descriptive detail:\n"
                f"{veils}"
            ),
        ]
    )
