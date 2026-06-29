"""
Chat turn runners — scene loop lifecycle, pre-play, world architect, and scene turns.

Extracted from chat.py to isolate turn execution from the HTTP/WebSocket router.
"""

from __future__ import annotations

import asyncio
import logging
import re as _re
import uuid
from collections import OrderedDict
from typing import Any, Optional

from .chat_support import (
    as_uuid,
    is_end_conversation_command,
    is_end_scene_command,
    is_ooc_question,
    is_recap_command,
    is_start_conversation_command,
    normalize_ooc_text,
    now_iso,
    resolve_pending_consequence_choice,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional layer imports (graceful degradation)
# ---------------------------------------------------------------------------

try:
    from monitor_agents.loops.scene_loop import SceneLoop
    from monitor_agents.loops.story_loop import StoryLoop

    _AGENTS_AVAILABLE = True
except Exception:  # noqa: BLE001
    SceneLoop = None  # type: ignore[assignment,misc]
    StoryLoop = None  # type: ignore[assignment,misc]
    _AGENTS_AVAILABLE = False

try:
    from monitor_agents.loops.world_building_loop import WorldBuildingLoop

    _WORLD_ARCHITECT_AVAILABLE = True
except Exception:  # noqa: BLE001
    _WORLD_ARCHITECT_AVAILABLE = False

try:
    from monitor_agents.loops.character_creation_loop import CharacterCreationLoop

    _CHAR_CREATION_AVAILABLE = True
except Exception:  # noqa: BLE001
    _CHAR_CREATION_AVAILABLE = False

try:
    from monitor_agents.loops.session_zero_loop import SessionZeroLoop

    _SESSION_ZERO_AVAILABLE = True
except Exception:  # noqa: BLE001
    _SESSION_ZERO_AVAILABLE = False

try:
    from monitor_agents.loops.conversation_loop import (
        ConversationLoop,
        ConversationMode,
    )

    _CONVERSATION_AVAILABLE = True
except Exception:  # noqa: BLE001
    ConversationLoop = None  # type: ignore[assignment,misc]
    ConversationMode = None  # type: ignore[assignment,misc]
    _CONVERSATION_AVAILABLE = False

try:
    from monitor_agents.recap_agent import RecapAgent

    _RECAP_AVAILABLE = True
except Exception:  # noqa: BLE001
    RecapAgent = None  # type: ignore[assignment,misc]
    _RECAP_AVAILABLE = False

try:
    from monitor_data.tools.mongodb_tools import mongodb_get_gm_profile

    _BOOTSTRAP_AVAILABLE = True
except Exception:  # noqa: BLE001
    _BOOTSTRAP_AVAILABLE = False

try:
    from .character_resolution import resolve_actor_character

    _CHARACTER_RESOLUTION_AVAILABLE = True
except Exception:  # noqa: BLE001
    _CHARACTER_RESOLUTION_AVAILABLE = False

try:
    from monitor_agents.utils.db_readers import mongodb_update_scene, run_sync_read
    from monitor_data.schemas.scenes import SceneUpdate

    _DB_READERS_AVAILABLE = True
except Exception:  # noqa: BLE001
    _DB_READERS_AVAILABLE = False


# ---------------------------------------------------------------------------
# In-process loop caches (shared state, set from chat.py)
# ---------------------------------------------------------------------------

_SCENE_LOOPS_MAX = 32
_SCENE_LOOPS: OrderedDict[str, tuple[tuple[Any, ...], Any]] = OrderedDict()
_CHAR_CREATION_LOOPS_MAX = 16
_CHAR_CREATION_LOOPS: OrderedDict[str, CharacterCreationLoop | None] = OrderedDict()
_SESSION_ZERO_LOOPS_MAX = 16
_SESSION_ZERO_LOOPS: OrderedDict[str, SessionZeroLoop | None] = OrderedDict()

# Cache for story states (Gap 4)
_STORY_STATES: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Scene loop lifecycle
# ---------------------------------------------------------------------------


def scene_loop_signature(
    session: dict[str, Any],
    *,
    scene_id: str,
    story_id: str,
) -> tuple[Any, ...]:
    actor_id = as_uuid(
        session.get("speaker_character_id") or session.get("character_id")
    )
    return (
        scene_id,
        story_id,
        session.get("play_mode", "dice_game_system"),
        session.get("system_id"),
        session.get("pack_id"),
        session.get("system_source_type"),
        session.get("system_source_id"),
        str(actor_id) if actor_id else None,
        session.get("tone", "dramatic"),
        session.get("gm_profile_id"),
    )


def get_scene_loop(
    session_id: str,
    session: dict[str, Any],
    *,
    scene_id: str,
    story_id: str,
    actor_context: dict[str, Any] | None = None,
) -> Any:
    signature = scene_loop_signature(session, scene_id=scene_id, story_id=story_id)
    cached = _SCENE_LOOPS.get(session_id)
    if cached and cached[0] == signature:
        _SCENE_LOOPS.move_to_end(session_id)
        return cached[1]

    # Load GM profile if configured
    gm_profile_dict: dict[str, Any] | None = None
    gm_profile_id = session.get("gm_profile_id")
    if gm_profile_id and _BOOTSTRAP_AVAILABLE:
        try:
            profile = mongodb_get_gm_profile(uuid.UUID(gm_profile_id))
            if profile:
                gm_profile_dict = profile.model_dump()
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to load GM profile %s, falling back to tone", gm_profile_id
            )

    loop = SceneLoop(
        scene_id=uuid.UUID(scene_id),
        story_id=uuid.UUID(story_id),
        universe_id=as_uuid(session.get("universe_id") or session.get("world_id")),
        play_mode=session.get("play_mode", "dice_game_system"),
        system_id=session.get("system_id"),
        pack_id=session.get("pack_id"),
        system_source_type=session.get("system_source_type"),
        system_source_id=session.get("system_source_id"),
        actor_id=as_uuid(
            session.get("speaker_character_id") or session.get("character_id")
        ),
        actor_context=actor_context,
        session_tone=session.get("tone", "dramatic"),
        gm_profile=gm_profile_dict,
    )
    _SCENE_LOOPS[session_id] = (signature, loop)
    _SCENE_LOOPS.move_to_end(session_id)
    while len(_SCENE_LOOPS) > _SCENE_LOOPS_MAX:
        _SCENE_LOOPS.popitem(last=False)
    return loop


def get_character_creation_loop(
    session_id: str,
    session: dict[str, Any],
    *,
    session_game_system_doc: Any,
) -> CharacterCreationLoop | None:
    """Get or create a CharacterCreationLoop for this session."""
    if not _CHAR_CREATION_AVAILABLE:
        return None

    system_doc = session_game_system_doc(session)
    if not system_doc:
        return None

    cached = _CHAR_CREATION_LOOPS.get(session_id)
    if cached is not None:
        _CHAR_CREATION_LOOPS.move_to_end(session_id)
        return cached

    try:
        loop = CharacterCreationLoop(game_context=system_doc)
        _CHAR_CREATION_LOOPS[session_id] = loop
        _CHAR_CREATION_LOOPS.move_to_end(session_id)
        while len(_CHAR_CREATION_LOOPS) > _CHAR_CREATION_LOOPS_MAX:
            _CHAR_CREATION_LOOPS.popitem(last=False)
        return loop
    except Exception as exc:  # noqa: BLE001
        logger.debug("CharacterCreationLoop creation failed: %s", exc)
        return None


def pop_character_creation_loop(session_id: str) -> None:
    """Remove a cached character creation loop."""
    _CHAR_CREATION_LOOPS.pop(session_id, None)


