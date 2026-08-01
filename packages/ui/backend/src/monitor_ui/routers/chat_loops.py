"""
Chat turn runners — scene loop lifecycle, pre-play, world architect, and scene turns.

Extracted from chat.py to isolate turn execution from the HTTP/WebSocket router.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from typing import Any

from .chat_support import (
    as_uuid,
    is_end_conversation_command,
    is_end_scene_command,
    is_ooc_question,
    is_recap_command,
    is_start_conversation_command,
    now_iso,
    resolve_pending_consequence_choice,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional layer imports (graceful degradation)
# ---------------------------------------------------------------------------

try:
    from monitor_agents.llm_errors import LLMProviderUnavailable
    from monitor_agents.loops.scene_loop import SceneLoop
    from monitor_agents.loops.scene_orchestrator import SceneOrchestrator
    from monitor_agents.loops.scene_support import strip_entity_tags
    from monitor_agents.loops.story_loop import StoryLoop

    _AGENTS_AVAILABLE = True
except Exception:
    SceneLoop = None  # type: ignore[assignment,misc]
    SceneOrchestrator = None  # type: ignore[assignment,misc]
    StoryLoop = None  # type: ignore[assignment,misc]
    LLMProviderUnavailable = None  # type: ignore[assignment,misc]

    def strip_entity_tags(text: str) -> str:
        return text or ""

    _AGENTS_AVAILABLE = False

try:
    from monitor_agents.loops.world_building_loop import WorldBuildingLoop

    _WORLD_ARCHITECT_AVAILABLE = True
except Exception:
    _WORLD_ARCHITECT_AVAILABLE = False

try:
    from monitor_agents.loops.character_creation_loop import CharacterCreationLoop

    _CHAR_CREATION_AVAILABLE = True
except Exception:
    _CHAR_CREATION_AVAILABLE = False

try:
    from monitor_agents.loops.session_zero_loop import (
        SessionZeroLoop,
    )

    _SESSION_ZERO_AVAILABLE = True
except Exception:
    _SESSION_ZERO_AVAILABLE = False

try:
    from monitor_agents.loops.conversation_loop import (
        ConversationLoop,
        ConversationMode,
    )

    _CONVERSATION_AVAILABLE = True
except Exception:
    ConversationLoop = None  # type: ignore[assignment,misc]
    ConversationMode = None  # type: ignore[assignment,misc]
    _CONVERSATION_AVAILABLE = False

try:
    from monitor_agents.recap.agent import RecapAgent

    _RECAP_AVAILABLE = True
except Exception:
    RecapAgent = None  # type: ignore[assignment,misc]
    _RECAP_AVAILABLE = False

try:
    from monitor_data.tools.mongodb_tools import mongodb_get_gm_profile

    _BOOTSTRAP_AVAILABLE = True
except Exception:
    _BOOTSTRAP_AVAILABLE = False

try:
    _PROMPT_COLLECTIONS_AVAILABLE = True
except Exception:
    _PROMPT_COLLECTIONS_AVAILABLE = False

try:
    from .character_resolution import resolve_actor_character

    _CHARACTER_RESOLUTION_AVAILABLE = True
except Exception:
    _CHARACTER_RESOLUTION_AVAILABLE = False

try:
    from monitor_agents.utils.db_readers import mongodb_update_scene, run_sync_read
    from monitor_data.schemas.scenes import SceneUpdate

    _DB_READERS_AVAILABLE = True
except Exception:
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
    actor_id = as_uuid(session.get("speaker_character_id") or session.get("character_id"))
    agreements_lines, agreements_veils = _session_agreements(session)
    return (
        scene_id,
        story_id,
        session.get("play_mode", "narrative"),
        session.get("system_id"),
        session.get("pack_id"),
        session.get("system_source_type"),
        session.get("system_source_id"),
        str(actor_id) if actor_id else None,
        session.get("tone", "dramatic"),
        session.get("gm_profile_id"),
        session.get("roll_model", "tap"),
        tuple(agreements_lines),
        tuple(agreements_veils),
    )


def _build_story_state_dict(session: dict[str, Any], *, story_id: str) -> dict[str, Any] | None:
    """Merge the session's own ``story_premise`` with whatever arc data the
    last StoryLoop advancement cached (``_STORY_STATES``, Gap 4), so
    ``SceneLoop`` -- and through it, the Narrator -- can see story-level
    context on every turn.

    Previously ``SceneLoop`` never received a ``story_state`` at all on
    either the web backend or the CLI (confirmed by reading both
    construction sites directly -- see
    CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md Q3), so the
    ``arc_label``/``tension_score``/``active_threads`` injection
    ``Narrator._generate_narrative_and_proposals`` already had for this
    case was dead code for real play. This restores it, not just adds
    ``story_premise`` alongside it.
    """
    universe_id = session.get("universe_id") or session.get("world_id")
    if not story_id or not universe_id:
        return None
    story_state = dict(_STORY_STATES.get(story_id) or {})
    story_state.setdefault("story_id", story_id)
    story_state.setdefault("universe_id", universe_id)
    premise = session.get("story_premise")
    if premise:
        story_state["story_premise"] = premise
    return story_state


def _session_agreements(session: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return the Session-Zero ``lines`` and ``veils`` arrays for a session.

    Agreements live on ``session["story_agreements"]`` (set by
    ``finalize_preplay``). When the player skipped Session Zero, the field
    is present but may be empty, which is the same default as a fully
    unanswered interview.
    """
    raw = session.get("story_agreements")
    if not isinstance(raw, dict):
        return [], []
    lines = [str(item).strip() for item in (raw.get("lines") or []) if str(item).strip()]
    veils = [str(item).strip() for item in (raw.get("veils") or []) if str(item).strip()]
    return lines, veils


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

    agreements_lines, agreements_veils = _session_agreements(session)

    # Load GM profile if configured
    gm_profile_dict: dict[str, Any] | None = None
    gm_profile_id = session.get("gm_profile_id")
    if gm_profile_id and _BOOTSTRAP_AVAILABLE:
        try:
            profile = mongodb_get_gm_profile(uuid.UUID(gm_profile_id))
            if profile:
                gm_profile_dict = profile.model_dump()
        except Exception:
            logger.warning("Failed to load GM profile %s, falling back to tone", gm_profile_id)

    loop = SceneLoop(
        scene_id=uuid.UUID(scene_id),
        story_id=uuid.UUID(story_id),
        universe_id=as_uuid(session.get("universe_id") or session.get("world_id")),
        play_mode=session.get("play_mode", "narrative"),
        system_id=session.get("system_id"),
        pack_id=session.get("pack_id"),
        system_source_type=session.get("system_source_type"),
        system_source_id=session.get("system_source_id"),
        actor_id=as_uuid(session.get("speaker_character_id") or session.get("character_id")),
        actor_context=actor_context,
        session_tone=session.get("tone", "dramatic"),
        gm_profile=gm_profile_dict,
        # Roll model: "gm" auto-rolls server-side (no player prompt); "tap"/
        # "manual" pause for the player (propose_roll → dice prompt).
        roll_mode="auto" if session.get("roll_model") == "gm" else "normal",
        story_state=_build_story_state_dict(session, story_id=story_id),
        agreements_lines=agreements_lines,
        agreements_veils=agreements_veils,
        # Shared reference: OOC director notes appended after this loop is
        # cached must be visible on the next turn.
        director_notes=session.setdefault("director_notes", []),
    )
    _SCENE_LOOPS[session_id] = (signature, loop)
    _SCENE_LOOPS.move_to_end(session_id)
    while len(_SCENE_LOOPS) > _SCENE_LOOPS_MAX:
        _SCENE_LOOPS.popitem(last=False)
    return loop


