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


DIRECTOR_NOTES_CAP = 20


async def seed_canon_from_session_zero(session: dict[str, Any]) -> None:
    """One-time: turn Session-Zero outcomes into retrievable canon.

    Writes a high-importance character memory (MongoDB + Qdrant via the
    create hook) so ContextAssembly retrieves who the PC is on every turn,
    and records premise/tone as director notes (ESTABLISHED FACTS). Runs at
    most once per session; failures degrade to a log line — the story still
    begins.
    """
    if session.get("canon_seeded"):
        return
    session["canon_seeded"] = True  # mark first: idempotent even on failure

    summary = session.get("character_summary")
    parts: list[str] = []
    if isinstance(summary, dict):
        name = str(summary.get("character_name") or session.get("speaker_label") or "").strip()
        concept = str(summary.get("concept") or "").strip()
        appearance = str(summary.get("appearance") or "").strip()
        backstory = str(summary.get("backstory") or "").strip()
        if name:
            parts.append(f"Name: {name}")
        if concept:
            parts.append(f"Origin & concept: {concept}")
        if appearance:
            parts.append(f"Appearance: {appearance}")
        if backstory:
            parts.append(f"Backstory: {backstory}")

    universe_id = session.get("universe_id") or session.get("world_id")
    entity_id = session.get("character_id")
    story_id = session.get("story_id")
    scene_id = session.get("scene_id")
    if parts and universe_id and entity_id and story_id:
        try:
            import anyio

            from monitor_data.schemas.memories import MemoryCreate
            from monitor_data.tools.mongodb_tools import mongodb_create_memory

            text = "PLAYER CHARACTER (established in Session Zero):\n" + "\n".join(parts)
            params = MemoryCreate(
                universe_id=UUID(str(universe_id)),
                entity_id=UUID(str(entity_id)),
                scene_id=UUID(str(scene_id)) if scene_id else None,
                text=text[:5000],
                importance=0.9,
                emotional_valence=0.0,
                metadata={"story_id": str(story_id), "source": "session_zero_canon_seed"},
            )
            await anyio.to_thread.run_sync(mongodb_create_memory, params)
        except Exception as exc:
            log.warning("preplay.canon_seed_memory_failed", error=str(exc))

    notes = session.setdefault("director_notes", [])
    if isinstance(notes, list):
        premise = str(session.get("story_premise") or "").strip()
        tone = str(session.get("tone") or "").strip()
        candidates = ([f"Story premise: {premise}"] if premise else []) + ([f"Tone: {tone}"] if tone else [])
        for note in candidates:
            if note not in notes:
                notes.append(note)
        del notes[:-DIRECTOR_NOTES_CAP]


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
    agreements = agreements.model_copy(update={"confirmed": True, "confirmed_at": confirmed_at})
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

    await seed_canon_from_session_zero(session)

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