def get_session_zero_loop(
    session_id: str,
    session: dict[str, Any],
    world_lore: list[str] | None = None,
    system_context: str = "",
) -> SessionZeroLoop | None:
    """Get or create a SessionZeroLoop for this session."""
    if not _SESSION_ZERO_AVAILABLE:
        return None

    cached = _SESSION_ZERO_LOOPS.get(session_id)
    if cached is not None:
        _SESSION_ZERO_LOOPS.move_to_end(session_id)
        return cached

    try:
        loop = SessionZeroLoop(
            tone=session.get("tone", "dramatic"),
            system_name=session.get("system_label") or "Unknown System",
            world_lore=world_lore or [],
            system_context=system_context,
            max_questions=7,
        )
        _SESSION_ZERO_LOOPS[session_id] = loop
        _SESSION_ZERO_LOOPS.move_to_end(session_id)
        while len(_SESSION_ZERO_LOOPS) > _SESSION_ZERO_LOOPS_MAX:
            _SESSION_ZERO_LOOPS.popitem(last=False)
        return loop
    except Exception as exc:  # noqa: BLE001
        logger.debug("SessionZeroLoop creation failed: %s", exc)
        return None


def pop_session_zero_loop(session_id: str) -> None:
    """Remove a cached session zero loop."""
    _SESSION_ZERO_LOOPS.pop(session_id, None)


def pop_scene_loop(session_id: str) -> None:
    """Remove a cached scene loop."""
    _SCENE_LOOPS.pop(session_id, None)


# ---------------------------------------------------------------------------
# Character name inference & persistence
# ---------------------------------------------------------------------------


def infer_character_name_from_text(
    text: str | None, fallback: str = "Player Character"
) -> str:
    """Best-effort name guess from a conversational character description."""
    if not text:
        return fallback

    patterns = (
        r"\b(?:my name is|call me|i am|i'm)\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,2})",
    )
    for pattern in patterns:
        match = _re.search(pattern, text, _re.IGNORECASE)
        if match:
            candidate = " ".join(part.capitalize() for part in match.group(1).split())
            if candidate:
                return candidate
    return fallback