def pop_scene_loop(session_id: str) -> None:
    try:
        _SCENE_LOOPS.pop(session_id, None)
    except NameError:
        pass


def pop_character_creation_loop(session_id: str) -> None:
    try:
        from monitor_agents.loops.preplay_orchestrator import _CHAR_CREATION_LOOPS

        _CHAR_CREATION_LOOPS.pop(session_id, None)
    except ImportError:
        pass


def pop_session_zero_loop(session_id: str) -> None:
    try:
        from monitor_agents.loops.preplay_orchestrator import (
            _CHARACTER_INTERVIEW_LOOPS,
            _STORY_AGREEMENT_LOOPS,
        )

        _CHARACTER_INTERVIEW_LOOPS.pop(session_id, None)
        _STORY_AGREEMENT_LOOPS.pop(session_id, None)
    except ImportError:
        pass


async def run_preplay_turn(
    session_id: str,
    user_content: str,
    *,
    sessions: dict[str, dict[str, Any]],
    messages: dict[str, list[Any]],
    db_save_session: Any,
    db_save_message: Any,
    session_game_system_doc: Any,
    gsr_available: bool,
) -> tuple[str, dict[str, Any]]:
    """
    Handle all player messages during the pre-play phase via LangGraph Orchestrator.
    """
    import logging

    logger = logging.getLogger(__name__)
    session = sessions.get(session_id, {})
    system_doc = session_game_system_doc(session) if callable(session_game_system_doc) else session_game_system_doc

    world_lore = []
    system_context = ""

    phase = session.get("phase", "character_interview")
    legacy_character_interview = (
        phase == "session_zero"
        and not session.get("character_id")
        and not session.get("story_agreements_started")
    )
    if phase in {"character_interview", "awaiting_character"} or legacy_character_interview:
        from .chat_opening import fetch_opening_hook

        try:
            lore_data = await fetch_opening_hook(session)
            world_lore = lore_data.get("axioms", []) + lore_data.get("facts", [])
        except Exception as exc:
            logger.debug("Failed to fetch opening hook for session zero: %s", exc)

        try:
            from monitor_agents.character_interview import ground_world_lore

            world_lore = ground_world_lore(world_lore, session.get("system_label") or "", system_context)
        except Exception as exc:
            logger.debug("Failed to ground world lore: %s", exc)

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
                prompts = [
                    logic.get("prompt_template") for logic in cc.get("logic", []) if logic.get("prompt_template")
                ]
                if prompts:
                    context_parts.append("Themes: " + " | ".join(prompts))
            system_context = "\n".join(context_parts)

    try:
        from monitor_agents.loops.preplay_orchestrator import PreplayOrchestrator, PreplayState
    except ImportError:
        return "Preplay orchestrator not available (agents layer required).", {}

    initial_state = PreplayState(
        session_id=session_id,
        user_content=user_content,
        session_data=session,
        system_doc=system_doc,
        gsr_available=gsr_available,
        world_lore=world_lore,
        system_context=system_context,
    )

    result = await PreplayOrchestrator.ainvoke(initial_state)

    new_session = result.get("session_data", session)
    sessions[session_id] = new_session
    db_save_session(new_session)

    return result.get("response_text", ""), result.get("metadata", {})


