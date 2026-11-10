"""Finalize pre-play exactly once and generate the first in-fiction opening."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from monitor_agents.loops.session_bootstrap import bootstrap_story_scene_with_start
from monitor_agents.loops.preplay_support import ensure_start_options
from monitor_agents.narrator.agent import Narrator
from monitor_agents.story_agreements import StoryAgreements
from monitor_agents.world_seed import resolve_chosen_start, situation_brief

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
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in seed_canon_from_session_zero)
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
    """Confirm agreements, bootstrap Story/Scene, and narrate the opening.

    Phase 2 guided start: a chosen start option (or, on the skip path, the
    seed's first option) is materialized into state as part of the
    bootstrap, and the opening narrates that situation — where the PC is,
    who is there, what is happening — ending on a prompt to act. The
    existing precedence holds: authored module intro first, resume recap
    second (see ``chat_opening.build_gm_opening``), generated opening third.
    """

    if not session.get("character_id"):
        raise ValueError("A player character must be selected or created before play begins.")

    raw_agreements = session.get("story_agreements")
    if not isinstance(raw_agreements, dict):
        raise ValueError("Session Zero agreements must be completed before play begins.")

    # The skip path never chose a start explicitly — the first option is its
    # documented contract, so the opening is still seeded.
    await ensure_start_options(session)
    resolve_chosen_start(session)

    agreements = StoryAgreements.model_validate(raw_agreements)
    confirmed_at = datetime.now(UTC)
    agreements = agreements.model_copy(update={"confirmed": True, "confirmed_at": confirmed_at})
    session["story_agreements"] = agreements.model_dump(mode="json")
    if agreements.story_premise:
        session["story_premise"] = agreements.story_premise
    if agreements.tone:
        session["tone"] = agreements.tone

    story_id, scene_id, bootstrap_error = await bootstrap_story_scene_with_start(session)
    session["story_id"] = story_id
    session["scene_id"] = scene_id
    if not story_id or not scene_id:
        raise RuntimeError(bootstrap_error or "Story/scene bootstrap did not return IDs.")

    await seed_canon_from_session_zero(session)

    gm_profile = await _load_gm_profile(session.get("gm_profile_id"))
    intro = session.get("session_intro") or {}
    character = session.get("character_summary") or {}
    context_text = _opening_context(intro, character, agreements)
    brief = situation_brief(session)
    if brief:
        context_text += (
            "\n\nSTARTING SITUATION (established state — narrate this, invent nothing that contradicts it):\n" + brief
        )

    narrative = ""
    module_intro = await _module_intro_text(session)
    generated = ""
    if not module_intro or brief:
        # Generate when there is no authored intro, or when a materialized
        # situation must be narrated after it (task 5). The authored module
        # intro keeps first position either way.
        try:
            generated = (
                await Narrator().generate_opening(
                    user_input=(
                        "(Begin the first in-fiction scene now. The character and table "
                        "agreements are final. Narrate the starting situation — where the "
                        "player character is, who is present, what is happening — and end "
                        "with a clear prompt to act.)"
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
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades to the situation template (in finalize_preplay)
            log.warning("preplay.opening_failed", error=str(exc))
            generated = ""

    if module_intro and generated:
        narrative = f"{module_intro}\n\n{generated}"
    elif module_intro:
        narrative = module_intro
    elif generated:
        narrative = generated

    if not narrative:
        # Deterministic opening: names the place, the people, and the hook.
        narrative = _template_opening(session, brief, agreements)
    else:
        narrative = _enforce_situation_names(narrative, session)

    session["phase"] = "active_play"
    session["preplay_finalized_at"] = confirmed_at.isoformat()
    # The checkpoint is no longer needed once we have begun play; the
    # persisted session now carries confirmed agreements, the bound PC,
    # and the bootstrapped Story/Scene IDs.
    session.pop("preplay_checkpoint", None)
    metadata: dict[str, Any] = {
        "type": "gm_opening",
        "phase": "active_play",
        "preplay_finalized": True,
        "story_id": story_id,
        "scene_id": scene_id,
        "bootstrap_error": bootstrap_error,
        "session_intro": intro,
        "story_agreements": session["story_agreements"],
    }
    materialized = session.get("materialized_start")
    if isinstance(materialized, dict):
        metadata["materialized_start"] = materialized
    return narrative, metadata


async def _module_intro_text(session: dict[str, Any]) -> str:
    """The session pack's authored verbatim opening, or ``""``.

    Same contract as ``chat_opening._fetch_module_intro`` (G-2): only a
    substantive read-aloud intro (>40 chars) counts.
    """
    pack_id_raw = session.get("pack_id")
    if not pack_id_raw:
        return ""
    try:
        from monitor_data.tools.mongodb_tools import mongodb_get_knowledge_pack

        pack = await asyncio.to_thread(mongodb_get_knowledge_pack, UUID(str(pack_id_raw)))
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _module_intro_text)
        log.debug("preplay.module_intro_fetch_failed", error=str(exc))
        return ""
    intro = (getattr(pack, "intro_text", None) or "").strip()
    return intro if len(intro) > 40 else ""


def _enforce_situation_names(narrative: str, session: dict[str, Any]) -> str:
    """Guarantee the opening names the place and at least two NPCs.

    The done-when pins this: the opening names a location and at least two
    NPCs that exist as instances. When the narration glosses over them,
    one compact closing sentence names who is here and where — and ends on
    the prompt to act.
    """
    materialized = session.get("materialized_start") if isinstance(session.get("materialized_start"), dict) else {}
    if not materialized:
        return narrative
    location = str(materialized.get("location") or "").strip()
    names = [str(npc.get("name") or "").strip() for npc in (materialized.get("npcs") or []) if isinstance(npc, dict)]
    names = [name for name in names if name]
    lowered = (narrative or "").lower()
    missing_location = bool(location) and location.lower() not in lowered
    missing_names = [name for name in names if name.lower() not in lowered]
    named_count = len(names) - len(missing_names)
    if not missing_location and named_count >= 2:
        return narrative

    pieces: list[str] = []
    if missing_names:
        if len(missing_names) == 1:
            pieces.append(f"{missing_names[0]} is here")
        else:
            pieces.append(f"{', '.join(missing_names[:-1])} and {missing_names[-1]} are here")
    if missing_location and location:
        pieces.append(f"at {location}" if pieces else f"The scene is set at {location}")
    coda = " ".join(pieces).strip()
    if not coda:
        return narrative
    coda = coda[0].upper() + coda[1:]
    suffix = f"{coda}. What do you do?"
    return f"{narrative.rstrip()}\n\n{suffix}" if narrative.strip() else suffix


def _template_opening(session: dict[str, Any], brief: str, agreements: StoryAgreements) -> str:
    """Deterministic opening naming the place, the people, and the hook.

    Reached when the LLM opening fails — the opening still names a location
    and the NPCs that exist as instances, and ends on a prompt to act.
    """
    materialized = session.get("materialized_start") if isinstance(session.get("materialized_start"), dict) else {}
    start_option = session.get("start_option") if isinstance(session.get("start_option"), dict) else {}
    name = session.get("speaker_label") or "Your character"
    location = str(materialized.get("location") or start_option.get("location") or "").strip()
    npcs = materialized.get("npcs") or start_option.get("npcs") or []
    npc_names = [str(npc.get("name") or "").strip() for npc in npcs if isinstance(npc, dict)]
    npc_names = [npc for npc in npc_names if npc]
    hook = str(materialized.get("hook") or start_option.get("hook") or "").strip()

    parts: list[str] = []
    if location:
        present = ""
        if npc_names:
            if len(npc_names) == 1:
                present = f" with {npc_names[0]}"
            else:
                present = f" with {', '.join(npc_names[:-1])} and {npc_names[-1]}"
        parts.append(f"{name} stands in {location}{present}.")
    else:
        parts.append(f"{name} stands at the threshold of {agreements.story_premise or 'the situation before you'}.")
    for npc in npcs[:4]:
        if not isinstance(npc, dict):
            continue
        npc_name = str(npc.get("name") or "").strip()
        want = str(npc.get("want") or "").strip()
        if npc_name and want:
            parts.append(f"{npc_name} wants {want}.")
    if hook:
        parts.append(hook if hook.endswith((".", "!", "?")) else hook + ".")
    parts.append("What do you do?")
    return " ".join(parts)


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
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _load_gm_profile)
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