def persist_session_character(
    session: dict[str, Any],
    preview: dict[str, Any],
    source_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist a pre-play character into the selected world and bind it to the session."""
    universe_id = session.get("universe_id") or session.get("world_id")
    if not universe_id:
        return None

    from .entities import _persist_generated_entity

    saved = _persist_generated_entity(
        universe_id=str(universe_id),
        preview=preview,
        source_meta=source_meta,
    )
    entity_id = saved.get("entity_id")
    if entity_id:
        session["character_id"] = entity_id
        session["speaker_character_id"] = entity_id
        controlled = list(session.get("controlled_character_ids", []))
        if entity_id not in controlled:
            controlled.append(entity_id)
        session["controlled_character_ids"] = controlled
    return saved


# ---------------------------------------------------------------------------
# OOC answer helper
# ---------------------------------------------------------------------------


async def answer_ooc_question(
    session: dict[str, Any],
    question: str,
    *,
    session_game_system_doc: Any,
    gsr_available: bool,
) -> str:
    """
    Answer an OOC question in-fiction, drawing from the game system schema and entity archetypes.

    Never mentions rule numbers or attribute abbreviations in isolation.
    Describes character possibilities in narrative terms.
    """
    question = normalize_ooc_text(question)
    system_doc = session_game_system_doc(session)
    universe_id = session.get("universe_id")

    mechanical_hint = ""
    if system_doc and gsr_available:
        try:
            from .chat_game_system import _GSR_AVAILABLE as _gsr

            if _gsr:
                from monitor_agents.game_system import GameSystemRuntime

                gsr = GameSystemRuntime(system_doc)
                probe_text = question
                lower_q = question.lower()
                if "would i roll to" in lower_q:
                    probe_text = lower_q.replace("would i roll to", "i ")
                elif "what do i roll for" in lower_q:
                    probe_text = lower_q.replace("what do i roll for", "i ")
                elif any(
                    word in lower_q
                    for word in (
                        "shoot",
                        "attack",
                        "sneak",
                        "talk",
                        "convince",
                        "search",
                        "repair",
                        "hack",
                    )
                ):
                    probe_text = f"I {question}"

                action_type, stat_name, dc = gsr.infer_action_stat(probe_text)
                core_formula = (system_doc.get("core_mechanic") or {}).get(
                    "formula"
                ) or "the system's core mechanic"
                if any(
                    word in lower_q
                    for word in (
                        "roll",
                        "shoot",
                        "attack",
                        "sneak",
                        "talk",
                        "convince",
                        "search",
                        "repair",
                        "hack",
                    )
                ):
                    mechanical_hint = (
                        f"Mechanically, I'd usually call for **{stat_name}** using **{core_formula}**. "
                        f"For a risky attempt, expect pressure around **{dc}** unless the fiction changes it."
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("answer_ooc_question mechanical hint failed: %s", exc)

    # Gather entity archetypes for character type questions
    archetype_lines: list[str] = []
    try:
        from monitor_data.db.neo4j import get_neo4j_client  # noqa: PLC0415

        neo = get_neo4j_client()
        rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (e:Entity) WHERE e.entity_type = 'character' AND e.is_archetype = true "
            "AND (e.universe_id = $uid OR 1=1) "
            "RETURN e.name AS name, e.description AS desc "
            "LIMIT 8",
            {"uid": universe_id or ""},
        )
        for r in rows:
            name = r.get("name", "")
            desc = (r.get("desc") or "")[:120]
            if name:
                archetype_lines.append(f"{name}: {desc}" if desc else name)
    except Exception:  # noqa: BLE001
        pass

    # Try LLM answer if agents available
    if _AGENTS_AVAILABLE:
        try:
            from monitor_agents.narrator import Narrator

            narrator = Narrator()
            lore_block = "\n".join(archetype_lines[:6]) if archetype_lines else ""
            result = await narrator.narrate_turn(
                scene_id=uuid.uuid4(),
                user_input=f"[OOC] {question}",
                resolution=None,
                context={
                    "entities": [{"context": lore_block}] if lore_block else [],
                    "memories": [],
                    "turns": [],
                },
                game_context=system_doc,
                session_tone=session.get("tone", "dramatic"),
            )
            answer = result.get("narrative_text", "").strip()
            if answer and len(answer) > 30:
                if mechanical_hint and mechanical_hint.lower() not in answer.lower():
                    return f"{answer}\n\n{mechanical_hint}"
                return answer
        except Exception as exc:  # noqa: BLE001
            logger.debug("answer_ooc_question LLM failed: %s", exc)

    # Fallback: describe archetypes in plain prose
    if archetype_lines:
        intro = "Out here, people survive in different ways.\n\n"
        body = "\n".join(f"- {line}" for line in archetype_lines[:5])
        closing = "\n\nWhat pulls at you?"
        if mechanical_hint:
            closing = f"\n\n{mechanical_hint}\n\nWhat pulls at you?"
        return intro + body + closing

    sys_name = session.get("system_label") or "this world"
    base = (
        f"In {sys_name}, who you are is defined by what you do and how you survive. "
        "Tell me about your character — even a rough idea is enough to start."
    )
    return f"{base}\n\n{mechanical_hint}" if mechanical_hint else base


# ---------------------------------------------------------------------------
# Pre-play turn handler
# ---------------------------------------------------------------------------


async def _generate_prologue(session: dict[str, Any], summary_text: str) -> str:
    """Generate a prologue opening that incorporates the character's backstory.

    Called after Session Zero completes and the player chooses narrative-only
    mode (no mechanical character creation). Uses the Narrator to weave the
    character's backstory into an opening scene.
    """
    if _AGENTS_AVAILABLE:
        try:
            from monitor_agents.narrator import Narrator

            narrator = Narrator()
            summary = session.get("session_zero_summary") or {}
            concept = summary.get("concept", "") if isinstance(summary, dict) else ""
            backstory = summary.get("backstory", "") if isinstance(summary, dict) else ""

            prologue = await narrator.generate_opening(
                user_input=(
                    f"[Prologue — the character's backstory follows]\n"
                    f"Concept: {concept}\nBackstory: {backstory}\n"
                    f"Set the opening scene that incorporates this backstory."
                ),
                context={"entities": [], "memories": [], "turns": []},
                game_context=None,
                session_tone=session.get("tone", "dramatic"),
            )
            if prologue and len(prologue) > 40:
                return prologue
        except Exception as exc:  # noqa: BLE001
            logger.debug("_generate_prologue LLM call failed: %s", exc)

    # Fallback: use the summary text directly
    if summary_text:
        return summary_text + "\n\nThe story begins. What do you do?"
    return "Your character is ready. The story begins — what do you do?"


async def run_preplay_turn(
    session_id: str,
    user_content: str,
    *,
    sessions: dict[str, dict],
    messages: dict[str, list[dict]],
    db_save_session: Any,
    db_save_message: Any,
    session_game_system_doc: Any,
    gsr_available: bool,
) -> tuple[str, dict[str, Any]]:
    """
    Handle all player messages during the pre-play phase.

    Routes:
    - OOC question about rules/character types → answer_ooc_question
    - char_creation phase + confirmation → roll stats + transition to active_play
    - Character description or creation confirmation → acknowledge + transition to active_play
    """
    session = sessions.get(session_id, {})
    phase = session.get("phase", "awaiting_character")

    # --- OOC question ---
    if is_ooc_question(user_content):
        answer = await answer_ooc_question(
            session,
            user_content,
            session_game_system_doc=session_game_system_doc,
            gsr_available=gsr_available,
        )
        return answer, {"type": "ooc_answer", "phase": phase}

    if phase in {"awaiting_character", "char_creation", "session_zero"}:
        session["pending_character_concept"] = user_content

    # --- Session Zero interview phase ---
    if phase == "session_zero" and _SESSION_ZERO_AVAILABLE:
        world_lore = []
        system_context = ""
        if session_id not in _SESSION_ZERO_LOOPS:
            try:
                from .chat_opening import fetch_opening_hook
                lore_data = await fetch_opening_hook(session)
                world_lore = lore_data.get("axioms", []) + lore_data.get("facts", [])
            except Exception as exc:
                logger.debug("Failed to fetch opening hook for session zero: %s", exc)
                
            try:
                system_doc = session_game_system_doc(session)
                if system_doc and isinstance(system_doc, dict):
                    context_parts = []
                    cc = system_doc.get("character_creation")
                    if cc:
                        bgs = [bg.get("name") for bg in cc.get("backgrounds", []) if bg.get("name")]
                        if bgs:
                            context_parts.append("Backgrounds/Origins: " + ", ".join(bgs))
                        steps = [step.get("title") for step in cc.get("steps", []) if step.get("title")]
                        if steps:
                            context_parts.append("Creation Steps: " + ", ".join(steps))
                        prompts = [logic.get("prompt_template") for logic in cc.get("logic", []) if logic.get("prompt_template")]
                        if prompts:
                            context_parts.append("Themes: " + " | ".join(prompts))
                    system_context = "\n".join(context_parts)
            except Exception as exc:
                logger.debug("Failed to build system context for session zero: %s", exc)

        sz_loop = get_session_zero_loop(session_id, session, world_lore, system_context)
        if sz_loop:
            try:
                result = await sz_loop.process_player_input(user_content)
                if result.get("complete"):
                    summary = result.get("summary")
                    # Store the summary for the character creation handoff
                    if summary:
                        session["session_zero_summary"] = (
                            summary.model_dump() if hasattr(summary, "model_dump") else summary
                        )
                        if summary.character_name:
                            session["speaker_label"] = summary.character_name
                        session["pending_character_concept"] = summary.concept or user_content

                    session["phase"] = "char_creation"
                    db_save_session(session)

                    # If a game system is available, start the CharacterCreationLoop
                    system_doc = session_game_system_doc(session)
                    if system_doc and gsr_available and _CHAR_CREATION_AVAILABLE:
                        cc_loop = get_character_creation_loop(
                            session_id,
                            session,
                            session_game_system_doc=session_game_system_doc,
                        )
                        if cc_loop:
                            try:
                                start_result = await cc_loop.start()
                                gm_msg = start_result.get(
                                    "gm_message", "Let's build your character."
                                )
                                response = (
                                    result.get("gm_message", "")
                                    + "\n\n---\n\n"
                                    + gm_msg
                                )
                                return response, {
                                    "type": "session_zero_complete",
                                    "phase": "char_creation",
                                    "summary": summary.model_dump() if summary else None,
                                    "total_steps": start_result.get("total_steps", 0),
                                }
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("post-session-zero char creation start failed: %s", exc)

                    # No mechanics: go straight to active_play with prologue
                    session["phase"] = "active_play"
                    db_save_session(session)
                    prologue = await _generate_prologue(session, result.get("gm_message", ""))
                    return prologue, {
                        "type": "session_zero_complete",
                        "phase": "active_play",
                        "summary": summary.model_dump() if summary else None,
                    }
                else:
                    gm_msg = result.get("gm_message", "Tell me more.")
                    return gm_msg, {
                        "type": "session_zero_question",
                        "phase": "session_zero",
                        "question_number": result.get("question_number", 0),
                        "total_questions": result.get("total_questions", 7),
                        "category": result.get("category", "custom"),
                    }
            except Exception as exc:  # noqa: BLE001
                logger.debug("run_preplay_turn session zero loop failed: %s", exc)
                # Fall through to char_creation on error

    # --- Conversational character creation via CharacterCreationLoop ---
    if phase == "char_creation" and _CHAR_CREATION_AVAILABLE:
        cc_loop = get_character_creation_loop(
            session_id,
            session,
            session_game_system_doc=session_game_system_doc,
        )
        if cc_loop:
            try:
                result = await cc_loop.process_player_input(user_content)
                if result.get("complete"):
                    char = result.get("character", {})
                    system_doc = session_game_system_doc(session)
                    sheet_md = result.get("sheet_markdown", "")
                    preview = {
                        "kind": "pc",
                        "name": char.get("name")
                        or session.get("speaker_label")
                        or "Adventurer",
                        "description": session.get("pending_character_concept") or "",
                        "concept": session.get("pending_character_concept") or "",
                        "system_name": (system_doc or {}).get(
                            "name", session.get("system_label") or ""
                        ),
                        "attributes": char.get("attributes") or {},
                        "resources": char.get("resources") or {},
                        "skills": char.get("skills") or {},
                        "sheet": sheet_md or str(char),
                        "tags": ["pc", "generated"],
                        "source": "character_creation_loop",
                    }
                    saved = None
                    try:
                        saved = persist_session_character(
                            session,
                            preview,
                            {
                                "source_type": session.get("system_source_type")
                                or "generic_library",
                                "source_label": (system_doc or {}).get(
                                    "name", "Narrative"
                                ),
                                "system_id": session.get("system_id"),
                                "pack_id": session.get("pack_id"),
                            },
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("run_preplay_turn char loop save failed: %s", exc)

                    session["phase"] = "active_play"
                    db_save_session(session)
                    pop_character_creation_loop(session_id)
                    response_text = (
                        f"{preview['name']} is ready. I have the sheet for reference. "
                        "Let's begin in the fiction — what do you do?"
                    )
                    return response_text, {
                        "type": "char_creation_complete",
                        "phase": "active_play",
                        "character": char,
                        "sheet": sheet_md,
                        "saved_character": saved,
                    }
                else:
                    gm_msg = result.get(
                        "gm_message", "Tell me more about your character."
                    )
                    return gm_msg, {
                        "type": "char_creation_step",
                        "phase": "char_creation",
                        "step_index": result.get("step_index", 0),
                        "total_steps": result.get("total_steps", 0),
                    }
            except Exception as exc:  # noqa: BLE001
                logger.debug("run_preplay_turn char creation loop failed: %s", exc)

    # --- char_creation phase: player confirming stat roll (legacy fallback) ---
    if phase == "char_creation":
        lower = user_content.strip().lower()
        _SKIP_RE = _re.compile(
            r"\b(skip|no|nah|narrative|don'?t|pass|just play|free.?form)\b",
            _re.IGNORECASE,
        )
        if _SKIP_RE.search(lower):
            saved = None
            concept = session.get("pending_character_concept") or user_content
            preview = {
                "kind": "pc",
                "name": session.get("speaker_label")
                or infer_character_name_from_text(concept),
                "description": concept,
                "concept": concept,
                "system_name": session.get("system_label") or "Narrative",
                "attributes": {},
                "resources": {},
                "skills": {},
                "sheet": concept,
                "tags": ["pc", "narrative_only"],
                "source": "narrative_only",
            }
            try:
                saved = persist_session_character(
                    session,
                    preview,
                    {
                        "source_type": "narrative_only",
                        "source_label": session.get("system_label") or "Narrative",
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("run_preplay_turn narrative-only save failed: %s", exc)

            session["phase"] = "active_play"
            db_save_session(session)
            return (
                "No numbers needed — your story speaks for itself. Let's begin.",
                {
                    "type": "preplay_ack",
                    "phase": "active_play",
                    "saved_character": saved,
                },
            )

        # Assume anything else is confirmation — roll stats
        system_doc = session_game_system_doc(session)
        if system_doc and gsr_available:
            try:
                from monitor_agents.game_system import GameSystemRuntime

                gsr = GameSystemRuntime(system_doc)
                rolled = gsr.roll_character()
                sheet = gsr.format_character_sheet(rolled)
                preview = {
                    "kind": "pc",
                    "name": session.get("speaker_label")
                    or infer_character_name_from_text(
                        session.get("pending_character_concept")
                    ),
                    "description": session.get("pending_character_concept") or "",
                    "concept": session.get("pending_character_concept") or "",
                    "system_name": system_doc.get(
                        "name", session.get("system_label") or ""
                    ),
                    "attributes": rolled.get("stats", {}),
                    "resources": rolled.get("derived", {}),
                    "skills": {},
                    "rolls_detail": rolled.get("rolls_detail", {}),
                    "sheet": sheet,
                    "special_abilities": [],
                    "tags": ["pc", "generated"],
                    "source": "runtime_roll",
                }
                saved = None
                try:
                    saved = persist_session_character(
                        session,
                        preview,
                        {
                            "source_type": session.get("system_source_type")
                            or (
                                "generic_library"
                                if session.get("system_id")
                                else "narrative_only"
                            ),
                            "source_label": system_doc.get(
                                "name", session.get("system_label") or "Narrative"
                            ),
                            "system_id": session.get("system_id"),
                            "pack_id": session.get("pack_id"),
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("run_preplay_turn character save failed: %s", exc)

                session["phase"] = "active_play"
                db_save_session(session)
                name = preview.get("name") or "Your character"
                return (
                    f"{name} is ready. I have the sheet for reference. "
                    "Let's begin in the fiction — what do you do?",
                    {
                        "type": "char_stats_rolled",
                        "phase": "active_play",
                        "stats": rolled.get("stats", {}),
                        "derived": rolled.get("derived", {}),
                        "sheet": sheet,
                        "saved_character": saved,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("run_preplay_turn stat roll failed: %s", exc)

        # Fallback: just transition to active_play
        session["phase"] = "active_play"
        db_save_session(session)
        return (
            "Stats locked. You're in. What do you do?",
            {"type": "preplay_ack", "phase": "active_play"},
        )

    # --- Player has described their character (or any substantive response to the opening) ---
    system_doc = session_game_system_doc(session)

    # Generate an in-fiction acknowledgement via LLM if possible
    acknowledgement = ""
    if _AGENTS_AVAILABLE:
        try:
            from monitor_agents.narrator import Narrator

            narrator = Narrator()
            result = await narrator.narrate_turn(
                scene_id=uuid.uuid4(),
                user_input=f"[Character intro] {user_content}",
                resolution=None,
                context={"entities": [], "memories": [], "turns": []},
                game_context=system_doc,
                session_tone=session.get("tone", "dramatic"),
            )
            acknowledgement = result.get("narrative_text", "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.debug("run_preplay_turn LLM ack failed: %s", exc)
    if not acknowledgement:
        acknowledgement = "Understood. That's who you are."

    # --- Start Session Zero interview (guided character development) ---
    if _SESSION_ZERO_AVAILABLE:
        sz_loop = get_session_zero_loop(session_id, session)
        if sz_loop:
            try:
                start_result = await sz_loop.start()
                session["phase"] = "session_zero"
                db_save_session(session)
                gm_msg = start_result.get("gm_message", "Tell me more about your character.")
                response = acknowledgement + "\n\n" + gm_msg
                return response, {
                    "type": "session_zero_start",
                    "phase": "session_zero",
                    "question_number": start_result.get("question_number", 1),
                    "total_questions": start_result.get("total_questions", 7),
                    "category": start_result.get("category", "custom"),
                    "saved_character": None,
                }
            except Exception as exc:  # noqa: BLE001
                logger.debug("run_preplay_turn session zero start failed: %s", exc)

    # --- Fallback: Transition to char_creation if a game system is available ---
    saved = None
    if system_doc and gsr_available:
        # Try conversational character creation first
        if _CHAR_CREATION_AVAILABLE:
            cc_loop = get_character_creation_loop(
                session_id,
                session,
                session_game_system_doc=session_game_system_doc,
            )
            if cc_loop:
                try:
                    start_result = await cc_loop.start()
                    gm_msg = start_result.get(
                        "gm_message", "Let's build your character."
                    )
                    session["phase"] = "char_creation"
                    db_save_session(session)
                    response = acknowledgement + "\n\n" + gm_msg
                    return response, {
                        "type": "char_creation_start",
                        "phase": "char_creation",
                        "total_steps": start_result.get("total_steps", 0),
                        "saved_character": None,
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.debug("run_preplay_turn char creation start failed: %s", exc)

        # Fallback: build a mechanical offer
        mech_offer = ""
        try:
            from monitor_agents.game_system import GameSystemRuntime

            gsr = GameSystemRuntime(system_doc)
            attrs = gsr.primary_attributes
            attr_names = [a.get("name", "") for a in attrs[:4] if a.get("name")]
            creation_method = gsr.ability_method_description()
            if len(attr_names) > 1:
                attr_list = f"{', '.join(attr_names[:-1])} and {attr_names[-1]}"
            elif attr_names:
                attr_list = attr_names[0]
            else:
                attr_list = ""
            if attr_list:
                mech_offer = (
                    f"\n\nWhen you're ready, I can ground that in the system — "
                    f"your core stats will be {attr_list}. "
                    + (
                        f"They're generated by {creation_method.lower().rstrip('.')}. "
                        if creation_method
                        else ""
                    )
                    + "Want me to roll them, or would you rather assign them yourself?"
                )
        except Exception:  # noqa: BLE001
            pass

        session["phase"] = "char_creation"
        response = acknowledgement + mech_offer
    else:
        # No mechanics to offer: go straight to active play
        session["phase"] = "active_play"
        response = acknowledgement
        preview = {
            "kind": "pc",
            "name": session.get("speaker_label")
            or infer_character_name_from_text(user_content),
            "description": user_content,
            "concept": user_content,
            "system_name": session.get("system_label") or "Narrative",
            "attributes": {},
            "resources": {},
            "skills": {},
            "sheet": user_content,
            "tags": ["pc", "narrative_only"],
            "source": "narrative_only",
        }
        try:
            saved = persist_session_character(
                session,
                preview,
                {
                    "source_type": "narrative_only",
                    "source_label": session.get("system_label") or "Narrative",
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("run_preplay_turn direct character save failed: %s", exc)
    db_save_session(session)

    return response, {
        "type": "preplay_ack",
        "phase": session["phase"],
        "saved_character": saved,
    }


# ---------------------------------------------------------------------------
# World Architect turn runner
# ---------------------------------------------------------------------------


async def run_world_architect_turn(
    session_id: str,
    user_content: str,
    *,
    sessions: dict[str, dict],
    messages: dict[str, list[dict]],
    db_save_session: Any,
    db_load_messages: Any,
) -> tuple[str, dict[str, Any]]:
    """Run one world-building turn through WorldBuildingLoop."""
    session = sessions.get(session_id)
    if not session:
        return ("Session not found.", {})

    if not _WORLD_ARCHITECT_AVAILABLE:
        return (
            "The World Architect engine is not available yet.\n\n"
            "*(Install the agents layer to enable conversational world building.)*",
            {"world_architect_available": False},
        )

    universe_id = as_uuid(session.get("universe_id") or session.get("world_id"))
    multiverse_id = as_uuid(session.get("multiverse_id"))

    # Build conversation history from stored messages
    msgs = messages.get(session_id) or db_load_messages(session_id)
    history = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in msgs
        if m.get("role") in ("player", "gm", "system")
    ]

    try:
        loop = WorldBuildingLoop(
            session_id=session_id,
            universe_id=universe_id,
            multiverse_id=multiverse_id,
        )
        result = await loop.run(
            user_input=user_content,
            conversation_history=history,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("World Architect turn failed: %s", exc)
        return (
            "I encountered an issue processing your request. "
            "Could you rephrase or try again?",
            {"error": str(exc)},
        )

    # Capture newly created container IDs and update session
    new_u_id = result.get("universe_id")
    new_m_id = result.get("multiverse_id")

    if new_u_id:
        session["universe_id"] = str(new_u_id)
    if new_m_id:
        session["multiverse_id"] = str(new_m_id)

    if new_u_id or new_m_id:
        db_save_session(session)

    response = result.get("response_text", "…")
    metadata: dict[str, Any] = {
        "type": "world_architect",
        "committed": result.get("committed_count", 0),
        "proposals": len(result.get("extracted_proposals", [])),
        "turns_count": result.get("turns_count", 0),
        "coverage_summary": result.get("coverage_summary", ""),
        "known_open_questions": result.get("known_open_questions", [])[:4],
        "priority_gaps": result.get("priority_gaps", [])[:3],
        "universe_id": str(new_u_id) if new_u_id else None,
        "multiverse_id": str(new_m_id) if new_m_id else None,
    }
    return (response, metadata)


# ---------------------------------------------------------------------------
# Scene loop turn runner
# ---------------------------------------------------------------------------


def _format_dice_spec(modifier: int, *, roll_under: bool = False) -> str:
    """Return the client dice spec for a pending d20 check."""
    if roll_under:
        return "1d20"
    if modifier > 0:
        return f"1d20+{modifier}"
    if modifier < 0:
        return f"1d20{modifier}"
    return "1d20"


def _dice_request_from_resolution(
    resolution: dict[str, Any],
    user_content: str,
) -> dict[str, Any] | None:
    """Convert a Resolver propose_roll result into frontend prompt metadata."""
    if resolution.get("resolution_type") != "propose_roll":
        return None

    try:
        modifier = int(resolution.get("modifier") or 0)
    except (TypeError, ValueError):
        modifier = 0
    stat = str(resolution.get("stat") or "relevant stat")
    dc = resolution.get("difficulty_class")
    roll_under = bool(resolution.get("roll_under"))
    spec = _format_dice_spec(modifier, roll_under=roll_under)
    reason = str(
        resolution.get("roll_invitation")
        or f"{stat} check"
        or "Roll to resolve the action"
    )

    return {
        "spec": spec,
        "reason": reason,
        "stat": stat,
        "difficulty_class": dc,
        "modifier": modifier,
        "roll_under": roll_under,
        "action_type": resolution.get("action_type"),
        "intent_type": resolution.get("intent_type"),
        "risk_preview": resolution.get("risk_preview"),
        "original_action": user_content,
    }


def _parse_dice_result_message(content: str) -> dict[str, Any] | None:
    """Extract spec, rolls, and total from the websocket dice-result message."""
    if "[DICE RESULT]" not in content:
        return None
    match = _re.search(
        r"rolled\s+(?P<spec>\S+)(?:\s+\[(?P<rolls>[^\]]*)\])?\s*=\s*(?P<total>-?\d+)",
        content,
        flags=_re.IGNORECASE,
    )
    if not match:
        return None
    rolls_raw = match.group("rolls") or ""
    rolls = [
        int(part.strip())
        for part in rolls_raw.split(",")
        if part.strip().lstrip("-").isdigit()
    ]
    return {
        "spec": match.group("spec"),
        "rolls": rolls,
        "total": int(match.group("total")),
    }


def _success_level_from_roll(
    *,
    total: int,
    natural: int,
    dc: int | None,
    modifier: int,
    roll_under: bool,
) -> tuple[str, bool | None, str]:
    """Resolve the submitted roll using the pending check metadata."""
    if dc is None:
        return "success", True, "submitted roll"

    if roll_under:
        target = dc + modifier
        if natural == 1:
            level = "critical_success"
        elif natural == 20:
            level = "critical_failure"
        elif natural <= target:
            level = "success"
        elif natural <= target + 2:
            level = "partial_success"
        else:
            level = "failure"
        breakdown = f"1d20({natural}) <= {dc} + {modifier} = {target}"
    else:
        if natural == 20:
            level = "critical_success"
        elif natural == 1:
            level = "critical_failure"
        elif total >= dc:
            level = "success"
        elif total >= dc - 2:
            level = "partial_success"
        else:
            level = "failure"
        breakdown = f"1d20({natural}) + {modifier} = {total} vs DC {dc}"

    return level, level in {"success", "critical_success"}, breakdown


def _resolved_roll_from_pending(
    session: dict[str, Any],
    content: str,
) -> tuple[str, dict[str, Any]] | None:
    """Build a Resolver-compatible dice result from a pending roll request."""
    pending = session.get("pending_dice_request")
    parsed = _parse_dice_result_message(content)
    if not isinstance(pending, dict) or not parsed:
        return None

    try:
        modifier = int(pending.get("modifier") or 0)
    except (TypeError, ValueError):
        modifier = 0
    dc_raw = pending.get("difficulty_class")
    try:
        dc = int(dc_raw) if dc_raw is not None else None
    except (TypeError, ValueError):
        dc = None

    total = int(parsed["total"])
    rolls = list(parsed.get("rolls") or [])
    natural = rolls[0] if rolls else max(1, total - modifier)
    roll_under = bool(pending.get("roll_under"))
    level, success, breakdown = _success_level_from_roll(
        total=total,
        natural=natural,
        dc=dc,
        modifier=modifier,
        roll_under=roll_under,
    )
    effects = ["momentum_gained" if success else "setback", "fiction_advances"]
    pressure = {
        "critical_success": "surging",
        "success": "steady",
        "partial_success": "rising",
        "failure": "high",
        "critical_failure": "spiking",
    }.get(level, "steady")

    reason = str(pending.get("reason") or pending.get("stat") or parsed["spec"])
    resolution = {
        "scene_id": session.get("scene_id"),
        "action_type": pending.get("action_type") or "action",
        "intent_type": pending.get("intent_type") or "action",
        "roll_type": "check",
        "intent_target": None,
        "requires_clarification": False,
        "stat": pending.get("stat"),
        "difficulty_class": dc,
        "attribute_value": None,
        "modifier": modifier,
        "roll_total": total,
        "roll_breakdown": breakdown,
        "roll_detail": {
            "spec": parsed["spec"],
            "total": total,
            "rolls": rolls,
            "reason": reason,
        },
        "resolution_type": "dice",
        "forced_narrative": False,
        "success": success,
        "success_level": level,
        "effects": effects,
        "risk_preview": pending.get("risk_preview"),
        "consequence_options": [],
        "requires_player_choice": False,
        "narrative_pressure": pressure,
        "proposals": [],
        "roll_necessity": "accepted_roll",
    }
    original_action = str(pending.get("original_action") or "The pending action")
    narrated_input = f"{original_action}\n\n{content}"
    return narrated_input, resolution


async def run_scene_turn(
    session_id: str,
    user_content: str,
    *,
    sessions: dict[str, dict],
    messages: dict[str, list[dict]],
    db_save_session: Any,
    db_load_messages: Any,
    bootstrap_story_scene: Any,
    session_game_system_doc: Any,
    gsr_available: bool,
) -> tuple[str, dict[str, Any]]:
    """
    Run one turn through SceneLoop for the given session.

    Returns ``(narrative_text, metadata)``.  Falls back to a placeholder if
    the agents layer is unavailable or the session has no scene/story yet.
    """
    session = sessions.get(session_id)
    if not session:
        return ("Session not found.", {})

    # Transition ooc → active_play on the next player message
    if session.get("phase") == "ooc":
        session["phase"] = "active_play"
        session["updated_at"] = now_iso()
        db_save_session(session)

    scene_id: Optional[str] = session.get("scene_id")
    story_id: Optional[str] = session.get("story_id")

    # Resolve actor character for context (Gap 1)
    actor_context: dict[str, Any] | None = None
    if _CHARACTER_RESOLUTION_AVAILABLE:
        try:
            resolved = resolve_actor_character(session)
            if resolved:
                actor_context = resolved.model_dump(mode="json")
        except Exception as exc:
            logger.debug("Failed to resolve actor character: %s", exc)

    pending_choice = resolve_pending_consequence_choice(
        session,
        user_content,
        save_session=db_save_session,
        now_fn=now_iso,
    )
    if pending_choice is not None:
        return pending_choice

    # Active-play clarification: route explicit OOC/rules questions
    if is_ooc_question(user_content):
        answer = await answer_ooc_question(
            session,
            user_content,
            session_game_system_doc=session_game_system_doc,
            gsr_available=gsr_available,
        )
        session["phase"] = "ooc"
        session["updated_at"] = now_iso()
        db_save_session(session)
        return (
            answer,
            {
                "type": "ooc_answer",
                "phase": "ooc",
                "story_id": story_id,
                "scene_id": scene_id,
                "ooc": True,
            },
        )

    # --- Active conversation routing (GAP 2) ---
    if session.get("conversation_active"):
        if is_end_conversation_command(user_content):
            session.pop("conversation_active", None)
            session.pop("conversation_npc_name", None)
            session.pop("conversation_npc_id", None)
            pop_conversation_loop(session_id)
            session["updated_at"] = now_iso()
            db_save_session(session)
            return (
                "The conversation ends. The world resumes around you. What do you do?",
                {
                    "type": "conversation_end",
                    "phase": "active_play",
                    "conversation_active": False,
                    "story_id": story_id,
                    "scene_id": scene_id,
                },
            )
        return await run_conversation_turn(
            session_id,
            user_content,
            session,
            db_save_session=db_save_session,
        )

    # --- Meta-command: end scene (GAP 4) ---
    if is_end_scene_command(user_content):
        return await run_end_scene(
            session_id,
            session,
            sessions=sessions,
            messages=messages,
            db_save_session=db_save_session,
            db_load_messages=db_load_messages,
            bootstrap_story_scene=bootstrap_story_scene,
        )

    # --- Meta-command: recap (GAP 3) ---
    if is_recap_command(user_content):
        return await run_recap_command(session)

    # --- Meta-command: start conversation (GAP 2) ---
    npc_target = is_start_conversation_command(user_content)
    if npc_target:
        return await run_start_conversation(
            session_id,
            npc_target,
            session,
            db_save_session=db_save_session,
        )

    resolved_roll = _resolved_roll_from_pending(session, user_content)
    resolution_override: dict[str, Any] | None = None
    scene_input = user_content
    if resolved_roll is not None:
        scene_input, resolution_override = resolved_roll
        session.pop("pending_dice_request", None)
        session["updated_at"] = now_iso()
        db_save_session(session)
    elif session.get("pending_dice_request"):
        session.pop("pending_dice_request", None)
        session["updated_at"] = now_iso()
        db_save_session(session)

    if (not scene_id or not story_id) and session.get("universe_id"):
        story_id, scene_id, _ = bootstrap_story_scene(session)
        db_save_session(session)

    if not _AGENTS_AVAILABLE or not scene_id or not story_id:
        return (
            "The narrative engine is standing by…\n\n"
            "*(Bind this session to a universe and opening scene to activate the live GM loop.)*",
            {
                "agents_available": _AGENTS_AVAILABLE,
                "story_id": story_id,
                "scene_id": scene_id,
            },
        )

    try:
        loop = get_scene_loop(
            session_id,
            session,
            scene_id=scene_id,
            story_id=story_id,
            actor_context=actor_context,
        )
        if resolution_override is not None:
            result = await loop.run(
                user_input=scene_input,
                resolution_override=resolution_override,
            )
        else:
            result = await loop.run(user_input=scene_input)
    except Exception as exc:  # noqa: BLE001
        logger.exception("SceneLoop turn failed (session=%s): %s", session_id, exc)
        return (
            "*(The GM is gathering their thoughts — try again in a moment.)*",
            {
                "agents_available": _AGENTS_AVAILABLE,
                "story_id": story_id,
                "scene_id": scene_id,
                "error": str(exc),
            },
        )

    narrative = result.get("narrative_text") or "…"
    resolution = result.get("resolution", {})
    metadata = {
        "type": "scene_turn",
        "phase": session.get("phase", "active_play"),
        "resolution_type": resolution.get("resolution_type"),
        "intent_type": resolution.get("intent_type"),
        "success_level": resolution.get("success_level"),
        "roll_breakdown": resolution.get("roll_breakdown"),
        "roll_detail": resolution.get("roll_detail"),
        "stat": resolution.get("stat"),
        "difficulty_class": resolution.get("difficulty_class"),
        "effects": resolution.get("effects", []),
        "risk_preview": resolution.get("risk_preview"),
        "consequence_options": resolution.get("consequence_options", []),
        "requires_player_choice": resolution.get("requires_player_choice", False),
        "narrative_pressure": resolution.get("narrative_pressure"),
        "turn_id": result.get("turn_id"),
        "resolution_id": result.get("resolution_id"),
        "working_state": result.get("working_state", {}),
        "scene_checkpoint": result.get("scene_checkpoint", {}),
        "social_read": result.get("social_read", {}),
        "relationship_snapshot": result.get("relationship_snapshot", {}),
        "turns_count": result.get("turns_count", 0),
        "story_id": story_id,
        "scene_id": scene_id,
    }

    dice_request = _dice_request_from_resolution(resolution, user_content)
    if dice_request:
        metadata["dice_request"] = dice_request
        session["pending_dice_request"] = {
            **dice_request,
            "scene_id": scene_id,
            "story_id": story_id,
            "turn_id": result.get("turn_id"),
            "created_at": now_iso(),
        }
        session["updated_at"] = now_iso()
        db_save_session(session)
    if metadata.get("working_state"):
        session["latest_working_state"] = metadata["working_state"]
    if metadata.get("scene_checkpoint"):
        session["latest_scene_checkpoint"] = metadata["scene_checkpoint"]
    if metadata.get("social_read"):
        session["latest_social_read"] = metadata["social_read"]
    if metadata.get("relationship_snapshot"):
        session["latest_relationship_snapshot"] = metadata["relationship_snapshot"]

    if metadata["requires_player_choice"] and metadata["consequence_options"]:
        session["pending_consequence"] = {
            "turn_id": metadata.get("turn_id"),
            "resolution_id": metadata.get("resolution_id"),
            "options": list(metadata.get("consequence_options", [])),
            "risk_preview": metadata.get("risk_preview"),
            "created_at": now_iso(),
        }
        session["updated_at"] = now_iso()
        db_save_session(session)
        metadata["awaiting_consequence_choice"] = True
    else:
        pending_cleared = session.pop("pending_consequence", None) is not None
        if (
            metadata.get("working_state")
            or metadata.get("scene_checkpoint")
            or pending_cleared
        ):
            session["updated_at"] = now_iso()
            db_save_session(session)

    # Handle scene completion and world advancement
    if (
        result.get("scene_complete")
        and story_id
        and _AGENTS_AVAILABLE
        and StoryLoop is not None
    ):
        try:
            story_loop = StoryLoop(
                story_id=uuid.UUID(story_id),
                universe_id=uuid.UUID(session["universe_id"]),
            )
            # This triggers simulate_world_advance node in StoryLoop
            story_result = await story_loop.complete_current_scene(
                scene_id=uuid.UUID(scene_id),
                outcome=result,
            )

            # If a new scene was created for transition, update session
            if story_result.get("current_scene_id"):
                session["scene_id"] = str(story_result["current_scene_id"])
                metadata["next_scene_id"] = str(story_result["current_scene_id"])
                # Mark as transition for UI
                metadata["scene_transition"] = True

            if story_result.get("story_complete"):
                session["phase"] = "completed"
                metadata["story_complete"] = True

            db_save_session(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to advance StoryLoop: %s", exc)

    # Fetch and cache story state for metadata (Gap 4)
    if story_id and _AGENTS_AVAILABLE:
        try:
            from .stories import get_story_state

            story_state = await get_story_state(uuid.UUID(story_id))
            if story_state:
                metadata["arc_label"] = story_state.arc_label
                metadata["tension_score"] = story_state.tension_score
                metadata["active_threads"] = story_state.active_threads
                # Cache for session state response
                _STORY_STATES[story_id] = {
                    "story_id": str(story_state.story_id),
                    "universe_id": str(story_state.universe_id),
                    "arc_label": story_state.arc_label,
                    "tension_score": story_state.tension_score,
                    "active_threads": story_state.active_threads,
                    "completed_threads": story_state.completed_threads,
                    "in_game_time": story_state.in_game_time.isoformat(),
                    "world_ticks": story_state.world_ticks,
                    "scenes_completed": story_state.scenes_completed,
                }
        except Exception as exc:
            logger.debug("Failed to fetch story state for metadata: %s", exc)

    # Backward-compatible pass-through for older agent results.
    if result.get("dice_request"):
        metadata["dice_request"] = result["dice_request"]
    return (narrative, metadata)


# ---------------------------------------------------------------------------
# Conversation loop cache (GAP 2)
# ---------------------------------------------------------------------------

_CONVERSATION_LOOPS_MAX = 16
_CONVERSATION_LOOPS: OrderedDict[str, ConversationLoop | None] = OrderedDict()


def pop_conversation_loop(session_id: str) -> None:
    """Remove a cached conversation loop."""
    _CONVERSATION_LOOPS.pop(session_id, None)


# ---------------------------------------------------------------------------
# Meta-command handlers (GAP 4, GAP 3, GAP 2)
# ---------------------------------------------------------------------------


async def run_end_scene(
    session_id: str,
    session: dict[str, Any],
    *,
    sessions: dict[str, dict],
    messages: dict[str, list[dict]],
    db_save_session: Any,
    db_load_messages: Any,
    bootstrap_story_scene: Any,
) -> tuple[str, dict[str, Any]]:
    """
    Force scene completion: canonize pending proposals, advance StoryLoop,
    and prepare the next scene for play.
    """
    scene_id: str | None = session.get("scene_id")
    story_id: str | None = session.get("story_id")

    if not scene_id or not story_id or not _AGENTS_AVAILABLE:
        return (
            "No active scene to end.",
            {"type": "end_scene_error", "phase": session.get("phase")},
        )

    loop = _SCENE_LOOPS.get(session_id)
    loop_instance = loop[1] if loop else None

    narrative = ""
    metadata: dict[str, Any] = {"type": "end_scene", "phase": "active_play"}

    try:
        if loop_instance is not None:
            await loop_instance.finalize()
            narrative = (
                "Scene ended. All pending changes have been evaluated and committed."
            )

        # Mark scene as finalizing in MongoDB
        if _DB_READERS_AVAILABLE:
            await run_sync_read(
                mongodb_update_scene,
                uuid.UUID(scene_id),
                SceneUpdate(status="finalizing"),
            )

        # Transition phase to scene_end before advancing the story
        session["phase"] = "scene_end"

        # Advance the story: world simulation + new scene creation
        if StoryLoop is not None:
            story_loop = StoryLoop(
                story_id=uuid.UUID(story_id),
                universe_id=uuid.UUID(session["universe_id"]),
            )
            outcome = {"total_minutes_passed": 60}  # default 1-hour scene
            story_result = await story_loop.complete_current_scene(
                scene_id=uuid.UUID(scene_id),
                outcome=outcome,
            )

            # Generate summary and mark scene as completed
            summary = await _generate_scene_summary(session_id, messages)
            if _DB_READERS_AVAILABLE:
                await run_sync_read(
                    mongodb_update_scene,
                    uuid.UUID(scene_id),
                    SceneUpdate(status="completed", summary=summary),
                )

            metadata["scene_status"] = "completed"
            metadata["scene_summary"] = summary

            if story_result.get("current_scene_id"):
                new_scene_id = str(story_result["current_scene_id"])
                session["scene_id"] = new_scene_id
                session["phase"] = "active_play"
                metadata["next_scene_id"] = new_scene_id
                metadata["scene_transition"] = True
                narrative += "\n\nThe world has moved forward. A new scene awaits."

                # Invalidate the cached SceneLoop so next turn creates a fresh one
                _SCENE_LOOPS.pop(session_id, None)
                metadata["scene_loop_reset"] = True

            if story_result.get("story_complete"):
                session["phase"] = "completed"
                metadata["story_complete"] = True
                narrative += "\n\nThe story has reached its conclusion."

            db_save_session(session)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_end_scene failed (session=%s): %s", session_id, exc)
        return (
            "The scene ends, but the world machinery stuttered. Try again.",
            {"type": "end_scene_error", "error": str(exc)},
        )

    return narrative, metadata


async def run_recap_command(
    session: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    Generate a "Story So Far" recap via RecapAgent for the current story.
    """
    story_id = session.get("story_id")
    universe_id = session.get("universe_id") or session.get("world_id")

    if not story_id or not universe_id:
        return (
            "No story is active yet. Start playing to build history.",
            {"type": "recap", "phase": session.get("phase")},
        )

    if not _RECAP_AVAILABLE or RecapAgent is None:
        return (
            "The recap engine is not available right now.",
            {"type": "recap_error", "agents_available": False},
        )

    try:
        agent = RecapAgent()
        recap_text = await agent.generate_recap(
            story_id=uuid.UUID(story_id),
            universe_id=uuid.UUID(universe_id),
            tone_context="Evocative narrative summary for the player.",
        )
        if not recap_text or len(recap_text.strip()) < 20:
            recap_text = (
                "The story is just beginning. Every legend starts with a first step."
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("RecapAgent failed (story=%s): %s", story_id, exc)
        return (
            "I couldn't gather the story threads right now. Try again later.",
            {"type": "recap_error", "error": str(exc)},
        )

    return recap_text, {"type": "recap", "phase": session.get("phase", "active_play")}


async def run_start_conversation(
    session_id: str,
    npc_query: str,
    session: dict[str, Any],
    *,
    db_save_session: Any,
) -> tuple[str, dict[str, Any]]:
    """
    Start a dedicated ConversationLoop session with an NPC.

    Resolves the NPC by name from Neo4j entities in the current universe.
    """
    universe_id = session.get("universe_id") or session.get("world_id")
    if not universe_id:
        return (
            "No universe is bound to this session. Can't find NPCs.",
            {"type": "conversation_error"},
        )

    if not _CONVERSATION_AVAILABLE or ConversationLoop is None:
        return (
            "The conversation engine is not available right now.",
            {"type": "conversation_error", "agents_available": False},
        )

    # Search for the NPC by name in Neo4j
    npc_id: str | None = None
    npc_name: str = npc_query
    try:
        from monitor_data.db.neo4j import get_neo4j_client  # noqa: PLC0415

        neo = get_neo4j_client()
        rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (e:Entity) WHERE e.entity_type = 'character' "
            "AND (e.universe_id = $uid OR e.is_archetype = true) "
            "AND toLower(e.name) CONTAINS toLower($name) "
            "RETURN e.entity_id AS id, e.name AS name "
            "LIMIT 5",
            {"uid": universe_id, "name": npc_query},
        )
        if rows:
            npc_id = str(rows[0]["id"])
            npc_name = rows[0].get("name", npc_query)
        else:
            return (
                f"I don't know anyone named **{npc_query}** in this world. "
                "Try a different name, or check the Entities tab.",
                {"type": "conversation_error", "npc_query": npc_query},
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("NPC lookup failed: %s", exc)
        return (
            f"I had trouble looking up **{npc_query}**. The world memory may be unavailable.",
            {"type": "conversation_error", "error": str(exc)},
        )

    player_id = session.get("character_id") or session.get("speaker_character_id")

    # Create conversation loop via the classmethod start()
    try:
        loop = await ConversationLoop.start(
            universe_id=uuid.UUID(universe_id),
            mode=ConversationMode.DIRECT,
            npc_ids=[uuid.UUID(npc_id)],
            scene_id=uuid.UUID(session["scene_id"])
            if session.get("scene_id")
            else None,
            story_id=uuid.UUID(session["story_id"])
            if session.get("story_id")
            else None,
            player_entity_id=uuid.UUID(player_id) if player_id else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ConversationLoop.start failed: %s", exc)
        return (
            "Couldn't start the conversation engine.",
            {"type": "conversation_error", "error": str(exc)},
        )

    # Cache the loop
    _CONVERSATION_LOOPS[session_id] = loop
    _CONVERSATION_LOOPS.move_to_end(session_id)
    while len(_CONVERSATION_LOOPS) > _CONVERSATION_LOOPS_MAX:
        _CONVERSATION_LOOPS.popitem(last=False)

    # The NPC context is loaded by start(), build opening
    opening = (
        f"You approach **{npc_name}**. They turn to face you, waiting. What do you say?"
    )

    # Store conversation state on session
    session["conversation_active"] = True
    session["conversation_npc_name"] = npc_name
    session["conversation_npc_id"] = npc_id
    session["updated_at"] = now_iso()
    db_save_session(session)

    return opening, {
        "type": "conversation_start",
        "phase": "active_play",
        "npc_name": npc_name,
        "npc_id": npc_id,
        "conversation_active": True,
    }


async def run_conversation_turn(
    session_id: str,
    user_content: str,
    session: dict[str, Any],
    *,
    db_save_session: Any,
) -> tuple[str, dict[str, Any]]:
    """
    Process a turn within an active ConversationLoop session.
    """
    loop = _CONVERSATION_LOOPS.get(session_id)
    if loop is None:
        session.pop("conversation_active", None)
        db_save_session(session)
        return (
            "The conversation has ended. What do you do next?",
            {
                "type": "conversation_end",
                "phase": "active_play",
                "conversation_active": False,
            },
        )

    npc_name = session.get("conversation_npc_name", "the NPC")

    try:
        responses = await loop.step(user_content)
        if not responses:
            return (
                f"**{npc_name}** says nothing. The silence hangs between you.",
                {
                    "type": "conversation_turn",
                    "phase": "active_play",
                    "conversation_active": True,
                },
            )

        # Format NPC responses into prose
        lines: list[str] = []
        for resp in responses:
            name = resp.get("npc_name", npc_name)
            text = resp.get("text", "...")
            emotion = resp.get("emotional_state", "")
            emotion_note = f" *({emotion})*" if emotion else ""
            lines.append(f"**{name}**{emotion_note}: {text}")

        narrative = "\n\n".join(lines)
        return narrative, {
            "type": "conversation_turn",
            "phase": "active_play",
            "conversation_active": True,
            "npc_name": npc_name,
            "social_read": responses[0].get("social_read", {}) if responses else {},
            "relationship_snapshot": responses[0].get("relationship_snapshot", {})
            if responses
            else {},
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("ConversationLoop.step failed: %s", exc)
        session.pop("conversation_active", None)
        pop_conversation_loop(session_id)
        db_save_session(session)
        return (
            "The conversation breaks off unexpectedly.",
            {"type": "conversation_error", "error": str(exc)},
        )


async def _generate_scene_summary(
    session_id: str, messages: dict[str, list[dict]]
) -> str:
    """Generate a 2-3 sentence narrative summary of the scene from the last few turns."""
    turns = messages.get(session_id, [])
    # Get last 10 turns, filter for player and gm
    relevant_turns = []
    for m in turns:
        role = str(m.get("role") or "").upper()
        if role in ("PLAYER", "GM", "USER"):
            relevant_turns.append(f"{role}: {m.get('content', '')}")

    relevant_turns = relevant_turns[-10:]

    if not relevant_turns:
        return ""

    history_text = "\n".join(relevant_turns)

    if _AGENTS_AVAILABLE:
        try:
            from monitor_agents.narrator import Narrator

            narrator = Narrator()
            summary_prompt = (
                "Summarize the following scene in 2-3 concise sentences. "
                "Focus on the key narrative outcome and emotional peak. "
                "Write in the third-person past tense. "
                "Do not mention game mechanics.\n\n"
                f"{history_text}"
            )

            # generate_opening is the safest public method to get just text
            summary = await narrator.generate_opening(
                user_input=None,
                context={"entities": [], "memories": [], "turns": []},
                session_tone="summary",
                gm_profile={"prompt_override": summary_prompt},
            )
            return summary.strip()
        except Exception as exc:
            logger.warning("Failed to generate scene summary: %s", exc)

    return "The scene concludes."


# ---------------------------------------------------------------------------
# OOC / AI Persona turn (Roleplay UI)
# ---------------------------------------------------------------------------


async def run_ooc_turn(
    session_id: str,
    user_content: str,
    character_id: str,
    sessions: dict[str, dict],
    messages: dict[str, list[dict]],
    db_save_session: Any,
) -> tuple[str, dict[str, Any]]:
    """
    OOC turn — bare AI persona with no memory/world context.

    Routing: send_message → chat_mode == "ooc" or is_ooc_persona == True.
    Skips SceneLoop entirely. Uses character card + gm_notes as the prompt.
    No memory is read or written.
    """
    session = sessions.get(session_id, {})

    # Resolve actor character for context (Gap 1)
    character: dict[str, Any] | None = None
    if _CHARACTER_RESOLUTION_AVAILABLE:
        try:
            resolved = resolve_actor_character(session)
            if resolved:
                character = resolved.model_dump(mode="json")
        except Exception as exc:
            logger.debug("Failed to resolve actor character for OOC: %s", exc)

    if not character:
        from .character_storage import get_character

        character = get_character(character_id)

    if not character:
        return ("Character not found.", {"type": "error", "chat_mode": "ooc"})

    # Build bare character prompt
    prompt_parts = []
    if character.get("name"):
        prompt_parts.append(f"Name: {character['name']}")
    if character.get("description"):
        prompt_parts.append(f"Description: {character['description']}")
    if character.get("personality"):
        prompt_parts.append(f"Personality: {character['personality']}")
    if character.get("first_message"):
        prompt_parts.append(f"First message: {character['first_message']}")

    gm_notes = character.get("gm_notes", "").strip()
    if gm_notes:
        prompt_parts.append(f"\n[AI Instructions / Author's Note]:\n{gm_notes}")

    character_prompt = "\n\n".join(prompt_parts)

    # Run Narrator in bare mode (no entities, no memories, no game system)
    try:
        from monitor_agents.narrator import Narrator

        narrator = Narrator()
        result = await narrator.narrate_turn(
            scene_id=uuid.uuid4(),  # dummy — not used in OOC mode
            user_input=user_content,
            resolution=None,
            context={
                "entities": [],
                "memories": [],
                "turns": [],
                "source_profile": {},
            },
            game_context={},
            session_tone="dramatic",
            gm_profile={"prompt_override": character_prompt},
        )
        narrative = result.get("narrative_text", "")
    except Exception as exc:
        logger.warning("OOC turn failed: %s", exc)
        narrative = "The character is unavailable right now."

    # Update session phase to indicate OOC
    session["phase"] = "ooc"
    session["updated_at"] = now_iso()
    db_save_session(session)

    return (
        narrative,
        {
            "type": "character_response",
            "chat_mode": "ooc",
            "character_id": character_id,
            "character_name": character.get("name"),
            "is_ooc_persona": character.get("is_ooc_persona", False),
        },
    )