# ---------------------------------------------------------------------------
# World Architect turn runner
# ---------------------------------------------------------------------------


async def run_world_architect_turn(
    session_id: str,
    user_content: str,
    *,
    sessions: dict[str, dict[str, Any]],
    messages: dict[str, list[dict[str, Any]]],
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
    except Exception as exc:
        logger.warning("World Architect turn failed: %s", exc)
        return (
            "I encountered an issue processing your request. Could you rephrase or try again?",
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


async def run_scene_turn(
    session_id: str,
    user_content: str,
    *,
    sessions: dict[str, dict[str, Any]],
    messages: dict[str, list[dict[str, Any]]],
    db_save_session: Any,
    db_load_messages: Any,
    bootstrap_story_scene: Any,
    session_game_system_doc: Any,
    gsr_available: bool,
) -> tuple[str, dict[str, Any]]:
    """
    Run one turn through SceneOrchestrator for the given session.
    """
    session = sessions.get(session_id)
    if not session:
        return ("Session not found.", {})

    actor_context: dict[str, Any] | None = None
    if _CHARACTER_RESOLUTION_AVAILABLE:
        try:
            resolved = resolve_actor_character(session)
            if resolved:
                actor_context = resolved.model_dump(mode="json")
        except Exception as exc:
            logger.debug("Failed to resolve actor character: %s", exc)

    if not _AGENTS_AVAILABLE or SceneOrchestrator is None:
        return (
            "The narrative engine is standing by…\n\n"
            "*(Bind this session to a universe and opening scene to activate the live GM loop.)*",
            {
                "agents_available": False,
                "story_id": session.get("story_id"),
                "scene_id": session.get("scene_id"),
            },
        )

    from .stories import get_story_state

    class OrchestratorCallbacks:
        pass

    callbacks: Any = OrchestratorCallbacks()
    callbacks.db_save_session = db_save_session
    callbacks.now_iso = now_iso
    callbacks.is_ooc_question = is_ooc_question
    callbacks.is_end_conversation_command = is_end_conversation_command
    callbacks.is_end_scene_command = is_end_scene_command
    callbacks.is_recap_command = is_recap_command
    callbacks.is_start_conversation_command = is_start_conversation_command
    from monitor_agents.loops.preplay_support import answer_ooc_question

    callbacks.answer_ooc_question = answer_ooc_question
    callbacks.resolve_pending_consequence_choice = resolve_pending_consequence_choice
    callbacks.run_conversation_turn = run_conversation_turn
    callbacks.run_end_scene = run_end_scene
    callbacks.run_recap_command = run_recap_command
    callbacks.run_start_conversation = run_start_conversation
    callbacks.pop_conversation_loop = pop_conversation_loop
    callbacks.get_scene_loop = get_scene_loop
    callbacks.sessions = sessions
    callbacks.messages = messages
    callbacks.db_load_messages = db_load_messages
    callbacks.bootstrap_story_scene = bootstrap_story_scene
    callbacks.session_game_system_doc = session_game_system_doc
    callbacks.gsr_available = gsr_available
    callbacks.get_story_state = get_story_state

    def set_story_state_cache(story_id: str, state_data: dict[str, Any]) -> None:
        _STORY_STATES[story_id] = state_data

    callbacks.set_story_state_cache = set_story_state_cache

    orchestrator = SceneOrchestrator()
    state_dict = {
        "session_id": session_id,
        "user_content": user_content,
        "session": session,
        "actor_context": actor_context,
        "callbacks": callbacks,
        "story_id": session.get("story_id"),
        "scene_id": session.get("scene_id"),
        "agents_available": _AGENTS_AVAILABLE,
    }
    return await orchestrator.run(state_dict)


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
    sessions: dict[str, dict[str, Any]],
    messages: dict[str, list[dict[str, Any]]],
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
            narrative = "Scene ended. All pending changes have been evaluated and committed."

        # Mark scene as finalizing in MongoDB
        if _DB_READERS_AVAILABLE:
            await run_sync_read(
                mongodb_update_scene,
                uuid.UUID(scene_id),
                SceneUpdate(status="finalizing"),
            )

        # Transition phase to scene_ended before advancing the story.
        # Must match frontend PHASE_STYLE keys (PlayConsole.tsx,
        # lib/play-constants.ts) -- both key on "scene_ended", not
        # "scene_end"; the mismatch meant the intended cyan "Scene ended"
        # pill silently fell through to the generic default style.
        session["phase"] = "scene_ended"

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
    except Exception as exc:
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
            recap_text = "The story is just beginning. Every legend starts with a first step."
    except Exception as exc:
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
        from monitor_data.db.neo4j import get_neo4j_client

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
    except Exception as exc:
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
            scene_id=uuid.UUID(session["scene_id"]) if session.get("scene_id") else None,
            story_id=uuid.UUID(session["story_id"]) if session.get("story_id") else None,
            player_entity_id=uuid.UUID(player_id) if player_id else None,
        )
    except Exception as exc:
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
    opening = f"You approach **{npc_name}**. They turn to face you, waiting. What do you say?"

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
            "relationship_snapshot": responses[0].get("relationship_snapshot", {}) if responses else {},
        }
    except Exception as exc:
        logger.warning("ConversationLoop.step failed: %s", exc)
        session.pop("conversation_active", None)
        pop_conversation_loop(session_id)
        db_save_session(session)
        return (
            "The conversation breaks off unexpectedly.",
            {"type": "conversation_error", "error": str(exc)},
        )


async def _generate_scene_summary(session_id: str, messages: dict[str, list[dict[str, Any]]]) -> str:
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
            from monitor_agents.narrator.agent import Narrator

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
    sessions: dict[str, dict[str, Any]],
    messages: dict[str, list[dict[str, Any]]],
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
        from monitor_agents.narrator.agent import Narrator

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
        narrative = strip_entity_tags(result.get("narrative_text", ""))
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
